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
import gc
import psutil
import time

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class ModernPresentationGenerator:
    def __init__(self, base_path: str):
        # Добавлен конструктор с параметром base_path
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
        
        # Ограничения для экономии памяти
        self.max_workers = 2
        self.image_cache_size = 8
        self._image_cache = {}

    def _check_memory_usage(self):
        """Проверяем использование памяти"""
        try:
            memory = psutil.virtual_memory()
            if memory.percent > 85:
                logger.warning(f"⚠️ Использование памяти высокое: {memory.percent}%")
                return False
            return True
        except:
            return True  # Если не можем проверить, продолжаем работу

    def _force_garbage_collection(self):
        """Принудительная очистка памяти"""
        gc.collect()
        time.sleep(0.1)

    def _load_and_process_image_optimized(self, image_path: str, make_bw: bool):
        """Оптимизированная загрузка изображений с контролем памяти"""
        if not self._check_memory_usage():
            self._force_garbage_collection()
            
        cache_key = f"{image_path}_{make_bw}"
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]
            
        # Ограничиваем размер кэша
        if len(self._image_cache) >= self.image_cache_size:
            self._image_cache.pop(next(iter(self._image_cache)))
            
        path = Path(image_path)
        if not path.exists():
            return None
            
        try:
            # Загружаем с уменьшением качества для экономии памяти
            with Image.open(path) as img:
                # Сразу уменьшаем размер если изображение слишком большое
                max_pixels = 1024 * 1024  # 1MP
                if img.width * img.height > max_pixels:
                    ratio = (max_pixels / (img.width * img.height)) ** 0.5
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                
                img = img.convert("RGBA")

                if make_bw:
                    grayscale = ImageOps.grayscale(img.convert("RGB"))
                    alpha = img.split()[3] if len(img.split()) > 3 else None
                    if alpha:
                        img = Image.merge("RGBA", (grayscale, grayscale, grayscale, alpha))
                    else:
                        img = grayscale.convert("RGBA")

                # Увеличиваем на 30% но с ограничением
                max_dim = Inches(14)
                dpi = 96
                target_px = int(max_dim.inches * dpi)
                
                new_width = int(img.width * self.photo_scale_factor)
                new_height = int(img.height * self.photo_scale_factor)
                
                img_resized = img.resize((new_width, new_height), Image.LANCZOS)
                
                if new_width > target_px or new_height > target_px:
                    img_resized.thumbnail((target_px, target_px), Image.LANCZOS)

                self._image_cache[cache_key] = img_resized
                return img_resized
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки изображения {image_path}: {e}")
            return None

    def _find_track_file_optimized(self, track_path: str):
        """Оптимизированный поиск файлов треков"""
        possible_paths = [
            Path(track_path),
            Path.cwd() / "downloads" / Path(track_path).name,
            Path.cwd() / "uploads" / Path(track_path).name
        ]
        return next((p for p in possible_paths if p.exists()), None)

    def _load_tracks_from_json_optimized(self):
        """Загружает треки с минимальным использованием памяти"""
        possible_paths = [
            Path.cwd() / "tracks.json",
            Path.cwd() / "Track_data.json", 
            Path.cwd() / "track_data.json",
            Path.cwd() / "data.json",
        ]
        
        json_path = None
        for path in possible_paths:
            if path.exists():
                json_path = path
                logger.info(f"📁 Найден файл с треками: {path}")
                break
        
        if not json_path:
            logger.warning("⚠️ Файл с треками не найден")
            return []
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            tracks = data.get("tracks", [])
            if not tracks and isinstance(data, list):
                tracks = data
                
            logger.info(f"🎵 Загружено {len(tracks)} треков")
            return tracks
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки треков: {e}")
            return []

    def _process_audio_segment_optimized(self, rels_path, track, slide_num, media_dir):
        """Оптимизированная обработка аудио с контролем памяти"""
        if not self._check_memory_usage():
            self._force_garbage_collection()
            
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
            real_path = self._find_track_file_optimized(track_path)
            if not real_path:
                logger.warning(f"⚠️ Файл трека не найден: {track_path}")
                return None

            # Загружаем аудио с минимальным использованием памяти
            audio = AudioSegment.from_file(real_path)
            seg_start = int(float(track.get("segment_start", 0)) * 1000)
            seg_dur = int(float(track.get("segment_duration", self.default_ms / 1000)) * 1000)
            end_ms = min(len(audio), seg_start + seg_dur + self.buffer_ms)
            
            # Вырезаем сегмент
            if seg_start > 0 or end_ms < len(audio):
                clip = audio[seg_start:end_ms]
            else:
                clip = audio

            out_media_path = media_dir / os.path.basename(targets[0])
            
            # Используем более низкое качество для экономии памяти
            clip.export(out_media_path, format="mp3", bitrate="96k")
            
            # Очищаем память
            del audio, clip
            self._force_garbage_collection()

            return (slide_num, track)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки аудио для слайда {slide_num}: {e}")
            return None

    def _replace_placeholders_and_photos_optimized(self, prs, slide_track_map, make_bw: bool):
        """Оптимизированная вставка текста и фото с поэтапной обработкой"""
        slide_height = prs.slide_height
        
        # Обрабатываем по одному слайду за раз
        for i, slide in enumerate(prs.slides):
            if i % 5 == 0:  # Проверяем память каждые 5 слайдов
                if not self._check_memory_usage():
                    self._force_garbage_collection()
            
            slide_num = int(''.join(ch for ch in slide.part.partname if ch.isdigit()) or 0)
            
            if slide_num not in slide_track_map:
                continue

            track = slide_track_map[slide_num]
            artist = track.get("artist", "Неизвестный исполнитель")
            title = track.get("title", "Без названия")

            # Замена текста
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                    
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        if "{{ARTIST}}" in run.text:
                            self._replace_placeholder_optimized(paragraph, run, artist)
                        elif "{{TRACK}}" in run.text:
                            self._replace_placeholder_optimized(paragraph, run, title)

            # Обработка и вставка фото (только если нужно для этого слайда)
            image_path = track.get("image_path", "")
            if image_path:
                processed_img = self._load_and_process_image_optimized(image_path, make_bw)
                if processed_img:
                    self._insert_processed_image_optimized(slide, processed_img, slide_num, slide_height)
                    # Очищаем ссылку на изображение
                    del processed_img

        logger.info("✅ Замена текста и добавление фото завершены")

    def _replace_placeholder_optimized(self, paragraph, run, text):
        """Оптимизированная замена плейсхолдера"""
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

    def _insert_processed_image_optimized(self, slide, processed_img, slide_num, slide_height):
        """Оптимизированная вставка изображения"""
        try:
            temp_img_path = Path(tempfile.gettempdir()) / f"temp_photo_{slide_num}_{os.getpid()}.png"
            processed_img.save(temp_img_path, "PNG", optimize=True)

            dpi = 96
            width = Inches(processed_img.width / dpi)
            height = Inches(processed_img.height / dpi)
            left = Inches(0)
            top = slide_height - height

            slide.shapes.add_picture(str(temp_img_path), left, top, width=width, height=height)
            
            # Сразу удаляем временный файл
            try:
                temp_img_path.unlink(missing_ok=True)
            except:
                pass

            logger.debug(f"🖼️ Фото добавлено на слайд {slide_num}")

        except Exception as e:
            logger.error(f"❌ Ошибка вставки фото для слайда {slide_num}: {e}")

    def _process_audio_sequential(self, audio_tasks):
        """Последовательная обработка аудио для экономии памяти"""
        results = []
        for i, task in enumerate(audio_tasks):
            if i % 3 == 0:  # Проверяем память каждые 3 задачи
                if not self._check_memory_usage():
                    self._force_garbage_collection()
                    time.sleep(0.5)  # Даем системе время освободить память
                    
            result = self._process_audio_segment_optimized(*task)
            if result:
                results.append(result)
                
        return results

    def generate(self, game_title: str, tracks: list = None, make_bw: bool = False, use_parallel: bool = False):
        """Оптимизированная генерация презентации для сервера с 512MB RAM"""
        
        logger.info("🚀 Запуск оптимизированной генерации презентации")
        
        # Принудительная очистка памяти перед началом
        self._force_garbage_collection()
        
        # Загружаем треки
        if not tracks:
            tracks = self._load_tracks_from_json_optimized()
        
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
            raise ValueError("❌ Нет треков для генерации")

        logger.info(f"🎵 Используется треков: {len(tracks)}")

        # Создаем временную директорию
        tmp = Path(tempfile.mkdtemp(prefix="pptx_opt_"))
        extract_dir = tmp / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Извлекаем шаблон
            with zipfile.ZipFile(self.base_path, "r") as z:
                z.extractall(extract_dir)

            slides_dir = extract_dir / "ppt" / "slides"
            slides_rels_dir = slides_dir / "_rels"
            media_dir = extract_dir / "ppt" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_root = Path.cwd() / "output" / f"presentation_{timestamp}"
            out_root.mkdir(parents=True, exist_ok=True)

            # Замена заголовка
            slide1 = slides_dir / "slide1.xml"
            if slide1.exists():
                content = slide1.read_text(encoding="utf-8")
                if "{{TITLE}}" in content:
                    slide1.write_text(content.replace("{{TITLE}}", game_title), encoding="utf-8")
                    logger.info(f"📝 Заголовок заменен на: {game_title}")

            # Подготавливаем задачи для обработки аудио
            rels_files = sorted(
                [f for f in slides_rels_dir.glob("slide*.xml.rels")],
                key=lambda x: int(''.join(filter(str.isdigit, x.stem)) or 0)
            )
            
            slide_track_map = {}
            audio_tasks = []
            track_index = 0
            track_for_13_and_44 = None

            for rels_path in rels_files:
                slide_num = int(''.join(filter(str.isdigit, rels_path.stem)) or 0)
                
                if slide_num in self.skip_slides:
                    continue
                
                if slide_num == 13:
                    if track_index < len(tracks):
                        track_for_13_and_44 = tracks[track_index]
                        track = track_for_13_and_44
                        audio_tasks.append((rels_path, track, slide_num, media_dir))
                        slide_track_map[slide_num] = track
                    continue
                elif slide_num == 44:
                    if track_for_13_and_44:
                        track = track_for_13_and_44
                        audio_tasks.append((rels_path, track, slide_num, media_dir))
                        slide_track_map[slide_num] = track
                    continue
                else:
                    if track_index >= len(tracks):
                        break
                    
                    track = tracks[track_index]
                    track_index += 1
                    
                    audio_tasks.append((rels_path, track, slide_num, media_dir))
                    slide_track_map[slide_num] = track

            # Обработка аудио - используем последовательную обработку для экономии памяти
            logger.info("🔄 Обработка аудио (последовательно для экономии памяти)...")
            results = self._process_audio_sequential(audio_tasks)
            
            # Обновляем карту треков
            for slide_num, processed_track in results:
                slide_track_map[slide_num] = processed_track

            logger.info(f"📊 Распределено треков по слайдам: {len(slide_track_map)}")

            # Создаем финальный PPTX
            final_pptx = out_root / f"presentation_{timestamp}.pptx"
            
            # Очищаем память перед сборкой
            self._force_garbage_collection()
            
            with zipfile.ZipFile(final_pptx, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        fp = Path(root) / file
                        arcname = os.path.relpath(fp, extract_dir)
                        zip_out.write(fp, arcname)

            # Очищаем кэш изображений перед финальной обработкой
            self._image_cache.clear()
            self._force_garbage_collection()

            # Финальная обработка текста и фото
            logger.info("🎨 Замена текста и добавление фото...")
            prs = Presentation(final_pptx)
            self._replace_placeholders_and_photos_optimized(prs, slide_track_map, make_bw)
            prs.save(final_pptx)

            # Финальная очистка памяти
            del prs
            self._force_garbage_collection()

            logger.info(f"✅ Презентация готова: {final_pptx}")
            logger.info(f"📁 Папка с результатами: {out_root}")
            return str(out_root)

        except Exception as e:
            logger.error(f"❌ Ошибка при генерации презентации: {e}")
            raise
        finally:
            # Тщательная очистка
            self._image_cache.clear()
            self._force_garbage_collection()
            
            try:
                shutil.rmtree(tmp, ignore_errors=True)
                logger.info("🧹 Временные файлы очищены")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось полностью очистить временные файлы: {e}")


# Пример использования
if __name__ == "__main__":
    try:
        generator = ModernPresentationGenerator("template.pptx")
        result_path = generator.generate(
            game_title="Моя оптимизированная викторина",
            tracks=None,
            make_bw=False,
            use_parallel=False
        )
        print(f"🎉 Презентация создана в: {result_path}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")