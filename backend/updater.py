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

logger = logging.getLogger(__name__)

class GitHubUpdater:
    def __init__(self, repo_owner="strdr1", repo_name="MusicLotoMaker", branch="master"):
        """
        Инициализация автообновителя
        
        Args:
            repo_owner: Владелец репозитория (strdr1)
            repo_name: Название репозитория (MusicLotoMaker)
            branch: Ветка для обновлений (master)
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch
        
        # Базовые URL GitHub API
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.raw_base = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}"
        self.download_url = f"https://github.com/{repo_owner}/{repo_name}/archive/refs/heads/{branch}.zip"
        
        # Пути проекта
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.version_file = os.path.join(self.base_dir, "config", "version.json")
        
        # Инициализация текущей версии
        self.current_version = self.get_current_version()
        
        logger.info(f"✅ GitHub Updater инициализирован для {repo_owner}/{repo_name} ({branch})")
        logger.info(f"📁 Текущая версия: {self.current_version}")
    
    def get_current_version(self):
        """Получить текущую версию из файла или установить по умолчанию"""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    version_data = json.load(f)
                    return version_data.get('version', '1.0.0')
            else:
                # Если файла нет, пытаемся определить версию из git
                try:
                    git_dir = os.path.join(self.base_dir, ".git")
                    if os.path.exists(git_dir):
                        result = subprocess.run(
                            ["git", "rev-parse", "--short", "HEAD"],
                            cwd=self.base_dir,
                            capture_output=True,
                            text=True,
                            encoding='utf-8'
                        )
                        if result.returncode == 0:
                            commit_hash = result.stdout.strip()
                            version = f"1.0.0-git-{commit_hash}"
                            
                            # Сохраняем в файл
                            self.save_version(version)
                            return version
                except:
                    pass
                
                # Если git не доступен, используем дату
                version = f"1.0.0-{datetime.now().strftime('%Y%m%d')}"
                self.save_version(version)
                return version
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения текущей версии: {e}")
            return "1.0.0-unknown"
    
    def save_version(self, version):
        """Сохранить версию в файл"""
        try:
            config_dir = os.path.dirname(self.version_file)
            os.makedirs(config_dir, exist_ok=True)
            
            version_data = {
                "version": version,
                "updated_at": datetime.now().isoformat(),
                "repo": f"{self.repo_owner}/{self.repo_name}",
                "branch": self.branch
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
            # Получаем информацию о последнем коммите
            commits_url = f"{self.api_base}/commits/{self.branch}"
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "MusicLotoMaker-Updater"
            }
            
            response = requests.get(commits_url, headers=headers, timeout=10)
            if response.status_code == 200:
                commit_data = response.json()
                commit_hash = commit_data.get('sha', '')[:7]
                commit_date = commit_data.get('commit', {}).get('author', {}).get('date', '')
                
                # Формируем версию из хэша коммита
                latest_version = f"1.0.0-git-{commit_hash}"
                
                # Получаем сообщение коммита для информации
                commit_message = commit_data.get('commit', {}).get('message', '').split('\n')[0]
                
                return {
                    "version": latest_version,
                    "commit_hash": commit_hash,
                    "commit_date": commit_date,
                    "commit_message": commit_message,
                    "update_available": latest_version != self.current_version,
                    "is_newer": self.is_version_newer(latest_version, self.current_version)
                }
            else:
                logger.error(f"❌ Ошибка получения версии с GitHub: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка соединения с GitHub: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения последней версии: {e}")
            return None
    
    def is_version_newer(self, version1, version2):
        """Сравнить две версии"""
        try:
            # Простое сравнение по дате или хэшу
            if 'git-' in version1 and 'git-' in version2:
                # Сравниваем хэши коммитов
                hash1 = version1.split('git-')[-1]
                hash2 = version2.split('git-')[-1]
                return hash1 != hash2
            
            # Для версий с датой
            if '-' in version1 and '-' in version2:
                date1 = version1.split('-')[-1]
                date2 = version2.split('-')[-1]
                return date1 > date2
            
            return version1 != version2
            
        except:
            return version1 != version2
    
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
            
            update_available = latest_info["update_available"] and latest_info["is_newer"]
            
            result = {
                "success": True,
                "current_version": self.current_version,
                "latest_version": latest_info["version"],
                "update_available": update_available,
                "commit_info": {
                    "hash": latest_info["commit_hash"],
                    "date": latest_info["commit_date"],
                    "message": latest_info["commit_message"]
                },
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
    
    def download_update(self):
        """Скачать обновление с GitHub"""
        try:
            logger.info("📥 Скачивание обновления с GitHub...")
            
            # Создаем временную директорию
            temp_dir = tempfile.mkdtemp(prefix="music_loto_update_")
            zip_path = os.path.join(temp_dir, "update.zip")
            
            # Скачиваем ZIP архив
            response = requests.get(self.download_url, stream=True, timeout=30)
            if response.status_code != 200:
                logger.error(f"❌ Ошибка скачивания: {response.status_code}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {
                    "success": False,
                    "error": f"Ошибка скачивания: {response.status_code}"
                }
            
            # Сохраняем ZIP файл
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Логируем прогресс каждые 10%
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            if percent % 10 < 0.1:
                                logger.info(f"📥 Прогресс загрузки: {percent:.1f}%")
            
            logger.info(f"✅ Обновление скачано: {downloaded / 1024 / 1024:.2f} MB")
            
            return {
                "success": True,
                "temp_dir": temp_dir,
                "zip_path": zip_path,
                "downloaded_size": downloaded,
                "message": "Обновление успешно скачано"
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания обновления: {e}")
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
            
            # Распаковываем ZIP
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
            logger.error(f"❌ Ошибка распаковки обновления: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def backup_current_files(self):
        """Создать резервную копию текущих файлов"""
        try:
            logger.info("💾 Создание резервной копии...")
            
            backup_dir = os.path.join(self.base_dir, "backup", f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(backup_dir, exist_ok=True)
            
            # Файлы и папки для резервного копирования
            items_to_backup = [
                "frontend",
                "backend",
                "config",
                "requirements.txt",
                "server.py"
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
                    logger.debug(f"✅ Резервная копия: {item}")
            
            logger.info(f"✅ Создана резервная копия: {backup_dir} ({len(backed_up)} элементов)")
            
            return {
                "success": True,
                "backup_dir": backup_dir,
                "backed_up_items": backed_up
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания резервной копии: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def apply_update(self, source_dir):
        """Применить обновление"""
        try:
            logger.info("🔄 Применение обновления...")
            
            # Список файлов и папок для обновления
            update_items = [
                "frontend",
                "backend",
                "config",
                "requirements.txt",
                "server.py",
                "processors",
                "modules",
                "static",
                "templates"
            ]
            
            updated_items = []
            
            for item in update_items:
                source_path = os.path.join(source_dir, item)
                dest_path = os.path.join(self.base_dir, item)
                
                if os.path.exists(source_path):
                    if os.path.isfile(source_path):
                        # Обновляем файл
                        shutil.copy2(source_path, dest_path)
                        updated_items.append(item)
                        logger.info(f"✅ Обновлен файл: {item}")
                    else:
                        # Обновляем папку
                        if os.path.exists(dest_path):
                            shutil.rmtree(dest_path)
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
        """Запустить полный процесс обновления"""
        try:
            logger.info("🚀 Запуск процесса обновления...")
            
            # 1. Скачиваем обновление
            download_result = self.download_update()
            if not download_result.get("success"):
                return download_result
            
            temp_dir = download_result["temp_dir"]
            zip_path = download_result["zip_path"]
            
            # 2. Распаковываем
            extract_result = self.extract_update(temp_dir, zip_path)
            if not extract_result.get("success"):
                shutil.rmtree(temp_dir, ignore_errors=True)
                return extract_result
            
            source_dir = extract_result["source_dir"]
            
            # 3. Создаем резервную копию
            backup_result = self.backup_current_files()
            if not backup_result.get("success"):
                logger.warning(f"⚠️ Ошибка резервного копирования: {backup_result.get('error')}")
                # Продолжаем без резервной копии
            
            # 4. Применяем обновление
            update_result = self.apply_update(source_dir)
            if not update_result.get("success"):
                # TODO: Восстановление из резервной копии
                return update_result
            
            # 5. Обновляем версию
            latest_info = self.get_latest_version()
            if latest_info:
                new_version = latest_info["version"]
                self.save_version(new_version)
                self.current_version = new_version
            else:
                new_version = f"1.0.0-updated-{datetime.now().strftime('%Y%m%d_%H%M')}"
                self.save_version(new_version)
                self.current_version = new_version
            
            # 6. Очищаем временные файлы
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"🎉 Обновление успешно завершено! Новая версия: {new_version}")
            
            return {
                "success": True,
                "message": "Обновление успешно установлено",
                "new_version": new_version,
                "backup_created": backup_result.get("success", False),
                "backup_dir": backup_result.get("backup_dir"),
                "updated_items": update_result.get("updated_items", [])
            }
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обновления: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Не удалось установить обновление"
            }
    
    def restart_application(self):
        """Перезапустить приложение"""
        try:
            logger.info("🔄 Перезапуск приложения...")
            
            # Эта функция должна быть вызвана извне после ответа клиенту
            # Здесь просто логируем и возвращаем инструкции
            
            restart_script = os.path.join(self.base_dir, "restart.py")
            
            # Создаем скрипт перезапуска
            restart_code = f'''#!/usr/bin/env python3
import os
import sys
import time
import subprocess

# Добавляем путь к проекту
project_dir = r"{self.base_dir}"
sys.path.insert(0, project_dir)

print("🔄 Перезапуск Music Loto Maker...")
time.sleep(2)

# Запускаем сервер
os.chdir(project_dir)
subprocess.Popen([sys.executable, "server.py"])
print("✅ Сервер перезапущен!")
'''

            with open(restart_script, 'w', encoding='utf-8') as f:
                f.write(restart_code)
            
            # Делаем скрипт исполняемым (для Linux/Mac)
            if os.name != 'nt':
                os.chmod(restart_script, 0o755)
            
            return {
                "success": True,
                "message": "Приложение готово к перезапуску",
                "restart_script": restart_script,
                "instructions": "Запустите restart.py для завершения обновления"
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания скрипта перезапуска: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Создаем глобальный экземпляр обновителя с вашими данными GitHub
updater = GitHubUpdater(
    repo_owner="strdr1",
    repo_name="MusicLotoMaker",
    branch="master"
)