# -*- coding: utf-8 -*-
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
import numpy as np
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class AudioPeakAnalyzer:
    """Анализатор пиков громкости в аудио"""

    def __init__(self, sample_rate=22050, channels=1, window_sec=0.6, read_sec=1.0, position_bias=0.3):
        self.sample_rate = sample_rate
        self.channels = channels
        self.window_sec = window_sec
        self.read_sec = read_sec
        self.position_bias = max(0.0, min(position_bias, 1.0))

    def find_loudest_segment_start(self, file_path: str, duration: int = 30, lead_in: int = 5) -> float:
        """Находит стартовую точку за lead_in секунд до самого 'звучного' момента."""
        try:
            if not os.path.exists(file_path):
                return 45.0

            total_duration = self._get_audio_duration(file_path)
            if total_duration <= duration:
                return 0.0

            loudest_time = self._analyze_rms_volume_stream(file_path, total_duration)
            suggested_start = max(0.0, loudest_time - lead_in)

            max_possible = max(0.0, total_duration - duration)
            if suggested_start > max_possible:
                suggested_start = max(0.0, max_possible - 2.0)

            return suggested_start

        except Exception as e:
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
        except:
            pass
        return 0.0

    def _analyze_rms_volume_stream(self, file_path: str, total_duration: float) -> float:
        sr = int(self.sample_rate)
        window_samples = int(self.window_sec * sr)
        read_samples = int(self.read_sec * sr)
        bytes_per_sample = 2
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
            return self._improved_heuristic(total_duration)

        rms_windows = []
        window_positions = []
        rolling_buffer = bytearray()

        samples_processed = 0
        eof = False

        try:
            while True:
                chunk = p.stdout.read(block_bytes)
                if not chunk:
                    eof = True
                rolling_buffer += chunk

                while len(rolling_buffer) >= window_samples * bytes_per_sample * self.channels:
                    window_bytes = rolling_buffer[:window_samples * bytes_per_sample * self.channels]
                    del rolling_buffer[:window_samples * bytes_per_sample * self.channels]

                    rms = self._rms_from_pcm16(window_bytes)
                    center_sample_index = samples_processed + (window_samples // 2)
                    center_time = center_sample_index / sr
                    rms_windows.append(rms)
                    window_positions.append(center_time)
                    samples_processed += window_samples

                if eof:
                    break

            p.stdout.close()
            p.wait(timeout=5)

        except Exception as e:
            try:
                p.kill()
            except:
                pass

        if not rms_windows:
            return self._improved_heuristic(total_duration)

        max_rms = max(rms_windows) if rms_windows else 1.0
        norm_rms = [r / max_rms for r in rms_windows]

        best_idx = max(range(len(norm_rms)), key=lambda x: norm_rms[x])
        best_time = window_positions[best_idx] if window_positions else total_duration * 0.4

        return float(max(0.0, min(best_time, total_duration)))

    def _rms_from_pcm16(self, pcm_bytes: bytes) -> float:
        n = len(pcm_bytes) // 2
        if n == 0:
            return 0.0
        
        samples = []
        for i in range(0, len(pcm_bytes), 2):
            if i + 1 < len(pcm_bytes):
                samples.append(struct.unpack('<h', pcm_bytes[i:i+2])[0])
        
        if not samples:
            return 0.0
            
        s = 0.0
        for v in samples:
            s += (v / 32768.0) ** 2
        mean_sq = s / len(samples)
        return math.sqrt(mean_sq)

    def _improved_heuristic(self, total_duration: float) -> float:
        if total_duration <= 90:
            return total_duration * 0.5
        elif total_duration <= 150:
            return total_duration * 0.45
        elif total_duration <= 240:
            return total_duration * 0.40
        else:
            return total_duration * 0.35

    def _smart_fallback(self, file_path: str, duration: int) -> float:
        try:
            total_duration = self._get_audio_duration(file_path)
            if total_duration == 0:
                return 45.0

            suggested = self._improved_heuristic(total_duration)
            suggested = max(10, min(suggested, total_duration - max(5, duration)))
            max_possible = total_duration - duration
            if suggested > max_possible:
                suggested = max(0, max_possible - 2)

            return suggested
        except Exception as e:
            return 45.0

class AudioEditor:
    def __init__(self):
        self.current_playing = None
        self.playback_thread = None
        self.stop_playback_flag = False

        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._create_directories()

        self.peak_analyzer = AudioPeakAnalyzer(
            sample_rate=22050,
            window_sec=0.6,
            read_sec=1.0,
            position_bias=0.3
        )

    def _create_directories(self):
        folders = ["temp", "output", "images", "covers", "tracks_data"]
        for folder in folders:
            folder_path = os.path.join(self.BASE_DIR, folder)
            os.makedirs(folder_path, exist_ok=True)

    def generate_waveform(self, file_path, width=1200, height=120):
        """Генерация пикового waveform через ffmpeg"""
        try:
            temp_waveform = os.path.join(self.BASE_DIR, "temp", f"waveform_{hashlib.md5(file_path.encode()).hexdigest()[:8]}.png")
            
            cmd = [
                'ffmpeg', '-i', file_path,
                '-filter_complex', 
                f'[0:a]aformat=channel_layouts=mono,compand=attacks=0:decays=0.3:points=-80/-80|-24/-12|0/0,showwavespic=s={width}x{height}:colors=#3b82f6[wave]',
                '-map', '[wave]',
                '-frames:v', '1',
                '-y',
                temp_waveform
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(temp_waveform):
                with open(temp_waveform, 'rb') as f:
                    waveform_data = f.read()
                
                b64_data = base64.b64encode(waveform_data).decode()
                
                try:
                    os.remove(temp_waveform)
                except:
                    pass
                    
                return f"data:image/png;base64,{b64_data}"
            else:
                return self._create_fallback_waveform(width, height)
                
        except Exception as e:
            return self._create_fallback_waveform(width, height)

    def _create_fallback_waveform(self, width, height):
        try:
            points = []
            segments = 400
            center_y = height / 2
            
            for i in range(segments + 1):
                x = (i / segments) * width
                
                t = i / segments * 12 * math.pi
                
                base1 = math.sin(t) * 0.5
                base2 = math.sin(t * 3.7) * 0.3  
                base3 = math.sin(t * 8.2) * 0.2
                
                combined = base1 + base2 + base3
                
                if i % 53 == 0:
                    peak = 0.9 + (i % 4) * 0.15
                elif i % 29 == 0:
                    peak = 0.7 + (i % 3) * 0.1
                elif i % 17 == 0:
                    peak = 0.5 + (i % 2) * 0.1
                elif i % 11 == 0:
                    peak = 0.3
                else:
                    peak = 0
                
                wave_height = combined + peak
                wave_height = max(-0.95, min(0.95, wave_height))
                
                y = center_y + (wave_height * (height / 2 - 8))
                points.append(f"{x},{y}")
            
            path_data = f"M {points[0]} L {', '.join(points[1:])}"
            
            svg_content = f'''
            <svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <linearGradient id="waveGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stop-color="#3b82f6" />
                        <stop offset="30%" stop-color="#10b981" />
                        <stop offset="70%" stop-color="#f59e0b" />
                        <stop offset="100%" stop-color="#ef4444" />
                    </linearGradient>
                </defs>
                
                <rect width="100%" height="100%" fill="#0f172a"/>
                
                <line x1="0" y1="{center_y}" x2="{width}" y2="{center_y}" 
                      stroke="#334155" stroke-width="0.5" opacity="0.6"/>
                
                <path d="{path_data}" 
                      fill="none" 
                      stroke="url(#waveGradient)" 
                      stroke-width="2.5" 
                      stroke-linecap="round"
                      stroke-linejoin="round"/>
            </svg>
            '''
            return f"data:image/svg+xml;base64,{base64.b64encode(svg_content.encode()).decode()}"
            
        except Exception as e:
            return "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIwMCIgaGVpZ2h0PSIxMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iIzBmMTcyYSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjNjQ3NDhiIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiPldhdmVmb3JtPC90ZXh0Pjwvc3ZnPg=="

    def extract_segment(self, file_path, start_time, duration=30, output_path=None):
        try:
            if not output_path:
                track_id = hashlib.md5(f"{file_path}_{start_time}".encode()).hexdigest()[:8]
                output_path = os.path.join(self.BASE_DIR, "temp", f"segment_{track_id}.mp3")

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-i', file_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'libmp3lame',
                '-q:a', '2',
                '-ac', '2',
                '-ar', '44100',
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения отрезка: {e}")
        return None

    def get_audio_duration(self, file_path):
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"❌ Ошибка получения длительности: {e}")
        return 0

    def suggest_best_segment(self, file_path, duration=30):
        try:
            start_time = self.peak_analyzer.find_loudest_segment_start(file_path, duration, lead_in=5)
            return start_time
        except Exception as e:
            logger.error(f"❌ Ошибка анализа громкости: {e}")
            return 45.0

    def play_segment_thread(self, file_path, start_time, duration=30):
        try:
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

                time.sleep(duration + 2)

                try:
                    if os.path.exists(temp_segment):
                        os.remove(temp_segment)
                except:
                    pass

                return True
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения: {e}")
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
        except Exception as e:
            logger.error(f"❌ Ошибка остановки воспроизведения: {e}")

# Глобальный экземпляр
audio_editor = AudioEditor()