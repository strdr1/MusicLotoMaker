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
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
    def suggest_best_segment(self, file_path: str, duration: int = 30) -> float:
        """Анализирует аудио через AI и возвращает лучший стартовый момент"""
        try:
            if not self.api_key:
                logger.warning("⚠️ OPENROUTER_API_KEY не установлен, используем fallback")
                return self._fallback_analysis(file_path, duration)
            
            # Получаем информацию о треке
            track_info = self._get_audio_info(file_path)
            if not track_info:
                return 30.0
            
            # Создаем промпт для AI
            prompt = self._create_analysis_prompt(track_info, duration)
            
            # Отправляем запрос к AI
            best_start = self._query_ai(prompt, track_info, duration)
            
            if best_start is not None:
                logger.info(f"🎯 AI предложил отрезок: {best_start}с")
                return best_start
            else:
                return self._fallback_analysis(file_path, duration)
                
        except Exception as e:
            logger.error(f"❌ AI анализ failed: {e}")
            return self._fallback_analysis(file_path, duration)
    
    def _get_audio_info(self, file_path: str) -> dict:
        """Получает базовую информацию об аудиофайле"""
        try:
            # Длительность через ffprobe
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            total_duration = float(result.stdout.strip())
            
            return {
                'total_duration': total_duration,
                'filename': os.path.basename(file_path)
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об аудио: {e}")
            return None
    
    def _create_analysis_prompt(self, track_info: dict, duration: int) -> str:
        """Создает промпт для AI анализа"""
        total_duration = track_info['total_duration']
        
        prompt = f"""Проанализируй музыкальный трек и определи лучший начальный момент для отрезка длиной {duration} секунд.

Общая длительность: {total_duration:.1f} секунд
Длина нужного отрезка: {duration} секунд

Требования к отрезку:
1. Должен быть музыкально интересным и запоминающимся
2. Должен содержать основную мелодию или вокал
3. Не должен начинаться с тишины или монотонного вступления
4. Должен хорошо представлять трек

Верни ТОЛЬКО число - начальную секунду в формате float.

Правила:
- Отрезок должен полностью помещаться в трек
- Максимальное время: {total_duration - duration:.1f} секунд
- Минимальное время: 0 секунд

Верни только число:"""
        
        return prompt
    
    def _query_ai(self, prompt: str, track_info: dict, duration: int) -> float:
        """Отправляет запрос к OpenRouter AI"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://music-loto-maker.com",
                "X-Title": "Music Loto Maker"
            }
            
            data = {
                "model": "deepseek/deepseek-chat:free",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 50,
                "temperature": 0.3
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            ai_response = result['choices'][0]['message']['content'].strip()
            
            # Парсим ответ AI
            best_start = self._parse_ai_response(ai_response, track_info, duration)
            return best_start
            
        except Exception as e:
            logger.error(f"❌ Ошибка запроса к AI: {e}")
            return None
    
    def _parse_ai_response(self, ai_response: str, track_info: dict, duration: int) -> float:
        """Парсит ответ AI и валидирует результат"""
        try:
            # Ищем число в ответе
            import re
            numbers = re.findall(r'\d+\.?\d*', ai_response)
            if not numbers:
                return None
            
            best_start = float(numbers[0])
            total_duration = track_info['total_duration']
            
            # Валидация результата
            if 0 <= best_start <= (total_duration - duration):
                return best_start
            else:
                logger.warning(f"⚠️ AI вернул невалидное время: {best_start}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга ответа AI: {e}")
            return None
    
    def _fallback_analysis(self, file_path: str, duration: int) -> float:
        """Fallback анализ когда AI недоступен"""
        try:
            track_info = self._get_audio_info(file_path)
            if not track_info:
                return 30.0
            
            total_duration = track_info['total_duration']
            
            # Простая эвристика: 25% от длительности, но не менее 30с
            suggested = min(max(30.0, total_duration * 0.25), 120.0)
            suggested = min(suggested, total_duration - duration)
            
            logger.info(f"🎵 Fallback анализ: {suggested}с")
            return suggested
            
        except Exception as e:
            logger.error(f"❌ Fallback анализ failed: {e}")
            return 30.0

class AudioEditor:
    def __init__(self):
        self.current_playing = None
        self.playback_thread = None
        self.stop_playback_flag = False
        
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._create_directories()
        
        # Инициализируем AI анализатор
        self.ai_analyzer = AIAudioAnalyzer()

    def _create_directories(self):
        """Создает необходимые папки"""
        folders = ["temp", "output", "images", "covers", "tracks_data"]
        for folder in folders:
            folder_path = os.path.join(self.BASE_DIR, folder)
            os.makedirs(folder_path, exist_ok=True)
            logger.info(f"📁 Создана папка: {folder_path}")

    def load_audio(self, file_path):
        """Загрузка аудиофайла"""
        try:
            duration = self.get_audio_duration(file_path)
            return {"duration": duration, "file_path": file_path}
        except Exception as e:
            logger.error(f"Ошибка загрузки аудио: {e}")
            return None

    def get_audio_duration(self, file_path):
        """Получение длительности аудио"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            duration = float(result.stdout.strip())
            logger.info(f"⏱️ Длительность аудио: {duration} сек")
            return duration
        except Exception as e:
            logger.error(f"Ошибка получения длительности: {e}")
            return 0

    def extract_segment(self, file_path, start_time, duration=30, output_path=None):
        """Извлечение отрезка"""
        try:
            logger.info(f"🎵 Создание временного отрывка: {file_path} с {start_time}с")
            
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
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"✅ Временный отрывок создан: {output_path}")
                return output_path
            else:
                logger.error(f"❌ Ошибка ffmpeg: {result.stderr}")
                return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания временного отрывка: {e}")
            return None

    def suggest_best_segment(self, file_path, duration=30):
        """Умный выбор лучшего отрезка через AI"""
        try:
            # Используем AI анализатор вместо старой логики
            return self.ai_analyzer.suggest_best_segment(file_path, duration)
            
        except Exception as e:
            logger.error(f"❌ Ошибка AI анализа аудио: {e}")
            return 30.0

    # Старые методы оставляем для совместимости
    def _analyze_audio_energy(self, file_path):
        """Анализ энергии аудио (для совместимости)"""
        return 30.0

    def _analyze_audio_complexity(self, file_path):
        """Анализ сложности аудио (для совместимости)"""
        return 45.0

    def process_track_complete(self, track_data, clip_path=None):
        """Полная обработка трека"""
        try:
            logger.info(f"🎵 Полная обработка трека: {track_data['artist']} - {track_data['title']}")
            
            track_id = self._generate_track_id(track_data['artist'], track_data['title'])
            
            if not clip_path:
                clip_path = self.extract_segment(
                    track_data['file_path'],
                    track_data.get('segment_start', 0),
                    track_data.get('segment_duration', 30)
                )
            
            complete_track_data = {
                **track_data,
                'id': track_id,
                'clip_path': clip_path,
                'segment_start': track_data.get('segment_start', 0),
                'segment_duration': track_data.get('segment_duration', 30),
                'created_at': self._get_current_time()
            }
            
            self._save_track_json(complete_track_data, track_id)
            
            logger.info(f"✅ Трек полностью обработан: {track_id}")
            return complete_track_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка полной обработки трека: {e}")
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
            
            logger.info(f"✅ JSON сохранен: {json_path}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения JSON: {e}")

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
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки {json_file}: {e}")
            
            return all_tracks
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных треков: {e}")
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
            return False
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
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
            # Создаем простой SVG waveform
            waveform_svg = self._create_simple_waveform()
            return f"data:image/svg+xml;base64,{base64.b64encode(waveform_svg.encode()).decode()}"
        except Exception as e:
            logger.error(f"Ошибка генерации waveform: {e}")
            return None

    def _create_simple_waveform(self):
        return '''<svg width="1200" height="120" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#f8fafc"/>
            <path d="M0,60 C150,30 300,90 450,60 C600,30 750,90 900,60 C1050,30 1200,90 1200,60" 
                  stroke="#3b82f6" stroke-width="3" fill="none"/>
            <path d="M0,60 C150,90 300,30 450,60 C600,90 750,30 900,60 C1050,90 1200,30 1200,60" 
                  stroke="#60a5fa" stroke-width="2" fill="none" opacity="0.7"/>
        </svg>'''

# Глобальный экземпляр
audio_editor = AudioEditor()