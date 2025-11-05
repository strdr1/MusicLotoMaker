# -*- coding: utf-8 -*-
import os
import dropbox
import logging
from pathlib import Path
from dropbox.exceptions import ApiError, AuthError

logger = logging.getLogger(__name__)

# Настройки Dropbox OAuth2
APP_KEY = os.getenv("DROPBOX_APP_KEY", "efeldnjeg5vown4")
APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "cl4di18jzokw4ib")
REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN", "mvG9te2oJicAAAAAAAAAAcadnoncZEzs8609dNs1wAtxiFd7jf4bVK0QPUFBCpt4")

class DropboxStorage:
    def __init__(self):
        try:
            logger.info("🔑 Инициализация Dropbox клиента...")
            self.dbx = dropbox.Dropbox(
                app_key=APP_KEY,
                app_secret=APP_SECRET,
                oauth2_refresh_token=REFRESH_TOKEN
            )
            # Проверим подключение
            account = self.dbx.users_get_current_account()
            logger.info(f"✅ Подключено к Dropbox как: {account.name.display_name}")
        except AuthError as e:
            logger.error(f"❌ Ошибка авторизации Dropbox: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Dropbox клиента: {e}")
            raise

    def download_base_pptx(self, local_path):
        """Скачать base.pptx из Dropbox, если локального нет."""
        try:
            if os.path.exists(local_path):
                logger.info(f"✅ base.pptx уже существует: {local_path}")
                return True

            dropbox_path = "/base.pptx"
            logger.info("📦 Скачиваем base.pptx из Dropbox...")
            metadata, response = self.dbx.files_download(dropbox_path)

            with open(local_path, "wb") as f:
                f.write(response.content)

            logger.info(f"✅ base.pptx скачан: {local_path}")
            return True
        except ApiError as e:
            logger.error(f"❌ Ошибка Dropbox API при скачивании base.pptx: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания base.pptx: {e}")
            return False

    def download_artist_photos(self, local_dir):
        """Скачать фото артистов из Dropbox, если локальной папки нет или она пуста."""
        try:
            os.makedirs(local_dir, exist_ok=True)
            local_files = os.listdir(local_dir)
            if local_files:
                logger.info(f"✅ В папке {local_dir} уже есть {len(local_files)} файлов")
                return True

            logger.info("📥 Загружаем фото артистов из Dropbox...")
            result = self.dbx.files_list_folder("/artists")
            downloaded = 0

            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    local_path = os.path.join(local_dir, entry.name)
                    try:
                        metadata, response = self.dbx.files_download(entry.path_lower)
                        with open(local_path, "wb") as f:
                            f.write(response.content)
                        downloaded += 1
                        logger.info(f"✅ Загружено фото: {entry.name}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка при скачивании фото {entry.name}: {e}")

            logger.info(f"📸 Скачано {downloaded} фото артистов")
            return downloaded > 0

        except ApiError as e:
            logger.error(f"❌ Ошибка Dropbox API: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания фото артистов: {e}")
            return False

    def list_artist_photos(self):
        """Получить список фото артистов в Dropbox."""
        try:
            logger.info("📄 Получаем список файлов из /artists...")
            result = self.dbx.files_list_folder("/artists")
            photos = []
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    photos.append({
                        "filename": entry.name,
                        "artist_name": Path(entry.name).stem.replace("_", " "),
                        "dropbox_path": entry.path_lower
                    })
            logger.info(f"📸 Найдено {len(photos)} фото артистов")
            return photos
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка фото: {e}")
            return []
