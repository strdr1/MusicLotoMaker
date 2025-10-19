import os
import json
import datetime
from backend.audio_editor import audio_editor

class MediaLibrary:
    def __init__(self):
        self.tracks = []
        self.data_file = "track_data.json"
        self.load_from_file()
    
    def add_track(self, file_path, original_filename):
        """Добавление трека с автоматическим установлением умного отрезка"""
        name_without_ext = os.path.splitext(original_filename)[0]
        
        # Получаем следующий ID на основе существующих треков
        if self.tracks:
            next_id = max(track['id'] for track in self.tracks) + 1
        else:
            next_id = 1
            
        duration = audio_editor.get_audio_duration(file_path)
        
        # Автоматически определяем лучший отрезок
        suggested_start = audio_editor.suggest_best_segment(file_path)

        # Используем metadata_processor для канонизации артиста и названия
        try:
            from backend.processors.metadata_processor import create_metadata_processor
            metadata_processor = create_metadata_processor()
            parsed = metadata_processor.process(original_filename)
            artist = parsed.get("artist", "").strip()
            title = parsed.get("title", "").strip()
            print(f"[Metadata] Parsed artist='{artist}', title='{title}'")
        except Exception as e:
            print(f"[Metadata] Ошибка обработки метаданных: {e}")
            artist, title = self._parse_filename(name_without_ext)
        
        track = {
            'id': next_id,
            'file_path': file_path,
            'original_filename': original_filename,
            'artist': artist,
            'title': title,
            'cover_path': None,
            'image_path': None,  # Фото НЕ загружается автоматически
            'clip_path': None,
            'segment_start': suggested_start,  # Автоматически установленный умный отрезок
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
        self.save_to_file()
        print(f"✅ Трек добавлен с ID: {next_id}, умный отрезок: {suggested_start}с")
        return track

    def _parse_filename(self, name):
        separators = [" – ", " - ", " _ ", " –", " -"]
        for sep in separators:
            if sep in name:
                parts = name.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return name, "Без названия"

    def update_track_segment(self, track_id, start_time, duration=30):
        """Обновить отрезок трека (автоматический или ручной)"""
        for track in self.tracks:
            if track['id'] == track_id:
                track['segment_start'] = start_time
                track['segment_duration'] = duration
                self.save_to_file()
                print(f"🔄 Обновлен отрезок трека {track_id}: {start_time}с")
                return True
        return False

    def get_tracks(self):
        return sorted(self.tracks, key=lambda x: x['id'])

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
                # Удаляем файлы трека
                if os.path.exists(track['file_path']):
                    try:
                        os.remove(track['file_path'])
                        print(f"🗑️ Удален аудиофайл: {track['file_path']}")
                    except Exception as e:
                        print(f"⚠️ Не удалось удалить аудиофайл: {e}")
                
                # Удаляем фото артиста если есть
                if track.get('image_path') and os.path.exists(track['image_path']):
                    try:
                        os.remove(track['image_path'])
                        print(f"🗑️ Удалено фото: {track['image_path']}")
                    except Exception as e:
                        print(f"⚠️ Не удалось удалить фото: {e}")
                
                self.tracks.pop(i)
                self.save_to_file()
                print(f"✅ Трек {track_id} удален из медиатеки")
                return True
        print(f"❌ Трек {track_id} не найден для удаления")
        return False

    def clear(self):
        """Очистить всю медиатеку"""
        deleted_count = 0
        for track in self.tracks:
            if os.path.exists(track['file_path']):
                try:
                    os.remove(track['file_path'])
                    deleted_count += 1
                except Exception as e:
                    print(f"⚠️ Не удалось удалить аудиофайл {track['file_path']}: {e}")
            
            if track.get('image_path') and os.path.exists(track['image_path']):
                try:
                    os.remove(track['image_path'])
                except Exception as e:
                    print(f"⚠️ Не удалось удалить фото {track['image_path']}: {e}")
        
        self.tracks = []
        self.save_to_file()
        print(f"✅ Медиатека очищена. Удалено треков: {deleted_count}")

    def save_to_file(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'tracks': self.tracks
                }, f, ensure_ascii=False, indent=2)
            print(f"💾 Медиатека сохранена. Треков: {len(self.tracks)}")
        except Exception as e:
            print(f"❌ Ошибка сохранения медиатеки: {e}")

    def load_from_file(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tracks = data.get('tracks', [])
                print(f"📂 Медиатека загружена. Треков: {len(self.tracks)}")
                
                # Логируем ID существующих треков для отладки
                if self.tracks:
                    track_ids = [track['id'] for track in self.tracks]
                    print(f"📊 ID существующих треков: {track_ids}")
        except Exception as e:
            print(f"❌ Ошибка загрузки медиатеки: {e}")
            self.tracks = []

    def get_tracks_count(self):
        return len(self.tracks)

    def get_next_available_id(self):
        """Получить следующий доступный ID"""
        if not self.tracks:
            return 1
        
        # Находим максимальный ID среди существующих треков
        max_id = max(track['id'] for track in self.tracks)
        return max_id + 1

    def reorganize_ids(self):
        """Переупорядочить ID треков (опционально)"""
        if not self.tracks:
            return
        
        # Сортируем треки по дате создания или другому критерию
        sorted_tracks = sorted(self.tracks, key=lambda x: x.get('created_at', ''))
        
        # Присваиваем новые последовательные ID
        for new_id, track in enumerate(sorted_tracks, 1):
            track['id'] = new_id
        
        self.save_to_file()
        print(f"🔄 ID треков переупорядочены. Новый диапазон: 1-{len(self.tracks)}")