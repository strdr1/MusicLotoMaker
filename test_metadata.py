# test_metadata.py
from backend.processors.metadata_processor import create_metadata_processor

# Создаем экземпляр парсера
processor = create_metadata_processor()

# Примеры файлов, которые нужно проверить
samples = [
    "Korol_i_SHut_-_Lesnik.mp3",
    "Artur_Pirozhkov_-_Samo_Soboj.mp3",
    "Ramil_-_Chto_U_Nee_Vnutri.mp3",
    "Sqwoz_Bab_-_Romantic.mp3",
    "GAYAZOV_BROTHER_-_Pyanyjj_Tuman.mp3",
    "Гио_Пика_-_Где_Прошла_Ты.mp3"
]

print("=== Тест разбора метаданных ===\n")
for s in samples:
    result = processor.process(s)
    artist = result.get("artist")
    title = result.get("title")
    print(f"{s} →")
    print(f"  👤 Исполнитель: {artist}")
    print(f"  🎵 Название: {title}")
    print("-" * 50)
