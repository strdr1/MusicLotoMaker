# backend/processors/metadata_processor.py
import re
import requests
import os
import logging

logger = logging.getLogger(__name__)

class HuggingFaceMusicParser:
    def __init__(self, api_token=None):
        self.api_token = api_token or os.getenv('HF_API_TOKEN')
        if self.api_token:
            self.headers = {"Authorization": f"Bearer {self.api_token}"}
        else:
            self.headers = {}
            logger.info("⚠️ Hugging Face API token not provided, using smart parsing only")
    
    def clean_filename(self, filename):
        """Очистка имени файла"""
        clean = re.sub(r'\.(mp3|wav|flac|m4a|aac)$', '', filename, flags=re.IGNORECASE)
        clean = re.sub(r'[_-]?\d+$', '', clean)  # Убираем цифровые ID
        return clean.strip()
    
    def smart_parse(self, filename):
        """Умный парсинг русских названий"""
        clean_name = self.clean_filename(filename)
        logger.info(f"🔍 Анализ файла: {clean_name}")
        
        # Полные имена исполнителей (должны совпадать полностью или частично)
        known_artists = {
            'gayazov brother': 'GAYAZOV BROTHER',
            'gayazov': 'GAYAZOV BROTHER',
            'гиозав братер': 'GAYAZOV BROTHER',
            'гио пика': 'Гио Пика',
            'gio pika': 'Гио Пика',
            'тим амеди': 'Тим Амеди',
            'tima amedi': 'Тима Амеди',
            'гюн плюс': 'ГимПлюс',
            'gym plus': 'ГимПлюс'
        }
        
        # Известные названия треков
        title_mapping = {
            'pyanyjj tuman': 'Пьяный туман',
            'пьяный туман': 'Пьяный туман',
            'pьяnyjj tuman': 'Пьяный туман',
            'где прошла ты': 'Где прошла ты',
            'gde prosla ty': 'Где прошла ты'
        }
        
        # Сначала проверяем специальные случаи
        special_cases = [
            # GAYAZOV BROTHER cases
            (r'gayazov[\s_-]*brother[\s_-]*([^-]+)$', 'GAYAZOV BROTHER', 1),
            (r'гаязов[\s_-]*братер[\s_-]*([^-]+)$', 'GAYAZOV BROTHER', 1),
            (r'гиозав[\s_-]*бразер[\s_-]*([^-]+)$', 'GAYAZOV BROTHER', 1),
        ]
        
        for pattern, artist, group_idx in special_cases:
            match = re.search(pattern, clean_name.lower())
            if match:
                title = match.group(group_idx).strip(' -_')
                if title:
                    # Исправляем известные названия
                    title_lower = title.lower()
                    for wrong, correct in title_mapping.items():
                        if wrong in title_lower:
                            title = correct
                            break
                    logger.info(f"✅ Специальный случай: {artist} - {title}")
                    return {"artist": artist, "title": title}
        
        # Пытаемся разделить по разделителям
        separators = [' - ', ' _ ', ' — ', ' – ', '_-_']
        for sep in separators:
            if sep in clean_name:
                parts = clean_name.split(sep, 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
                    
                    logger.info(f"🔍 Разделитель '{sep}': artist='{artist}', title='{title}'")
                    
                    # Обрабатываем GAYAZOV BROTHER случай
                    artist_lower = artist.lower()
                    title_lower = title.lower()
                    
                    # Если в artist есть "gayazov", а в title есть "brother" - объединяем
                    if 'gayazov' in artist_lower and 'brother' in title_lower:
                        artist = 'GAYAZOV BROTHER'
                        # Убираем "brother" из названия
                        title = re.sub(r'brother', '', title, flags=re.IGNORECASE).strip(' -_')
                        logger.info(f"✅ Объединен GAYAZOV BROTHER: {artist} - {title}")
                    
                    # Исправляем известных исполнителей
                    for wrong, correct in known_artists.items():
                        if wrong in artist_lower:
                            artist = correct
                            break
                    
                    # Исправляем известные названия
                    for wrong, correct in title_mapping.items():
                        if wrong in title_lower:
                            title = correct
                            break
                    
                    # Чистим название от остатков разделителей
                    title = title.strip(' -_')
                    
                    logger.info(f"✅ После коррекции: {artist} - {title}")
                    return {"artist": artist, "title": title}
        
        # Обработка подчеркиваний как разделителей
        if '_' in clean_name and ' - ' not in clean_name:
            parts = clean_name.split('_', 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                title = parts[1].strip()
                
                logger.info(f"🔍 Подчеркивание как разделитель: artist='{artist}', title='{title}'")
                
                # Специальная обработка для GAYAZOV_BROTHER
                if artist.lower() == 'gayazov' and 'brother' in title.lower():
                    # Если title начинается с "brother", то это часть имени исполнителя
                    if title.lower().startswith('brother'):
                        artist = 'GAYAZOV BROTHER'
                        title = title[7:].strip(' -_')  # Убираем "brother" из начала
                    else:
                        # Иначе объединяем
                        artist = 'GAYAZOV BROTHER'
                        title = re.sub(r'brother', '', title, flags=re.IGNORECASE).strip(' -_')
                
                # Применяем маппинг
                artist_lower = artist.lower()
                for wrong, correct in known_artists.items():
                    if wrong in artist_lower:
                        artist = correct
                        break
                
                title_lower = title.lower()
                for wrong, correct in title_mapping.items():
                    if wrong in title_lower:
                        title = correct
                        break
                
                title = title.strip(' -_')
                logger.info(f"✅ После обработки подчеркивания: {artist} - {title}")
                return {"artist": artist, "title": title}
        
        # Если ничего не помогло, ищем известные паттерны в целом названии
        clean_lower = clean_name.lower()
        for artist_key, artist_correct in known_artists.items():
            if artist_key in clean_lower:
                # Пытаемся извлечь название, убирая имя исполнителя
                if artist_key == 'gayazov brother':
                    # Специальная обработка для полного имени
                    title_part = re.sub(r'gayazov[\s_-]*brother', '', clean_lower, flags=re.IGNORECASE)
                else:
                    title_part = clean_lower.replace(artist_key, '')
                
                title_part = title_part.strip(' -_')
                if title_part:
                    # Исправляем известные названия
                    for wrong, correct in title_mapping.items():
                        if wrong in title_part:
                            title_part = correct
                            break
                    
                    logger.info(f"✅ Найден по паттерну: {artist_correct} - {title_part}")
                    return {"artist": artist_correct, "title": title_part}
        
        # Финальная попытка - базовое разделение
        if ' - ' in clean_name:
            parts = clean_name.split(' - ', 1)
            artist, title = parts[0].strip(), parts[1].strip()
        elif '_' in clean_name:
            parts = clean_name.split('_', 1)
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            artist, title = clean_name, ""
        
        logger.info(f"⚠️ Базовое разделение: {artist} - {title}")
        return {"artist": artist, "title": title}
    
    def parse_with_hugging_face(self, filename):
        """Парсинг через Hugging Face API"""
        if not self.api_token:
            return None
            
        try:
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1"
            
            prompt = f"""
            <s>[INST] Разбери название музыкального файла на исполнителя и название трека.
            Файл: "{filename}"
            
            Важно! Если видишь "GAYAZOV BROTHER" - это один исполнитель.
            "GAYAZOV" без "BROTHER" - тоже относится к GAYAZOV BROTHER.
            
            Верни ТОЛЬКО JSON в формате:
            {{"artist": "исполнитель", "title": "название трека"}}
            
            Примеры:
            - "GAYAZOV_BROTHER_-_Pyanyjj_tuman" → {{"artist": "GAYAZOV BROTHER", "title": "Пьяный туман"}}
            - "GAYAZOV_-_Pyanyjj_tuman" → {{"artist": "GAYAZOV BROTHER", "title": "Пьяный туман"}}
            - "гио пика-где прошла ты" → {{"artist": "Гио Пика", "title": "Где прошла ты"}}
            
            Не добавляй пояснений! Только JSON. [/INST]
            """
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 100,
                    "temperature": 0.1,
                    "do_sample": False,
                    "return_full_text": False
                }
            }
            
            response = requests.post(API_URL, headers=self.headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and 'generated_text' in result[0]:
                    text = result[0]['generated_text']
                    # Ищем JSON в ответе
                    import json
                    json_match = re.search(r'\{.*\}', text)
                    if json_match:
                        return json.loads(json_match.group())
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Hugging Face API error: {e}")
            return None
    
    def process(self, filename):
        """Основной метод обработки"""
        try:
            logger.info(f"🎵 Начало обработки: {filename}")
            
            # Сначала пробуем умный парсинг
            smart_result = self.smart_parse(filename)
            logger.info(f"🔍 Smart parse result: {smart_result}")
            
            # Если Hugging Face API доступен, используем его
            hf_result = self.parse_with_hugging_face(filename)
            if hf_result and hf_result.get('artist') and hf_result.get('title'):
                logger.info(f"🤖 Hugging Face result: {hf_result}")
                return hf_result
            
            logger.info(f"✅ Final result: {smart_result}")
            return smart_result
            
        except Exception as e:
            logger.error(f"❌ Metadata processing error: {e}")
            # Fallback на базовый парсинг при ошибках
            return {"artist": filename, "title": ""}

def create_metadata_processor():
    """Создает метадата процессор"""
    return HuggingFaceMusicParser()