# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем зависимости системные (если нужны: ffmpeg, libmagic и т.д.)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Открываем порт (если FastAPI или другой сервер)
EXPOSE 8000

# Запуск (замени `main.py` на твой главный файл)
CMD ["python", "app.py"]