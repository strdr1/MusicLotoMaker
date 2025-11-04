import dropbox
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
DROPBOX_TOKEN = "sl.u.AGFjsME0grwoeKwXqLsrva97cMKjPSKWLje2jyrS4uU_SSHXw84DyxOsXXi1pOmN1TywyopkbxNT0Cp6WZB6pkMGz6Oi6cZFQ7pTMdjKCSVY5VYXv6Fak1_9UjCxInRzzOKgqY_Mx2YdHQMsVX221OVsbM8lY_986-xpvXhymQiAvTAu2qrGR_wM4IjobpS7_p5yGo_ZGtdVIU4gYKGo4WKwKoTwCO1i41uTvitIk96QEg8teqttgIMf34V2uPCkoVhmiNQFzQF5vcfwnp7Pon0KLiGW2XDAhLfVH6TuCdmXZeI3IV6pnu8Yiwpo7jXfOMdxKIyqp7TkjhqXwmdG8B38WpfNTaSP3S3KKW6J2xCeVTJtX0wYYcQ4RM1ae2G_rd38ua5vPOdVK5geM7NVYazvjXLWhzOADe4yX6n3MhLaLHvZyTb-zBhSn1cEco53s0XncvNU2gNFZxAi-XcZqujGjR78I3a2GQiZBzu3MuUDSV1W46On1QeArl3i2x1FgiOhgocmBsIUXJOSipfu-RTbh2UgGq_CcgU6y8g2etcGNUEYFoqcyoqwRFRMAj4pJbsensSbxKeKeOdpRXlcstSxL8_sanns49ZPHwVa513UTD4-EVQyihbkvSG9vNd4omzAh2gf4S7lTVlv2oV6gmPEUEn1NCuaA7__kedcXery8sdn5DPDAEp4yOU9KGLd16p4q2PdexHS1doJMS4Ydes0XPT9bB0CVxj_AfxeKMO4q0Oj9wfe4keT_9Niwxm6TmtgCrA5UdlMmcuvtQ5rwQpS4fNsnBvjmEhInHf5SSnThqF0hX8mFWYzD1J0p_rb4Vb1PzMPhV6ESP_3eRiWTnTToYO9MnVXITfAqOWsJ6PO0mLq62ZpYkrYdqrVPQLjXODDztwB3c6-5TDnEkaq6PzLftXY8T8dV_KhRdg_XdghYVIFJGDQTKAYI2ZYfZn-MOjFr25B-JLZnhSe40XkqyETOZ1lKGaLjjYH_dRP9AYdZH_UM4W_iFjzXQL5Vy9ib1ZnCVG9BpmqSFvmX_608YDeKr41cEw7gQanGb1oeMjolhTS_H84jWJJiz1YhEC3lpE2-UXXTGaEmrWX470_uXivdcBKB5NZyOxEQOIuSmtSbSvd38khzFkNbO0rf2avhjFAuUaVPNm6JJS84nLC5IwKsfkHEYL9A-OJBmJyETM437Z8GGgGcoq7kaVsZD4WDIPpWcH1Tg-UIpU1BowbgcekbD_C810DrQL019VvTx7kiFKEoWazGZdpLRVwyAtMVZOh_EbsVNJxfjs3ASc289y5aBbge8jjHUrVFfyrQlf3F0B76qWw3xKAZbtXMHGM5XqNx5bengvCjn5LFkmjVHCgNXRh6d3HLYEkyYkmvdyiTef6RYx5JUOkQ1qiIjJyjKmG6qvsta2NRSE2RzzMI0dx"
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