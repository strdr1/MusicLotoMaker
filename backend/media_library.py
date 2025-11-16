import os
import json
import datetime
import re
import logging
import shutil

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
        """Изменить ID трека с автоматическим обновлением фото"""
        track = self.get_track(old_id)
        if not track:
            return False
            
        if self.get_track(new_id):
            raise ValueError("Новый ID уже занят")
        
        # Сохраняем старый путь к фото
        old_image_path = track.get('image_path')
        
        # Меняем ID
        track['id'] = new_id
        
        # Если у трека есть фото - переименовываем файл
        if old_image_path and os.path.exists(old_image_path):
            # Определяем новый путь для фото
            file_extension = os.path.splitext(old_image_path)[1]
            images_dir = os.path.dirname(old_image_path)
            new_image_path = os.path.join(images_dir, f"{new_id}_artist{file_extension}")
            
            try:
                # Переименовываем файл
                os.rename(old_image_path, new_image_path)
                # Обновляем путь в данных трека
                track['image_path'] = new_image_path
                logger.info(f"🖼️ Фото переименовано: {old_image_path} → {new_image_path}")
            except Exception as e:
                logger.error(f"❌ Ошибка переименования фото: {e}")
                # Если не удалось переименовать, оставляем старый путь
                track['image_path'] = old_image_path
        
        self.save_to_file()
        logger.info(f"🔄 ID трека изменён: {old_id} → {new_id}")
        return True

    def swap_track_ids(self, id1: int, id2: int) -> bool:
        """Поменять местами ID двух треков с обновлением ВСЕХ фото"""
        track1 = self.get_track(id1)
        track2 = self.get_track(id2)
        if not track1 or not track2:
            return False
        
        # ВРЕМЕННЫЕ ПУТИ для фото обоих треков
        temp_image_path1 = None
        temp_image_path2 = None
        
        # Создаем временные имена для фото чтобы избежать конфликтов
        if track1.get('image_path') and os.path.exists(track1['image_path']):
            temp_image_path1 = track1['image_path'] + '.temp_swap'
            os.rename(track1['image_path'], temp_image_path1)
            logger.info(f"📁 Временное фото для трека {id1}: {temp_image_path1}")
        
        if track2.get('image_path') and os.path.exists(track2['image_path']):
            temp_image_path2 = track2['image_path'] + '.temp_swap'
            os.rename(track2['image_path'], temp_image_path2)
            logger.info(f"📁 Временное фото для трека {id2}: {temp_image_path2}")
        
        # МЕНЯЕМ ID МЕСТАМИ
        track1['id'], track2['id'] = track2['id'], track1['id']
        logger.info(f"🔄 ID поменяны: {id1} ↔ {id2}")
        
        # ОБНОВЛЯЕМ ПУТИ К ФОТО ДЛЯ ОБОИХ ТРЕКОВ
        try:
            # Для track1 (теперь с ID id2)
            if temp_image_path1:
                file_extension = os.path.splitext(temp_image_path1)[1]
                images_dir = os.path.dirname(temp_image_path1)
                new_path1 = os.path.join(images_dir, f"{track1['id']}_artist{file_extension}")
                os.rename(temp_image_path1, new_path1)
                track1['image_path'] = new_path1
                logger.info(f"🖼️ Фото для бывшего {id1} (теперь {track1['id']}): {new_path1}")
            
            # Для track2 (теперь с ID id1)  
            if temp_image_path2:
                file_extension = os.path.splitext(temp_image_path2)[1]
                images_dir = os.path.dirname(temp_image_path2)
                new_path2 = os.path.join(images_dir, f"{track2['id']}_artist{file_extension}")
                os.rename(temp_image_path2, new_path2)
                track2['image_path'] = new_path2
                logger.info(f"🖼️ Фото для бывшего {id2} (теперь {track2['id']}): {new_path2}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления фото при обмене ID: {e}")
            # В случае ошибки пытаемся восстановить оригинальные имена
            try:
                if temp_image_path1 and os.path.exists(temp_image_path1):
                    os.rename(temp_image_path1, track1['image_path'])
                if temp_image_path2 and os.path.exists(temp_image_path2):
                    os.rename(temp_image_path2, track2['image_path'])
            except:
                logger.error("💥 Критическая ошибка восстановления фото!")
        
        self.save_to_file()
        logger.info(f"✅ Обмен ID завершен: {id1} ↔ {id2} с обновлением фото")
        return True

    def compact_ids(self) -> bool:
        """Уплотнить ID: сделать их последовательными 1..N с обновлением ВСЕХ фото"""
        self.tracks.sort(key=lambda x: x['id'])
        
        # Сначала переименовываем ВСЕ фото во временные имена
        temp_mappings = {}
        for track in self.tracks:
            old_image_path = track.get('image_path')
            if old_image_path and os.path.exists(old_image_path):
                temp_path = old_image_path + '.temp_compact'
                try:
                    os.rename(old_image_path, temp_path)
                    temp_mappings[track['id']] = (old_image_path, temp_path)
                    logger.info(f"📁 Временное фото для ID {track['id']}: {temp_path}")
                except Exception as e:
                    logger.error(f"❌ Ошибка создания временного файла для трека {track['id']}: {e}")
        
        # Затем присваиваем новые ID и переименовываем ВСЕ фото
        for i, track in enumerate(self.tracks, start=1):
            old_id = track['id']
            track['id'] = i
            
            # Обновляем фото если есть
            if old_id in temp_mappings:
                old_path, temp_path = temp_mappings[old_id]
                try:
                    file_extension = os.path.splitext(old_path)[1]
                    images_dir = os.path.dirname(old_path)
                    new_image_path = os.path.join(images_dir, f"{i}_artist{file_extension}")
                    os.rename(temp_path, new_image_path)
                    track['image_path'] = new_image_path
                    logger.info(f"🖼️ Фото обновлено: {old_path} → {new_image_path}")
                except Exception as e:
                    logger.error(f"❌ Ошибка переименования фото для трека {old_id}→{i}: {e}")
                    # Восстанавливаем оригинальный путь
                    track['image_path'] = old_path
        
        self.save_to_file()
        logger.info(f"📦 ID уплотнены. Теперь треков: {len(self.tracks)}")
        return True

    def reorder_tracks_with_photo_fix(self, track_ids: list) -> bool:
        """Переупорядочить треки по списку ID с ОБЯЗАТЕЛЬНЫМ обновлением фото"""
        try:
            # Получаем текущие треки
            current_tracks = {t['id']: t for t in self.tracks}
            
            # 1. Сначала переименовываем ВСЕ фото во временные имена
            temp_mappings = {}
            for track_id in track_ids:
                if track_id in current_tracks:
                    track = current_tracks[track_id]
                    old_image_path = track.get('image_path')
                    if old_image_path and os.path.exists(old_image_path):
                        temp_path = old_image_path + f'.temp_reorder_{track_id}'
                        try:
                            os.rename(old_image_path, temp_path)
                            temp_mappings[track_id] = (old_image_path, temp_path)
                            logger.info(f"📁 Временное фото для ID {track_id}: {temp_path}")
                        except Exception as e:
                            logger.error(f"❌ Ошибка создания временного файла для трека {track_id}: {e}")
            
            # 2. Присваиваем новые ID и переименовываем фото
            ordered_tracks = []
            for i, track_id in enumerate(track_ids):
                if track_id not in current_tracks:
                    continue
                    
                track = current_tracks[track_id]
                old_id = track['id']
                new_id = i + 1
                
                # Меняем ID
                track['id'] = new_id
                
                # Обновляем фото если есть
                if old_id in temp_mappings:
                    old_path, temp_path = temp_mappings[old_id]
                    try:
                        file_extension = os.path.splitext(old_path)[1]
                        images_dir = os.path.dirname(old_path)
                        new_image_path = os.path.join(images_dir, f"{new_id}_artist{file_extension}")
                        os.rename(temp_path, new_image_path)
                        track['image_path'] = new_image_path
                        logger.info(f"🖼️ Фото обновлено: {old_path} → {new_image_path}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка переименования фото для трека {old_id}→{new_id}: {e}")
                        # Восстанавливаем оригинальный путь
                        track['image_path'] = old_path
                
                ordered_tracks.append(track)
            
            # 3. Обновляем медиатеку
            self.tracks = ordered_tracks
            self.save_to_file()
            
            logger.info(f"🔄 Треки переупорядочены с обновлением фото. Новых ID: {len(ordered_tracks)}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при переупорядочивании: {e}")
            return False

    def fix_broken_image_paths(self) -> dict:
        """Исправляет сломанные пути к фото артистов"""
        fixed_count = 0
        broken_tracks = []
        
        for track in self.tracks:
            track_id = track['id']
            current_image_path = track.get('image_path')
            
            # Если путь есть, но не соответствует ID трека - исправляем
            if current_image_path and os.path.exists(current_image_path):
                # Ожидаемый путь к фото
                expected_filename = f"{track_id}_artist.png"
                expected_path = os.path.join(os.path.dirname(current_image_path), expected_filename)
                
                # Если текущий путь не соответствует ожидаемому
                if current_image_path != expected_path:
                    try:
                        # Переименовываем файл
                        os.rename(current_image_path, expected_path)
                        track['image_path'] = expected_path
                        fixed_count += 1
                        broken_tracks.append({
                            'id': track_id,
                            'artist': track.get('artist', ''),
                            'old_path': current_image_path,
                            'new_path': expected_path
                        })
                        logger.info(f"🔧 Исправлен путь фото: {current_image_path} → {expected_path}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка исправления пути фото для трека {track_id}: {e}")
                        broken_tracks.append({
                            'id': track_id,
                            'artist': track.get('artist', ''),
                            'error': str(e)
                        })
        
        if fixed_count > 0:
            self.save_to_file()
            logger.info(f"✅ Исправлено {fixed_count} сломанных путей к фото")
        
        return {
            'fixed_count': fixed_count,
            'broken_tracks': broken_tracks,
            'message': f'Исправлено {fixed_count} сломанных путей к фото'
        }

# Создаем глобальный экземпляр медиатеки
media_library = MediaLibrary()