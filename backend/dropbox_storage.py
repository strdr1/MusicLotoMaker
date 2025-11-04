import dropbox
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
DROPBOX_TOKEN = "sl.u.AGEDsGIZk5WnolPpuc9yxhhtHKFAbu0pIMH4g3nl6BLTXnZVhm-kbLWZOnLHofUep6a-glyW346z1pRltUob8fx1e5Ihm47huC17oPpSfj4OCulvL_FCfk6tNI3BLBDFA0ZVflvuSGAsS_Lof1y76L0fX7idd6nWrY_qzm0koodkGpvh0uo-BfuAPlQc_mxm1NXxy8porxWnC-bH9hgQcMVTTsJ4-9ihW_FBQpB71Y3d-ynHjBkCNP4-q7__eBJYPyMlPImgtBmlEl4N29Oz1ZfemngMonIb7hNtFXU9lA24CMrWStt1vw00NVlCZmr7GvMj2QgdcX035cXUbvLhMH3gpZLmBaRSf9HNxpQCCeeFRXdql2k3xS7QmvwENBo_i2o5S_ryePjz2ckhXwIfvlPc93SAb-mIDiKt0JCZl7XUowUnJtDwy-SrfYpaSAJmFG68j_uDWK67my4-klVqDrBq0kDITb7UJoonrNBcA7xUne5w-siOgU3FoGC63bqmwnKz2pvHWqtGhMzhDsBAmiB0vkNjwpW0xlgx0z3HotVum94OoArAFuiVVrQoRDIdxWIDcTd0XEMAf_RSqECPx-CxrWJlkJjw-F1MCjhSzse3R8JUPfTo7SIujgq9lXfqBWr5E9mUvwBrIXa1-Upj-BzallQDCBoSDwS8PJ_WQHGMIdt2_SwmNQDIi27P-2ODZBHI3N-bPurvNTtyWWKTFgw59ATto4sZEXzTzj8F3VW_dOF9g9XtcvqgCClFIAQ6PQGltx7yeq_GUQZPHncRo2Q6AMUVM4sWUMpc4mAxrUOKYzmtqsaPkse3rzks-1ZlQkxlsxpvJc8uMhJ8N3VFrm1k7_s3qx4ufCOjuKm01CLfLmKsFd_cRKI-2UopTPzaBnDbmc_mSc42beLqLy93TH6bBx2Xwid3GZMmDof4fwTTYl-1NTWg_YEWzhOQR42Ut34cJE0W2h0wLE438bcIna1tsW8gU473Bp2gYurhKVBaFQx2lvoPvTcmsiIjNFWXTOgjIWdUGSF7QObovRGwNkodxk1rGRrTgzbIuvFHzQBbwaxNLZAEpJvZd2eDbPhkslrujabLgRdsfservF91ueUZqhr5-mN_RqWJP5t3-D9rYPP9t6YBVzVepliw1KPw_PsZ2M0DbLbJTC0I_S1ggRJQT0Cn-ehrNrYK_Gj_Dd2j6fzcJlcLgMjUnQXAdluFZBi635PK8Iyg325zJPZq00ohFLjB32MPtQ2twJhXgjf5jduXacE-i5xxnu55F6Y5Y55i16_0YMfWPDTfj5gJlIt5iOwS9ZJhNvaFEroZonyl_WBGjY5kOcKSpg0F8Hb9tKvBZ8cc8cZLV4UVlAyEEVzBFFmMkwMRQORiLIzOnvnC6o7OwohtWld-uCj9qFjmyBc0fh4sEJ1tpvzJnR27h7pZ"


class DropboxStorage:
    def __init__(self):
        self.dbx = dropbox.Dropbox(DROPBOX_TOKEN)

    def download_base_pptx(self, local_path):
        """Скачать base.pptx из Dropbox если локального нет"""
        try:
            if os.path.exists(local_path):
                logger.info(f"✅ base.pptx уже существует: {local_path}")
                return True
                
            dropbox_path = "/base.pptx"
            metadata, response = self.dbx.files_download(dropbox_path)
            with open(local_path, "wb") as f:
                f.write(response.content)
            logger.info(f"✅ base.pptx скачан: {local_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания base.pptx: {e}")
            return False

    def download_artist_photos(self, local_dir):
        """Скачать фото артистов из Dropbox если локальной папки нет или она пуста"""
        try:
            os.makedirs(local_dir, exist_ok=True)
            
            # Проверяем, есть ли уже файлы
            local_files = os.listdir(local_dir)
            if local_files:
                logger.info(f"✅ В папке {local_dir} уже есть {len(local_files)} файлов")
                return True
                
            # Скачиваем фото если папка пустая
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
            
            logger.info(f"📥 Скачано {downloaded} фото артистов")
            return downloaded > 0
            
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания фото артистов: {e}")
            return False

    def list_artist_photos(self):
        """Только для информации - какие фото есть в Dropbox"""
        try:
            result = self.dbx.files_list_folder("/artists")
            photos = []
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    photos.append({
                        "filename": entry.name,
                        "artist_name": Path(entry.name).stem.replace("_", " "),
                        "dropbox_path": entry.path_lower
                    })
            return photos
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка фото из Dropbox: {e}")
            return []