import os
import zipfile
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import json
import logging
import random
import gc
import psutil
import time
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('presentation_generator.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Функция для автоматической установки недостающих библиотек
def install_missing_packages():
    """Автоматически устанавливает недостающие пакеты"""
    required_packages = {
        'pydub': 'pydub>=0.25.1',
        'PIL': 'Pillow>=10.0.0', 
        'pptx': 'python-pptx>=0.6.23',
        'psutil': 'psutil>=5.9.0'
    }
    
    missing_packages = []
    
    for package, pip_name in required_packages.items():
        try:
            if package == 'PIL':
                import PIL
            else:
                __import__(package)
            logger.info(f"✅ {package} уже установлен")
        except ImportError:
            missing_packages.append(pip_name)
            logger.warning(f"⚠️ {package} не найден, будет установлен")
    
    if missing_packages:
        logger.info(f"📦 Устанавливаем недостающие пакеты: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            logger.info("✅ Все пакеты успешно установлены")
            import importlib
            importlib.invalidate_caches()
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Ошибка установки пакетов: {e}")
            raise

# Устанавливаем недостающие пакеты при импорте
install_missing_packages()

# Теперь импортируем основные библиотеки
from pydub import AudioSegment
from PIL import Image, ImageOps
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE

class ModernPresentationGenerator:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        
        if not self.base_path.exists():
            logger.info(f"📦 Файл {base_path} не найден, пробуем скачать из Dropbox...")
            try:
                try:
                    from backend.dropbox_storage import DropboxStorage
                except ImportError:
                    logger.warning("⚠️ DropboxStorage не найден, пропускаем скачивание")
                    raise FileNotFoundError(f"❌ Шаблон не найден: {self.base_path}")
                
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
        self.fade_duration = 3000
        self.fade_in_duration = 1000
        
        # Восстанавливаем кеши для красных слов
        self._red_words_per_slide = {}
        self._artist_red_words_cache = {}
        self._image_cache = {}
        self.image_cache_size = 3

    def _log_memory_usage(self):
        """Упрощенное логирование памяти"""
        try:
            process = psutil.Process()
            process_memory = process.memory_info().rss / 1024 / 1024
            if process_memory > 200:
                logger.info(f"💾 Память процесса: {process_memory:.1f}MB")
        except:
            pass

    def _force_garbage_collection(self):
        """Упрощенная сборка мусора"""
        gc.collect()

    def _get_image_orientation(self, image_path: str):
        """Определяет ориентацию изображения"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                return "horizontal" if width > height else "vertical"
        except Exception as e:
            logger.error(f"❌ Ошибка определения ориентации изображения {image_path}: {e}")
            return "vertical"

    def _load_and_process_image_optimized(self, image_path: str, make_bw: bool):
        """Загружает и обрабатывает изображение с сохранением RGBA"""
        cache_key = f"{image_path}_{make_bw}"
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]
        
        if len(self._image_cache) >= self.image_cache_size:
            removed_key = next(iter(self._image_cache))
            del self._image_cache[removed_key]
        
        path = Path(image_path)
        if not path.exists():
            return None
        
        try:
            with Image.open(path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                if make_bw:
                    if img.mode == 'RGBA':
                        r, g, b, a = img.split()
                        grayscale = ImageOps.grayscale(img.convert("RGB"))
                        img = Image.merge("RGBA", (grayscale, grayscale, grayscale, a))
                    else:
                        img = ImageOps.grayscale(img).convert("RGBA")
                
                self._image_cache[cache_key] = img
                return img
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки изображения {image_path}: {e}")
            return None

    def _apply_fade_effects(self, audio_segment):
        """Применяет нарастание и затухание трека"""
        try:
            fade_in_duration = min(self.fade_in_duration, len(audio_segment) // 3)
            if fade_in_duration > 0:
                audio_segment = audio_segment.fade_in(fade_in_duration)
            
            fade_out_duration = min(self.fade_duration, len(audio_segment) - 1000)
            if fade_out_duration > 0:
                audio_segment = audio_segment.fade_out(fade_out_duration)
            
            return audio_segment
        except Exception as e:
            logger.error(f"❌ Ошибка применения эффектов затухания: {e}")
            return audio_segment

    def _find_track_file_simple(self, track_path: str):
        possible_paths = [
            Path(track_path),
            Path.cwd() / "downloads" / Path(track_path).name,
            Path.cwd() / "uploads" / Path(track_path).name
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        return None

    def _load_tracks_from_json_simple(self):
        possible_paths = [
            Path.cwd() / "tracks.json",
            Path.cwd() / "Track_data.json", 
            Path.cwd() / "track_data.json",
            Path.cwd() / "data.json",
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    tracks = data.get("tracks", [])
                    if not tracks and isinstance(data, list):
                        tracks = data
                    
                    logger.info(f"🎵 Загружено {len(tracks)} треков")
                    return tracks
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки треков: {e}")
        
        return []

    def _process_audio_segment_parallel(self, task):
        """Обработка аудио для параллельного выполнения"""
        rels_path, track, slide_num, media_dir = task
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
            real_path = self._find_track_file_simple(track_path)
            if not real_path:
                return None

            audio = AudioSegment.from_file(real_path)
            
            seg_start = int(float(track.get("segment_start", 0)) * 1000)
            seg_dur = int(float(track.get("segment_duration", self.default_ms / 1000)) * 1000)
            end_ms = min(len(audio), seg_start + seg_dur + self.buffer_ms)
            
            if seg_start > 0 or end_ms < len(audio):
                clip = audio[seg_start:end_ms]
            else:
                clip = audio

            clip = self._apply_fade_effects(clip)

            out_media_path = media_dir / os.path.basename(targets[0])
            clip.export(out_media_path, format="mp3", bitrate="96k")
            
            return (slide_num, track)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки аудио для слайда {slide_num}: {e}")
            return None

    def _safe_get_font_attr(self, font_attr, attr_name):
        """Безопасное получение атрибутов шрифта"""
        try:
            if font_attr is None:
                return None
                
            if hasattr(font_attr, 'value'):
                return font_attr.value
            else:
                return font_attr
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения {attr_name}: {e}")
            return None

    def _convert_mso_to_bool(self, mso_value):
        """Конвертирует MSO TriState в bool"""
        try:
            if mso_value is None:
                return False
                
            if hasattr(mso_value, 'value'):
                return mso_value.value == True
                
            if isinstance(mso_value, bool):
                return mso_value
                
            return bool(mso_value)
            
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации MSO {mso_value}: {e}")
            return False

    def _apply_text_formatting_with_style(self, original_run, new_text, is_artist, slide_num, artist_name=None):
        """Применяет форматирование с сохранением стиля оригинала и умным окрашиванием с кешированием"""
        try:
            RED = RGBColor(255, 0, 0)
            BLACK = RGBColor(0, 0, 0)
        
            # Сохраняем стиль оригинального run
            font_name = original_run.font.name
            font_size = original_run.font.size

            # БЕЗОПАСНОЕ получение и конвертация булевых атрибутов
            raw_bold = self._safe_get_font_attr(original_run.font.bold, "font.bold")
            raw_italic = self._safe_get_font_attr(original_run.font.italic, "font.italic")
            
            font_bold = self._convert_mso_to_bool(raw_bold)
            font_italic = self._convert_mso_to_bool(raw_italic)
        
            special_chars = {'@', '#', '$', '&', '€', '£', '¥'}
            special_patterns = {'zz', 'xxx', 'www', 'qq', 'kk'}
        
            words = new_text.split()
        
            # Инициализируем счетчик для слайда если нужно
            if slide_num not in self._red_words_per_slide:
                self._red_words_per_slide[slide_num] = 0
        
            # Если это артист и у нас есть кеш для него, используем его
            cached_red_words = set()
            if is_artist and artist_name and artist_name in self._artist_red_words_cache:
                cached_red_words = self._artist_red_words_cache[artist_name]
        
            # Находим слова для покраски
            paintable_words = []
            for word in words:
                # Проверяем кеш для этого артиста
                if word.lower() in cached_red_words:
                    paintable_words.append((word, True))
                    continue
                
                has_special_char = any(char in word for char in special_chars)
                has_special_pattern = any(pattern in word.lower() for pattern in special_patterns)
                
                paintable_words.append((word, has_special_char or has_special_pattern))

            # Гарантируем минимум 1 красное слово на слайд, но не более 1
            if (not any(paintable for _, paintable in paintable_words) and 
                words and self._red_words_per_slide[slide_num] == 0):
                random_index = random.randint(0, len(words) - 1)
                paintable_words[random_index] = (words[random_index], True)
        
            # Сохраняем выбранные красные слова в кеш для артиста
            red_words_for_artist = set()
            for word, should_paint in paintable_words:
                if should_paint:
                    red_words_for_artist.add(word.lower())
        
            if is_artist and artist_name and red_words_for_artist:
                self._artist_red_words_cache[artist_name] = red_words_for_artist
        
            # Очищаем оригинальный run и создаем новые с сохранением стиля
            original_run.text = ""
            parent_paragraph = original_run._parent
        
            for word, should_paint in paintable_words:
                # Проверяем лимит красных слов на слайд
                can_paint_red = should_paint and self._red_words_per_slide[slide_num] < 1
            
                if can_paint_red:
                    self._red_words_per_slide[slide_num] += 1
                
                    # Обрабатываем слово посимвольно
                    for char in word:
                        new_run = parent_paragraph.add_run()
                        new_run.text = char
                        # Сохраняем стиль оригинала
                        if font_name:
                            new_run.font.name = font_name
                        if font_size:
                            new_run.font.size = font_size
                    
                        # БЕЗОПАСНОЕ установление булевых значений
                        new_run.font.bold = font_bold
                        new_run.font.italic = font_italic
                    
                        # Красим только специальные символы (или все если слово выбрано случайно)
                        if char in special_chars or (should_paint and not any(c in word for c in special_chars)):
                            new_run.font.color.rgb = RED
                        else:
                            new_run.font.color.rgb = BLACK
                
                    # Добавляем пробел
                    space_run = parent_paragraph.add_run()
                    space_run.text = " "
                    if font_name:
                        space_run.font.name = font_name
                    if font_size:
                        space_run.font.size = font_size
                    space_run.font.bold = font_bold
                    space_run.font.italic = font_italic
                    space_run.font.color.rgb = BLACK
                    
                else:
                    # Обычное слово без окрашивания
                    new_run = parent_paragraph.add_run()
                    new_run.text = word + " "
                    # Сохраняем стиль оригинала
                    if font_name:
                        new_run.font.name = font_name
                    if font_size:
                        new_run.font.size = font_size
                
                    # БЕЗОПАСНОЕ установление булевых значений
                    new_run.font.bold = font_bold
                    new_run.font.italic = font_italic
                    new_run.font.color.rgb = BLACK
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в _apply_text_formatting_with_style: {e}")
            original_run.text = new_text

    def _move_button_to_corner_simple(self, slide, slide_height, slide_width, mirror=False):
        """ПРОСТАЯ версия перемещения кнопки"""
        try:
            for shape in slide.shapes:
                if hasattr(shape, 'image'):
                    try:
                        # Простая проверка через анализ имени файла
                        image_blip = shape._element.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
                        if image_blip is not None:
                            rId = image_blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                            if rId and rId in slide.part.rels:
                                rel = slide.part.rels[rId]
                                image_part = rel.target_part
                                if hasattr(image_part, 'partname'):
                                    filename = image_part.partname.split('/')[-1]
                                    
                                    if filename.lower() == 'image42.png':
                                        if mirror:
                                            # Левый нижний угол с отзеркаливанием
                                            new_left = Inches(0.2)
                                            new_top = slide_height - shape.height - Inches(0.2)
                                            shape.left = new_left
                                            shape.top = new_top
                                            original_width = shape.width
                                            shape.width = -original_width
                                            shape.left = new_left + original_width
                                        else:
                                            # Правый нижний угол
                                            shape.left = slide_width - shape.width - Inches(0.2)
                                            shape.top = slide_height - shape.height - Inches(0.2)
                                        return True
                    except:
                        continue
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка перемещения кнопки: {e}")
            return False

    def _insert_artist_photo_simple(self, slide, processed_img, slide_height, slide_width, template_type):
        """Вставка фото"""
        if processed_img is None:
            return
            
        temp_img_path = None
        try:
            temp_img_path = Path(tempfile.gettempdir()) / f"temp_photo_{random.randint(1000,9999)}.png"
            processed_img.save(temp_img_path, "PNG", optimize=True)
            
            if not temp_img_path.exists():
                return

            img_width_px, img_height_px = processed_img.size
            dpi = 96
            width_inches = img_width_px / dpi
            height_inches = img_height_px / dpi
            
            # Масштабирование
            scale_factors = {1: 1.2, 2: 1.15, 3: 1.1}
            scale_factor = scale_factors.get(template_type, 1.0)
            width_inches *= scale_factor
            height_inches *= scale_factor
            
            # Позиционирование
            if template_type == 1:
                left = Inches(0)
                top = slide_height - Inches(height_inches)
            elif template_type == 2:
                left = slide_width - Inches(width_inches)
                top = slide_height - Inches(height_inches)
            elif template_type == 3:
                left = Inches(0)
                top = slide_height - Inches(height_inches)
            else:
                return

            width = Inches(width_inches)
            height = Inches(height_inches)
            
            # Проверка границ
            left = max(Inches(0), min(left, slide_width - width))
            top = max(Inches(0), min(top, slide_height - height))
            
            slide.shapes.add_picture(str(temp_img_path), left, top, width=width, height=height)

        except Exception as e:
            logger.error(f"❌ Ошибка вставки фото: {e}")
        finally:
            if temp_img_path and temp_img_path.exists():
                try:
                    temp_img_path.unlink()
                except:
                    pass

    def _determine_template_type(self, image_path):
        """Определяет тип шаблона"""
        if not image_path:
            return 1
            
        orientation = self._get_image_orientation(image_path)
        if orientation == "vertical":
            return random.choice([1, 2])
        else:
            return 3

    def _process_slide_content_simple(self, slide, track, slide_num, make_bw, slide_height, slide_width):
        """Обработка содержимого одного слайда"""
        artist = track.get("artist", "Неизвестный исполнитель")
        title = track.get("title", "Без названия")
        image_path = track.get("image_path", "")

        # Определяем шаблон
        template_type = self._determine_template_type(image_path)
        
        # Загружаем и вставляем фото
        if image_path:
            processed_img = self._load_and_process_image_optimized(image_path, make_bw)
            if processed_img:
                self._insert_artist_photo_simple(
                    slide, processed_img, slide_height, slide_width, template_type
                )
                # Сразу освобождаем память
                del processed_img

        # Обрабатываем текст
        artist_shapes = []
        title_shapes = []
        
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
                
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    if "{{ARTIST}}" in run.text:
                        artist_shapes.append((shape, run))
                    elif "{{TRACK}}" in run.text:
                        title_shapes.append((shape, run))

        # Обрабатываем артиста с красными словами
        if artist_shapes:
            artist_shape, artist_run = artist_shapes[0]
            self._position_text_shape_simple(artist_shape, template_type, slide_width, slide_height, True)
            self._apply_text_formatting_with_style(artist_run, artist, True, slide_num, artist)

        # Обрабатываем трек
        if title_shapes:
            title_shape, title_run = title_shapes[0]
            self._position_text_shape_simple(title_shape, template_type, slide_width, slide_height, False)
            self._apply_text_formatting_with_style(title_run, title, False, slide_num, artist)

        # Обрабатываем кнопку
        if template_type == 2:
            self._move_button_to_corner_simple(slide, slide_height, slide_width, mirror=True)
        else:
            self._move_button_to_corner_simple(slide, slide_height, slide_width, mirror=False)

    def _position_text_shape_simple(self, shape, template_type, slide_width, slide_height, is_artist):
        """Позиционирует текстовую фигуру"""
        shape.text_frame.word_wrap = False
        
        try:
            shape.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
        except:
            pass
        
        for paragraph in shape.text_frame.paragraphs:
            paragraph.alignment = PP_ALIGN.LEFT
        
        if template_type == 1:
            if is_artist:
                shape.left = Inches(9.0)
                shape.top = Inches(0.8)
            else:
                shape.left = Inches(9.0)
                shape.top = Inches(2.0)
        elif template_type == 2:
            if is_artist:
                shape.left = Inches(0.5)
                shape.top = Inches(1.0)
            else:
                shape.left = Inches(0.5)
                shape.top = Inches(2.2)
        elif template_type == 3:
            if is_artist:
                shape.left = Inches(8.0)
                shape.top = Inches(1.0)
            else:
                shape.left = Inches(8.0)
                shape.top = Inches(2.2)

    def _process_audio_parallel(self, audio_tasks):
        """Параллельная обработка аудио"""
        results = []
        
        # Обрабатываем задачи параллельно
        with ThreadPoolExecutor(max_workers=2) as executor:  # Уменьшили до 2 потоков
            future_to_task = {executor.submit(self._process_audio_segment_parallel, task): task for task in audio_tasks}
            
            for future in future_to_task:
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"❌ Ошибка в аудио задаче: {e}")
        
        return results

    def _process_slides_incremental(self, final_pptx, slide_track_map, make_bw):
        """Обрабатывает слайды по одному чтобы не держать всю презентацию в памяти"""
        try:
            # Открываем презентацию
            prs = Presentation(final_pptx)
            slide_height = prs.slide_height
            slide_width = prs.slide_width
            
            # Обрабатываем каждый слайд и сразу сохраняем
            for i, slide in enumerate(prs.slides):
                slide_num = int(''.join(ch for ch in slide.part.partname if ch.isdigit()) or 0)
                
                if slide_num in slide_track_map:
                    track = slide_track_map[slide_num]
                    self._process_slide_content_simple(slide, track, slide_num, make_bw, slide_height, slide_width)
                    
                    # Каждые 5 слайдов сохраняем и чистим память
                    if i % 5 == 0:
                        prs.save(final_pptx)
                        self._force_garbage_collection()
                        logger.info(f"💾 Сохранение прогресса после слайда {i}")
            
            # Финальное сохранение
            prs.save(final_pptx)
            del prs
            self._force_garbage_collection()
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке слайдов: {e}")
            raise

    def generate(self, game_title: str, tracks: list = None, make_bw: bool = False, use_parallel: bool = True):
        """Генерация презентации с оптимизацией памяти"""
        logger.info("🚀 Запуск оптимизированной генерации презентации")
        
        # Очищаем кеши перед генерацией
        self._red_words_per_slide.clear()
        self._artist_red_words_cache.clear()
        self._image_cache.clear()
        
        if not tracks:
            tracks = self._load_tracks_from_json_simple()
        
        if not tracks:
            try:
                from backend.server import media_library
                library_tracks = media_library.get_tracks()
                if library_tracks:
                    tracks = library_tracks
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить треки из медиатеки: {e}")

        if not tracks:
            raise ValueError("❌ Нет треков для генерации")

        logger.info(f"🎵 Используется треков: {len(tracks)}")

        tmp = Path(tempfile.mkdtemp(prefix="pptx_opt_"))
        extract_dir = tmp / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Распаковка шаблона
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
                with open(slide1, 'r', encoding='utf-8') as f:
                    content = f.read()
                if "{{TITLE}}" in content:
                    with open(slide1, 'w', encoding='utf-8') as f:
                        f.write(content.replace("{{TITLE}}", game_title))

            # Обработка слайдов
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
                        track_index += 1
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

            # Параллельная обработка аудио
            logger.info("🔊 Обработка аудио...")
            if use_parallel and len(audio_tasks) > 1:
                results = self._process_audio_parallel(audio_tasks)
            else:
                # Последовательная обработка для маленьких наборов
                results = []
                for task in audio_tasks:
                    result = self._process_audio_segment_parallel(task)
                    if result:
                        results.append(result)
                    self._force_garbage_collection()
            
            for slide_num, processed_track in results:
                slide_track_map[slide_num] = processed_track

            # Создание финального файла
            final_pptx = out_root / f"presentation_{timestamp}.pptx"
            
            with zipfile.ZipFile(final_pptx, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        fp = Path(root) / file
                        arcname = os.path.relpath(fp, extract_dir)
                        zip_out.write(fp, arcname)

            self._force_garbage_collection()

            # Инкрементальная обработка слайдов
            logger.info("🎨 Обработка слайдов с красными словами...")
            self._process_slides_incremental(final_pptx, slide_track_map, make_bw)

            logger.info(f"✅ Презентация готова: {final_pptx}")
            logger.info("🎨 Красные слова успешно добавлены!")
            return str(out_root)

        except Exception as e:
            logger.error(f"❌ Ошибка при генерации презентации: {e}")
            raise
        finally:
            # Очищаем кеши
            self._red_words_per_slide.clear()
            self._artist_red_words_cache.clear()
            self._image_cache.clear()
            self._force_garbage_collection()
            
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except:
                pass

if __name__ == "__main__":
    try:
        logger.info("🎬 Запуск оптимизированного генератора презентаций")
        generator = ModernPresentationGenerator("template.pptx")
        result_path = generator.generate(
            game_title="Моя оптимизированная викторина",
            tracks=None,
            make_bw=False,
            use_parallel=True
        )
        print(f"🎉 Презентация создана в: {result_path}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")