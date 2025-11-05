# audio_editor.py
import os
import io
import base64
import threading
import time
import json
import hashlib
import logging
import requests
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class AIAudioAnalyzer:
    """AI анализатор аудио через OpenRouter"""
    
    def __init__(self):
        self.api_key = "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"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Проверенные бесплатные модели
        self.models = [
            "huggingfaceh4/zephyr-7b-beta:free",
            "mistralai/mistral-7b-instruct:free", 
        ]
        
        if self.api_key:
            logger.info(f"🔑 API Key загружен")
        else:
            logger.warning("⚠️ API Key не найден, используем умный фолбек")
        
    def suggest_best_segment(self, file_path: str, duration: int = 30, artist: str = None, title: str = None) -> float:
        """Анализирует аудио через AI и возвращает лучший стартовый момент"""
        try:
            # Сначала быстрая проверка файла
            if not os.path.exists(file_path):
                return self._smart_fallback(file_path, duration)
            
            # Пробуем AI только если есть ключ
            if self.api_key:
                track_info = self._get_audio_info(file_path)
                if track_info and track_info['total_duration'] > duration + 20:
                    ai_result = self._try_ai_analysis(track_info, duration, artist, title)
                    if ai_result is not None:
                        return ai_result
            
            # Всегда используем умный фолбек
            return self._smart_fallback(file_path, duration)
                
        except Exception as e:
            logger.error(f"❌ AI анализ failed: {e}")
            return self._smart_fallback(file_path, duration)
    
    def _get_audio_info(self, file_path: str) -> dict:
        """Быстрое получение информации об аудио"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                duration_str = result.stdout.strip()
                if duration_str:
                    total_duration = float(duration_str)
                    return {
                        'total_duration': total_duration,
                        'filename': os.path.basename(file_path)
                    }
        except:
            pass
        return None
    
    def _try_ai_analysis(self, track_info: dict, duration: int, artist: str, title: str) -> float:
        """Пробуем AI анализ с правильным промптом"""
        prompt = self._create_correct_prompt(track_info, duration, artist, title)
        
        for model in self.models:
            try:
                result = self._query_ai_simple(prompt, model)
                if result:
                    parsed = self._parse_ai_response(result, track_info, duration)
                    if parsed is not None:
                        logger.info(f"✅ AI предложил: {parsed:.1f}с")
                        return parsed
            except:
                continue
        return None
    
    def _create_correct_prompt(self, track_info: dict, duration: int, artist: str, title: str) -> str:
        """Правильный промпт с информацией о треке"""
        total_duration = track_info['total_duration']
        
        if artist and title:
            track_info_str = f"Трек: {artist} - {title}"
        else:
            track_info_str = f"Трек: {track_info['filename']}"
        
        return f"""Ты музыкальный эксперт. Проанализируй трек и найди лучший момент для начала {duration}-секундного отрывка.

{track_info_str}
Длительность трека: {total_duration:.1f} секунд

Задача: Найди момент начала припева (самой запоминающейся части трека) и верни время за 5-8 секунд ДО него.

Требования:
- Отрывок должен захватывать начало припева
- Должен быть музыкально насыщенным
- Должен хорошо представлять трек

Ограничения:
- Максимальное время начала: {total_duration - duration:.1f} секунд
- Минимальное время: 0 секунд

Верни ТОЛЬКО число - секунду начала в формате 45.2 (без текста, без кавычек):"""
    
    def _query_ai_simple(self, prompt: str, model: str) -> str:
        """Простой запрос к AI"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 15,
                "temperature": 0.1,
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip()
        except:
            pass
        return None
    
    def _parse_ai_response(self, ai_response: str, track_info: dict, duration: int) -> float:
        """Парсим ответ AI"""
        try:
            # Ищем любое число в ответе
            import re
            numbers = re.findall(r'\d+\.?\d*', ai_response)
            if numbers:
                best_start = float(numbers[0])
                total_duration = track_info['total_duration']
                max_possible = total_duration - duration
                
                # Проверяем границы
                if 0 <= best_start <= max_possible:
                    return best_start
        except:
            pass
        return None
    
    def _smart_fallback(self, file_path: str, duration: int) -> float:
        """Умный фолбек на основе длительности трека"""
        try:
            track_info = self._get_audio_info(file_path)
            if not track_info:
                return 45.0  # Умное значение по умолчанию
            
            total_duration = track_info['total_duration']
            
            # Простая эвристика: припев обычно начинается на 25-35% трека
            # Берем 30% и отступаем 5 секунд до припева
            chorus_start_estimate = total_duration * 0.3
            suggested = max(0, chorus_start_estimate - 5)
            
            # Ограничиваем диапазон 25-60 секунд
            suggested = max(25.0, min(suggested, 60.0))
            
            # Проверяем границы
            max_possible = total_duration - duration
            if max_possible < 10:  # Если трек очень короткий
                suggested = 0.0
            else:
                suggested = min(suggested, max_possible)
            
            logger.info(f"🎵 Умный фолбек: {suggested:.1f}с (из {total_duration:.1f}с)")
            return suggested
            
        except Exception as e:
            logger.error(f"❌ Фолбек failed: {e}")
            return 45.0  # Надежное значение по умолчанию

class AudioEditor:
    def __init__(self):
        self.current_playing = None
        self.playback_thread = None
        self.stop_playback_flag = False
        
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._create_directories()
        
        # Инициализируем AI анализатор
        self.ai_analyzer = AIAudioAnalyzer()
        logger.info("🎵 AudioEditor с правильным AI анализом")

    def _create_directories(self):
        """Создает необходимые папки"""
        folders = ["temp", "output", "images", "covers", "tracks_data"]
        for folder in folders:
            folder_path = os.path.join(self.BASE_DIR, folder)
            os.makedirs(folder_path, exist_ok=True)

    def load_audio(self, file_path):
        """Загрузка аудиофайла"""
        try:
            if not os.path.exists(file_path):
                return None
                
            duration = self.get_audio_duration(file_path)
            if duration == 0:
                return None
                
            return {"duration": duration, "file_path": file_path}
        except:
            return None

    def get_audio_duration(self, file_path):
        """Получение длительности аудио"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except:
            pass
        return 0

    def extract_segment(self, file_path, start_time, duration=30, output_path=None):
        """Извлечение отрезка"""
        try:
            if not output_path:
                track_id = hashlib.md5(f"{file_path}_{start_time}".encode()).hexdigest()[:8]
                output_path = os.path.join(self.BASE_DIR, "temp", f"segment_{track_id}.mp3")
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            cmd = [
                'ffmpeg', '-y', '-i', file_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'libmp3lame',
                '-ab', '192k',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return output_path
        except:
            pass
        return None

    def suggest_best_segment(self, file_path, duration=30, artist=None, title=None):
        """Умный выбор лучшего отрезка с информацией о треке"""
        try:
            return self.ai_analyzer.suggest_best_segment(file_path, duration, artist, title)
        except:
            return 45.0

    # В process_track_complete передаем artist и title в AI анализатор
    def process_track_complete(self, track_data, clip_path=None):
        try:
            track_id = self._generate_track_id(track_data['artist'], track_data['title'])
            
            # Получаем умный отрезок с информацией о треке
            smart_start = self.suggest_best_segment(
                track_data['file_path'], 
                track_data.get('segment_duration', 30),
                track_data.get('artist'),
                track_data.get('title')
            )
            
            if not clip_path:
                clip_path = self.extract_segment(
                    track_data['file_path'],
                    smart_start,  # Используем умное начало
                    track_data.get('segment_duration', 30)
                )
            
            complete_track_data = {
                **track_data,
                'id': track_id,
                'clip_path': clip_path,
                'segment_start': smart_start,  # Сохраняем умное начало
                'segment_duration': track_data.get('segment_duration', 30),
                'created_at': self._get_current_time()
            }
            
            self._save_track_json(complete_track_data, track_id)
            logger.info(f"✅ Трек обработан с умным отрезком: {smart_start:.1f}с")
            return complete_track_data
        except Exception as e:
            logger.error(f"❌ Ошибка обработки трека: {e}")
            return track_data

    def _generate_track_id(self, artist, title):
        unique_string = f"{artist}_{title}_{datetime.now().timestamp()}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:8]

    def _get_current_time(self):
        return datetime.now().isoformat()

    def _save_track_json(self, track_data, track_id):
        try:
            json_filename = f"{track_id}.json"
            json_path = os.path.join(self.BASE_DIR, "tracks_data", json_filename)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(track_data, f, ensure_ascii=False, indent=2, default=str)
        except:
            pass

    # Остальные методы без изменений...
    def get_all_tracks_data(self):
        try:
            tracks_data_dir = os.path.join(self.BASE_DIR, "tracks_data")
            if not os.path.exists(tracks_data_dir):
                return []
            
            all_tracks = []
            for json_file in Path(tracks_data_dir).glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        track_data = json.load(f)
                    all_tracks.append(track_data)
                except:
                    continue
            return all_tracks
        except:
            return []

    def play_segment_thread(self, file_path, start_time, duration=30):
        try:
            temp_segment = self.extract_segment(file_path, start_time, duration)
            if temp_segment and os.path.exists(temp_segment):
                if os.name == 'nt':
                    os.system(f'start wmplayer "{temp_segment}"')
                elif os.name == 'posix':
                    if os.uname().sysname == 'Darwin':
                        os.system(f'afplay "{temp_segment}"')
                    else:
                        os.system(f'xdg-open "{temp_segment}"')
                
                time.sleep(duration + 2)
                if os.path.exists(temp_segment):
                    os.remove(temp_segment)
                return True
        except:
            pass
        return False

    def play_segment(self, file_path, start_time, duration=30):
        self.stop_playback()
        self.playback_thread = threading.Thread(
            target=self.play_segment_thread,
            args=(file_path, start_time, duration)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()
        return True

    def stop_playback(self):
        self.stop_playback_flag = True
        try:
            if os.name == 'nt':
                os.system('taskkill /f /im wmplayer.exe 2>nul')
            else:
                os.system('pkill -f "afplay\|xdg-open" 2>/dev/null')
        except:
            pass

    def generate_waveform(self, file_path, width=1200, height=120):
        try:
            waveform_svg = '''<svg width="1200" height="120" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#f8fafc"/>
                <path d="M0,60 C150,30 300,90 450,60 C600,30 750,90 900,60 C1050,30 1200,90 1200,60" 
                      stroke="#3b82f6" stroke-width="3" fill="none"/>
            </svg>'''
            return f"data:image/svg+xml;base64,{base64.b64encode(waveform_svg.encode()).decode()}"
        except:
            return None

# Глобальный экземпляр
audio_editor = AudioEditor()