import os
import json
import datetime
import re
import logging

logger = logging.getLogger(__name__)

def normalize_track_string(text: str) -> str:
    """
    Нормализует строку для сравнения треков
    """
    if not text:
        return ""
    
    # Приводим к нижнему регистру
    normalized = text.lower().strip()
    
    # Заменяем множественные пробелы на один
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Убираем некоторые символы, которые могут различаться в написании
    chars_to_remove = ['!', '?', '.', ',', ';', ':', '"', "'", '`', '(', ')', '[', ']', '{', '}']
    for char in chars_to_remove:
        normalized = normalized.replace(char, '')
    
    # Нормализуем дефисы и тире
    normalized = normalized.replace('–', '-').replace('—', '-')
    
    return normalized

class MediaLibrary:
    def __init__(self, data_file: str = "track_data.json"):
        self.tracks = []
        self.data_file = data_file
        self.load_from_file()
    
    def track_exists(self, artist: str, title: str) -> bool:
        """
        Проверяет, существует ли трек с таким же артистом и названием
        Возвращает True если дубликат найден
        """
        if not artist or not title:
            return False
            
        # Нормализуем строки для сравнения
        artist_normalized = normalize_track_string(artist)
        title_normalized = normalize_track_string(title)
        
        for track in self.tracks:
            track_artist = normalize_track_string(track.get('artist', ''))
            track_title = normalize_track_string(track.get('title', ''))
            
            # Сравниваем нормализованные значения
            if track_artist == artist_normalized and track_title == title_normalized:
                return True
                
        return False
    
    def find_duplicate_tracks(self, artist: str, title: str) -> list:
        """
        Находит все треки-дубликаты
        """
        if not artist or not title:
            return []
            
        artist_normalized = normalize_track_string(artist)
        title_normalized = normalize_track_string(title)
        
        duplicates = []
        for track in self.tracks:
            track_artist = normalize_track_string(track.get('artist', ''))
            track_title = normalize_track_string(track.get('title', ''))
            
            if track_artist == artist_normalized and track_title == title_normalized:
                duplicates.append({
                    'id': track['id'],
                    'artist': track.get('artist', ''),
                    'title': track.get('title', ''),
                    'file_path': track.get('file_path', ''),
                    'original_filename': track.get('original_filename', '')
                })
                
        return duplicates
    
    def get_track_by_artist_title(self, artist: str, title: str) -> dict:
        """
        Находит трек по артисту и названию
        """
        if not artist or not title:
            return None
            
        artist_normalized = normalize_track_string(artist)
        title_normalized = normalize_track_string(title)
        
        for track in self.tracks:
            track_artist = normalize_track_string(track.get('artist', ''))
            track_title = normalize_track_string(track.get('title', ''))
            
            if track_artist == artist_normalized and track_title == title_normalized:
                return track
                
        return None

    def add_track(self, file_path: str, original_filename: str, metadata: dict = None):
        """
        Добавление трека с автоматическим установлением умного отрезка
        и проверкой дубликатов
        """
        name_without_ext = os.path.splitext(original_filename)[0]
        
        # Получаем следующий ID на основе существующих треков
        next_id = self.get_next_available_id()
        
        # Парсим метаданные
        if metadata:
            cleaned_artist = re.sub(r'\s*\([^)]*\)$', '', metadata.get('artist', 'Неизвестный исполнитель')).strip()
            cleaned_title = re.sub(r'\s*\([^)]*\)$', '', metadata.get('title', 'Без названия')).strip()
        else:
            # Используем metadata_processor для канонизации артиста и названия
            try:
                from backend.processors.metadata_processor import create_metadata_processor
                metadata_processor = create_metadata_processor()
                parsed = metadata_processor.process(original_filename)
                cleaned_artist = parsed.get("artist", "").strip()
                cleaned_title = parsed.get("title", "").strip()
                logger.info(f"[Metadata] Parsed artist='{cleaned_artist}', title='{cleaned_title}'")
            except Exception as e:
                logger.warning(f"[Metadata] Ошибка обработки метаданных: {e}")
                cleaned_artist, cleaned_title = self._parse_filename(name_without_ext)
        
        # ПРОВЕРКА ДУБЛИКАТА ПЕРЕД ДОБАВЛЕНИЕМ
        if self.track_exists(cleaned_artist, cleaned_title):
            existing_track = self.get_track_by_artist_title(cleaned_artist, cleaned_title)
            logger.warning(f"🚫 Дубликат трека: {cleaned_artist} - {cleaned_title} (ID: {existing_track['id']})")
            return {
                'success': False,
                'error': 'duplicate',
                'message': f'Трек уже существует в медиатеке (ID: {existing_track["id"]})',
                'existing_track': existing_track
            }
        
        # Получаем информацию об аудио
        try:
            from backend.audio_editor import audio_editor
            duration = audio_editor.get_audio_duration(file_path)
            suggested_start = audio_editor.suggest_best_segment(file_path)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка audio_editor: {e}")
            duration = 180  # fallback
            suggested_start = 30  # fallback

        track = {
            'id': next_id,
            'file_path': file_path,
            'original_filename': original_filename,
            'artist': cleaned_artist,
            'title': cleaned_title,
            'cover_path': None,
            'image_path': None,  # Фото НЕ загружается автоматически
            'clip_path': None,
            'segment_start': suggested_start,  # Автоматически установленный умный отрезок
            'segment_duration': 30,
            'duration': duration,
            'status': 'uploaded',
            'waveform_data': None,
            'metadata': metadata or {},
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        # Генерация waveform (опционально)
        try:
            from backend.audio_editor import audio_editor
            track['waveform_data'] = audio_editor.generate_waveform(file_path)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка генерации waveform: {e}")
            track['waveform_data'] = None

        self.tracks.append(track)
        self.save_to_file()
        logger.info(f"✅ Трек добавлен с ID: {next_id}, умный отрезок: {suggested_start}с")
        return {
            'success': True,
            'track': track
        }

    def _parse_filename(self, name: str) -> tuple:
        """Парсит имя файла для извлечения артиста и названия"""
        separators = [" – ", " - ", " _ ", " –", " -"]
        for sep in separators:
            if sep in name:
                parts = name.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return name, "Без названия"

    def update_track_segment(self, track_id: int, start_time: float, duration: float = 30):
        """Обновить отрезок трека (автоматический или ручной)"""
        for track in self.tracks:
            if track['id'] == track_id:
                track['segment_start'] = start_time
                track['segment_duration'] = duration
                track['updated_at'] = datetime.datetime.now().isoformat()
                self.save_to_file()
                logger.info(f"🔄 Обновлен отрезок трека {track_id}: {start_time}с")
                return True
        return False

    def get_tracks(self):
        """Получить все треки, отсортированные по ID"""
        return sorted(self.tracks, key=lambda x: x['id'])

    def get_track(self, track_id: int):
        """Получить трек по ID"""
        for track in self.tracks:
            if track['id'] == track_id:
                return track
        return None

    def update_track(self, track_id: int, track_data: dict):
        """Обновить данные трека"""
        for track in self.tracks:
            if track['id'] == track_id:
                track.update(track_data)
                track['updated_at'] = datetime.datetime.now().isoformat()
                self.save_to_file()
                logger.info(f"🔄 Обновлен трек ID: {track_id}")
                return True
        return False

    def delete_track(self, track_id: int):
        """Удалить трек и связанные файлы"""
        for i, track in enumerate(self.tracks):
            if track['id'] == track_id:
                # Удаляем файлы трека
                files_removed = []
                
                # Аудиофайл
                if os.path.exists(track['file_path']):
                    try:
                        os.remove(track['file_path'])
                        files_removed.append(track['file_path'])
                        logger.info(f"🗑️ Удален аудиофайл: {track['file_path']}")
                    except Exception as e:
                        logger.error(f"⚠️ Не удалось удалить аудиофайл: {e}")
                
                # Фото артиста если есть
                if track.get('image_path') and os.path.exists(track['image_path']):
                    try:
                        os.remove(track['image_path'])
                        files_removed.append(track['image_path'])
                        logger.info(f"🗑️ Удалено фото: {track['image_path']}")
                    except Exception as e:
                        logger.error(f"⚠️ Не удалось удалить фото: {e}")
                
                # Удаляем из списка
                self.tracks.pop(i)
                self.save_to_file()
                logger.info(f"✅ Трек {track_id} удален из медиатеки. Удалено файлов: {len(files_removed)}")
                return {
                    'success': True,
                    'files_removed': files_removed
                }
        
        logger.warning(f"❌ Трек {track_id} не найден для удаления")
        return {
            'success': False,
            'error': 'Track not found'
        }

    def clear(self):
        """Очистить всю медиатеку"""
        deleted_count = 0
        files_removed = []
        
        for track in self.tracks:
            if os.path.exists(track['file_path']):
                try:
                    os.remove(track['file_path'])
                    deleted_count += 1
                    files_removed.append(track['file_path'])
                except Exception as e:
                    logger.error(f"⚠️ Не удалось удалить аудиофайл {track['file_path']}: {e}")
            
            if track.get('image_path') and os.path.exists(track['image_path']):
                try:
                    os.remove(track['image_path'])
                    files_removed.append(track['image_path'])
                except Exception as e:
                    logger.error(f"⚠️ Не удалось удалить фото {track['image_path']}: {e}")
        
        self.tracks = []
        self.save_to_file()
        logger.info(f"✅ Медиатека очищена. Удалено треков: {deleted_count}, файлов: {len(files_removed)}")
        
        return {
            'success': True,
            'tracks_deleted': deleted_count,
            'files_removed': files_removed
        }

    def save_to_file(self):
        """Сохранить медиатеку в файл"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'tracks': self.tracks,
                    'last_updated': datetime.datetime.now().isoformat(),
                    'total_tracks': len(self.tracks)
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Медиатека сохранена. Треков: {len(self.tracks)}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения медиатеки: {e}")

    def load_from_file(self):
        """Загрузить медиатеку из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tracks = data.get('tracks', [])
                logger.info(f"📂 Медиатека загружена. Треков: {len(self.tracks)}")
                
                # Логируем ID существующих треков для отладки
                if self.tracks:
                    track_ids = [track['id'] for track in self.tracks]
                    logger.info(f"📊 ID существующих треков: {track_ids}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки медиатеки: {e}")
            self.tracks = []

    def get_tracks_count(self):
        """Получить количество треков"""
        return len(self.tracks)

    def get_next_available_id(self):
        """Получить следующий доступный ID"""
        if not self.tracks:
            return 1
        max_id = max(track['id'] for track in self.tracks)
        return max_id + 1

    def search_tracks(self, query: str):
        """Поиск треков по артисту или названию"""
        if not query:
            return self.get_tracks()
            
        query_normalized = normalize_track_string(query)
        results = []
        
        for track in self.tracks:
            artist = normalize_track_string(track.get('artist', ''))
            title = normalize_track_string(track.get('title', ''))
            
            if query_normalized in artist or query_normalized in title:
                results.append(track)
        
        return results

    def get_tracks_without_images(self):
        """Получить треки без фото артиста"""
        return [track for track in self.tracks if not track.get('image_path') or not os.path.exists(track.get('image_path', ''))]

    def get_tracks_with_images(self):
        """Получить треки с фото артиста"""
        return [track for track in self.tracks if track.get('image_path') and os.path.exists(track.get('image_path', ''))]

    def get_artists(self):
        """Получить список всех артистов"""
        artists = set()
        for track in self.tracks:
            artist = track.get('artist', '').strip()
            if artist:
                artists.add(artist)
        return sorted(list(artists))

    def get_tracks_by_artist(self, artist: str):
        """Получить все треки артиста"""
        artist_normalized = normalize_track_string(artist)
        return [track for track in self.tracks if normalize_track_string(track.get('artist', '')) == artist_normalized]

    def export_to_json(self, include_file_paths: bool = False):
        """Экспорт медиатеки в JSON"""
        export_data = {
            'export_date': datetime.datetime.now().isoformat(),
            'total_tracks': len(self.tracks),
            'tracks': []
        }
        
        for track in self.tracks:
            track_data = {
                'id': track['id'],
                'artist': track.get('artist', ''),
                'title': track.get('title', ''),
                'duration': track.get('duration', 0),
                'segment_start': track.get('segment_start', 0),
                'segment_duration': track.get('segment_duration', 30),
                'created_at': track.get('created_at', ''),
                'has_image': bool(track.get('image_path') and os.path.exists(track.get('image_path', '')))
            }
            
            if include_file_paths:
                track_data['file_path'] = track.get('file_path', '')
                track_data['image_path'] = track.get('image_path', '')
            
            export_data['tracks'].append(track_data)
        
        return export_data
    def change_track_id(self, old_id: int, new_id: int) -> bool:
        """Изменить ID трека. new_id должен быть свободен."""
        track = self.get_track(old_id)
        if not track:
            return False
        if self.get_track(new_id):
            raise ValueError("Новый ID уже занят")
        track['id'] = new_id
        self.save_to_file()
        logger.info(f"🔄 ID трека изменён: {old_id} → {new_id}")
        return True

    def swap_track_ids(self, id1: int, id2: int) -> bool:
        """Поменять местами ID двух треков."""
        track1 = self.get_track(id1)
        track2 = self.get_track(id2)
        if not track1 or not track2:
            return False
        track1['id'], track2['id'] = track2['id'], track1['id']
        self.save_to_file()
        logger.info(f"🔄 ID треков поменяны местами: {id1} ↔ {id2}")
        return True

    def compact_ids(self) -> bool:
        """Уплотнить ID: сделать их последовательными 1..N без пропусков."""
        self.tracks.sort(key=lambda x: x['id'])
        for i, track in enumerate(self.tracks, start=1):
            track['id'] = i
        self.save_to_file()
        logger.info(f"📦 ID уплотнены. Теперь треков: {len(self.tracks)}")
        return True
# Создаем глобальный экземпляр медиатеки
media_library = MediaLibrary()