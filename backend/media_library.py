# backend/media_library.py
import os
import json
import datetime
from backend.audio_editor import audio_editor
from backend.image_search import search_artist_image, download_image

class MediaLibrary:
    def __init__(self):
        self.tracks = []
        self.current_id = 1
        self.data_file = "track_data.json"
        self.load_from_file()
    
    def add_track(self, file_path, original_filename):
        """Добавить трек в медиатеку"""
        name_without_ext = os.path.splitext(original_filename)[0]
        
        duration = audio_editor.get_audio_duration(file_path)
        suggested_start = audio_editor.suggest_best_segment(file_path)
        
        # Улучшенный парсинг: поддержка " – ", " - ", "_"
        artist, title = self._parse_filename(name_without_ext)
        
        track = {
            'id': self.current_id,
            'file_path': file_path,
            'original_filename': original_filename,
            'artist': artist,
            'title': title,
            'cover_path': None,
            'image_path': None,
            'clip_path': None,  # ← путь к сохранённому отрезку
            'segment_start': suggested_start,
            'segment_duration': 30,
            'duration': duration,
            'status': 'uploaded',
            'waveform_data': None,
            'created_at': datetime.datetime.now().isoformat()
        }
        
        try:
            track['waveform_data'] = audio_editor.generate_waveform(file_path)
        except Exception as e:
            print(f"Ошибка генерации waveform: {e}")
            track['waveform_data'] = None
        
        self.tracks.append(track)
        self.current_id += 1
        self.save_to_file()
        return track

    def _parse_filename(self, name):
        """Парсит имя файла на artist и title"""
        separators = [" – ", " - ", " _ ", " –", " -"]
        for sep in separators:
            if sep in name:
                parts = name.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return name, "Без названия"

    def update_track_segment(self, track_id, start_time, duration=30):
        """Обновить отрезок трека"""
        for track in self.tracks:
            if track['id'] == track_id:
                track['segment_start'] = start_time
                track['segment_duration'] = duration
                if not track.get('image_path') and track.get('artist'):
                    self._fetch_and_save_artist_image(track)
                self.save_to_file()
                return True
        return False

    def _fetch_and_save_artist_image(self, track):
        """Поиск и сохранение фото исполнителя"""
        try:
            artist = track['artist']
            print(f"[MediaLibrary] Поиск фото для: {artist}")
            image_url = search_artist_image(artist)
            if image_url:
                safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in artist)
                image_path = os.path.join("images", f"{safe_name}.jpg")
                if download_image(image_url, image_path):
                    track['image_path'] = image_path
                    print(f"[MediaLibrary] Фото сохранено: {image_path}")
                else:
                    print(f"[MediaLibrary] Не удалось скачать фото для {artist}")
            else:
                print(f"[MediaLibrary] Фото не найдено для {artist}")
        except Exception as e:
            print(f"[MediaLibrary] Ошибка при поиске фото: {e}")

    def save_project(self):
        """
        Сохраняет проект: для всех треков — отрезки + фото.
        Вызывается при нажатии «Сохранить проект».
        """
        os.makedirs("output", exist_ok=True)
        os.makedirs("images", exist_ok=True)
        
        for track in self.tracks:
            # 1. Сохраняем аудио-отрезок
            clip_path = audio_editor.save_clip_permanently(
                track['file_path'],
                track['segment_start'],
                track.get('segment_duration', 30)
            )
            if clip_path:
                track['clip_path'] = clip_path
            
            # 2. Ищем фото (если ещё нет)
            if not track.get('image_path') and track.get('artist'):
                self._fetch_and_save_artist_image(track)
        
        self.save_to_file()
        return len(self.tracks)

    def play_track_segment(self, track_id):
        track = self.get_track(track_id)
        if track:
            return audio_editor.play_segment(
                track['file_path'], 
                track['segment_start'], 
                track['segment_duration']
            )
        return False
    
    def stop_playback(self):
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
                if 'artist' in track_data:
                    track['artist'] = track_data['artist']
                if 'title' in track_data:
                    track['title'] = track_data['title']
                if 'artist' in track_data and not track.get('image_path'):
                    self._fetch_and_save_artist_image(track)
                self.save_to_file()
                return True
        return False

    def add_track_with_metadata(self, track_data):
        try:
            track_id = self.current_id
            track = {
                'id': track_id,
                'file_path': track_data['file_path'],
                'original_filename': track_data['original_filename'],
                'artist': track_data.get('artist', ''),
                'title': track_data.get('title', ''),
                'metadata': track_data.get('metadata', {}),
                'segment_start': 0,
                'segment_duration': 30,
                'image_path': None,
                'clip_path': None,
                'cover_path': None,
                'created_at': datetime.datetime.now().isoformat()
            }
            if track['artist']:
                self._fetch_and_save_artist_image(track)
            self.tracks.append(track)
            self.current_id += 1
            self.save_to_file()
            return track
        except Exception as e:
            print(f"Error adding track with metadata: {e}")
            return None

    def delete_track(self, track_id):
        for i, track in enumerate(self.tracks):
            if track['id'] == track_id:
                if os.path.exists(track['file_path']):
                    try:
                        os.remove(track['file_path'])
                    except:
                        pass
                if track.get('image_path') and os.path.exists(track['image_path']):
                    try:
                        os.remove(track['image_path'])
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
            if track.get('image_path') and os.path.exists(track['image_path']):
                try:
                    os.remove(track['image_path'])
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