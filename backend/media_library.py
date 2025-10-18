# backend/media_library.py
import os
import json
from backend.audio_editor import audio_editor

class MediaLibrary:
    def __init__(self):
        self.tracks = []
        self.current_id = 1
        self.data_file = "media_library.json"
        self.load_from_file()
    
    def add_track(self, file_path, original_filename):
        """Добавить трек в медиатеку"""
        name_without_ext = os.path.splitext(original_filename)[0]
        
        # Получаем длительность аудио
        duration = audio_editor.get_audio_duration(file_path)
        
        # Авто-рекомендация отрезка
        suggested_start = audio_editor.suggest_best_segment(file_path)
        
        track = {
            'id': self.current_id,
            'file_path': file_path,
            'original_filename': original_filename,
            'artist': name_without_ext,
            'title': 'Без названия',
            'cover_path': None,
            'segment_start': suggested_start,
            'segment_duration': 30,
            'duration': duration,
            'status': 'uploaded',
            'waveform_data': None
        }
        
        # Генерируем waveform (асинхронно чтобы не блокировать интерфейс)
        try:
            track['waveform_data'] = audio_editor.generate_waveform(file_path)
        except Exception as e:
            print(f"Ошибка генерации waveform: {e}")
            track['waveform_data'] = None
        
        self.tracks.append(track)
        self.current_id += 1
        self.save_to_file()
        return track
    
    def update_track_segment(self, track_id, start_time, duration=30):
        """Обновить отрезок трека"""
        for track in self.tracks:
            if track['id'] == track_id:
                track['segment_start'] = start_time
                track['segment_duration'] = duration
                self.save_to_file()
                return True
        return False
    
    def play_track_segment(self, track_id):
        """Воспроизвести отрезок трека"""
        track = self.get_track(track_id)
        if track:
            return audio_editor.play_segment(
                track['file_path'], 
                track['segment_start'], 
                track['segment_duration']
            )
        return False
    
    def stop_playback(self):
        """Остановить воспроизведение"""
        audio_editor.stop_playback()
    
    def get_tracks(self):
        return self.tracks
    
    def get_track(self, track_id):
        for track in self.tracks:
            if track['id'] == track_id:
                return track
        return None
    
    def update_track(self, track_id, track_data):
        for track in self.tracks:
            if track['id'] == track_id:
                track.update(track_data)
                self.save_to_file()
                return True
        return False
    
    def delete_track(self, track_id):
        for i, track in enumerate(self.tracks):
            if track['id'] == track_id:
                if os.path.exists(track['file_path']):
                    try:
                        os.remove(track['file_path'])
                    except:
                        pass
                self.tracks.pop(i)
                self.save_to_file()
                return True
        return False
    
    def clear(self):
        for track in self.tracks:
            if os.path.exists(track['file_path']):
                try:
                    os.remove(track['file_path'])
                except:
                    pass
        self.tracks = []
        self.save_to_file()
    
    def save_to_file(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'tracks': self.tracks,
                    'current_id': self.current_id
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения медиатеки: {e}")
    
    def load_from_file(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tracks = data.get('tracks', [])
                    self.current_id = data.get('current_id', 1)
        except Exception as e:
            print(f"Ошибка загрузки медиатеки: {e}")
            self.tracks = []
            self.current_id = 1
def add_track_with_metadata(self, track_data):
    """Добавить трек с готовыми метаданными"""
    try:
        track_id = len(self.tracks) + 1
        track = {
            'id': track_id,
            'file_path': track_data['file_path'],
            'original_filename': track_data['original_filename'],
            'artist': track_data.get('artist', ''),
            'title': track_data.get('title', ''),
            'metadata': track_data.get('metadata', {}),
            'segment_start': 0,
            'segment_duration': 30,
            'created_at': datetime.now().isoformat()
        }
        
        self.tracks.append(track)
        self.save_to_file()
        return track
    except Exception as e:
        print(f"Error adding track with metadata: {e}")
        return None