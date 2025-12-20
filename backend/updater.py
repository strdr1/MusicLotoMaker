"""
GitHub Auto-Updater для Music Loto Maker
Автоматически проверяет и устанавливает обновления с GitHub
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
import subprocess
import sys
import re

logger = logging.getLogger(__name__)

class GitHubUpdater:
    def __init__(self, repo_owner="strdr1", repo_name="MusicLotoMaker", use_tags=True):
        """
        Инициализация автообновителя
        
        Args:
            repo_owner: strdr1
            repo_name: MusicLotoMaker
            use_tags: Использовать теги версий (True) или коммиты (False)
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.use_tags = use_tags
        
        # Базовые URL GitHub API
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.raw_base = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}"
        
        # Пути проекта
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.version_file = os.path.join(self.base_dir, "config", "version.json")
        
        # Инициализация текущей версии
        self.current_version = self.get_current_version()
        
        logger.info(f"✅ GitHub Updater инициализирован для {repo_owner}/{repo_name}")
        logger.info(f"📁 Текущая версия: {self.current_version}")
    
    def get_current_version(self):
        """Получить текущую версию"""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    version_data = json.load(f)
                    return version_data.get('version', 'v1.0.0')
            else:
                # Если файла нет, используем дефолтную версию
                version = "v1.0.0"
                self.save_version(version)
                return version
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения версии: {e}")
            return "v1.0.0"
    
    def is_valid_version(self, version):
        """Проверить что версия соответствует формату vX.X.X.X"""
        pattern = r'^v\d+(\.\d+)*$'
        return re.match(pattern, version) is not None
    
    def compare_versions(self, v1, v2):
        """Сравнить две версии. Возвращает: -1 если v1 < v2, 0 если равны, 1 если v1 > v2"""
        try:
            # Убираем 'v' и разбиваем на части
            v1_parts = [int(x) for x in v1.lstrip('v').split('.')]
            v2_parts = [int(x) for x in v2.lstrip('v').split('.')]
            
            # Дополняем до одинаковой длины (макс 4 части)
            max_len = 4
            v1_parts = (v1_parts + [0] * max_len)[:max_len]
            v2_parts = (v2_parts + [0] * max_len)[:max_len]
            
            # Сравниваем по частям
            for i in range(max_len):
                if v1_parts[i] < v2_parts[i]:
                    return -1
                elif v1_parts[i] > v2_parts[i]:
                    return 1
            
            return 0
        except:
            return 0
    
    def save_version(self, version):
        """Сохранить версию в файл"""
        try:
            config_dir = os.path.dirname(self.version_file)
            os.makedirs(config_dir, exist_ok=True)
            
            version_data = {
                "version": version,
                "updated_at": datetime.now().isoformat(),
                "repo": f"{self.repo_owner}/{self.repo_name}",
                "timestamp": datetime.now().isoformat()
            }
            
            with open(self.version_file, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Версия сохранена: {version}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения версии: {e}")
            return False
    
    def get_latest_version(self):
        """Получить последнюю версию с GitHub"""
        try:
            if self.use_tags:
                # Получаем последний тег
                tags_url = f"{self.api_base}/tags"
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "MusicLotoMaker-Updater"
                }
                
                response = requests.get(tags_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    tags = response.json()
                    
                    # Ищем валидные теги версий
                    valid_tags = []
                    for tag in tags:
                        tag_name = tag.get('name', '')
                        if self.is_valid_version(tag_name):
                            valid_tags.append(tag_name)
                    
                    if valid_tags:
                        # Сортируем по версии
                        valid_tags.sort(key=lambda x: self.compare_versions('v0.0.0', x), reverse=True)
                        latest_tag = valid_tags[0]
                        
                        # Получаем информацию о коммите тега
                        tag_url = f"{self.api_base}/git/ref/tags/{latest_tag}"
                        tag_response = requests.get(tag_url, headers=headers, timeout=10)
                        
                        commit_info = {}
                        if tag_response.status_code == 200:
                            tag_data = tag_response.json()
                            commit_sha = tag_data.get('object', {}).get('sha', '')
                            if commit_sha:
                                commit_url = f"{self.api_base}/commits/{commit_sha}"
                                commit_response = requests.get(commit_url, headers=headers, timeout=10)
                                if commit_response.status_code == 200:
                                    commit_data = commit_response.json()
                                    commit_info = {
                                        'hash': commit_sha[:7],
                                        'date': commit_data.get('commit', {}).get('author', {}).get('date', ''),
                                        'message': commit_data.get('commit', {}).get('message', '').split('\n')[0]
                                    }
                        
                        return {
                            "version": latest_tag,
                            "download_url": f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/tags/{latest_tag}.zip",
                            "commit_info": commit_info,
                            "is_tag": True
                        }
            
            # Если тегов нет или не используем теги - получаем последний коммит
            commits_url = f"{self.api_base}/commits/master"
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "MusicLotoMaker-Updater"
            }
            
            response = requests.get(commits_url, headers=headers, timeout=10)
            if response.status_code == 200:
                commit_data = response.json()
                commit_hash = commit_data.get('sha', '')[:7]
                commit_date = commit_data.get('commit', {}).get('author', {}).get('date', '')
                commit_message = commit_data.get('commit', {}).get('message', '').split('\n')[0]
                
                latest_version = f"commit-{commit_hash}"
                
                return {
                    "version": latest_version,
                    "download_url": f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/heads/master.zip",
                    "commit_info": {
                        "hash": commit_hash,
                        "date": commit_date,
                        "message": commit_message
                    },
                    "is_tag": False
                }
            
            return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения версии: {e}")
            return None
    
    def check_for_updates(self):
        """Проверить наличие обновлений"""
        try:
            logger.info("🔍 Проверка обновлений...")
            
            latest_info = self.get_latest_version()
            if not latest_info:
                return {
                    "success": False,
                    "error": "Не удалось проверить обновления",
                    "current_version": self.current_version,
                    "update_available": False
                }
            
            # Проверяем наличие обновления
            update_available = False
            if self.current_version and latest_info["version"]:
                if latest_info.get("is_tag", False) and self.is_valid_version(latest_info["version"]):
                    # Сравниваем теги версий
                    comparison = self.compare_versions(self.current_version, latest_info["version"])
                    update_available = comparison < 0
                else:
                    # Для коммитов просто проверяем равенство
                    update_available = self.current_version != latest_info["version"]
            
            result = {
                "success": True,
                "current_version": self.current_version,
                "latest_version": latest_info["version"],
                "update_available": update_available,
                "is_tag": latest_info.get("is_tag", False),
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
        """Скачать обновление"""
        try:
            logger.info(f"📥 Скачивание обновления: {download_url}")
            
            # Создаем временную директорию
            temp_dir = tempfile.mkdtemp(prefix="music_loto_update_")
            zip_path = os.path.join(temp_dir, "update.zip")
            
            # Скачиваем
            headers = {"User-Agent": "MusicLotoMaker-Updater"}
            response = requests.get(download_url, stream=True, timeout=30, headers=headers)
            if response.status_code != 200:
                logger.error(f"❌ Ошибка скачивания: {response.status_code}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {
                    "success": False,
                    "error": f"Ошибка скачивания: {response.status_code}"
                }
            
            # Сохраняем
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(zip_path)
            logger.info(f"✅ Обновление скачано: {file_size / 1024 / 1024:.2f} MB")
            
            return {
                "success": True,
                "temp_dir": temp_dir,
                "zip_path": zip_path,
                "downloaded_size": file_size,
                "message": "Обновление успешно скачано"
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def extract_update(self, temp_dir, zip_path):
        """Распаковать обновление"""
        try:
            logger.info("📦 Распаковка обновления...")
            
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            
            # Распаковываем
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Ищем основную директорию
            extracted_items = os.listdir(extract_dir)
            if len(extracted_items) == 1:
                source_dir = os.path.join(extract_dir, extracted_items[0])
            else:
                source_dir = extract_dir
            
            logger.info(f"✅ Обновление распаковано в: {source_dir}")
            
            return {
                "success": True,
                "source_dir": source_dir,
                "extract_dir": extract_dir
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка распаковки: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def backup_current_files(self):
        """Создать резервную копию"""
        try:
            logger.info("💾 Создание резервной копии...")
            
            backup_dir = os.path.join(self.base_dir, "backup", f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(backup_dir, exist_ok=True)
            
            # Что будем бэкапить
            items_to_backup = [
                "frontend",
                "backend",
                "static",
                "config",
                "requirements.txt",
                "server.py",
                "updater.py"
            ]
            
            backed_up = []
            
            for item in items_to_backup:
                item_path = os.path.join(self.base_dir, item)
                if os.path.exists(item_path):
                    dest_path = os.path.join(backup_dir, item)
                    
                    if os.path.isfile(item_path):
                        shutil.copy2(item_path, dest_path)
                    else:
                        shutil.copytree(item_path, dest_path, dirs_exist_ok=True)
                    
                    backed_up.append(item)
            
            logger.info(f"✅ Создана резервная копия: {backup_dir}")
            
            return {
                "success": True,
                "backup_dir": backup_dir,
                "backed_up_items": backed_up
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания бэкапа: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def apply_update(self, source_dir):
        """Применить обновление"""
        try:
            logger.info("🔄 Применение обновления...")
            
            # Что обновляем
            update_items = [
                "frontend",
                "backend", 
                "static",
                "config",
                "requirements.txt",
                "server.py",
                "updater.py",
                "processors",
                "modules",
                "templates"
            ]
            
            # Также ищем HTML файлы в корне
            for item in os.listdir(source_dir):
                if item.lower().endswith(('.html', '.htm')):
                    update_items.append(item)
            
            updated_items = []
            
            for item in update_items:
                source_path = os.path.join(source_dir, item)
                dest_path = os.path.join(self.base_dir, item)
                
                if os.path.exists(source_path):
                    if os.path.isfile(source_path):
                        # Обновляем файл
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(source_path, dest_path)
                        updated_items.append(item)
                        logger.info(f"✅ Обновлен файл: {item}")
                    else:
                        # Обновляем папку
                        if os.path.exists(dest_path):
                            shutil.rmtree(dest_path)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copytree(source_path, dest_path)
                        updated_items.append(item)
                        logger.info(f"✅ Обновлена папка: {item}")
            
            logger.info(f"✅ Обновление применено: {len(updated_items)} элементов")
            
            return {
                "success": True,
                "updated_items": updated_items
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения обновления: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def run_update(self):
        """Запустить процесс обновления"""
        try:
            logger.info("🚀 Запуск процесса обновления...")
            
            # 1. Получаем последнюю версию
            latest_info = self.get_latest_version()
            if not latest_info:
                return {
                    "success": False,
                    "error": "Не удалось получить информацию об обновлении"
                }
            
            # 2. Скачиваем
            download_result = self.download_update(latest_info["download_url"])
            if not download_result.get("success"):
                return download_result
            
            temp_dir = download_result["temp_dir"]
            zip_path = download_result["zip_path"]
            
            # 3. Распаковываем
            extract_result = self.extract_update(temp_dir, zip_path)
            if not extract_result.get("success"):
                shutil.rmtree(temp_dir, ignore_errors=True)
                return extract_result
            
            source_dir = extract_result["source_dir"]
            
            # 4. Создаем бэкап
            backup_result = self.backup_current_files()
            
            # 5. Применяем обновление
            update_result = self.apply_update(source_dir)
            if not update_result.get("success"):
                shutil.rmtree(temp_dir, ignore_errors=True)
                return update_result
            
            # 6. Обновляем версию
            new_version = latest_info["version"]
            self.save_version(new_version)
            self.current_version = new_version
            
            # 7. Очищаем временные файлы
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"🎉 Обновление завершено! Новая версия: {new_version}")
            
            return {
                "success": True,
                "message": "Обновление успешно установлено",
                "new_version": new_version,
                "backup_created": backup_result.get("success", False),
                "updated_items": update_result.get("updated_items", [])
            }
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обновления: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Не удалось установить обновление"
            }

# Создаем глобальный экземпляр
updater = GitHubUpdater(
    repo_owner="strdr1",
    repo_name="MusicLotoMaker",
    use_tags=True
)