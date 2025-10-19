import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pydub import AudioSegment
import io
import os
import base64
import threading
import time
import json
import requests
import logging
from datetime import datetime
import hashlib
from pathlib import Path
import mutagen
from PIL import Image
import tempfile
import librosa
from scipy import signal

logger = logging.getLogger(__name__)

class AudioEditor:
    def __init__(self):
        self.current_playing = None
        self.playback_thread = None
        self.stop_playback_flag = False
        
        # Определяем базовую директорию
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Создаём необходимые папки при инициализации
        self._create_directories()
        
    def _create_directories(self):
        """Создает все необходимые папки"""
        folders = ["temp", "output", "images", "covers", "tracks_data"]
        for folder in folders:
            folder_path = os.path.join(self.BASE_DIR, folder)
            os.makedirs(folder_path, exist_ok=True)
            logger.info(f"📁 Создана папка: {folder_path}")

    def _get_full_path(self, relative_path):
        """Возвращает полный путь с учетом BASE_DIR"""
        return os.path.join(self.BASE_DIR, relative_path)

    def load_audio(self, file_path):
        """Загрузка аудиофайла"""
        try:
            audio = AudioSegment.from_file(file_path)
            return audio
        except Exception as e:
            logger.error(f"Ошибка загрузки аудио: {e}")
            return None

    def get_audio_duration(self, file_path):
        """Получение длительности аудио"""
        try:
            audio = AudioSegment.from_file(file_path)
            return len(audio) / 1000.0  # в секундах
        except Exception as e:
            logger.error(f"Ошибка получения длительности: {e}")
            return 0

    def extract_segment(self, file_path, start_time, duration=30, output_path=None):
        """Извлечение отрезка для временного использования (предпросмотр/презентация)"""
        try:
            logger.info(f"🎵 Создание временного отрывка: {file_path} с {start_time}с")
            
            audio = AudioSegment.from_file(file_path)
            
            # Проверяем длительность
            total_duration = len(audio) / 1000.0
            if total_duration < duration:
                logger.warning(f"⚠️ Трек короче {duration} секунд, используем весь")
                segment = audio
            else:
                # Обрезаем отрезок
                start_ms = int(start_time * 1000)
                end_ms = int((start_time + duration) * 1000)
                segment = audio[start_ms:end_ms]
            
            if not output_path:
                # Создаем уникальное имя для временного отрывка
                track_id = hashlib.md5(f"{file_path}_{start_time}".encode()).hexdigest()[:8]
                output_path = self._get_full_path(f"temp/segment_{track_id}.mp3")
            
            # Создаем папку temp если не существует
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Экспортируем отрезок
            segment.export(output_path, format="mp3", bitrate="192k")
            logger.info(f"✅ Временный отрывок создан: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания временного отрывка: {e}")
            return None

    def _analyze_audio_energy(self, file_path):
        """Анализ энергии аудио для поиска лучшего отрезка"""
        try:
            # Загружаем аудио с помощью librosa
            y, sr = librosa.load(file_path, sr=None)
            
            # Вычисляем энергию (RMS)
            frame_length = 2048
            hop_length = 512
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            
            # Нормализуем энергию
            rms_normalized = (rms - np.min(rms)) / (np.max(rms) - np.min(rms))
            
            # Разбиваем на сегменты по 30 секунд
            segment_duration = 30
            frames_per_segment = int(segment_duration * sr / hop_length)
            
            # Вычисляем среднюю энергию для каждого сегмента
            segment_energies = []
            for i in range(0, len(rms_normalized), frames_per_segment):
                segment = rms_normalized[i:i + frames_per_segment]
                if len(segment) > 0:
                    segment_energies.append(np.mean(segment))
            
            # Находим сегмент с максимальной энергией
            if segment_energies:
                best_segment_idx = np.argmax(segment_energies)
                best_start_time = best_segment_idx * segment_duration
                
                # Проверяем, что отрезок не выходит за пределы трека
                total_duration = len(y) / sr
                if best_start_time + segment_duration > total_duration:
                    best_start_time = max(0, total_duration - segment_duration)
                
                logger.info(f"🎯 Найден лучший отрезок: {best_start_time}с (энергия: {segment_energies[best_segment_idx]:.3f})")
                return best_start_time
            
            return 30.0  # fallback
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка анализа энергии: {e}, используем fallback")
            return 30.0

    def _analyze_audio_complexity(self, file_path):
        """Анализ сложности/вариативности аудио"""
        try:
            y, sr = librosa.load(file_path, sr=None)
            
            # Вычисляем спектральный центроид (сложность тембра)
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            
            # Вычисляем zero-crossing rate (ритмическая сложность)
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            
            # Комбинируем метрики
            complexity = (spectral_centroids / np.max(spectral_centroids) + 
                         zcr / np.max(zcr)) / 2
            
            segment_duration = 30
            frames_per_segment = int(segment_duration * sr / 512)  # примерный hop_length
            
            segment_complexities = []
            for i in range(0, len(complexity), frames_per_segment):
                segment = complexity[i:i + frames_per_segment]
                if len(segment) > 0:
                    segment_complexities.append(np.mean(segment))
            
            if segment_complexities:
                best_segment_idx = np.argmax(segment_complexities)
                best_start_time = best_segment_idx * segment_duration
                
                total_duration = len(y) / sr
                if best_start_time + segment_duration > total_duration:
                    best_start_time = max(0, total_duration - segment_duration)
                
                logger.info(f"🎵 Найден сложный отрезок: {best_start_time}с")
                return best_start_time
            
            return 45.0  # fallback к середине
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка анализа сложности: {e}")
            return 45.0

    def suggest_best_segment(self, file_path, duration=30):
        """Умный выбор лучшего отрезка с комбинированным анализом"""
        try:
            audio = AudioSegment.from_file(file_path)
            total_duration = len(audio) / 1000.0
            
            if total_duration <= duration:
                logger.info("🎵 Трек короче 30 секунд, используем начало")
                return 0
            
            # Комбинированный анализ: энергия + сложность
            energy_start = self._analyze_audio_energy(file_path)
            complexity_start = self._analyze_audio_complexity(file_path)
            
            # Взвешенное среднее (больше веса энергии)
            best_start = (energy_start * 0.7 + complexity_start * 0.3)
            
            # Ограничиваем пределы трека
            best_start = max(0, min(best_start, total_duration - duration))
            
            # Округляем до целых секунд
            best_start = int(best_start)
            
            logger.info(f"🎯 Умный анализ: энергия={energy_start}с, сложность={complexity_start}с, итог={best_start}с")
            
            return float(best_start)
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа аудио: {e}")
            # Fallback: возвращаем 30 секунд от начала
            return 30.0

    def process_track_complete(self, track_data, clip_path=None):
        """Полная обработка трека: JSON + фото + отрывок"""
        try:
            logger.info(f"🎵 Полная обработка трека: {track_data['artist']} - {track_data['title']}")
            
            # Генерируем ID трека
            track_id = self._generate_track_id(track_data['artist'], track_data['title'])
            
            # 1. Создаем отрывок если не передан (только для демо)
            if not clip_path:
                clip_path = self.extract_segment(
                    track_data['file_path'],
                    track_data.get('segment_start', 0),
                    track_data.get('segment_duration', 30)
                )
            
            # 2. Ищем фото исполнителя
            image_path = self._download_artist_image(track_data['artist'], track_id)
            
            # 3. Извлекаем обложку из аудиофайла
            cover_path = self._extract_cover_from_audio(track_data['file_path'], track_id)
            
            # 4. Обновляем track_data
            complete_track_data = {
                **track_data,
                'id': track_id,
                'image_path': image_path,
                'clip_path': clip_path,
                'cover_path': cover_path,
                'segment_start': track_data.get('segment_start', 0),
                'segment_duration': track_data.get('segment_duration', 30),
                'created_at': self._get_current_time()
            }
            
            # 5. Сохраняем в JSON
            self._save_track_json(complete_track_data, track_id)
            
            logger.info(f"✅ Трек полностью обработан: {track_id}")
            logger.info(f"   📁 Временный отрывок: {clip_path}")
            logger.info(f"   🖼️ Фото: {image_path}")
            logger.info(f"   🎨 Обложка: {cover_path}")
            
            return complete_track_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка полной обработки трека: {e}")
            return track_data

    def _download_artist_image(self, artist, track_id):
        """Скачивает изображение артиста - УПРОЩЕННАЯ ВЕРСИЯ"""
        try:
            from image_search import image_searcher
            return image_searcher.search_and_download_artist_image(artist, track_id)
        except ImportError:
            logger.warning("⚠️ ImageSearch не доступен, создаем placeholder")
            return self._create_placeholder_image(artist, track_id)
        except Exception as e:
            logger.error(f"❌ Ошибка создания изображения: {e}")
            return None

    def _create_placeholder_image(self, artist, track_id):
        """Создает placeholder изображение с именем артиста"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Создаем изображение
            width, height = 400, 400
            image = Image.new('RGB', (width, height), color=(73, 109, 137))
            draw = ImageDraw.Draw(image)
            
            # Пробуем использовать шрифт (если доступен)
            try:
                font = ImageFont.truetype("arial.ttf", 40)
            except:
                font = ImageFont.load_default()
            
            # Рисуем текст
            text = artist[:15] + "..." if len(artist) > 15 else artist
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (width - text_width) / 2
            y = (height - text_height) / 2
            
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
            
            # Сохраняем
            image_path = self._get_full_path(f"images/{track_id}_artist.jpg")
            image.save(image_path, "JPEG")
            
            return image_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания placeholder: {e}")
            return None

    def _extract_cover_from_audio(self, file_path, track_id):
        """Извлекает обложку из аудиофайла"""
        try:
            audio = mutagen.File(file_path)
            
            if audio and hasattr(audio, 'tags'):
                # Ищем обложку в разных тегах
                cover_tags = ['APIC:', 'covr', 'metadata_block_picture']
                
                for tag in cover_tags:
                    if tag in audio.tags:
                        cover_data = audio.tags[tag].data
                        
                        # Сохраняем обложку
                        cover_path = self._get_full_path(f"covers/{track_id}_cover.jpg")
                        with open(cover_path, 'wb') as f:
                            f.write(cover_data)
                        
                        logger.info(f"✅ Обложка извлечена: {cover_path}")
                        return cover_path
            
            logger.info("ℹ️ Обложка не найдена в аудиофайле")
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось извлечь обложку: {e}")
            return None

    def _generate_track_id(self, artist, title):
        """Генерирует уникальный ID для трека"""
        unique_string = f"{artist}_{title}_{datetime.now().timestamp()}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:8]

    def _get_current_time(self):
        """Возвращает текущее время в ISO формате"""
        return datetime.now().isoformat()

    def _save_track_json(self, track_data, track_id):
        """Сохраняет данные трека в JSON файл"""
        try:
            json_filename = f"{track_id}.json"
            json_path = self._get_full_path(f"tracks_data/{json_filename}")
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(track_data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"✅ JSON сохранен: {json_path}")
            
            # Также сохраняем в общий файл со всеми треками
            self._update_tracks_index(track_data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения JSON: {e}")

    def _update_tracks_index(self, track_data):
        """Обновляет общий индекс всех треков"""
        try:
            index_path = self._get_full_path("tracks_data/tracks_index.json")
            
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    index = json.load(f)
            else:
                index = []
            
            # Добавляем или обновляем трек в индексе
            existing_track = None
            for i, track in enumerate(index):
                if track.get('id') == track_data['id']:
                    existing_track = i
                    break
            
            if existing_track is not None:
                index[existing_track] = track_data
            else:
                index.append(track_data)
            
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"✅ Индекс треков обновлен: {len(index)} треков")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления индекса: {e}")

    def get_all_tracks_data(self):
        """Возвращает данные всех обработанных треков"""
        try:
            index_path = self._get_full_path("tracks_data/tracks_index.json")
            
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных треков: {e}")
            return []

    # Воспроизведение для предпросмотра
    def play_segment_thread(self, file_path, start_time, duration=30):
        """Воспроизведение отрезка в отдельном потоке"""
        try:
            # Создаем временный отрезок для воспроизведения
            temp_segment = self.extract_segment(file_path, start_time, duration)
            
            if temp_segment and os.path.exists(temp_segment):
                # Воспроизведение через системный плеер
                if os.name == 'nt':  # Windows
                    os.system(f'start wmplayer "{temp_segment}"')
                elif os.name == 'posix':  # macOS/Linux
                    if os.uname().sysname == 'Darwin':  # macOS
                        os.system(f'afplay "{temp_segment}"')
                    else:  # Linux
                        os.system(f'xdg-open "{temp_segment}"')
                
                # Удаляем временный файл после использования
                time.sleep(duration + 2)  # Ждем завершения воспроизведения
                if os.path.exists(temp_segment):
                    os.remove(temp_segment)
                
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
            return False

    def play_segment(self, file_path, start_time, duration=30):
        """Запуск воспроизведения в отдельном потоке"""
        self.stop_playback()
        self.playback_thread = threading.Thread(
            target=self.play_segment_thread,
            args=(file_path, start_time, duration)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()
        return True

    def stop_playback(self):
        """Остановка воспроизведения"""
        self.stop_playback_flag = True

    def generate_waveform(self, file_path, width=1200, height=120):
        """Генерация waveform изображения"""
        try:
            audio = AudioSegment.from_file(file_path)
            if audio.channels == 2:
                samples = np.array(audio.get_array_of_samples())
                samples = samples.reshape((-1, 2))
                samples = samples.mean(axis=1)
            else:
                samples = np.array(audio.get_array_of_samples())
            
            if len(samples) > 0:
                samples = samples.astype(np.float32)
                samples = samples / np.max(np.abs(samples))
            
            target_points = min(width, len(samples))
            if len(samples) > target_points:
                step = len(samples) // target_points
                samples = samples[::step]
            
            fig = plt.figure(figsize=(width/100, height/100), dpi=100, 
                           facecolor='white', edgecolor='white')
            ax = fig.add_subplot(111)
            ax.set_facecolor('white')
            
            plt.plot(samples, color='#2563eb', linewidth=2.0)
            plt.fill_between(range(len(samples)), samples, color='#2563eb', alpha=0.4)
            plt.axis('off')
            plt.margins(0)
            plt.tight_layout(pad=0)
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', pad_inches=0, 
                       facecolor='white', edgecolor='white')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return f"data:image/png;base64,{image_base64}"
        except Exception as e:
            logger.error(f"Ошибка генерации waveform: {e}")
            return None

# Глобальный экземпляр редактора
audio_editor = AudioEditor()