import threading
import time
import os
import sys
import subprocess
import importlib.util

# Добавляем backend в путь импорта
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

def ensure_playwright_chromium():
    """
    Проверяет, установлен ли playwright и его браузер chromium.
    Если нет — устанавливает его.
    """
    try:
        import playwright
        from playwright.sync_api import sync_playwright
        # Пробуем открыть браузер
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("✅ Playwright и Chromium уже установлены и работают.")
    except ImportError:
        print("❌ Playwright не установлен.")
        return
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "Browser was not found" in str(e):
            print("❌ Chromium не установлен. Запускаю playwright install chromium...")
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                print("✅ Chromium успешно установлен.")
            except subprocess.CalledProcessError:
                print("❌ Не удалось установить Chromium.")
                input("Нажмите Enter для выхода...")
                sys.exit(1)
        else:
            print(f"❌ Неизвестная ошибка в Playwright: {e}")
            input("Нажмите Enter для выхода...")
            sys.exit(1)


try:
    from backend.server import app
    import uvicorn
    print("✅ Все импорты успешны")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("📦 Установите зависимости: pip install fastapi uvicorn python-pptx reportlab pydub pillow aiofiles pywebview playwright")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# Убедимся, что playwright и chromium установлены
ensure_playwright_chromium()

def run_server():
    """Запуск сервера FastAPI"""
    print("🌐 Запуск сервера на http://127.0.0.1:8000")
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error", access_log=False)
    except Exception as e:
        print(f"❌ Ошибка сервера: {e}")

def check_server_ready():
    """Проверка готовности сервера"""
    import requests
    for i in range(30):  # Пробуем 30 раз с интервалом 1 секунда
        try:
            response = requests.get("http://127.0.0.1:8000/api/status", timeout=1)
            if response.status_code == 200:
                print("✅ Сервер готов!")
                return True
        except:
            pass
        time.sleep(1)
    print("❌ Сервер не запустился за 30 секунд")
    return False

if __name__ == '__main__':
    import uvicorn
    # Убедимся, что playwright и chromium установлены
    ensure_playwright_chromium()
    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000)