# audio_editor.py
import os
import io
import base64
import threading
import time
import json
import hashlib
import logging
import subprocess
import tempfile
import math
import struct
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioPeakAnalyzer:
    """Анализатор пиков громкости в аудио — ультра-умная, но лёгкая версия.

    Идея:
    - Используем ffmpeg, чтобы стримить аудио в PCM (моно, пониженая частота),
      затем в чистом Python считаем RMS за окна (0.5 — 1.0 с).
    - Считаем не только простое RMS, но и скорость роста энергии (прыжки),
      локальную контрастность (peak / local_mean) и позиционную приоритизацию
      (чтобы предпочесть припевы, которые часто ближе к середине/второй трети).
    - Нет numpy/ scipy — только stdlib и ffmpeg.
    """

    def __init__(self, sample_rate=22050, channels=1, window_sec=0.5, read_sec=0.5, position_bias=0.2):
        """
        :param sample_rate: частота для анализа (пониженная для скорости)
        :param channels: 1 (моно)
        :param window_sec: размер окна для RMS в секундах (0.25-1.0)
        :param read_sec: сколько секунд данных читать за один блок из ffmpeg
        :param position_bias: как сильно смещать в сторону более поздних частей трека (0..1)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.window_sec = window_sec
        self.read_sec = read_sec
        self.position_bias = max(0.0, min(position_bias, 1.0))
        logger.info("🎵 Инициализирован улучшенный анализатор пиков (PCM streaming RMS)")

    def find_loudest_segment_start(self, file_path: str, duration: int = 30, lead_in: int = 5) -> float:
        """Находит стартовую точку за lead_in секунд до самого "звучного" момента."""
        try:
            if not os.path.exists(file_path):
                logger.warning("⚠️ Файл не найден, возврат дефолтного значения 45s")
                return 45.0

            total_duration = self._get_audio_duration(file_path)
            if total_duration <= duration:
                return 0.0

            loudest_time = self._analyze_rms_volume_stream(file_path, total_duration)
            suggested_start = max(0.0, loudest_time - lead_in)

            max_possible = max(0.0, total_duration - duration)
            if suggested_start > max_possible:
                suggested_start = max(0.0, max_possible - 2.0)

            logger.info(f"🔊 Самый 'энергичный' момент: {loudest_time:.2f}s, предлагаемый старт: {suggested_start:.2f}s")
            return suggested_start

        except Exception as e:
            logger.exception(f"❌ Анализ громкости failed: {e}")
            return self._smart_fallback(file_path, duration)

    def _get_audio_duration(self, file_path: str) -> float:
        """Получает длительность аудио через ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.debug(f"_get_audio_duration error: {e}")
        return 0.0

    def _analyze_rms_volume_stream(self, file_path: str, total_duration: float) -> float:
        """
        Стримовый анализ: запрашиваем из ffmpeg PCM и считаем RMS в окнах.
        Возвращаем центр окна с наибольшим скорректированным score.
        """
        # Параметры
        sr = int(self.sample_rate)
        window_samples = int(self.window_sec * sr)
        read_samples = int(self.read_sec * sr)
        bytes_per_sample = 2  # pcm_s16le -> 2 bytes per sample
        block_bytes = read_samples * bytes_per_sample * self.channels

        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-i', file_path,
            '-f', 's16le',
            '-acodec', 'pcm_s16le',
            '-ac', str(self.channels),
            '-ar', str(sr),
            '-'
        ]

        try:
            p = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            logger.error(f"❌ Не удалось запустить ffmpeg для стрима: {e}")
            return self._improved_heuristic(total_duration)

        rms_windows = []     # список rms по окнам
        window_positions = []  # позиции окон в секундах (центр окна)
        rolling_buffer = bytearray()

        bytes_read = 0
        samples_processed = 0
        read_iter = 0
        eof = False

        try:
            # Читаем поток по блокам
            while True:
                chunk = p.stdout.read(block_bytes)
                if not chunk:
                    eof = True
                rolling_buffer += chunk
                bytes_read += len(chunk)

                # Обрабатываем окна из rolling_buffer, пока хватает данных на окно
                while len(rolling_buffer) >= window_samples * bytes_per_sample * self.channels:
                    # Вычисляем RMS для текущего окна (берём первые window_samples)
                    window_bytes = rolling_buffer[:window_samples * bytes_per_sample * self.channels]
                    # Убираем использованные байты (движущийся скользящий)
                    # Чтобы учесть перекрытие между окнами — можно сдвигать на половину окна,
                    # но для простоты используем скользящий шаг window_samples (без overlap).
                    del rolling_buffer[:window_samples * bytes_per_sample * self.channels]

                    # Считаем RMS
                    rms = self._rms_from_pcm16(window_bytes)
                    # Центр окна в секундах
                    center_sample_index = samples_processed + (window_samples // 2)
                    center_time = center_sample_index / sr
                    rms_windows.append(rms)
                    window_positions.append(center_time)
                    samples_processed += window_samples

                read_iter += 1
                # safety: если eof и buffer не содержит полноценного окна — выходим
                if eof:
                    break

            # Дождёмся завершения процесса
            p.stdout.close()
            p.wait(timeout=5)

        except Exception as e:
            logger.debug(f"stream read exception: {e}")
            try:
                p.kill()
            except:
                pass

        # Если не получили данных — fallback
        if not rms_windows:
            logger.warning("⚠️ Не получилось получить RMS окна — используем эвристику")
            return self._improved_heuristic(total_duration)

        # Нормализуем RMS (0..1)
        max_rms = max(rms_windows) if rms_windows else 1.0
        norm_rms = [r / max_rms for r in rms_windows]

        # Вычисляем скорость роста энергии (delta) — предпочитаем места с резким подъёмом
        deltas = [0.0]
        for i in range(1, len(norm_rms)):
            deltas.append(max(0.0, norm_rms[i] - norm_rms[i - 1]))

        # Локальная контрастность: отношение rms к среднему в окне +/- k
        contrast = []
        k = 3  # окна вокруг
        for i in range(len(norm_rms)):
            lo = max(0, i - k)
            hi = min(len(norm_rms), i + k + 1)
            local_mean = sum(norm_rms[lo:hi]) / (hi - lo)
            if local_mean <= 0:
                contrast.append(norm_rms[i])
            else:
                contrast.append(norm_rms[i] / (local_mean + 1e-9))

        # Финальная скоринговая функция — сочетание rms, delta, contrast и position bias
        scores = []
        for i in range(len(norm_rms)):
            pos_frac = (window_positions[i] / max(1.0, total_duration))
            # позиционный множитель: небольшое предпочтение центральной/второй трети
            # мы сдвигаем позицию/вес так, чтобы припевы (обычно 30-70%) чуть выигрывали
            pos_weight = 1.0 + self.position_bias * (0.5 - abs(0.5 - pos_frac)) * 2.0
            score = (
                0.5 * norm_rms[i] +        # основная громкость
                0.3 * deltas[i] +         # резкий подъём энергии
                0.2 * contrast[i]        # локальная контрастность
            ) * pos_weight
            scores.append(score)

        # Найдём индекс с максимальным score
        best_idx = max(range(len(scores)), key=lambda x: scores[x])
        best_time = window_positions[best_idx]

        # Смягчение/коррекции:
        # Если лучший момент получился очень близко к началу или концу — слегка сдвинем в сторону внутри трека
        if best_time < 5.0:
            best_time = min(best_time + 3.0, total_duration - 10)
        if best_time > total_duration - 5.0:
            best_time = max(total_duration - 10.0, best_time - 3.0)

        # Дополнительная эвристика: если трек очень короткий, взять середину
        if total_duration <= 60:
            return max(0.0, total_duration * 0.45)

        return float(max(0.0, min(best_time, total_duration)))

    def _rms_from_pcm16(self, pcm_bytes: bytes) -> float:
        """Вычисляет RMS из блока PCM s16le."""
        # Количество сэмплов
        n = len(pcm_bytes) // 2
        if n == 0:
            return 0.0
        # '<h' little-endian signed short
        fmt = '<' + 'h' * n
        try:
            samples = struct.unpack(fmt, pcm_bytes)
        except struct.error:
            # fallback: более безопасное чтение по шагам
            samples = []
            for i in range(0, len(pcm_bytes), 2):
                if i + 1 < len(pcm_bytes):
                    samples.append(struct.unpack('<h', pcm_bytes[i:i+2])[0])

        # Вычисление RMS
        s = 0.0
        for v in samples:
            s += (v / 32768.0) ** 2
        mean_sq = s / max(1, len(samples))
        return math.sqrt(mean_sq)

    def _improved_heuristic(self, total_duration: float) -> float:
        """Улучшенная эвристика для определения лучшего момента (быстрый fallback)."""
        # Эмпирические правила:
        if total_duration <= 120:  # до 2 минут
            return total_duration * 0.45
        elif total_duration <= 240:  # 2-4 минуты
            return total_duration * 0.40
        else:
            return total_duration * 0.35

    def _smart_fallback(self, file_path: str, duration: int) -> float:
        """Умный фолбек использует длительность и простые правила."""
        try:
            total_duration = self._get_audio_duration(file_path)
            if total_duration == 0:
                return 45.0

            suggested = self._improved_heuristic(total_duration)
            suggested = max(10, min(suggested, total_duration - max(5, duration)))
            max_possible = total_duration - duration
            if suggested > max_possible:
                suggested = max(0, max_possible - 2)

            logger.info(f"🎵 Умный фолбек: {suggested:.1f}s")
            return suggested
        except Exception as e:
            logger.error(f"❌ Фолбек failed: {e}")
            return 45.0


class AudioEditor:
    def __init__(self):
        self.current_playing = None
        self.playback_thread = None
        self.stop_playback_flag = False

        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._create_directories()

        # Инициализируем анализатор громкости (можно настроить параметры)
        self.peak_analyzer = AudioPeakAnalyzer(sample_rate=22050, window_sec=0.6, read_sec=1.0, position_bias=0.18)
        logger.info("🎵 AudioEditor с улучшенным анализом пиков громкости")

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
                logger.error(f"❌ Файл не существует: {file_path}")
                return None

            duration = self.get_audio_duration(file_path)
            if duration == 0:
                logger.error(f"❌ Не удалось получить длительность: {file_path}")
                return None

            logger.info(f"✅ Аудио загружено: {file_path}, длительность: {duration:.1f}с")
            return {"duration": duration, "file_path": file_path}

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки аудио: {e}")
            return None

    def get_audio_duration(self, file_path):
        """Получение длительности аудио"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                logger.info(f"📊 Длительность аудио: {duration:.1f}с")
                return duration
        except Exception as e:
            logger.error(f"❌ Ошибка получения длительности: {e}")
        return 0

    def extract_segment(self, file_path, start_time, duration=30, output_path=None):
        """Извлечение отрезка с улучшенными параметрами"""
        try:
            if not output_path:
                track_id = hashlib.md5(f"{file_path}_{start_time}".encode()).hexdigest()[:8]
                output_path = os.path.join(self.BASE_DIR, "temp", f"segment_{track_id}.mp3")

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            cmd = [
                'ffmpeg', '-y',
                '-i', file_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'libmp3lame',
                '-q:a', '2',  # Качество
                '-ac', '2',   # Стерео
                '-ar', '44100',
                output_path
            ]

            logger.info(f"🎵 Извлекаем отрезок: {start_time}-{start_time + duration}с")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"✅ Отрезок сохранен: {output_path}")
                    return output_path
                else:
                    logger.error("❌ Создан пустой файл")
            else:
                logger.error(f"❌ Ошибка ffmpeg: {result.stderr}")

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения отрезка: {e}")
        return None

    def suggest_best_segment(self, file_path, duration=30, artist=None, title=None):
        """Находит лучший отрезок по пику громкости"""
        try:
            start_time = self.peak_analyzer.find_loudest_segment_start(file_path, duration, lead_in=5)
            logger.info(f"🎯 Предлагаемый старт: {start_time:.1f}с")
            return start_time
        except Exception as e:
            logger.error(f"❌ Ошибка анализа громкости: {e}")
            return 45.0

    def process_track_complete(self, track_data, clip_path=None):
        """Полная обработка трека с улучшенным логированием"""
        try:
            track_id = self._generate_track_id(track_data.get('artist', ''), track_data.get('title', ''))

            logger.info(f"🎵 Обрабатываем трек: {track_data.get('artist')} - {track_data.get('title')}")

            segment_duration = track_data.get('segment_duration', 30)
            smart_start = self.suggest_best_segment(track_data['file_path'], segment_duration)

            if not clip_path:
                clip_path = self.extract_segment(track_data['file_path'], smart_start, segment_duration)

            if not clip_path:
                logger.error("❌ Не удалось создать отрезок")
                return track_data

            complete_track_data = {
                **track_data,
                'id': track_id,
                'clip_path': clip_path,
                'segment_start': round(smart_start, 1),
                'segment_duration': segment_duration,
                'created_at': self._get_current_time(),
                'file_size': os.path.getsize(clip_path) if clip_path and os.path.exists(clip_path) else 0
            }

            self._save_track_json(complete_track_data, track_id)
            logger.info(f"✅ Трек успешно обработан: старт {smart_start:.1f}с, ID {track_id}")
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

            logger.info(f"💾 JSON сохранен: {json_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения JSON: {e}")

    def get_all_tracks_data(self):
        """Получение всех треков с улучшенной обработкой ошибок"""
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
                    continue

            logger.info(f"📁 Загружено треков: {len(all_tracks)}")
            return sorted(all_tracks, key=lambda x: x.get('created_at', ''), reverse=True)

        except Exception as e:
            logger.error(f"❌ Ошибка получения треков: {e}")
            return []

    def play_segment_thread(self, file_path, start_time, duration=30):
        """Воспроизведение отрезка в отдельном потоке"""
        try:
            logger.info(f"▶️ Воспроизведение: {start_time}-{start_time + duration}с")
            temp_segment = self.extract_segment(file_path, start_time, duration)
            if temp_segment and os.path.exists(temp_segment):
                if os.name == 'nt':
                    os.system(f'start wmplayer "{temp_segment}"')
                elif os.name == 'posix':
                    try:
                        if os.uname().sysname == 'Darwin':
                            os.system(f'afplay "{temp_segment}"')
                        else:
                            os.system(f'xdg-open "{temp_segment}"')
                    except Exception:
                        os.system(f'xdg-open "{temp_segment}"')

                # Ждем завершения воспроизведения
                time.sleep(duration + 2)

                # Удаляем временный файл
                try:
                    if os.path.exists(temp_segment):
                        os.remove(temp_segment)
                        logger.info("✅ Временный файл удален")
                except:
                    pass

                return True
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения: {e}")
        return False

    def play_segment(self, file_path, start_time, duration=30):
        """Запуск воспроизведения отрезка"""
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
        try:
            if os.name == 'nt':
                os.system('taskkill /f /im wmplayer.exe 2>nul')
            else:
                os.system('pkill -f "afplay\|xdg-open" 2>/dev/null')
            logger.info("⏹️ Воспроизведение остановлено")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки воспроизведения: {e}")

    def generate_waveform(self, file_path, width=1200, height=120):
        """Генерация waveform (упрощенная версия)"""
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
