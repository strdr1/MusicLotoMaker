"""
GitHub Auto-Updater для Music Loto Maker (приватный режим)
"""

import os
import json
import logging
import zipfile
import shutil
import tempfile
import requests
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

GITHUB_TOKEN = "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"  # ← СЮДА ВСТАВЬТЕ СВОЙ ТОКЕН

class GitHubUpdater:
    def __init__(self, repo_owner="strdr1", repo_name="MusicLotoMaker"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.version_file = os.path.join(self.base_dir, "config", "version.json")
        self.token = GITHUB_TOKEN.strip()
        
        self.current_version = self.get_current_version()
        logger.info(f"✅ GitHub Updater для {repo_owner}/{repo_name}")
        logger.info(f"📁 Текущая версия: {self.current_version}")
        if self.token:
            logger.info("🔑 Используется вшитый токен для доступа к приватному репо")

    def _get_headers(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "MusicLotoMaker-Updater"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def get_current_version(self):
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('version', 'v1.0.0')
            else:
                version = "v1.0.0"
                self.save_version(version)
                return version
        except Exception as e:
            logger.error(f"❌ Ошибка чтения версии: {e}")
            return "v1.0.0"

    def save_version(self, version):
        try:
            config_dir = os.path.dirname(self.version_file)
            os.makedirs(config_dir, exist_ok=True)
            data = {
                "version": version,
                "updated_at": datetime.now().isoformat(),
                "repo": f"{self.repo_owner}/{self.repo_name}"
            }
            with open(self.version_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Версия сохранена: {version}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения версии: {e}")
            return False

    def get_latest_release(self):
        try:
            releases_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
            logger.info(f"🔍 Запрос релиза: {releases_url}")
            response = requests.get(releases_url, headers=self._get_headers(), timeout=10)
            
            if response.status_code == 200:
                release_data = response.json()
                return {
                    "version": release_data.get('tag_name', ''),
                    "download_url": release_data.get('zipball_url', ''),
                    "is_release": True,
                    "message": release_data.get('body', '')
                }
            else:
                logger.warning(f"⚠️ Релизов нет: {response.status_code}")
                logger.debug(f"Ответ GitHub: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения релиза: {e}")
            return None

    def get_latest_commit(self):
        try:
            commits_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits/master"
            logger.info(f"🔍 Запрос коммита: {commits_url}")
            response = requests.get(commits_url, headers=self._get_headers(), timeout=10)
            
            if response.status_code == 200:
                commit_data = response.json()
                commit_hash = commit_data.get('sha', '')[:7]
                return {
                    "version": f"commit-{commit_hash}",
                    "download_url": f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/heads/master.zip",
                    "is_release": False,
                    "commit_info": {
                        "hash": commit_hash,
                        "date": commit_data.get('commit', {}).get('author', {}).get('date', ''),
                        "message": commit_data.get('commit', {}).get('message', '').split('\n')[0]
                    }
                }
            else:
                logger.error(f"❌ Ошибка получения коммита: {response.status_code}")
                logger.debug(f"Ответ GitHub: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения коммита: {e}")
            return None

    def check_for_updates(self):
        try:
            logger.info("🔍 Проверка обновлений...")
            latest_info = self.get_latest_release()
            if not latest_info:
                logger.info("ℹ️ Релизов нет, проверяем коммиты...")
                latest_info = self.get_latest_commit()
            
            if not latest_info:
                return {
                    "success": False,
                    "error": "Не удалось проверить обновления",
                    "current_version": self.current_version,
                    "update_available": False
                }
            
            update_available = self.current_version != latest_info["version"]
            result = {
                "success": True,
                "current_version": self.current_version,
                "latest_version": latest_info["version"],
                "update_available": update_available,
                "is_release": latest_info.get("is_release", False),
                "commit_info": latest_info.get("commit_info", {}),
                "timestamp": datetime.now().isoformat()
            }
            
            if update_available:
                logger.info(f"🔄 Обновление доступно: {self.current_version} → {latest_info['version']}")
                result["message"] = f"Доступно обновление {latest_info['version']}"
            else:
                logger.info(f"✅ У вас последняя версия: {self.current_version}")
                result["message"] = "Установлена последняя версия"
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка проверки обновлений: {e}")
            return {
                "success": False,
                "error": str(e),
                "current_version": self.current_version,
                "update_available": False
            }

    def download_update(self, download_url):
        try:
            logger.info(f"📥 Скачивание: {download_url}")
            temp_dir = tempfile.mkdtemp(prefix="update_")
            zip_path = os.path.join(temp_dir, "update.zip")
            headers = {"User-Agent": "MusicLotoMaker-Updater"}
            response = requests.get(download_url, stream=True, timeout=30, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"❌ Ошибка скачивания: {response.status_code}")
                return {"success": False, "error": f"Ошибка скачивания: {response.status_code}"}
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(zip_path)
            logger.info(f"✅ Скачано: {file_size / 1024 / 1024:.2f} MB")
            return {"success": True, "temp_dir": temp_dir, "zip_path": zip_path, "size": file_size}
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания: {e}")
            return {"success": False, "error": str(e)}

    def apply_update(self, zip_path):
        try:
            logger.info("📦 Применение обновления...")
            extract_dir = tempfile.mkdtemp(prefix="extract_")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            items = os.listdir(extract_dir)
            source_dir = os.path.join(extract_dir, items[0]) if len(items) == 1 else extract_dir
            logger.info(f"📁 Извлечено в: {source_dir}")
            
            updated_count = 0
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, source_dir)
                    dst_path = os.path.join(self.base_dir, rel_path)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    updated_count += 1
            
            logger.info(f"✅ Обновлено файлов: {updated_count}")
            shutil.rmtree(os.path.dirname(zip_path), ignore_errors=True)
            shutil.rmtree(extract_dir, ignore_errors=True)
            
            return {"success": True, "updated_count": updated_count}
        except Exception as e:
            logger.error(f"❌ Ошибка применения: {e}")
            return {"success": False, "error": str(e)}

    def run_update(self):
        try:
            logger.info("🚀 Запуск обновления...")
            check_result = self.check_for_updates()
            if not check_result.get("success"):
                return check_result
            if not check_result.get("update_available"):
                return {"success": False, "message": "Обновлений нет"}
            
            latest_info = self.get_latest_release() or self.get_latest_commit()
            if not latest_info:
                return {"success": False, "error": "Не удалось получить информацию об обновлении"}
            
            download_result = self.download_update(latest_info["download_url"])
            if not download_result.get("success"):
                return download_result
            
            apply_result = self.apply_update(download_result["zip_path"])
            if not apply_result.get("success"):
                return apply_result
            
            new_version = latest_info["version"]
            self.save_version(new_version)
            self.current_version = new_version
            logger.info(f"🎉 Обновление завершено! Новая версия: {new_version}")
            
            return {
                "success": True,
                "message": "Обновление успешно установлено",
                "new_version": new_version,
                "updated_count": apply_result.get("updated_count", 0)
            }
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обновления: {e}")
            return {"success": False, "error": str(e), "message": "Не удалось установить обновление"}

# Создаём экземпляр
updater = GitHubUpdater("strdr1", "MusicLotoMaker")