# backend/audio_editor.py
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

class AudioEditor:
    def __init__(self):
        self.current_playing = None
        self.playback_thread = None
        self.stop_playback_flag = False
    
    def load_audio(self, file_path):
        """Загрузка аудиофайла"""
        try:
            audio = AudioSegment.from_file(file_path)
            return audio
        except Exception as e:
            print(f"Ошибка загрузки аудио: {e}")
            return None
    
    def get_audio_duration(self, file_path):
        """Получение длительности аудио"""
        try:
            audio = AudioSegment.from_file(file_path)
            return len(audio) / 1000.0  # в секундах
        except Exception as e:
            print(f"Ошибка получения длительности: {e}")
            return 0
    
    def play_segment_thread(self, file_path, start_time, duration=30):
        """Воспроизведение отрезка в отдельном потоке"""
        try:
            audio = AudioSegment.from_file(file_path)
            segment = audio[start_time*1000:(start_time + duration)*1000]
            
            # Экспортируем отрезок
            temp_path = f"temp/segment_{os.path.basename(file_path)}.mp3"
            segment.export(temp_path, format="mp3")
            
            # Используем системную команду для воспроизведения
            if os.name == 'nt':  # Windows
                os.system(f'start wmplayer "{temp_path}"')
            elif os.name == 'posix':  # macOS/Linux
                if os.uname().sysname == 'Darwin':  # macOS
                    os.system(f'afplay "{temp_path}"')
                else:  # Linux
                    os.system(f'xdg-open "{temp_path}"')
            
            return True
        except Exception as e:
            print(f"Ошибка воспроизведения: {e}")
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
    
    def extract_segment(self, file_path, start_time, duration=30, output_path=None):
        """Извлечение 30-секундного отрезка"""
        try:
            audio = AudioSegment.from_file(file_path)
            segment = audio[start_time*1000:(start_time + duration)*1000]
            
            if not output_path:
                output_path = f"output/segment_{os.path.basename(file_path)}.mp3"
            
            segment.export(output_path, format="mp3")
            return output_path
        except Exception as e:
            print(f"Ошибка извлечения отрезка: {e}")
            return None
    
    def generate_waveform(self, file_path, width=800, height=200):
        """Генерация waveform изображения"""
        try:
            # Загружаем аудио
            audio = AudioSegment.from_file(file_path)
            
            # Получаем семплы
            if audio.channels == 2:
                # Стерео - усредняем каналы
                samples = np.array(audio.get_array_of_samples())
                samples = samples.reshape((-1, 2))
                samples = samples.mean(axis=1)
            else:
                # Моно
                samples = np.array(audio.get_array_of_samples())
            
            # Нормализуем
            if len(samples) > 0:
                samples = samples.astype(np.float32)
                samples = samples / np.max(np.abs(samples))
            
            # Уменьшаем количество точек для производительности
            target_points = min(width, len(samples))
            if len(samples) > target_points:
                step = len(samples) // target_points
                samples = samples[::step]
            
            # Создаем график
            plt.figure(figsize=(width/100, height/100), dpi=100)
            plt.plot(samples, color='#2563eb', linewidth=1)
            plt.fill_between(range(len(samples)), samples, color='#2563eb', alpha=0.3)
            plt.axis('off')
            plt.margins(0)
            plt.tight_layout(pad=0)
            
            # Сохраняем в base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', pad_inches=0)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return f"data:image/png;base64,{image_base64}"
            
        except Exception as e:
            print(f"Ошибка генерации waveform: {e}")
            return None
    
    def suggest_best_segment(self, file_path, duration=30):
        """Умный выбор лучшего отрезка на основе анализа энергии и тембра"""
        try:
            audio = AudioSegment.from_file(file_path)
            total_duration = len(audio) / 1000.0
            
            if total_duration <= duration:
                return 0
            
            print(f"🔍 Анализируем аудио: {total_duration:.1f} секунд")
            
            # Конвертируем в numpy array для анализа
            samples = np.array(audio.get_array_of_samples())
            
            if audio.channels == 2:
                samples = samples.reshape((-1, 2))
                samples = samples.mean(axis=1)  # Стерео в моно
            
            # Нормализуем
            samples = samples.astype(np.float32)
            if len(samples) > 0:
                samples = samples / np.max(np.abs(samples))
            
            sample_rate = audio.frame_rate
            
            # Анализируем тремя способами
            best_candidates = []
            
            # 1. Анализ по энергии (RMS)
            energy_result = self._analyze_by_energy(samples, sample_rate, duration, total_duration)
            best_candidates.append(energy_result)
            
            # 2. Анализ по вариативности (ищем интересные части)
            variability_result = self._analyze_by_variability(samples, sample_rate, duration, total_duration)
            best_candidates.append(variability_result)
            
            # 3. Анализ по пиковым моментам
            peaks_result = self._analyze_by_peaks(samples, sample_rate, duration, total_duration)
            best_candidates.append(peaks_result)
            
            # Выбираем лучший кандидат
            best_candidate = max(best_candidates, key=lambda x: x['score'])
            best_start = best_candidate['start_time']
            
            # Проверяем границы
            best_start = max(0, min(best_start, total_duration - duration))
            
            print(f"✅ Выбран отрезок: {best_start:.1f}с (метод: {best_candidate['method']}, оценка: {best_candidate['score']:.3f})")
            
            return best_start
            
        except Exception as e:
            print(f"❌ Ошибка анализа аудио: {e}")
            # Fallback: середина трека
            audio = AudioSegment.from_file(file_path)
            total_duration = len(audio) / 1000.0
            return max(0, (total_duration - duration) / 2)

    def _analyze_by_energy(self, samples, sample_rate, duration, total_duration):
        """Анализ по энергии звука"""
        try:
            segment_size = int(sample_rate * 2)  # 2-секундные сегменты
            num_segments = len(samples) // segment_size
            
            segment_energies = []
            for i in range(num_segments):
                start_idx = i * segment_size
                end_idx = min((i + 1) * segment_size, len(samples))
                segment = samples[start_idx:end_idx]
                
                if len(segment) > 0:
                    energy = np.sqrt(np.mean(segment**2))
                    segment_energies.append(energy)
                else:
                    segment_energies.append(0)
            
            # Ищем лучший 30-секундный отрезок
            target_segments = duration // 2  # 15 сегментов по 2 секунды = 30 секунд
            best_energy = 0
            best_start_segment = 0
            
            for i in range(len(segment_energies) - target_segments + 1):
                window_energy = np.mean(segment_energies[i:i + target_segments])
                if window_energy > best_energy:
                    best_energy = window_energy
                    best_start_segment = i
            
            return {
                'start_time': best_start_segment * 2,
                'score': best_energy,
                'method': 'энергия'
            }
        except Exception as e:
            print(f"Ошибка анализа по энергии: {e}")
            return {
                'start_time': max(0, (total_duration - duration) / 2),
                'score': 0.5,
                'method': 'энергия (ошибка)'
            }

    def _analyze_by_variability(self, samples, sample_rate, duration, total_duration):
        """Анализ по вариативности (ищем интересные изменения)"""
        try:
            segment_size = int(sample_rate * 3)  # 3-секундные сегменты
            num_segments = len(samples) // segment_size
            
            segment_variability = []
            for i in range(num_segments):
                start_idx = i * segment_size
                end_idx = min((i + 1) * segment_size, len(samples))
                segment = samples[start_idx:end_idx]
                
                if len(segment) > 10:
                    # Вычисляем вариативность через стандартное отклонение
                    variability = np.std(segment)
                    segment_variability.append(variability)
                else:
                    segment_variability.append(0)
            
            # Ищем отрезок с максимальной средней вариативностью
            target_segments = duration // 3  # 10 сегментов по 3 секунды = 30 секунд
            best_variability = 0
            best_start_segment = 0
            
            for i in range(len(segment_variability) - target_segments + 1):
                window_var = np.mean(segment_variability[i:i + target_segments])
                if window_var > best_variability:
                    best_variability = window_var
                    best_start_segment = i
            
            return {
                'start_time': best_start_segment * 3,
                'score': best_variability,
                'method': 'вариативность'
            }
        except Exception as e:
            print(f"Ошибка анализа по вариативности: {e}")
            return {
                'start_time': max(0, (total_duration - duration) / 2),
                'score': 0.5,
                'method': 'вариативность (ошибка)'
            }

    def _analyze_by_peaks(self, samples, sample_rate, duration, total_duration):
        """Анализ по пиковым моментам"""
        try:
            # Находим области с высокой амплитудой
            window_size = int(sample_rate * 5)  # 5-секундные окна
            num_windows = len(samples) // window_size
            
            window_peaks = []
            for i in range(num_windows):
                start_idx = i * window_size
                end_idx = min((i + 1) * window_size, len(samples))
                window = samples[start_idx:end_idx]
                
                if len(window) > 0:
                    # Максимальная амплитуда в окне
                    peak = np.max(np.abs(window))
                    window_peaks.append(peak)
                else:
                    window_peaks.append(0)
            
            # Ищем лучшее 30-секундное окно (6 окон по 5 секунд)
            target_windows = duration // 5
            best_peak_score = 0
            best_start_window = 0
            
            for i in range(len(window_peaks) - target_windows + 1):
                window_score = np.mean(window_peaks[i:i + target_windows])
                if window_score > best_peak_score:
                    best_peak_score = window_score
                    best_start_window = i
            
            return {
                'start_time': best_start_window * 5,
                'score': best_peak_score,
                'method': 'пиковые моменты'
            }
        except Exception as e:
            print(f"Ошибка анализа по пикам: {e}")
            return {
                'start_time': max(0, (total_duration - duration) / 2),
                'score': 0.5,
                'method': 'пики (ошибка)'
            }

# Глобальный экземпляр редактора
audio_editor = AudioEditor()