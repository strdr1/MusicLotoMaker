import dropbox
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
DROPBOX_TOKEN = "sl.u.AGENkMw7usVTcYysulWFK0p_e3QM-iHLOisErxZE2Z5zgTHflbfL02EHGR3JhkoMG6A0F0lQ2yHpX5LnDqnwAwVQsTGfg3ewhX6X1LytBvsQ8pt3Mz3vRu6GYS7jrndM0Bm7o41gBdXW7-uMz9VPmhIyq_g1P_9DcEyYj2rx9G3PZA4H9BSTxYdf4R69MzPxe0H7T7kP7aVwQ4r7e1oyvBUYNXbtwR3Oo1p3g13URikQmUUZPJgbSn4RsAY994Qk1u2z9k5qh4N_j37p0SgBAh46CfYWQTwVVRuemaVxVl1iefSrALaxV6dSmHgzNrgZxge6p5P84w014xeRGPl5kOJCODR9DZlWAbqUrocsJ82zNBXY5pvurAIQBvmKjvwDuDGFai89y0sSlVs3ABifwJtyrGitn3YGaEs5PkqeZpd70aS-GmvpXMKjPWOnerrb7JeSAZG8kY6nRYcrJCqzVJv7DmzOi0vZKXYIMNtS-UIinnimjPbwAk86HL62qyjVc_O08-pwsiy4xIjZYImxQAvwFGBYsuwWSyvWps6fADwFjMv_9ogsluRRjNpP5dAturvS_WocQHXTLkAdsQUGLWPCi7c1Bomy104kN24CtBoxK07KqoAM4Wjlz-VCaQmKHPgv8qCVUAWcJLf-fyWWsWWMpECF_nrbido5DWLVUsrZI5lYFIOxVDePPeaaGFEeHHT3IXrInzc_3enapjwlZwyKZPRTafLxyDmnfLmIs_GgppgooKI0iSkepTipCpKuqpkOkklPZ5_hLbp6389fcjZ8YmFWQ_mQ3uVhUelox0PswCQBcj-8Q8ZkokC_V5pKUMC37T9e5TFkbRduJ6SouRD_ZBBv-0_0I49FyNelsJQSTbLFoooyu-zshnQhcEqfLMs5JZ8nodrrV3VdIQnn4OcHgK2dC0CRSrgkN8ea_iuSmtJqr80h9U52mMSs1dBgD59qbN3nYmr3YmmVN0Y5AjR5ihD6CskuMG5hpQpMrjEwMcJEdftbE6pWu5tasMiGDID-Zp6gztmAhY86FLxK22HFhldfZ2Tfmmfk2lDovZvk2RjtsgFaGKnr2t1Vx3NPCHL8jH4jLRGZ5t84fBFus4k3h3UffKaEfHBe2TcGvegXcoXJjzuMi7KqA2BqCxTlFOFCLh-0MIwa7k_irJ9bQ9KuEOJi1VO-kgnlYRbgSep0Xzbyr_4LGRpHVEGi3rK5qSv5CuxNQATV_THshRf2GDh__Q78D-cjH9Eh3wRgbPPDlsft25_Lo9Dfri26D2ekfhDgTiicQD8n2Xcl6GU_xUQQO5r1dc6pKeRR0IE5rBVJ5t39vmRbrSgUHPh93E8q-SgBxqtGx0nQ3Sg0ZVe_QQOcJtxiNevyCI2Dv0UJ6hDqhZhpVKP820mYtxfQ6pLubx_5DWm8LzqNZYiV2zKNs6RgGNCFgRWkEAhJ_9jvjG9Exw"

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