import dropbox
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
DROPBOX_TOKEN = "sl.u.AGFcSTlNvULMaLUqYtEEUSrZnP7uiPFXSTKYm-XwHotcPVIQ2kTS8-HTJn4r7fXVAOy7qv2JPO_4OMF91st_pgAtScvXTn8SI5XH23htxN8HoWeD0VXthdsvYor5fSgnIK2ftvCDfTlcIfclkUtWCaTswFdeltM3eJaZyI7H66xilZ4-NlH3xfnYm61gdCzsEfARv39xwTsy5aun18gxinWoA4Zl0oniLJ0Ln_TVYxTRlAGczaFFJgLvLNvNXV9OywC5vJ13iouK3Wh8i-4eVZXu7jkBXC6hbs7DkCOT-36ywkB_1MJCihUY83dJlbanyoBWxIpZo6LP91uaefFynEmhKKkCuUF2cvh8G_cXFVD9srxgIC6u68XMLTzsffacgedV-VSoCt77AuRlC5hC2bpM1ITAAQ1kly8ssLqugaaFB4bOqkmNynjkPUdHRMZ1Ho9tW-QJo72XNNCOUX6zDS0i_1FCbrd0rgor4aQs2jFlW9REE6cCK_qutv0xbfbWjiUrRNOcGlnvpQfoLa0TyKCNnwEbfv7Ekh50uSyKADjVXbcsoYMjN_ysfppCcwhmqbYBrdw5pXPDXbemiUfhfrMZ5_LxHJNnh5BKkJveXSce3PVrgwcuSooBOtiDYWQSCZvmi8qPvS0TD0cND9hD2JwG9gH14pRlr3YGISkfdQfhKwUb5pxdtRsFzU3aEqRjbpYAHRP-GU5vO2IWN3HsFlZj5wuvMK6imonzghbjnbzYj8XQxe0CDDeCTtULSLnJezAW5Sgc093YexiUpfcddDqe1Au6AOMd50nPb0rNoEjsDGJUaU3BCgw-HgMJHJdx4IRQZRLl8uV3nidJc5WcjM-h9YR0ChiIRpsKeJT7XIjXAUs1vCLZPAvO7K22p48q0m8RWypVlW9pyFuBeD00FTFkhIF5-XkcAYK9rsShy6EEurcWtr75kyetP7SCyFocsR6MfM6dq50gADtSBiyrRw5WV5pC_GT7mwTJvK87hbv7KdTvdMZovL_EX6Bcjyx4GL0IWN7ccW5On1DXJ2PmAH0RAP585190ox_LrVY8izOQUMCw39JYXreYeF_mu36SDF7iu2cJ6pMOyxG0Jwj-DvCzD4yge7xYPZRPOUvfef5Nfsr8ZfP4-i3VzEOBetGx_ZFWfZjidQvyPPmNmGhebeAGqzwVdpV-4oeKTGnC-f9pB5voiBdzvZzVUsZujM153R_3CMBLMiF-vWMUOB7fYrf84oXi1NJvaS0E8fI9DMdXOThTyUeUw_-H-0e1advilK6aoc3J56nkQwsz2X7Iv_MntguEJ7XJGFUDn9xoW6sXGlVIyJ6Dxq7KXH5qkelbrCy6Z3pSaTtGTH9XZ7z7buZblDed-KnfwXHXTb3a-Gkb4ooqPWpInR6PEshhoYPExz7mdBulyAFzEDnBmQERjzfn"
class DropboxStorage:
    def __init__(self):
        self.dbx = dropbox.Dropbox(DROPBOX_TOKEN)

    def upload_artist_photo(self, image_path, artist_name):
        try:
            safe_name = artist_name.replace(" ", "_").lower()
            filename = f"{safe_name}{Path(image_path).suffix}"
            dropbox_path = f"/artist_photos/{filename}"

            with open(image_path, "rb") as f:
                self.dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)

            try:
                link = self.dbx.sharing_create_shared_link_with_settings(dropbox_path)
            except dropbox.exceptions.ApiError as e:
                if isinstance(e.error, dropbox.sharing.CreateSharedLinkWithSettingsError) and e.error.is_shared_link_already_exists():
                    # Получаем существующую ссылку
                    links = self.dbx.sharing_list_shared_links(path=dropbox_path, direct_only=True)
                    if links.links:
                        link = links.links[0]
                    else:
                        raise
                else:
                    raise

            return {
                "artist_name": artist_name,
                "filename": filename,
                "dropbox_path": dropbox_path,
                "download_url": link.url.replace("?dl=0", "?raw=1")
            }
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки фото в Dropbox: {e}")
            return None

    def list_artist_photos(self):
        try:
            result = self.dbx.files_list_folder("/artist_photos")
            photos = []
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    try:
                        link = self.dbx.sharing_create_shared_link_with_settings(entry.path_lower)
                    except dropbox.exceptions.ApiError as e:
                        if isinstance(e.error, dropbox.sharing.CreateSharedLinkWithSettingsError) and e.error.is_shared_link_already_exists():
                            links = self.dbx.sharing_list_shared_links(path=entry.path_lower, direct_only=True)
                            if links.links:
                                link = links.links[0]
                            else:
                                raise
                        else:
                            raise

                    photos.append({
                        "filename": entry.name,
                        "artist_name": Path(entry.name).stem.replace("_", " "),
                        "download_url": link.url.replace("?dl=0", "?raw=1")
                    })
            return photos
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка фото из Dropbox: {e}")
            return []



    def delete_artist_photo(self, dropbox_path):
        try:
            self.dbx.files_delete_v2(dropbox_path)
            logger.info(f"✅ Фото удалено из Dropbox: {dropbox_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления фото: {e}")
            return False

    def upload_base_pptx(self, file_path):
        try:
            dropbox_path = "/base.pptx"
            with open(file_path, "rb") as f:
                self.dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            link = self.dbx.sharing_create_shared_link_with_settings(dropbox_path)
            logger.info("✅ base.pptx загружен в Dropbox")
            return {
                "file_id": dropbox_path,
                "download_url": link.url.replace("?dl=0", "?raw=1")
            }
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки base.pptx: {e}")
            return None

    def download_base_pptx(self, local_path):
        try:
            dropbox_path = "/base.pptx"
            metadata, response = self.dbx.files_download(dropbox_path)
            with open(local_path, "wb") as f:
                f.write(response.content)
            logger.info(f"✅ base.pptx скачан: {local_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания base.pptx: {e}")
            return False

