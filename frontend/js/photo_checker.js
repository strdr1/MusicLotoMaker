// frontend/js/photo_checker.js
// Функционал проверки фото артистов

let photoCheckResults = [];

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    setTimeout(createPhotoCheckTab, 100);
});

// Создание новой вкладки "Проверка фото артистов"
function createPhotoCheckTab() {
    const nav = document.querySelector('nav.tabs');
    if (!nav) return;

    if (document.querySelector('[data-tab="photo-check"]')) return;

    // Находим кнопку "Билеты" и вставляем после нее
    const ticketsBtn = document.querySelector('[data-tab="tickets"]');
    if (!ticketsBtn) return;

    // Создаем кнопку вкладки
    const tabBtn = document.createElement('button');
    tabBtn.className = 'tab-btn';
    tabBtn.dataset.tab = 'photo-check';
    tabBtn.innerHTML = '🖼️ Проверка фото';
    ticketsBtn.parentNode.insertBefore(tabBtn, ticketsBtn.nextSibling);

    // Создаем контент вкладки
    const container = document.querySelector('.container');
    if (!container) return;

    const tabContent = document.createElement('div');
    tabContent.id = 'photo-check';
    tabContent.className = 'tab-content';
    tabContent.innerHTML = getPhotoCheckTabHTML();
    container.appendChild(tabContent);

    // Добавляем обработчик события
    tabBtn.addEventListener('click', function () {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        this.classList.add('active');
        document.getElementById('photo-check').classList.add('active');
    });

    console.log('✅ Вкладка "Проверка фото артистов" создана');
}

// HTML для вкладки проверки фото
function getPhotoCheckTabHTML() {
    return `
        <div class="photo-check-section">
            <div class="generator-card">
                <h2>🖼️ Проверка фото артистов</h2>
                <p class="subtitle">Проверьте наличие фото артистов в локальной папке /artists</p>
                <p><small>🔍 Поиск с очисткой спецсимволов (. ! ? и т.д.)</small></p>
                
                <div class="form-group">
                    <label for="photoCheckTrackList">Список треков для проверки:</label>
                    <textarea id="photoCheckTrackList" class="form-input" rows="10" placeholder="Введите список треков в формате:
Виктор Цой - Группа крови
Анна Асти - По барам
Кино - Звезда по имени Солнце
Моргенштерн - Cadillac"></textarea>
                    <small class="text-muted">Формат: Исполнитель - Название трека (каждый с новой строки)</small>
                </div>
                
                <div class="form-actions" style="margin: 20px 0;">
                    <button class="btn btn-primary" onclick="checkArtistPhotos()" id="photoCheckBtn">
                        🔍 Проверить фото
                    </button>
                    <button class="btn btn-secondary" onclick="clearPhotoCheckList()">
                        🗑️ Очистить
                    </button>
                </div>
                
                <!-- Статистика проверки -->
                <div id="photoCheckStats" class="photo-stats-card" style="display: none;">
                    <h4>📊 Статистика проверки:</h4>
                    <div class="photo-stats-grid">
                        <div class="photo-stat-card">
                            <div class="photo-stat-icon">📋</div>
                            <div class="photo-stat-info">
                                <span class="photo-stat-label">Всего артистов</span>
                                <span class="photo-stat-value" id="totalArtistsCount">0</span>
                            </div>
                        </div>
                        <div class="photo-stat-card">
                            <div class="photo-stat-icon">✅</div>
                            <div class="photo-stat-info">
                                <span class="photo-stat-label">С фото</span>
                                <span class="photo-stat-value" id="artistsWithPhotosCount">0</span>
                            </div>
                        </div>
                        <div class="photo-stat-card">
                            <div class="photo-stat-icon">⚠️</div>
                            <div class="photo-stat-info">
                                <span class="photo-stat-label">Без фото</span>
                                <span class="photo-stat-value" id="artistsWithoutPhotosCount">0</span>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Результаты проверки -->
                <div id="photoCheckResults" class="photo-results-section" style="display: none;">
                    <h3>📋 Результаты проверки</h3>
                    
                    <div class="photo-results-table">
                        <div class="photo-results-header-row">
                            <div class="photo-col-artist">Артист</div>
                            <div class="photo-col-status">Статус фото</div>
                            <div class="photo-col-filename">Найденный файл</div>
                        </div>
                        <div id="photoCheckResultsList" class="photo-results-list">
                            <!-- Результаты будут здесь -->
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Извлечение имен артистов из списка треков
function extractArtistsFromTrackList(trackListText) {
    const lines = trackListText.trim().split('\n');
    const artists = new Set();

    for (let line of lines) {
        line = line.trim();
        if (!line) continue;

        // Удаляем ВСЕ невидимые и мусорные символы
        line = cleanInvisibleChars(line);

        // Удаляем нумерацию (1., 2., 10. и т.д.) с невидимыми символами
        line = line
            .replace(/^[\d\u2070\u00B9\u00B2\u00B3\u2074-\u2079]+[\.\)\s\u200B\u200C\u200D\u2060\uFEFF\u00AD]*/, '')
            .replace(/^[⁠ ​﻿‬‭‮ ]*/, '')  // Дополнительные невидимые символы
            .trim();

        // Удаляем маркеры списка
        line = line
            .replace(/^[•\-*◦‣⁃⁌⁍⦙▸▹►▻◄◅⬅⬆⬇➔➘➙➚➛➜➝➞➟➠➡➢➣➤➥➦➧➨➩➪➫➬➭➮➯➱➲➳➴➵➶➷➸➹➺➻➼➽➾]/, '')
            .trim();

        // Парсим артиста
        let artist = '';
        const separators = [' - ', ' – ', ' — ', ' — ', '-', '–', '—'];

        for (let sep of separators) {
            if (line.includes(sep)) {
                const parts = line.split(sep, 2);
                artist = parts[0].trim();
                break;
            }
        }

        if (!artist) {
            // Пробуем разделить по любому дефису/тире
            const dashMatch = line.match(/^([^-–—]+)[-–—]/);
            if (dashMatch) {
                artist = dashMatch[1].trim();
            }
        }

        if (artist) {
            // Очищаем артиста от мусора перед добавлением
            artist = cleanInvisibleChars(artist);
            artists.add(artist);
        }
    }

    return Array.from(artists);
}
function cleanInvisibleChars(text) {
    if (!text) return '';

    // Удаляем невидимые символы
    const invisibleRegex = /[\u200B-\u200D\u2060\uFEFF\u00AD\u180E\u200E-\u200F\u202A-\u202E\u2066-\u2069\u2022\u2023\u2043\u204C\u204D\u2219\u25E6\u25AA\u25AB\u25CF\u25CB\u25A0]/g;

    // Удаляем специальные цифры (¹²³⁴⁵⁶⁷⁸⁹⁰)
    const specialNumbers = /[\u00B9\u00B2\u00B3\u2070\u2074-\u2079]/g;

    // Удаляем эмодзи и пиктограммы
    const emojiRegex = /[\u263A-\u27BF\u2600-\u26FF\u2700-\u27BF\u{1F300}-\u{1F9FF}\u{1FA00}-\u{1FA6F}]/gu;

    return text
        .replace(invisibleRegex, '')
        .replace(specialNumbers, '')
        .replace(emojiRegex, '')
        .replace(/\s+/g, ' ')
        .trim();
}


// Проверка фото артистов
async function checkArtistPhotos() {
    const trackListText = document.getElementById('photoCheckTrackList').value.trim();
    if (!trackListText) {
        // Используем глобальную функцию showNotification из app.js
        if (typeof window.showNotification === 'function') {
            window.showNotification('Введите список треков для проверки', 'warning');
        } else {
            alert('⚠️ Введите список треков для проверки');
        }
        return;
    }

    // Извлекаем артистов
    const artists = extractArtistsFromTrackList(trackListText);
    if (artists.length === 0) {
        if (typeof window.showNotification === 'function') {
            window.showNotification('Не удалось извлечь имена артистов', 'warning');
        } else {
            alert('⚠️ Не удалось извлечь имена артистов');
        }
        return;
    }

    console.log(`🔍 Проверяем ${artists.length} артистов`, artists);

    // Обновляем UI
    const checkBtn = document.getElementById('photoCheckBtn');
    const originalText = checkBtn.innerHTML;
    checkBtn.disabled = true;
    checkBtn.innerHTML = '🔄 Проверка...';

    // Сбрасываем результаты
    photoCheckResults = [];

    // Скрываем предыдущие результаты
    document.getElementById('photoCheckResults').style.display = 'none';
    document.getElementById('photoCheckStats').style.display = 'none';

    // Показываем прогресс
    let progressInterval = setInterval(() => {
        const progress = Math.round((photoCheckResults.length / artists.length) * 100);
        checkBtn.innerHTML = `🔄 Проверка... ${progress}%`;
    }, 100);

    // Проверяем каждого артиста
    for (const artistName of artists) {
        try {
            const result = await checkArtistPhoto(artistName);
            photoCheckResults.push({
                originalName: artistName,
                hasPhoto: result.has_photo,
                foundFiles: result.found_files || [],
                filename: result.exact_match || result.found_files?.[0] || null,
                matchType: result.match_type || 'none',
                searchName: result.search_name || '',
                message: result.message || ''
            });

        } catch (error) {
            console.error(`Ошибка проверки артиста ${artistName}:`, error);
            photoCheckResults.push({
                originalName: artistName,
                hasPhoto: false,
                foundFiles: [],
                error: error.message
            });
        }
    }

    // Очищаем интервал
    clearInterval(progressInterval);

    // Восстанавливаем кнопку
    checkBtn.disabled = false;
    checkBtn.innerHTML = originalText;

    // Показываем результаты
    showPhotoCheckResults();

    // Статистика
    const withPhotos = photoCheckResults.filter(r => r.hasPhoto).length;
    const withoutPhotos = photoCheckResults.length - withPhotos;

    // Используем глобальную функцию showNotification
    const message = `✅ Проверено: ${withPhotos} с фото, ${withoutPhotos} без фото`;
    const notificationType = withoutPhotos === 0 ? 'success' : 'warning';

    if (typeof window.showNotification === 'function') {
        window.showNotification(message, notificationType);
    } else {
        alert(`${notificationType === 'success' ? '✅' : '⚠️'} ${message}`);
    }
}

// Проверка наличия фото артиста
async function checkArtistPhoto(artistName) {
    try {
        const response = await fetch(`${API_BASE}/local/check-artist-photo?artist=${encodeURIComponent(artistName)}`);

        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }

        return await response.json();

    } catch (error) {
        console.error('Ошибка проверки фото:', error);
        throw error;
    }
}

// Показать результаты проверки
function showPhotoCheckResults() {
    const resultsSection = document.getElementById('photoCheckResults');
    const statsSection = document.getElementById('photoCheckStats');
    const resultsList = document.getElementById('photoCheckResultsList');

    if (!resultsSection || !resultsList) return;

    // Статистика
    const totalArtists = photoCheckResults.length;
    const artistsWithPhotos = photoCheckResults.filter(r => r.hasPhoto).length;
    const artistsWithoutPhotos = totalArtists - artistsWithPhotos;

    // Обновляем статистику
    document.getElementById('totalArtistsCount').textContent = totalArtists;
    document.getElementById('artistsWithPhotosCount').textContent = artistsWithPhotos;
    document.getElementById('artistsWithoutPhotosCount').textContent = artistsWithoutPhotos;

    // Показываем статистику
    if (statsSection) {
        statsSection.style.display = 'block';
    }

    // Отображаем результаты
    if (totalArtists === 0) {
        resultsList.innerHTML = `
            <div class="photo-empty-results">
                <div class="photo-empty-icon">📋</div>
                <p>Нет данных для отображения</p>
            </div>
        `;
    } else {
        resultsList.innerHTML = photoCheckResults.map((artist, index) => `
            <div class="photo-result-item ${artist.hasPhoto ? 'has-photo' : 'no-photo'}">
                <div class="photo-col-artist">
                    <span class="photo-artist-name">${escapeHtml(artist.originalName)}</span>
                    ${artist.searchName ? `<small class="photo-warning" style="display: block; margin-top: 4px; font-size: 11px; color: #666;">искали: ${escapeHtml(artist.searchName)}</small>` : ''}
                    ${artist.error ? `<small class="photo-error">${escapeHtml(artist.error)}</small>` : ''}
                    ${artist.matchType === 'exact' ? `<small class="photo-warning" style="background: rgba(34, 197, 94, 0.1); color: #10b981; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-top: 4px;">точное совпадение</small>` : ''}
                </div>
                <div class="photo-col-status">
                    <span class="photo-status-badge ${artist.hasPhoto ? 'status-success' : 'status-warning'}">
                        ${artist.hasPhoto ? '✅ Есть фото' : '⚠️ Нет фото'}
                    </span>
                </div>
                <div class="photo-col-filename">
                    ${artist.filename ?
                `<span class="photo-filename" title="${escapeHtml(artist.filename)}">
                            ${escapeHtml(truncateFilename(artist.filename, 25))}
                        </span>` :
                '<span class="photo-no-file">—</span>'
            }
                </div>
            </div>
        `).join('');
    }

    // Показываем секцию результатов
    resultsSection.style.display = 'block';

    // Прокручиваем к результатам
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Обрезать длинное имя файла
function truncateFilename(filename, maxLength = 25) {
    if (filename.length <= maxLength) return filename;
    return filename.substring(0, maxLength - 3) + '...';
}

// Очистить список проверки
function clearPhotoCheckList() {
    document.getElementById('photoCheckTrackList').value = '';
    document.getElementById('photoCheckResults').style.display = 'none';
    document.getElementById('photoCheckStats').style.display = 'none';
    photoCheckResults = [];

    // Используем глобальную функцию showNotification
    if (typeof window.showNotification === 'function') {
        window.showNotification('Список очищен', 'info');
    } else {
        alert('ℹ️ Список очищен');
    }
}

// Экранирование HTML
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Проверяем API_BASE
if (typeof API_BASE === 'undefined') {
    console.warn('⚠️ API_BASE не определена, использую относительный путь');
    window.API_BASE = '/api';
}

console.log('✅ Photo checker module loaded');