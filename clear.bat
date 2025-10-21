@echo off
echo Очистка кэша Music Loto Maker...
del "artist_photo_cache.json" 2>nul
del "bad_image_urls.json" 2>nul
rmdir /s /q "images" 2>nul
mkdir "images" 2>nul
echo ✅ Кэш очищен!
pause
