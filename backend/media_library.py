import os
import json
import datetime
from backend.audio_editor import audio_editor
from backend.image_search import image_searcher  # ✅ Используем fetch_artist_png
from backend.processors.metadata_processor import create_metadata_processor

# создаем глобальный процессор
metadata_processor = create_metadata_processor()


class MediaLibrary:
    def __init__(self):
        self.tracks = []
        self.current_id = 1
        self.data_file = "track_data.json"
        self.load_from_file()
    
    def add_track(self, file_path, original_filename):
        """Добавление трека с автоматическим анализом имени файла"""
        name_without_ext = os.path.splitext(original_filename)[0]
        duration = audio_editor.get_audio_duration(file_path)
        suggested_start = audio_editor.suggest_best_segment(file_path)

        # 🧠 Используем metadata_processor для канонизации артиста и названия
        try:
            parsed = metadata_processor.process(original_filename)
            artist = parsed.get("artist", "").strip()
            title = parsed.get("title", "").strip()
            print(f"[Metadata] Parsed artist='{artist}', title='{title}'")
        except Exception as e:
            print(f"[Metadata] Ошибка обработки метаданных: {e}")
            artist, title = self._parse_filename(name_without_ext)
        
        track = {
            'id': self.current_id,
            'file_path': file_path,
            'original_filename': original_filename,
            'artist': artist,
            'title': title,
            'cover_path': None,
            'image_path': None,
            'clip_path': None,
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

        # ✅ Автоматический поиск иконки артиста
        self._fetch_and_save_artist_image(track)
        
        self.tracks.append(track)
        self.current_id += 1
        self.save_to_file()
        return track

    def _parse_filename(self, name):
        separators = [" – ", " - ", " _ ", " –", " -"]
        for sep in separators:
            if sep in name:
                parts = name.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return name, "Без названия"

    def update_track_segment(self, track_id, start_time, duration=30):
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
        """Автоматический поиск и обработка фото исполнителя"""
        try:
            artist = track['artist']
            if not artist:
                return
            print(f"[MediaLibrary] Поиск фото для: {artist}")
            image_path = image_searcher.fetch_artist_png(artist, track['id'])
            if image_path:
                track['image_path'] = image_path
                print(f"[MediaLibrary] Фото сохранено: {image_path}")
            else:
                print(f"[MediaLibrary] Фото не найдено для {artist}")
        except Exception as e:
            print(f"[MediaLibrary] Ошибка при поиске фото: {e}")

    def refresh_all_metadata(self):
        """🧠 Обновление артиста и названия для всех треков"""
        updated = 0
        for track in self.tracks:
            filename = track.get('original_filename')
            if not filename:
                continue
            try:
                parsed = metadata_processor.process(filename)
                artist = parsed.get("artist", "").strip()
                title = parsed.get("title", "").strip()
                if artist:
                    track["artist"] = artist
                if title:
                    track["title"] = title
                updated += 1
                print(f"[Metadata] Обновлено: {filename} → {artist} - {title}")
            except Exception as e:
                print(f"[Metadata] Ошибка обновления {filename}: {e}")
        self.save_to_file()
        return updated

    def save_project(self):
        os.makedirs("output", exist_ok=True)
        os.makedirs("images", exist_ok=True)
        
        for track in self.tracks:
            clip_path = audio_editor.save_clip_permanently(
                track['file_path'],
                track['segment_start'],
                track.get('segment_duration', 30)
            )
            if clip_path:
                track['clip_path'] = clip_path
            
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
