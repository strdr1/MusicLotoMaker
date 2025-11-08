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
            logging.info(f"✅ {package} уже установлен")
        except ImportError:
            missing_packages.append(pip_name)
            logging.warning(f"⚠️ {package} не найден, будет установлен")
    
    if missing_packages:
        logging.info(f"📦 Устанавливаем недостающие пакеты: {', '.join(missing_packages)}")
        try:
            # Устанавливаем все недостающие пакеты одной командой
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            logging.info("✅ Все пакеты успешно установлены")
            
            # Перезагружаем текущий модуль чтобы импорты заработали
            import importlib
            importlib.invalidate_caches()
            
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ Ошибка установки пакетов: {e}")
            raise

# Устанавливаем недостающие пакеты при импорте
install_missing_packages()

# Теперь импортируем основные библиотеки
from pydub import AudioSegment
from PIL import Image, ImageOps
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
        gc.collect()
        time.sleep(0.1)

    def _get_image_orientation(self, image_path: str):
        """Определяет ориентацию изображения"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                if width > height:
                    return "horizontal"
                else:
                    return "vertical"
        except Exception as e:
            logger.warning(f"⚠️ Не удалось определить ориентацию изображения {image_path}: {e}")
            return "vertical"  # По умолчанию вертикальное

    def _load_and_process_image_optimized(self, image_path: str, make_bw: bool):
        """ДЕТАЛЬНАЯ ЗАГРУЗКА ИЗОБРАЖЕНИЯ С ЛОГИРОВАНИЕМ"""
        logger.info(f"🖼️ === НАЧАЛО ЗАГРУЗКИ ИЗОБРАЖЕНИЯ ===")
        logger.info(f"🖼️ Полный путь из JSON: {image_path}")
        
        if not self._check_memory_usage():
            self._force_garbage_collection()
            
        cache_key = f"{image_path}_{make_bw}"
        if cache_key in self._image_cache:
            logger.info(f"🖼️ Используем кэш для: {image_path}")
            return self._image_cache[cache_key]
            
        if len(self._image_cache) >= self.image_cache_size:
            self._image_cache.pop(next(iter(self._image_cache)))
        
        # Ищем файл по имени в разных местах
        filename = Path(image_path).name
        logger.info(f"🖼️ Ищем файл по имени: {filename}")
        
        possible_paths = [
            Path.cwd() / "images" / filename,
            Path.cwd() / "downloads" / filename,
            Path.cwd() / "uploads" / filename,
            Path.cwd() / filename,
            Path.cwd() / "media" / filename,
        ]
        
        found_path = None
        for path in possible_paths:
            logger.info(f"🔍 Проверяем путь: {path}")
            if path.exists():
                found_path = path
                logger.info(f"✅ Файл найден: {path}")
                break
        
        if not found_path:
            logger.error(f"❌ Файл изображения не найден ни в одном месте: {filename}")
            logger.info(f"📁 Содержимое папки images: {list((Path.cwd() / 'images').glob('*')) if (Path.cwd() / 'images').exists() else 'Папка не существует'}")
            return None
            
        try:
            logger.info(f"🖼️ Открываем изображение: {found_path}")
            with Image.open(found_path) as img:
                logger.info(f"🖼️ Изображение открыто: {img.size}, mode: {img.mode}")
                
                # Сохраняем оригинальные размеры
                original_width, original_height = img.size
                
                # Конвертируем в RGBA если нужно
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                    logger.info(f"🖼️ Конвертировано в RGBA")

                if make_bw:
                    logger.info(f"🖼️ Применяем ЧБ фильтр")
                    grayscale = ImageOps.grayscale(img.convert("RGB"))
                    alpha = img.split()[3] if len(img.split()) > 3 else None
                    if alpha:
                        img = Image.merge("RGBA", (grayscale, grayscale, grayscale, alpha))
                    else:
                        img = grayscale.convert("RGBA")

                # Возвращаем изображение без изменения размеров
                self._image_cache[cache_key] = img
                logger.info(f"🖼️ === УСПЕШНО ЗАГРУЖЕНО ===")
                return img
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки изображения {found_path}: {e}")
            return None

    def _apply_fade_effects(self, audio_segment):
        """Применяет нарастание в начале и затухание в конце трека"""
        # Нарастание в начале (1 секунда)
        fade_in_duration = min(self.fade_in_duration, len(audio_segment) // 3)
        if fade_in_duration > 0:
            audio_segment = audio_segment.fade_in(fade_in_duration)
        
        # Затухание в конце (3 секунды)
        fade_out_duration = min(self.fade_duration, len(audio_segment) - 1000)
        if fade_out_duration > 0:
            audio_segment = audio_segment.fade_out(fade_out_duration)
        
        return audio_segment

    def _find_track_file_optimized(self, track_path: str):
        """Ищет аудио файл по имени"""
        logger.info(f"🎵 Поиск аудио файла: {track_path}")
        filename = Path(track_path).name
        logger.info(f"🎵 Ищем по имени: {filename}")
        
        possible_paths = [
            Path.cwd() / "downloads" / filename,
            Path.cwd() / "uploads" / filename,
            Path.cwd() / filename,
        ]
        
        for path in possible_paths:
            logger.info(f"🔍 Проверяем: {path}")
            if path.exists():
                logger.info(f"✅ Аудио файл найден: {path}")
                return path
        
        logger.warning(f"⚠️ Аудио файл не найден: {filename}")
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
            
            # Логируем информацию о первом треке для диагностики
            if tracks:
                first_track = tracks[0]
                logger.info(f"🎵 Первый трек: {first_track.get('artist')} - {first_track.get('title')}")
                logger.info(f"🎵 Путь к изображению: {first_track.get('image_path')}")
                logger.info(f"🎵 Путь к аудио: {first_track.get('file_path')}")
                
            return tracks
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки треков: {e}")
            return []

    def _process_audio_segment_optimized(self, rels_path, track, slide_num, media_dir):
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

            audio = AudioSegment.from_file(real_path)
            seg_start = int(float(track.get("segment_start", 0)) * 1000)
            seg_dur = int(float(track.get("segment_duration", self.default_ms / 1000)) * 1000)
            end_ms = min(len(audio), seg_start + seg_dur + self.buffer_ms)
            
            if seg_start > 0 or end_ms < len(audio):
                clip = audio[seg_start:end_ms]
            else:
                clip = audio

            # Применяем нарастание и затухание
            clip = self._apply_fade_effects(clip)

            out_media_path = media_dir / os.path.basename(targets[0])
            
            clip.export(out_media_path, format="mp3", bitrate="96k")
            
            del audio, clip
            self._force_garbage_collection()

            return (slide_num, track)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки аудио для слайда {slide_num}: {e}")
            return None

    def _apply_text_formatting_with_style(self, original_run, new_text, is_artist, slide_num, artist_name=None):
        """УПРОЩЕННАЯ ВЕРСИЯ - без работы с bold/italic"""
        try:
            logger.info(f"🔧 Начало форматирования текста: '{new_text}'")
        
            RED = RGBColor(255, 0, 0)
            BLACK = RGBColor(0, 0, 0)
        
            # Сохраняем только имя и размер шрифта
            font_name = original_run.font.name
            font_size = original_run.font.size

            logger.info(f"📝 Параметры шрифта: name={font_name}, size={font_size}")
        
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
                logger.info(f"🎨 Используем кеш красных слов для артиста '{artist_name}': {cached_red_words}")
        
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
                    new_run.font.color.rgb = BLACK
        
            logger.info(f"✅ Форматирование завершено для текста: '{new_text}'")
        
        except Exception as e:
            logger.error(f"❌ Ошибка в _apply_text_formatting_with_style: {e}")
        
            # Аварийное восстановление - просто устанавливаем текст
            try:
                original_run.text = new_text
                logger.info("🆘 Установлен простой текст в качестве запасного варианта")
            except:
                logger.error("💥 Не удалось установить даже простой текст")
            raise

    def _move_button_to_corner(self, slide, slide_height, slide_width, mirror=False):
        """Перемещает кнопку image42.png в угол"""
        try:
            logger.info(f"🔍 Поиск кнопки image42.png на слайде")
        
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
                                        logger.info(f"Фигура {i}: rId={rId}, filename={filename}")
                                    
                                        if filename.lower() == 'image42.png':
                                            if mirror:
                                                # Левый нижний угол
                                                shape.left = Inches(0.2)
                                                shape.top = slide_height - shape.height - Inches(0.2)
                                            else:
                                                # Правый нижний угол
                                                shape.left = slide_width - shape.width - Inches(0.2)
                                                shape.top = slide_height - shape.height - Inches(0.2)
                                            logger.info(f"✅ Кнопка перемещена!")
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
        """Вставляет фото артиста с проверкой на None"""
        try:
            if processed_img is None:
                logger.warning("⚠️ Пропускаем вставку фото - изображение не загружено")
                return
                
            temp_img_path = Path(tempfile.gettempdir()) / f"temp_photo_{random.randint(1000,9999)}.png"
            processed_img.save(temp_img_path, "PNG", optimize=True)

            img_width_px, img_height_px = processed_img.size
            dpi = 96
            
            # Конвертируем пиксели в дюймы
            width_inches = img_width_px / dpi
            height_inches = img_height_px / dpi
            
            # Увеличиваем фото для ВСЕХ шаблонов
            if template_type == 1:
                # Шаблон 1: Вертикальное фото слева
                scale_factor = 1.2
                width_inches *= scale_factor
                height_inches *= scale_factor
                
                left = Inches(0)
                top = slide_height - Inches(height_inches)
                width = Inches(width_inches)
                height = Inches(height_inches)
                
            elif template_type == 2:
                # Шаблон 2: Вертикальное фото справа
                scale_factor = 1.15
                width_inches *= scale_factor
                height_inches *= scale_factor
                
                left = slide_width - Inches(width_inches)
                top = slide_height - Inches(height_inches)
                width = Inches(width_inches)
                height = Inches(height_inches)
                
            elif template_type == 3:
                # Шаблон 3: Горизонтальное фото
                scale_factor = 1.1
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

            slide.shapes.add_picture(str(temp_img_path), left, top, width=width, height=height)
            
            try:
                temp_img_path.unlink(missing_ok=True)
            except:
                pass

            logger.info(f"🖼️ Фото добавлено по шаблону {template_type}")

        except Exception as e:
            logger.error(f"❌ Ошибка вставки фото: {e}")

    def _replace_placeholders_and_photos_optimized(self, prs, slide_track_map, make_bw: bool):
        slide_height = prs.slide_height
        slide_width = prs.slide_width
        
        # Сбрасываем счетчик красных слов перед обработкой слайдов
        self._red_words_per_slide.clear()
        
        for i, slide in enumerate(prs.slides):
            if i % 5 == 0:
                if not self._check_memory_usage():
                    self._force_garbage_collection()
            
            slide_num = int(''.join(ch for ch in slide.part.partname if ch.isdigit()) or 0)
            
            if slide_num not in slide_track_map:
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
                    logger.warning(f"⚠️ Не удалось загрузить изображение для слайда {slide_num}: {image_path}")

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

            # Обрабатываем артиста
            if artist_shapes:
                artist_shape, artist_run = artist_shapes[0]
                
                # Позиционируем согласно шаблону
                if template_type == 1:
                    # Шаблон 1: Вертикальное фото слева - текст ПРАВЕЕ и ВЫШЕ
                    artist_shape.left = Inches(9.0)
                    artist_shape.top = Inches(0.8)
                elif template_type == 2:
                    # Шаблон 2: Вертикальное фото справа - текст слева сверху
                    artist_shape.left = Inches(0.5)
                    artist_shape.top = Inches(1.0)
                elif template_type == 3:
                    # Шаблон 3: Горизонтальное фото - текст справа сверху
                    artist_shape.left = Inches(8.0)
                    artist_shape.top = Inches(1.0)
                
                artist_shape.text_frame.word_wrap = False
                artist_shape.text_frame.auto_size = True
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
                        title_shape.left = Inches(9.0)
                        title_shape.top = Inches(2.0)
                    elif template_type == 2:
                        title_shape.left = Inches(0.5)
                        title_shape.top = Inches(2.2)
                    elif template_type == 3:
                        title_shape.left = Inches(8.0)
                        title_shape.top = Inches(2.2)
                    
                    title_shape.text_frame.word_wrap = False
                    title_shape.text_frame.auto_size = True
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
                        slide.shapes._spTree.remove(shape._element)

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
        for i, task in enumerate(audio_tasks):
            if i % 3 == 0:
                if not self._check_memory_usage():
                    self._force_garbage_collection()
                    time.sleep(0.5)
                    
            result = self._process_audio_segment_optimized(*task)
            if result:
                results.append(result)
                
        return results

    def generate(self, game_title: str, tracks: list = None, make_bw: bool = False, use_parallel: bool = False):
        logger.info("🚀 Запуск оптимизированной генерации презентации")
        
        # Очищаем кеши перед новой генерацией
        self._force_garbage_collection()
        self._image_cache.clear()
        self._red_words_per_slide.clear()
        self._artist_red_words_cache.clear()
        
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
            with zipfile.ZipFile(self.base_path, "r") as z:
                z.extractall(extract_dir)

            slides_dir = extract_dir / "ppt" / "slides"
            slides_rels_dir = slides_dir / "_rels"
            media_dir = extract_dir / "ppt" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_root = Path.cwd() / "output" / f"presentation_{timestamp}"
            out_root.mkdir(parents=True, exist_ok=True)

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

            logger.info("🔄 Обработка аудио (последовательно для экономии памяти)...")
            results = self._process_audio_sequential(audio_tasks)
            
            for slide_num, processed_track in results:
                slide_track_map[slide_num] = processed_track

            logger.info(f"📊 Распределено треков по слайдам: {len(slide_track_map)}")

            final_pptx = out_root / f"presentation_{timestamp}.pptx"
            
            self._force_garbage_collection()
            
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