#!/usr/bin/env python3
import os
import sys
import time
import subprocess

# Добавляем путь к проекту
project_dir = r"F:\1\MusicLotoMaker\MusicLotoMaker"
sys.path.insert(0, project_dir)

print("🔄 Перезапуск Music Loto Maker...")
time.sleep(2)

# Запускаем сервер
os.chdir(project_dir)
subprocess.Popen([sys.executable, "server.py"])
print("✅ Сервер перезапущен!")
