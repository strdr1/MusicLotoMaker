import os
import zipfile
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from pydub import AudioSegment
import json
import logging
import random
from PIL import Image, ImageOps
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor
import concurrent.futures
from functools import lru_cache

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ModernPresentationGenerator:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        
        # Проверяем существование файла и пытаемся скачать если нет
        if not self.base_path.exists():
            logger.info(f"📦 Файл {base_path} не найден, пробуем скачать из Dropbox...")
            try:
                from backend.dropbox_storage import DropboxStorage
                dropbox_storage = DropboxStorage()
                if dropbox_storage.download_base_pptx(str(self.base_path)):
                    logger.info(f"✅ Файл успешно скачан: {self.base_path}")
                else:
                    raise FileNotFoundError(f"❌ Шаблон не найден и не удалось скачать: {self.base_path}")
            except Exception as e:
                logger.error(f"❌ Ошибка при скачивании шаблона: {e}")
                raise FileNotFoundError(f"❌ Шаблон не найден: {self.base_path}")

        self.skip_slides = {1, 2, 3, 4, 45, 46, 47, 88, 89, 90, 131}
        self.buffer_ms = 5000
        self.default_ms = 35_000
        self.photo_scale_factor = 1.3

    # === КЭШИРОВАНИЕ ===
    @lru_cache(maxsize=32)
    def _load_and_process_image(self, image_path: str, make_bw: bool):
        """Кэширует обработку изображений"""
        path = Path(image_path)
        if not path.exists():
            return None
            
        with Image.open(path) as img:
            img = img.convert("RGBA")

            if make_bw:
                grayscale = ImageOps.grayscale(img.convert("RGB"))
                alpha = img.split()[3]
                img = Image.merge("RGBA", (grayscale, grayscale, grayscale, alpha))

            # Увеличиваем на 30%
            max_dim = Inches(14)
            dpi = 96
            target_px = int(max_dim.inches * dpi)
            
            new_width = int(img.width * self.photo_scale_factor)
            new_height = int(img.height * self.photo_scale_factor)
            
            img_resized = img.resize((new_width, new_height), Image.LANCZOS)
            
            if new_width > target_px or new_height > target_px:
                img_resized.thumbnail((target_px, target_px), Image.LANCZOS)

            return img_resized

    @lru_cache(maxsize=128)
    def _find_track_file(self, track_path: str):
        """Кэширует поиск файлов треков"""
        possible_paths = [
            Path(track_path),
            Path.cwd() / "downloads" / Path(track_path).name,
            Path.cwd() / "uploads" / Path(track_path).name
        ]
        return next((p for p in possible_paths if p.exists()), None)

    def _load_tracks_from_json(self):
        """Загружает треки из различных возможных файлов"""
        # Пробуем разные возможные имена файлов
        possible_paths = [
            Path.cwd() / "tracks.json",
            Path.cwd() / "Track_data.json", 
            Path.cwd() / "track_data.json",
            Path.cwd() / "data.json",
            Path.cwd() / "track_data" / "tracks.json",  # если в папке
            Path.cwd() / "data" / "tracks.json"
        ]
        
        json_path = None
        for path in possible_paths:
            if path.exists():
                json_path = path
                logger.info(f"📁 Найден файл с треками: {path}")
                break
        
        if not json_path:
            logger.warning("⚠️ Файл с треками не найден — проверьте наличие tracks.json или Track_data.json")
            return []
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Проверяем разные возможные структуры JSON
            tracks = data.get("tracks", [])
            if not tracks and isinstance(data, list):
                tracks = data
                
            logger.info(f"🎵 Загружено {len(tracks)} треков из {json_path.name}")
            
            # Логируем первые несколько треков для отладки
            if tracks:
                for i, track in enumerate(tracks[:3]):
                    logger.debug(f"   {i+1}. {track.get('artist', 'Unknown')} - {track.get('title', 'Unknown')}")
                if len(tracks) > 3:
                    logger.debug(f"   ... и еще {len(tracks) - 3} треков")
                    
            return tracks
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {json_path.name}: {e}")
            return []

    def _get_rels_list_sorted(self, slides_rels_dir: Path):
        rels = list(slides_rels_dir.glob("slide*.xml.rels"))
        return sorted(rels, key=lambda p: int(''.join(ch for ch in p.stem if ch.isdigit()) or 0))

    # === ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА АУДИО ===
    def _process_audio_segment(self, args):
        """Обрабатывает один аудио-сегмент (для многопоточности)"""
        rels_path, track, slide_num, media_dir = args
        
        try:
            tree = ET.parse(rels_path)
            root = tree.getroot()
            targets = [
                rel.attrib.get("Target", "")
                for rel in root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
                if rel.attrib.get("Target", "").lower().endswith(".mp3")
            ]
            if not targets:
                return None

            track_path = track.get("file_path") or track.get("path", "")
            real_path = self._find_track_file(track_path)
            if not real_path:
                logger.warning(f"⚠️ Файл трека не найден: {track_path}")
                return None

            # Быстрая загрузка только метаданных для проверки длины
            audio = AudioSegment.from_file(real_path)
            seg_start = int(float(track.get("segment_start", 0)) * 1000)
            seg_dur = int(float(track.get("segment_duration", self.default_ms / 1000)) * 1000)
            end_ms = min(len(audio), seg_start + seg_dur + self.buffer_ms)
            
            # Вырезаем только если нужно
            if seg_start > 0 or end_ms < len(audio):
                clip = audio[seg_start:end_ms]
            else:
                clip = audio  # Используем оригинал если не нужно вырезать

            out_media_path = media_dir / os.path.basename(targets[0])
            clip.export(out_media_path, format="mp3", bitrate="128k")  # Уменьшаем битрейт для скорости

            return (slide_num, track)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки аудио для слайда {slide_num}: {e}")
            return None

    # === ОПТИМИЗИРОВАННАЯ ВСТАВКА ТЕКСТА И ФОТО ===
    def _replace_placeholders_and_photos(self, prs, slide_track_map, make_bw: bool):
        """Оптимизированная версия вставки текста и фото"""
        # Предварительная обработка всех изображений
        processed_images = {}
        for slide_num, track in slide_track_map.items():
            image_path = track.get("image_path", "")
            if image_path:
                processed_img = self._load_and_process_image(image_path, make_bw)
                if processed_img:
                    processed_images[slide_num] = processed_img

        # Получаем высоту слайда один раз
        slide_height = prs.slide_height

        for slide in prs.slides:
            slide_num = int(''.join(ch for ch in slide.part.partname if ch.isdigit()) or 0)
            
            if slide_num not in slide_track_map:
                continue

            track = slide_track_map[slide_num]
            artist = track.get("artist", "Неизвестный исполнитель")
            title = track.get("title", "Без названия")

            # === БЫСТРАЯ ЗАМЕНА ТЕКСТА ===
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                    
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        if "{{ARTIST}}" in run.text:
                            self._replace_placeholder(paragraph, run, artist)
                        elif "{{TRACK}}" in run.text:
                            self._replace_placeholder(paragraph, run, title)

            # === БЫСТРАЯ ВСТАВКА ФОТО ===
            if slide_num in processed_images:
                self._insert_processed_image(slide, processed_images[slide_num], slide_num, slide_height)

        logger.info("✅ Замена текста и добавление фото завершены")

    def _replace_placeholder(self, paragraph, run, text):
        """Быстрая замена плейсхолдера"""
        font_name = run.font.name
        font_size = run.font.size
        font_bold = run.font.bold
        font_italic = run.font.italic
        
        paragraph.clear()
        for word in text.split():
            new_run = paragraph.add_run()
            new_run.text = word + " "
            if font_name:
                new_run.font.name = font_name
            if font_size:
                new_run.font.size = font_size
            new_run.font.bold = font_bold
            new_run.font.italic = font_italic
            new_run.font.color.rgb = (
                RGBColor(255, 0, 0) if random.random() < 0.5 else RGBColor(0, 0, 0)
            )

    def _insert_processed_image(self, slide, processed_img, slide_num, slide_height):
        """Быстрая вставка предобработанного изображения"""
        try:
            temp_img_path = Path(tempfile.gettempdir()) / f"temp_photo_{slide_num}.png"
            processed_img.save(temp_img_path, "PNG", optimize=True)

            dpi = 96
            width = Inches(processed_img.width / dpi)
            height = Inches(processed_img.height / dpi)
            left = Inches(0)
            top = slide_height - height  # Используем переданную высоту слайда

            slide.shapes.add_picture(str(temp_img_path), left, top, width=width, height=height)
            temp_img_path.unlink(missing_ok=True)

            logger.info(f"🖼️ Фото добавлено на слайд {slide_num} ({width.inches:.1f}×{height.inches:.1f} дюйма)")

        except Exception as e:
            logger.error(f"❌ Ошибка вставки фото для слайда {slide_num}: {e}")

    # === ИСПРАВЛЕННАЯ ОПТИМИЗИРОВАННАЯ ГЕНЕРАЦИЯ ===
    def generate(self, game_title: str, tracks: list = None, make_bw: bool = False, use_parallel: bool = True):
        # Сначала пробуем переданные треки
        if not tracks:
            tracks = self._load_tracks_from_json()
        
        # Если из JSON не загрузилось, пробуем из медиатеки
        if not tracks:
            try:
                from backend.server import media_library
                library_tracks = media_library.get_tracks()
                if library_tracks:
                    tracks = library_tracks
                    logger.info(f"🎵 Загружено {len(tracks)} треков из медиатеки")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить треки из медиатеки: {e}")

        if not tracks:
            raise ValueError("❌ Нет треков — генерация невозможна. Загрузите треки в медиатеку или создайте tracks.json/Track_data.json")

        logger.info(f"🎵 Используется треков: {len(tracks)}")

        tmp = Path(tempfile.mkdtemp(prefix="pptx_work_"))
        extract_dir = tmp / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Быстрое извлечение
            with zipfile.ZipFile(self.base_path, "r") as z:
                z.extractall(extract_dir)

            slides_dir = extract_dir / "ppt" / "slides"
            slides_rels_dir = slides_dir / "_rels"
            media_dir = extract_dir / "ppt" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_root = Path.cwd() / "output" / f"presentation_{timestamp}"
            out_root.mkdir(parents=True, exist_ok=True)

            # Быстрая замена заголовка
            slide1 = slides_dir / "slide1.xml"
            if slide1.exists():
                content = slide1.read_text(encoding="utf-8")
                if "{{TITLE}}" in content:
                    slide1.write_text(content.replace("{{TITLE}}", game_title), encoding="utf-8")
                    logger.info(f"📝 Заголовок заменен на: {game_title}")

            # === ИСПРАВЛЕННАЯ ОБРАБОТКА АУДИО ===
            rels_list = self._get_rels_list_sorted(slides_rels_dir)
            slide_track_map = {}
            track_index = 0  # Отдельный индекс для треков
            track_for_13_and_44 = None

            # Подготавливаем задачи для параллельной обработки
            audio_tasks = []
            for rels_path in rels_list:
                slide_num = int(''.join(ch for ch in rels_path.stem if ch.isdigit()) or 0)
                
                # Пропускаем слайды из черного списка
                if slide_num in self.skip_slides:
                    continue
                
                # Обработка специальных слайдов 13 и 44
                if slide_num == 13:
                    # Для слайда 13 резервируем текущий трек, но не увеличиваем индекс
                    if track_index < len(tracks):
                        track_for_13_and_44 = tracks[track_index]
                        # НЕ увеличиваем track_index здесь!
                        track = track_for_13_and_44
                        audio_tasks.append((rels_path, track, slide_num, media_dir))
                        slide_track_map[slide_num] = track
                        logger.info(f"🎵 Слайд 13: зарезервирован трек '{track.get('title', 'Без названия')}'")
                    continue
                elif slide_num == 44:
                    # Слайд 44 использует тот же трек, что и слайд 13
                    if track_for_13_and_44:
                        track = track_for_13_and_44
                        audio_tasks.append((rels_path, track, slide_num, media_dir))
                        slide_track_map[slide_num] = track
                        logger.info(f"🎵 Слайд 44: использован трек '{track.get('title', 'Без названия')}'")
                    continue
                else:
                    # Обычные слайды
                    if track_index >= len(tracks):
                        logger.warning(f"⚠️ Закончились треки на слайде {slide_num}")
                        break
                    
                    track = tracks[track_index]
                    track_index += 1  # Увеличиваем индекс только для обычных слайдов
                    
                    audio_tasks.append((rels_path, track, slide_num, media_dir))
                    slide_track_map[slide_num] = track
                    logger.debug(f"🎵 Слайд {slide_num}: назначен трек '{track.get('title', 'Без названия')}' (индекс: {track_index-1})")

            # Параллельная обработка аудио
            if use_parallel and len(audio_tasks) > 1:
                logger.info("🔄 Параллельная обработка аудио...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    results = list(executor.map(self._process_audio_segment, audio_tasks))
                    # Обновляем карту треков результатами обработки
                    for result in results:
                        if result:
                            slide_num, processed_track = result
                            slide_track_map[slide_num] = processed_track
            else:
                # Последовательная обработка если не используем параллельность
                logger.info("🔄 Последовательная обработка аудио...")
                for task in audio_tasks:
                    result = self._process_audio_segment(task)
                    if result:
                        slide_num, processed_track = result
                        slide_track_map[slide_num] = processed_track

            # Логируем распределение треков для отладки
            logger.info(f"📊 Распределено треков по слайдам: {len(slide_track_map)}")
            logger.info(f"📊 Использовано треков из доступных: {track_index} из {len(tracks)}")

            # Быстрая сборка PPTX
            final_pptx = out_root / f"presentation_{timestamp}.pptx"
            with zipfile.ZipFile(final_pptx, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        fp = Path(root) / file
                        arcname = os.path.relpath(fp, extract_dir)
                        zip_out.write(fp, arcname)

            # Финальная обработка текста и фото
            prs = Presentation(final_pptx)
            self._replace_placeholders_and_photos(prs, slide_track_map, make_bw)
            prs.save(final_pptx)

            logger.info(f"✅ Презентация готова: {final_pptx}")
            logger.info(f"📁 Папка с результатами: {out_root}")
            return str(out_root)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка при генерации презентации: {e}")
            raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            logger.info("🧹 Временные файлы очищены")


# Пример использования
if __name__ == "__main__":
    try:
        generator = ModernPresentationGenerator("template.pptx")
        result_path = generator.generate(
            game_title="Моя музыкальная викторина",
            tracks=None,  # Автоматически загрузит из tracks.json или Track_data.json
            make_bw=False,
            use_parallel=True
        )
        print(f"🎉 Презентация создана в: {result_path}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")