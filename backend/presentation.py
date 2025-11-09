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

# Настройка расширенного логирования
logging.basicConfig(
    level=logging.DEBUG,
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
            # Устанавливаем все недостающие пакеты одной командой
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            logger.info("✅ Все пакеты успешно установлены")
            
            # Перезагружаем текущий модуль чтобы импорты заработали
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
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.oxml.xmlchemy import OxmlElement

class ModernPresentationGenerator:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        
        if not self.base_path.exists():
            logger.info(f"📦 Файл {base_path} не найден, пробуем скачать из Dropbox...")
            try:
                # Пытаемся импортировать dropbox, если нет - установим при необходимости
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
        self.fade_duration = 3000  # 3 секунды затухания
        self.fade_in_duration = 1000  # 1 секунда нарастания
        
        self.max_workers = 2
        self.image_cache_size = 8
        self._image_cache = {}
        self._red_words_per_slide = {}
        self._artist_red_words_cache = {}  # Кеш красных слов для каждого артиста

    def _log_memory_usage(self):
        """Логирует использование памяти"""
        try:
            memory = psutil.virtual_memory()
            process = psutil.Process()
            process_memory = process.memory_info().rss / 1024 / 1024
            logger.debug(f"💾 Память: системная {memory.percent}%, процесс {process_memory:.1f}MB")
        except Exception as e:
            logger.debug(f"⚠️ Не удалось получить информацию о памяти: {e}")

    def _check_memory_usage(self):
        try:
            memory = psutil.virtual_memory()
            if memory.percent > 85:
                logger.warning(f"⚠️ Использование памяти высокое: {memory.percent}%")
                return False
            return True
        except:
            return True

    def _force_garbage_collection(self):
        logger.debug("🧹 Принудительная сборка мусора")
        gc.collect()
        time.sleep(0.1)

    def _safe_set_auto_size(self, text_frame, enabled):
        """Безопасная установка auto_size с правильным enum значением"""
        try:
            if enabled:
                text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
            else:
                text_frame.auto_size = None
            logger.debug(f"✅ Auto_size установлен: {enabled}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить auto_size: {e}")
            # Пробуем альтернативный способ
            try:
                if hasattr(text_frame, '_bodyPr'):
                    if enabled:
                        text_frame._bodyPr.set('autofit', 'spAutoFit')
                    else:
                        text_frame._bodyPr.set('autofit', None)
                    logger.debug(f"✅ Auto_size установлен через альтернативный метод: {enabled}")
            except Exception as alt_e:
                logger.error(f"❌ Ошибка альтернативной установки auto_size: {alt_e}")

    def _get_image_orientation(self, image_path: str):
        """Определяет ориентацию изображения"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                orientation = "horizontal" if width > height else "vertical"
                logger.debug(f"📐 Ориентация изображения {image_path}: {orientation} ({width}x{height})")
                return orientation
        except Exception as e:
            logger.error(f"❌ Ошибка определения ориентации изображения {image_path}: {e}")
            return "vertical"  # По умолчанию вертикальное

    def _load_and_process_image_optimized(self, image_path: str, make_bw: bool):
        """Загружает и обрабатывает изображение с улучшенной обработкой ошибок"""
        if not self._check_memory_usage():
            self._force_garbage_collection()
        
        cache_key = f"{image_path}_{make_bw}"
        if cache_key in self._image_cache:
            logger.debug(f"🎨 Используем кешированное изображение: {cache_key}")
            return self._image_cache[cache_key]
        
        if len(self._image_cache) >= self.image_cache_size:
            removed_key = next(iter(self._image_cache))
            del self._image_cache[removed_key]
            logger.debug(f"🗑️ Удален из кеша: {removed_key}")
        
        path = Path(image_path)
        if not path.exists():
            logger.error(f"❌ Файл изображения не найден: {image_path}")
            return None
        
        try:
            logger.debug(f"🖼️ Загрузка изображения: {image_path}, BW: {make_bw}")
        
            # Проверяем доступность файла
            if not path.is_file():
                logger.error(f"❌ {image_path} не является файлом")
                return None
            
            # Проверяем размер файла
            file_size = path.stat().st_size
            if file_size == 0:
                logger.error(f"❌ Файл {image_path} пустой")
                return None
            
            with Image.open(path) as img:
                # Проверяем, что изображение загружено корректно
                if img is None:
                    logger.error(f"❌ Не удалось загрузить изображение: {image_path}")
                    return None
                
                # Сохраняем оригинальные размеры
                original_width, original_height = img.size
                logger.debug(f"📏 Размеры оригинала: {original_width}x{original_height}, режим: {img.mode}")
            
                # Конвертируем в RGBA если нужно
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                    logger.debug("🔄 Конвертировано в RGBA")

                if make_bw:
                    logger.debug("⚫ Конвертация в черно-белое")
                    grayscale = ImageOps.grayscale(img.convert("RGB"))
                    alpha = img.split()[3] if len(img.split()) > 3 else None
                    if alpha:
                        img = Image.merge("RGBA", (grayscale, grayscale, grayscale, alpha))
                    else:
                        img = grayscale.convert("RGBA")
                    logger.debug("✅ Конвертация в ЧБ завершена")

                # Возвращаем изображение без изменения размеров
                self._image_cache[cache_key] = img
                logger.debug(f"✅ Изображение успешно обработано и закешировано")
                return img
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки изображения {image_path}: {e}")
            import traceback
            logger.error(f"🔍 Детали ошибки изображения:\n{traceback.format_exc()}")
            return None

    def _apply_fade_effects(self, audio_segment):
        """Применяет нарастание в начале и затухание в конце трека"""
        try:
            logger.debug(f"🎵 Применение эффектов затухания: длина трека {len(audio_segment)}ms")
            
            # Нарастание в начале (1 секунда)
            fade_in_duration = min(self.fade_in_duration, len(audio_segment) // 3)
            if fade_in_duration > 0:
                audio_segment = audio_segment.fade_in(fade_in_duration)
                logger.debug(f"🔊 Нарастание: {fade_in_duration}ms")
            
            # Затухание в конце (3 секунды)
            fade_out_duration = min(self.fade_duration, len(audio_segment) - 1000)
            if fade_out_duration > 0:
                audio_segment = audio_segment.fade_out(fade_out_duration)
                logger.debug(f"🔇 Затухание: {fade_out_duration}ms")
            
            return audio_segment
        except Exception as e:
            logger.error(f"❌ Ошибка применения эффектов затухания: {e}")
            return audio_segment

    def _find_track_file_optimized(self, track_path: str):
        possible_paths = [
            Path(track_path),
            Path.cwd() / "downloads" / Path(track_path).name,
            Path.cwd() / "uploads" / Path(track_path).name
        ]
        
        for path in possible_paths:
            if path.exists():
                logger.debug(f"🔍 Найден файл трека: {path}")
                return path
                
        logger.warning(f"⚠️ Файл трека не найден: {track_path}")
        return None

    def _load_tracks_from_json_optimized(self):
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
        if not self._check_memory_usage():
            self._force_garbage_collection()
            
        try:
            logger.debug(f"🎵 Обработка аудио для слайда {slide_num}")
            
            tree = ET.parse(rels_path)
            root = tree.getroot()
            targets = [
                rel.attrib.get("Target", "")
                for rel in root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
                if rel.attrib.get("Target", "").lower().endswith(".mp3")
            ]
            if not targets:
                logger.warning(f"⚠️ Не найдены MP3 цели в rels файле: {rels_path}")
                return None

            track_path = track.get("file_path") or track.get("path", "")
            real_path = self._find_track_file_optimized(track_path)
            if not real_path:
                logger.warning(f"⚠️ Файл трека не найден: {track_path}")
                return None

            logger.debug(f"🔊 Загрузка аудио файла: {real_path}")
            audio = AudioSegment.from_file(real_path)
            logger.debug(f"📊 Длина оригинального трека: {len(audio)}ms")
            
            seg_start = int(float(track.get("segment_start", 0)) * 1000)
            seg_dur = int(float(track.get("segment_duration", self.default_ms / 1000)) * 1000)
            end_ms = min(len(audio), seg_start + seg_dur + self.buffer_ms)
            
            logger.debug(f"✂️ Сегмент: {seg_start}ms - {end_ms}ms (длительность: {seg_dur}ms)")
            
            if seg_start > 0 or end_ms < len(audio):
                clip = audio[seg_start:end_ms]
                logger.debug(f"✂️ Вырезан сегмент: {len(clip)}ms")
            else:
                clip = audio
                logger.debug("🎵 Используется полный трек")

            # Применяем нарастание и затухание
            clip = self._apply_fade_effects(clip)

            out_media_path = media_dir / os.path.basename(targets[0])
            
            logger.debug(f"💾 Экспорт в: {out_media_path}")
            clip.export(out_media_path, format="mp3", bitrate="96k")
            
            del audio, clip
            self._force_garbage_collection()

            logger.info(f"✅ Аудио обработано для слайда {slide_num}")
            return (slide_num, track)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки аудио для слайда {slide_num}: {e}")
            return None

    def _safe_get_font_attr(self, font_attr, attr_name):
        """Безопасное получение атрибутов шрифта с логированием"""
        try:
            if font_attr is None:
                logger.debug(f"📝 {attr_name}: None")
                return None
                
            if hasattr(font_attr, 'value'):
                value = font_attr.value
                logger.debug(f"📝 {attr_name}.value: {value} (тип: {type(value)})")
                return value
            else:
                value = font_attr
                logger.debug(f"📝 {attr_name}: {value} (тип: {type(value)})")
                return value
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения {attr_name}: {e}")
            return None

    def _convert_mso_to_bool(self, mso_value):
        """Конвертирует MSO TriState в bool с расширенным логированием"""
        try:
            logger.debug(f"🔄 Конвертация MSO: {mso_value} (тип: {type(mso_value)})")
            
            if mso_value is None:
                logger.debug("🔘 MSO: None -> False")
                return False
                
            # Если это enum с атрибутом value
            if hasattr(mso_value, 'value'):
                result = mso_value.value == True
                logger.debug(f"🔘 MSO.value: {mso_value.value} -> {result}")
                return result
                
            # Если это уже bool
            if isinstance(mso_value, bool):
                logger.debug(f"🔘 MSO уже bool: {mso_value}")
                return mso_value
                
            # Пробуем конвертировать в bool
            result = bool(mso_value)
            logger.debug(f"🔘 MSO конвертирован в bool: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации MSO {mso_value}: {e}")
            return False

    def _apply_text_formatting_with_style(self, original_run, new_text, is_artist, slide_num, artist_name=None):
        """Применяет форматирование с сохранением стиля оригинала и умным окрашиванием с кешированием"""
        try:
            logger.info(f"🔧 Начало форматирования текста: '{new_text}' (артист: {is_artist}, слайд: {slide_num})")
        
            RED = RGBColor(255, 0, 0)
            BLACK = RGBColor(0, 0, 0)
        
            # Сохраняем стиль оригинального run с расширенным логированием
            font_name = original_run.font.name
            font_size = original_run.font.size

            # БЕЗОПАСНОЕ получение и конвертация булевых атрибутов
            logger.debug("🔍 Анализ атрибутов шрифта:")
            
            raw_bold = self._safe_get_font_attr(original_run.font.bold, "font.bold")
            raw_italic = self._safe_get_font_attr(original_run.font.italic, "font.italic")
            
            font_bold = self._convert_mso_to_bool(raw_bold)
            font_italic = self._convert_mso_to_bool(raw_italic)
            
            logger.info(f"📝 Параметры шрифта: name={font_name}, size={font_size}, bold={font_bold}, italic={font_italic}")
        
            special_chars = {'@', '#', '$', '&', '€', '£', '¥'}
            special_patterns = {'zz', 'xxx', 'www', 'qq', 'kk'}
        
            words = new_text.split()
            logger.debug(f"📝 Слова для обработки: {words}")
        
            # Инициализируем счетчик для слайда если нужно
            if slide_num not in self._red_words_per_slide:
                self._red_words_per_slide[slide_num] = 0
                logger.debug(f"🔢 Инициализирован счетчик красных слов для слайда {slide_num}")
        
            # Если это артист и у нас есть кеш для него, используем его
            cached_red_words = set()
            if is_artist and artist_name and artist_name in self._artist_red_words_cache:
                cached_red_words = self._artist_red_words_cache[artist_name]
                logger.info(f"🎨 Используем кеш красных слов для артиста '{artist_name}': {cached_red_words}")
        
            # Находим слова для покраски
            paintable_words = []
            for word in words:
                # Проверяем кеш для этого артиста
                if word.lower() in cached_red_words:
                    paintable_words.append((word, True))
                    logger.debug(f"🎨 Слово из кеша: '{word}'")
                    continue
                
                has_special_char = any(char in word for char in special_chars)
                has_special_pattern = any(pattern in word.lower() for pattern in special_patterns)
                
                paintable_words.append((word, has_special_char or has_special_pattern))
                
                if has_special_char or has_special_pattern:
                    logger.debug(f"🔍 Слово с особыми символами/паттернами: '{word}'")

            # Гарантируем минимум 1 красное слово на слайд, но не более 1
            if (not any(paintable for _, paintable in paintable_words) and 
                words and self._red_words_per_slide[slide_num] == 0):
                random_index = random.randint(0, len(words) - 1)
                paintable_words[random_index] = (words[random_index], True)
                logger.debug(f"🎲 Случайно выбрано слово для покраски: '{words[random_index]}'")
        
            # Сохраняем выбранные красные слова в кеш для артиста
            red_words_for_artist = set()
            for word, should_paint in paintable_words:
                if should_paint:
                    red_words_for_artist.add(word.lower())
        
            if is_artist and artist_name and red_words_for_artist:
                self._artist_red_words_cache[artist_name] = red_words_for_artist
                logger.info(f"💾 Сохранили в кеш для артиста '{artist_name}': {red_words_for_artist}")
        
            # Очищаем оригинальный run и создаем новые с сохранением стиля
            original_run.text = ""
            parent_paragraph = original_run._parent
        
            for word, should_paint in paintable_words:
                # Проверяем лимит красных слов на слайд
                can_paint_red = should_paint and self._red_words_per_slide[slide_num] < 1
            
                if can_paint_red:
                    self._red_words_per_slide[slide_num] += 1
                    logger.info(f"🎨 Красим слово '{word}' в красный на слайде {slide_num}")
                
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
                            logger.debug(f"🔴 Красный символ: '{char}'")
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
        
            logger.info(f"✅ Форматирование завершено для текста: '{new_text}'")
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в _apply_text_formatting_with_style: {e}")
            import traceback
            logger.error(f"🔍 Трассировка ошибки:\n{traceback.format_exc()}")
            
            # Расширенное логирование состояния объекта
            try:
                logger.error(f"📌 Состояние original_run.font.bold: {original_run.font.bold} (тип: {type(original_run.font.bold)})")
                logger.error(f"📌 Состояние original_run.font.italic: {original_run.font.italic} (тип: {type(original_run.font.italic)})")
                logger.error(f"📌 Состояние original_run.font.name: {original_run.font.name} (тип: {type(original_run.font.name)})")
                logger.error(f"📌 Состояние original_run.font.size: {original_run.font.size} (тип: {type(original_run.font.size)})")
            except Exception as debug_e:
                logger.error(f"💥 Не удалось получить отладочную информацию: {debug_e}")
        
            # Аварийное восстановление - просто устанавливаем текст
            try:
                original_run.text = new_text
                logger.info("🆘 Установлен простой текст в качестве запасного варианта")
            except:
                logger.error("💥 Не удалось установить даже простой текст")
            raise

    def _move_button_to_corner(self, slide, slide_height, slide_width, mirror=False):
        """Перемещает кнопку image42.png в угол и при необходимости отзеркаливает через отрицательное масштабирование"""
        try:
            logger.info(f"🔍 ПОИСК КНОПКИ IMAGE42.PNG НА СЛАЙДЕ (зеркало: {mirror})")
        
            for i, shape in enumerate(slide.shapes):
                if hasattr(shape, 'image'):
                    try:
                        if hasattr(shape, '_element'):
                            ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                            blip_elements = shape._element.findall('.//a:blip', ns)
                        
                            if blip_elements:
                                blip = blip_elements[0]
                                rId = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                            
                                if rId and rId in slide.part.rels:
                                    rel = slide.part.rels[rId]
                                    image_part = rel.target_part
                                    if hasattr(image_part, 'partname'):
                                        filename = image_part.partname.split('/')[-1]
                                        logger.debug(f"Фигура {i}: rId={rId}, filename={filename}")
                                    
                                        if filename.lower() == 'image42.png':
                                            old_left, old_top = shape.left, shape.top
                                            old_width, old_height = shape.width, shape.height
                                        
                                            if mirror:
                                                # Левый нижний угол с отзеркаливанием через отрицательное масштабирование
                                                new_left = Inches(0.2)
                                                new_top = slide_height - shape.height - Inches(0.2)
                                            
                                                # Перемещаем кнопку
                                                shape.left = new_left
                                                shape.top = new_top
                                            
                                                # Зеркалим через отрицательную ширину
                                                # Сохраняем оригинальные размеры
                                                original_width = shape.width
                                                original_height = shape.height
                                            
                                                # Устанавливаем отрицательную ширину для зеркального отображения
                                                shape.width = -original_width
                                            
                                                # Корректируем позицию, т.к. при отрицательной ширине координаты меняются
                                                shape.left = new_left + original_width
                                            
                                                logger.info(f"✅ Кнопка отзеркалена через отрицательное масштабирование!")
                                                logger.info(f"📏 Было: {old_width}x{old_height}, стало: {shape.width}x{shape.height}")
                                                logger.info(f"📍 Было: {old_left},{old_top}, стало: {shape.left},{shape.top}")
                                            
                                            else:
                                                # Правый нижний угол без изменений
                                                shape.left = slide_width - shape.width - Inches(0.2)
                                                shape.top = slide_height - shape.height - Inches(0.2)
                                                logger.info(f"✅ Кнопка перемещена в правый нижний угол!")
                                        
                                            return True
                    except Exception as e:
                        logger.debug(f"Ошибка при анализе фигуры {i}: {e}")
                        continue
        
            logger.info("❌ Кнопка image42.png не найдена")
            return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске кнопки: {e}")
            return False

    def _insert_artist_photo(self, slide, processed_img, slide_height, slide_width, template_type):
        """Вставляет фото артиста согласно выбранному шаблону"""
        try:
            # Проверяем, что processed_img не None
            if processed_img is None:
                logger.error("❌ processed_img is None, невозможно вставить фото")
                return
            
            temp_img_path = Path(tempfile.gettempdir()) / f"temp_photo_{random.randint(1000,9999)}.png"
        
            # Сохраняем изображение во временный файл
            processed_img.save(temp_img_path, "PNG", optimize=True)
        
            # Проверяем, что файл создался и доступен для чтения
            if not temp_img_path.exists():
                logger.error(f"❌ Временный файл не создан: {temp_img_path}")
                return
            
            try:
                # Проверяем, что файл можно открыть
                with open(temp_img_path, 'rb') as f:
                    f.read(100)  # Читаем первые 100 байт для проверки
            except Exception as e:
                logger.error(f"❌ Временный файл поврежден: {e}")
                return

            img_width_px, img_height_px = processed_img.size
            dpi = 96
        
            # Конвертируем пиксели в дюймы
            width_inches = img_width_px / dpi
            height_inches = img_height_px / dpi
        
            logger.debug(f"📐 Размеры фото в дюймах: {width_inches:.2f}x{height_inches:.2f}")
        
            # Увеличиваем фото для ВСЕХ шаблонов
            if template_type == 1:
                # Шаблон 1: Вертикальное фото слева - УВЕЛИЧИВАЕМ ЕЩЕ БОЛЬШЕ
                scale_factor = 1.2  # Увеличиваем на 60%
                width_inches *= scale_factor
                height_inches *= scale_factor
            
                # Шаблон 1: Вертикальное фото слева снизу (БОЛЬШОЕ)
                left = Inches(0)
                top = slide_height - Inches(height_inches)
                width = Inches(width_inches)
                height = Inches(height_inches)
            
            elif template_type == 2:
                # Шаблон 2: Вертикальное фото справа - ТОЖЕ УВЕЛИЧИВАЕМ
                scale_factor = 1.15  # Увеличиваем на 50%
                width_inches *= scale_factor
                height_inches *= scale_factor
            
                left = slide_width - Inches(width_inches)
                top = slide_height - Inches(height_inches)
                width = Inches(width_inches)
                height = Inches(height_inches)
            
            elif template_type == 3:
                # Шаблон 3: Горизонтальное фото - ТОЖЕ УВЕЛИЧИВАЕМ
                scale_factor = 1.1  # Увеличиваем на 40%
                width_inches *= scale_factor
                height_inches *= scale_factor
            
                left = Inches(0)
                top = slide_height - Inches(height_inches)
                width = Inches(width_inches)
                height = Inches(height_inches)

            # Проверяем, чтобы фото не выходило за границы слайда
            if left < Inches(0):
                left = Inches(0)
            if top < Inches(0):
                top = Inches(0)
            if left + width > slide_width:
                width = slide_width - left
            if top + height > slide_height:
                height = slide_height - top

            logger.debug(f"📍 Позиция фото: left={left}, top={top}, width={width}, height={height}")
        
            # Вставляем фото в слайд
            slide.shapes.add_picture(str(temp_img_path), left, top, width=width, height=height)
        
            # Очищаем временный файл
            try:
                temp_img_path.unlink(missing_ok=True)
            except Exception as e:
                logger.debug(f"⚠️ Не удалось удалить временный файл: {e}")

            logger.info(f"🖼️ Фото добавлено по шаблону {template_type} (увеличено)")

        except Exception as e:
            logger.error(f"❌ Ошибка вставки фото: {e}")
            import traceback
            logger.error(f"🔍 Детали ошибки:\n{traceback.format_exc()}")

    def _replace_placeholders_and_photos_optimized(self, prs, slide_track_map, make_bw: bool):
        slide_height = prs.slide_height
        slide_width = prs.slide_width
        
        logger.info(f"📐 Размеры слайда: {slide_width} x {slide_height}")
        
        # Сбрасываем счетчик красных слов перед обработкой слайдов
        self._red_words_per_slide.clear()
        logger.info("🧹 Счетчик красных слов сброшен")
        
        for i, slide in enumerate(prs.slides):
            if i % 5 == 0:
                if not self._check_memory_usage():
                    self._force_garbage_collection()
            
            slide_num = int(''.join(ch for ch in slide.part.partname if ch.isdigit()) or 0)
            
            if slide_num not in slide_track_map:
                logger.debug(f"⏭️ Пропуск слайда {slide_num} - нет трека")
                continue

            track = slide_track_map[slide_num]
            artist = track.get("artist", "Неизвестный исполнитель")
            title = track.get("title", "Без названия")

            logger.info(f"🎨 Обработка слайда {slide_num}: {artist} - {title}")

            # Определяем ориентацию фото и выбираем шаблон
            image_path = track.get("image_path", "")
            template_type = 1  # По умолчанию первый шаблон
            
            if image_path:
                orientation = self._get_image_orientation(image_path)
                if orientation == "vertical":
                    # Случайный выбор между шаблонами 1 и 2 для вертикальных фото
                    template_type = random.choice([1, 2])
                else:
                    # Горизонтальные фото - шаблон 3
                    template_type = 3
                
                logger.info(f"📐 Ориентация фото: {orientation}, выбран шаблон {template_type}")
                
                # Загружаем и обрабатываем фото
                processed_img = self._load_and_process_image_optimized(image_path, make_bw)
                if processed_img:
                    self._insert_artist_photo(slide, processed_img, slide_height, slide_width, template_type)
                    del processed_img
                else:
                    logger.warning(f"⚠️ Не удалось обработать фото: {image_path}")
            else:
                logger.warning(f"⚠️ Нет пути к фото для слайда {slide_num}")

            # Ищем существующие текстовые блоки с плейсхолдерами и заменяем их
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

            logger.debug(f"🔍 Найдено artist shapes: {len(artist_shapes)}, title shapes: {len(title_shapes)}")

            # Обрабатываем артиста
            if artist_shapes:
                artist_shape, artist_run = artist_shapes[0]
                
                # Позиционируем согласно шаблону
                if template_type == 1:
                    # Шаблон 1: Вертикальное фото слева - текст ПРАВЕЕ и ВЫШЕ
                    artist_shape.left = Inches(9.0)  # Еще правее
                    artist_shape.top = Inches(0.8)   # Выше
                elif template_type == 2:
                    # Шаблон 2: Вертикальное фото справа - текст слева сверху
                    artist_shape.left = Inches(0.5)
                    artist_shape.top = Inches(1.0)
                elif template_type == 3:
                    # Шаблон 3: Горизонтальное фото - текст справа сверху
                    artist_shape.left = Inches(8.0)
                    artist_shape.top = Inches(1.0)
                
                artist_shape.text_frame.word_wrap = False
                # ИСПРАВЛЕНИЕ: Используем безопасную установку auto_size
                self._safe_set_auto_size(artist_shape.text_frame, True)
                
                for paragraph in artist_shape.text_frame.paragraphs:
                    paragraph.alignment = PP_ALIGN.LEFT
                
                try:
                    self._apply_text_formatting_with_style(artist_run, artist, True, slide_num, artist)
                except Exception as e:
                    logger.error(f"❌ Ошибка форматирования артиста '{artist}': {e}")
                    # Запасной вариант
                    artist_run.text = artist
                
                # Обрабатываем трек
                if title_shapes:
                    title_shape, title_run = title_shapes[0]
                    
                    # Позиционируем согласно шаблону
                    if template_type == 1:
                        # Шаблон 1: Вертикальное фото слева - текст ПРАВЕЕ и ВЫШЕ
                        title_shape.left = Inches(9.0)  # Еще правее
                        title_shape.top = Inches(2.0)   # Выше и ближе к артисту
                    elif template_type == 2:
                        # Шаблон 2: Вертикальное фото справа - текст слева сверху
                        title_shape.left = Inches(0.5)
                        title_shape.top = Inches(2.2)
                    elif template_type == 3:
                        # Шаблон 3: Горизонтальное фото - текст справа сверху
                        title_shape.left = Inches(8.0)
                        title_shape.top = Inches(2.2)
                    
                    title_shape.text_frame.word_wrap = False
                    # ИСПРАВЛЕНИЕ: Используем безопасную установку auto_size
                    self._safe_set_auto_size(title_shape.text_frame, True)
                    
                    for paragraph in title_shape.text_frame.paragraphs:
                        paragraph.alignment = PP_ALIGN.LEFT
                    
                    try:
                        self._apply_text_formatting_with_style(title_run, title, False, slide_num, artist)
                    except Exception as e:
                        logger.error(f"❌ Ошибка форматирования трека '{title}': {e}")
                        # Запасной вариант
                        title_run.text = title
                    
                    # Удаляем остальные фигуры чтобы избежать колизий
                    for shape, run in artist_shapes[1:] + title_shapes[1:]:
                        try:
                            slide.shapes._spTree.remove(shape._element)
                            logger.debug("🗑️ Удалена дублирующая текстовая фигура")
                        except Exception as e:
                            logger.debug(f"⚠️ Не удалось удалить фигуру: {e}")

            # Обрабатываем кнопку согласно шаблону
            if template_type == 2:
                # Шаблон 2: перемещаем в левый угол и зеркалим
                self._move_button_to_corner(slide, slide_height, slide_width, mirror=True)
            else:
                # Шаблоны 1 и 3: оставляем кнопку на месте
                self._move_button_to_corner(slide, slide_height, slide_width, mirror=False)

        logger.info("✅ Замена текста и добавление фото завершены")

    def _process_audio_sequential(self, audio_tasks):
        results = []
        logger.info(f"🎵 Начало последовательной обработки {len(audio_tasks)} аудио задач")
        
        for i, task in enumerate(audio_tasks):
            logger.debug(f"🔊 Обработка аудио задачи {i+1}/{len(audio_tasks)}")
            
            if i % 3 == 0:
                if not self._check_memory_usage():
                    self._force_garbage_collection()
                    time.sleep(0.5)
                    
            result = self._process_audio_segment_optimized(*task)
            if result:
                results.append(result)
                
        logger.info(f"✅ Обработано {len(results)} аудио сегментов")
        return results

    def generate(self, game_title: str, tracks: list = None, make_bw: bool = False, use_parallel: bool = False):
        logger.info("🚀 Запуск оптимизированной генерации презентации")
        self._log_memory_usage()
        
        # Очищаем кеши перед новой генерацией
        self._force_garbage_collection()
        self._image_cache.clear()
        self._red_words_per_slide.clear()
        self._artist_red_words_cache.clear()  # Очищаем кеш красных слов
        
        logger.info("🧹 Кеши очищены перед генерацией")
        
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

        tmp = Path(tempfile.mkdtemp(prefix="pptx_opt_"))
        extract_dir = tmp / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"📦 Распаковка шаблона в: {extract_dir}")
            with zipfile.ZipFile(self.base_path, "r") as z:
                z.extractall(extract_dir)

            slides_dir = extract_dir / "ppt" / "slides"
            slides_rels_dir = slides_dir / "_rels"
            media_dir = extract_dir / "ppt" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_root = Path.cwd() / "output" / f"presentation_{timestamp}"
            out_root.mkdir(parents=True, exist_ok=True)

            # Замена заголовка в первом слайде
            slide1 = slides_dir / "slide1.xml"
            if slide1.exists():
                content = slide1.read_text(encoding="utf-8")
                if "{{TITLE}}" in content:
                    slide1.write_text(content.replace("{{TITLE}}", game_title), encoding="utf-8")
                    logger.info(f"📝 Заголовок заменен на: {game_title}")

            rels_files = sorted(
                [f for f in slides_rels_dir.glob("slide*.xml.rels")],
                key=lambda x: int(''.join(filter(str.isdigit, x.stem)) or 0)
            )
            
            logger.info(f"📄 Найдено {len(rels_files)} rels файлов")
            
            slide_track_map = {}
            audio_tasks = []
            track_index = 0
            track_for_13_and_44 = None

            for rels_path in rels_files:
                slide_num = int(''.join(filter(str.isdigit, rels_path.stem)) or 0)
                
                if slide_num in self.skip_slides:
                    logger.debug(f"⏭️ Пропуск слайда {slide_num} (в skip_slides)")
                    continue
                
                if slide_num == 13:
                    if track_index < len(tracks):
                        track_for_13_and_44 = tracks[track_index]
                        track = track_for_13_and_44
                        audio_tasks.append((rels_path, track, slide_num, media_dir))
                        slide_track_map[slide_num] = track
                        track_index += 1
                        logger.debug(f"🎵 Слайд 13: трек {track_index}")
                    continue
                elif slide_num == 44:
                    if track_for_13_and_44:
                        track = track_for_13_and_44
                        audio_tasks.append((rels_path, track, slide_num, media_dir))
                        slide_track_map[slide_num] = track
                        logger.debug(f"🎵 Слайд 44: повтор трека со слайда 13")
                    continue
                else:
                    if track_index >= len(tracks):
                        logger.debug(f"⏹️ Закончились треки на слайде {slide_num}")
                        break
                    
                    track = tracks[track_index]
                    track_index += 1
                    
                    audio_tasks.append((rels_path, track, slide_num, media_dir))
                    slide_track_map[slide_num] = track
                    logger.debug(f"🎵 Слайд {slide_num}: трек {track_index}")

            logger.info("🔄 Обработка аудио (последовательно для экономии памяти)...")
            results = self._process_audio_sequential(audio_tasks)
            
            for slide_num, processed_track in results:
                slide_track_map[slide_num] = processed_track

            logger.info(f"📊 Распределено треков по слайдам: {len(slide_track_map)}")

            final_pptx = out_root / f"presentation_{timestamp}.pptx"
            
            self._force_garbage_collection()
            self._log_memory_usage()
            
            logger.info("📦 Создание финального PPTX файла...")
            with zipfile.ZipFile(final_pptx, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        fp = Path(root) / file
                        arcname = os.path.relpath(fp, extract_dir)
                        zip_out.write(fp, arcname)

            self._image_cache.clear()
            self._force_garbage_collection()

            logger.info("🎨 Замена текста и добавление фото...")
            prs = Presentation(final_pptx)
            self._replace_placeholders_and_photos_optimized(prs, slide_track_map, make_bw)
            prs.save(final_pptx)

            del prs
            self._force_garbage_collection()

            logger.info(f"✅ Презентация готова: {final_pptx}")
            logger.info(f"📁 Папка с результатами: {out_root}")
            return str(out_root)

        except Exception as e:
            logger.error(f"❌ Ошибка при генерации презентации: {e}")
            import traceback
            logger.error(f"🔍 Трассировка ошибки:\n{traceback.format_exc()}")
            raise
        finally:
            self._image_cache.clear()
            self._force_garbage_collection()
            
            try:
                shutil.rmtree(tmp, ignore_errors=True)
                logger.info("🧹 Временные файлы очищены")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось полностью очистить временные файлы: {e}")


if __name__ == "__main__":
    try:
        logger.info("🎬 Запуск генератора презентаций")
        generator = ModernPresentationGenerator("template.pptx")
        result_path = generator.generate(
            game_title="Моя оптимизированная викторина",
            tracks=None,
            make_bw=False,
            use_parallel=False
        )
        print(f"🎉 Презентация создана в: {result_path}")
        logger.info(f"🎉 Презентация создана в: {result_path}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        logger.error(f"🔍 Трассировка:\n{traceback.format_exc()}")