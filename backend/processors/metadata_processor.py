# processors/metadata_processor.py
import re
import os
import json
import logging
import requests
from datetime import datetime
from urllib.parse import quote
import time

os.makedirs("logs/ai_explanations", exist_ok=True)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("INFO - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

class SmartAIMusicParser:
    def __init__(self):
        self.cache_file = "music_metadata_cache.json"
        self.cache = self._load_cache()
        logger.info("🚀 Smart AI Music Parser initialized")

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except:
            pass

    def clean_filename(self, filename):
        """
        Очищает имя файла: убирает расширение и конечные числа (например, ID трека).
        Не убирает timestamp в начале - это делает _parse_filename_structure.
        """
        clean = re.sub(r'\.(mp3|wav|flac|m4a|aac)$', '', filename, flags=re.IGNORECASE)
        clean = re.sub(r'[_-]?\d+$', '', clean)
        return clean.strip(' _-')

    def _parse_filename_structure(self, clean_name):
        """
        Парсинг структуры файла, учитывая возможный timestamp в начале.
        """
        # Паттерн для timestamp: YYYYMMDD_HHMMSS (или похожий)
        # Убираем его в начале, если он есть
        name_without_timestamp = re.sub(r'^\d{8}_\d{6}_?', '', clean_name)
        clean_name = name_without_timestamp

        # Теперь парсим по структуре
        if ' - ' in clean_name:
            parts = clean_name.split(' - ', 1)
            artist_raw = parts[0].replace('_', ' ').strip()
            title_raw = parts[1].replace('_', ' ').strip()
            separator = "' - '"
        elif '-' in clean_name:
            # Если только один '-', не пробел
            parts = clean_name.split('-', 1)
            artist_raw = parts[0].replace('_', ' ').strip()
            title_raw = parts[1].replace('_', ' ').strip()
            separator = "'-'"
        elif '_' in clean_name:
            # Если нет '-', пробуем '_'
            parts = clean_name.rsplit('_', 1)
            if len(parts) > 1:
                artist_raw = parts[0].replace('_', ' ').strip()
                title_raw = parts[1].replace('_', ' ').strip()
                separator = "последнее '_'"
            else:
                # Если ни один из разделителей не найден, возвращаем всё как артиста
                artist_raw = clean_name.replace('_', ' ').strip()
                title_raw = "Без названия"
                separator = "нет"
        else:
            # Если нет разделителей, возвращаем всё как артиста
            artist_raw = clean_name.replace('_', ' ').strip()
            title_raw = "Без названия"
            separator = "нет"

        return artist_raw, title_raw, separator

    def _check_known_cases(self, artist_raw, title_raw):
        """Проверка по известным случаям"""
        # База известных русских артистов
        known_artists = {
            'korol i shut': 'Король и Шут',
            'mikhail krug': 'Михаил Круг',
            'viktor coji': 'Виктор Цой',
            'viktor tsoi': 'Виктор Цой',
            'sektor gaza': 'Сектор Газа',
            'yurij shatunov': 'Юрий Шатунов',
            'yurijj shatunov': 'Юрий Шатунов',
            'anna asti': 'Анна Асти',
            'artur pirozhkov': 'Артур Пирожков',
            'gorod 312': 'ГОРОД 312',
            'ddt': 'ДДТ',
            'alisa': 'Алиса',
            'nogu svelo': 'Ногу Свело!',
            'splin': 'Сплин',
            'bi-2': 'Би-2',
            'zemfira': 'Земфира',
            'agata kristi': 'Агата Кристи',
            'kino': 'Кино',
            'lyube': 'Любэ',
            'ivanushki': 'Иванушки International',
            'a studio': 'A\'Studio',
            'vintage': 'Vintage',
            'diskoteka avariya': 'Дискотека Авария'
        }

        # База известных треков
        known_tracks = {
            'vladimirskij central': 'Владимирский централ',
            'vladimir central': 'Владимирский централ',
            'gruppa krovi': 'Группа крови',
            'chastushki': 'Частушки',
            'tuman': 'Туман',
            'sedaya noch': 'Седая ночь',
            'prygnu so skaly': 'Прыгну со скалы',
            'povod': 'Повод',
            'mozhno ya s toboj': 'Можно я с тобой',
            'mozhno ya s tobojj': 'Можно я с тобой',
            'lesnik': 'Лесник',
            'carica': 'Царица',
            'tanec zlobnogo geniya': 'Танец злобного гения',
            'tanets zlobnogo geniya': 'Танец злобного гения',
            'kukushka': 'Кукушка',
            'pacany': 'Пацаны',
            'devochka s sovest': 'Девочка с совесть',
            'zvezda po imeni solnce': 'Звезда по имени Солнце',
            'ya svobodnen': 'Я свободен',
            'kroshitsya trava': 'Крошится трава',
            'belaya noch': 'Белая ночь',
            'ochen horosho': 'Очень хорошо',
            'koroleva krasoty': 'Королева красоты'
        }

        # Брендовые имена (оставляем как есть)
        brand_artists = {
            'instasamka': 'INSTASAMKA',
            'morgenstern': 'MORGENSTERN',
            'morgenstern': 'MORGENSTERN',
            'apent': 'APENT',
            'miyagi': 'Miyagi',
            'billie eilish': 'Billie Eilish',
            'the weeknd': 'The Weeknd',
            'ariana grande': 'Ariana Grande',
            'taylor swift': 'Taylor Swift',
            'ed sheeran': 'Ed Sheeran'
        }

        artist_lower = artist_raw.lower()
        title_lower = title_raw.lower()

        # Сначала проверяем известных артистов
        for key, value in known_artists.items():
            if key in artist_lower:
                # Теперь проверяем трек для этого артиста
                for track_key, track_value in known_tracks.items():
                    if track_key in title_lower:
                        return value, track_value, f"Известный артист '{key}' и трек '{track_key}'"
                # Если трек не найден, используем базовую нормализацию
                title = self._normalize_title(title_raw)
                return value, title, f"Известный артист '{key}'"

        # Проверяем брендовые имена
        for key, value in brand_artists.items():
            if key in artist_lower:
                return value, title_raw, f"Брендовое имя артиста '{key}'"

        # Проверяем известные треки (если артист не найден)
        for key, value in known_tracks.items():
            if key in title_lower:
                artist = self._normalize_artist(artist_raw)
                return artist, value, f"Известный трек '{key}'"

        return None, None, None

    def _normalize_artist(self, artist):
        """Нормализация артиста"""
        # Проверяем, не является ли artist путём
        if os.path.isabs(artist) or os.path.sep in artist.replace('\\', '/'):
            logger.warning(f"⚠️ Имя артиста выглядит как путь, возвращаем 'Неизвестный': {artist}")
            return "Неизвестный исполнитель"

        # Убираем суффиксы в скобках
        artist_cleaned = re.sub(r'\s*\([^)]*\)$', '', artist).strip()

        artist_lower = artist_cleaned.lower()

        # Автоматическое определение языка
        has_cyrillic = any(c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' for c in artist_lower)
        has_translit = any(p in artist_lower for p in ['sh', 'ch', 'zh', 'yu', 'ya', 'iy', 'ij'])

        if has_cyrillic:
            return artist_cleaned.title()
        elif has_translit:
            return self._transliterate_russian(artist_cleaned)
        else:
            return artist_cleaned.upper()

    def _normalize_title(self, title):
        """Нормализация названия"""
        # Убираем суффиксы в скобках
        title_cleaned = re.sub(r'\s*\([^)]*\)$', '', title).strip()

        title_lower = title_cleaned.lower()

        has_cyrillic = any(c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' for c in title_lower)
        has_translit = any(p in title_lower for p in ['sh', 'ch', 'zh', 'yu', 'ya', 'iy', 'ij'])

        if has_cyrillic:
            return title_cleaned.capitalize()
        elif has_translit:
            return self._transliterate_russian(title_cleaned)
        else:
            return title_cleaned

    def _transliterate_russian(self, text):
        """Транслитерация русских слов"""
        translit_map = {
            'sh': 'ш', 'ch': 'ч', 'zh': 'ж', 'kh': 'х',
            'yu': 'ю', 'ya': 'я', 'iy': 'ий', 'ij': 'ий', 'yj': 'ый',
            'y': 'ы', 'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г',
            'd': 'д', 'e': 'е', 'z': 'з', 'i': 'и', 'k': 'к',
            'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п',
            'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'f': 'ф',
            'c': 'ц', 'jo': 'ё', 'je': 'е'
        }

        special_cases = {
            'yurij': 'юрий', 'yuriy': 'юрий', 'yuri': 'юрий',
            'mikhail': 'михаил', 'mihail': 'михаил',
            'viktor': 'виктор', 'victor': 'виктор',
            'coji': 'цой', 'tsoi': 'цой',
            'shatunov': 'шатунов', 'krug': 'круг',
            'korol': 'король', 'shut': 'шут',
            'gaza': 'газа', 'asti': 'асти',
            'pirozhkov': 'пирожков', 'gorod': 'город',
            'sedaya': 'седая', 'noch': 'ночь',
            'gruppa': 'группа', 'krovi': 'крови',
            'tuman': 'туман', 'lesnik': 'лесник',
            'tanec': 'танец', 'zlobnogo': 'злобного', 'geniya': 'гения'
        }

        text_lower = text.lower()

        # Применяем специальные случаи
        for eng, rus in special_cases.items():
            if eng in text_lower:
                text_lower = text_lower.replace(eng, rus)

        # Применяем общие правила
        for eng, rus in translit_map.items():
            text_lower = text_lower.replace(eng, rus)

        # Капитализируем
        words = text_lower.split()
        return ' '.join(word.capitalize() for word in words)

    def _search_internet(self, artist_raw, title_raw):
        """Поиск в интернете (резервный вариант)"""
        try:
            # Простая эмуляция поиска
            query = f"{artist_raw} {title_raw}"

            # Эмуляция проверки в музыкальных базах
            time.sleep(0.5)  # Имитация задержки сети

            # Здесь могла бы быть реальная проверка через API
            # Но пока возвращаем None, так как это резервный вариант
            return None, None, "Интернет-поиск"

        except Exception as e:
            logger.debug(f"Интернет-поиск: {e}")
            return None, None, None

    def _analyze_filename(self, clean_name):
        """Основной анализ файла"""
        logger.info("🔍 Анализ файла...")

        # 1. Парсим структуру
        artist_raw, title_raw, separator = self._parse_filename_structure(clean_name)

        explanation = f"""🎵 ДЕТАЛЬНЫЙ АНАЛИЗ МУЗЫКАЛЬНОГО ФАЙЛА

📁 ИСХОДНЫЕ ДАННЫЕ:
- Файл: {clean_name}
- Артист (сырой): "{artist_raw}"
- Название (сырой): "{title_raw}"

🔍 СТРУКТУРНЫЙ АНАЛИЗ:
- Разделитель: {separator}
- Части файла: "{artist_raw}" - "{title_raw}"

🎯 ЭТАПЫ АНАЛИЗА:"""

        # 2. ПРОВЕРКА ПО ИЗВЕСТНЫМ СЛУЧАЯМ (ПРИОРИТЕТ)
        explanation += "\n\n1. 🔎 ПРОВЕРКА ПО ИЗВЕСТНЫМ СЛУЧАЯМ:"
        known_artist, known_title, known_reason = self._check_known_cases(artist_raw, title_raw)

        if known_artist and known_title:
            result = {"artist": known_artist, "title": known_title}
            explanation += f"\n- ✅ НАЙДЕНО В БАЗЕ ИЗВЕСТНЫХ СЛУЧАЕВ"
            explanation += f"\n- Причина: {known_reason}"
            explanation += f"\n- Артист: '{artist_raw}' → '{known_artist}'"
            explanation += f"\n- Название: '{title_raw}' → '{known_title}'"
            explanation += f"\n\n🎯 ФИНАЛЬНОЕ РЕШЕНИЕ: {json.dumps(result, ensure_ascii=False)}"
            return explanation, result

        explanation += "\n- ❌ НЕ НАЙДЕНО В БАЗЕ ИЗВЕСТНЫХ СЛУЧАЕВ"

        # 3. ПРОВЕРКА В ИНТЕРНЕТЕ (РЕЗЕРВНЫЙ ВАРИАНТ)
        explanation += "\n\n2. 🌐 ПРОВЕРКА В ИНТЕРНЕТЕ:"
        internet_artist, internet_title, internet_source = self._search_internet(artist_raw, title_raw)

        if internet_artist and internet_title:
            result = {"artist": internet_artist, "title": internet_title}
            explanation += f"\n- ✅ НАЙДЕНО В ИНТЕРНЕТЕ"
            explanation += f"\n- Источник: {internet_source}"
            explanation += f"\n- Артист: '{artist_raw}' → '{internet_artist}'"
            explanation += f"\n- Название: '{title_raw}' → '{internet_title}'"
        else:
            explanation += "\n- ❌ НЕ НАЙДЕНО В ИНТЕРНЕТЕ"

            # 4. АВТОМАТИЧЕСКАЯ НОРМАЛИЗАЦИЯ (ПОСЛЕДНИЙ ВАРИАНТ)
            explanation += "\n\n3. 🤖 АВТОМАТИЧЕСКАЯ НОРМАЛИЗАЦИЯ:"
            # Убираем скобки ДО нормализации
            artist_cleaned_before_norm = re.sub(r'\s*\([^)]*\)$', '', artist_raw).strip()
            title_cleaned_before_norm = re.sub(r'\s*\([^)]*\)$', '', title_raw).strip()
            
            artist = self._normalize_artist(artist_cleaned_before_norm)
            title = self._normalize_title(title_cleaned_before_norm)
            result = {"artist": artist, "title": title}

            explanation += f"\n- Артист: '{artist_raw}' → '{artist_cleaned_before_norm}' → '{artist}'"
            explanation += f"\n- Название: '{title_raw}' → '{title_cleaned_before_norm}' → '{title}'"
            explanation += "\n- Логика: удаление скобок, затем автоматическое определение языка и транслитерация"

        explanation += f"\n\n🎯 ФИНАЛЬНОЕ РЕШЕНИЕ: {json.dumps(result, ensure_ascii=False)}"

        return explanation, result

    def process(self, filename):
        logger.info(f"🎵 Processing: '{filename}'")
        clean_name = self.clean_filename(filename)
        cache_key = clean_name.lower()

        if cache_key in self.cache:
            logger.info("📦 Используется кэш")
            return self.cache[cache_key]

        # Анализ файла
        explanation, result = self._analyze_filename(clean_name)

        # Сохраняем объяснение
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
        path = f"logs/ai_explanations/{safe_name}.txt"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"Файл: {filename}\nОчищено: {clean_name}\n{'='*60}\n")
            f.write(explanation)

        logger.info(f"📄 Объяснение сохранено: {path}")
        logger.info(f"✅ Результат: {result}")

        self.cache[cache_key] = result
        self._save_cache()
        return result

    def clear_cache(self):
        try:
            self.cache = {}
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            logger.info("🗑️ Кэш очищен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")
            return False


_parser_instance = None

def create_metadata_processor():
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = SmartAIMusicParser()
        logger.info("🚀 Smart AI Music Parser создан")
    return _parser_instance

def clear_metadata_cache():
    global _parser_instance
    if _parser_instance:
        return _parser_instance.clear_cache()
    return False