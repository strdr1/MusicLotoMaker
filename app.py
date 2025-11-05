import os
import sys

# Добавляем backend в путь импорта
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

try:
    from backend.server import app
    import uvicorn
    print("✅ Все импорты успешны")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("📦 Установите зависимости: pip install -r requirements.txt")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

if __name__ == '__main__':
    print("🌐 Запуск сервера на http://0.0.0.0:8000")
    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000)