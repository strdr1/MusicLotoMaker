// frontend/js/app.js
const API_BASE = '/api';

// Глобальные переменные
let currentTracks = [];
let currentEditingTrack = null;
let currentEditorTrack = null;
let segmentStart = 0;
let segmentDuration = 30;
let totalTrackDuration = 0;
let isPlaying = false;
let playbackInterval = null;
let audioElement = null;
let isGeneratingWaveform = false;

// Upload queue
const MAX_FILES_TOTAL = 120;
const MAX_CONCURRENT_UPLOADS = 6;
let uploadQueue = [];
let activeUploads = 0;
let currentUploads = new Map();
let uploadCounter = 0;

// Volume Control
let currentVolume = 50;
let isMuted = false;

// Photo Management
let currentPhotoTrackId = null;
let currentPhotoUrls = [];
let currentPhotoIndex = 0;
let isSearchingPhotos = false;

// Download Progress
let downloadProgress = {
    total: 0,
    current: 0,
    currentTrack: '',
    isDownloading: false,
    results: []
};

// Опрос статуса скачивания
let statusPollInterval = null;

// ===== helpers =====
const $ = (sel) =>
    document.querySelector(sel) ||
    document.querySelector(`[data-id="${sel.replace('#', '').replace('.', '')}"]`);

function getGenerateBtn() {
    return document.querySelector('[data-id="btn-generate"]') || document.getElementById('btn-generate') || document.querySelector('#presentation .btn-primary.btn-large');
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();

    // авто-обновление счётчика каждые 10 сек
    setInterval(updateTracksCount, 10000);

    // обновляем при возвращении на вкладку браузера
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateTracksCount();
    });
});

function setupEventListeners() {
    // Обработчик загрузки файлов
    const fileInput = document.getElementById('fileInput');
    if (fileInput) fileInput.addEventListener('change', handleFileUpload);

    // Обработчик закрытия модальных окон
    const editModal = document.getElementById('editModal');
    if (editModal) {
        editModal.addEventListener('click', function (e) {
            if (e.target === this) closeEditModal();
        });
    }

    const audioEditorModal = document.getElementById('audioEditorModal');
    if (audioEditorModal) {
        audioEditorModal.addEventListener('click', function (e) {
            if (e.target === this) closeAudioEditor();
        });
    }

    const photoModal = document.getElementById('photoModal');
    if (photoModal) {
        photoModal.addEventListener('click', function (e) {
            if (e.target === this) closePhotoModal();
        });
    }

    // Обработчик слайдера времени
    const timeSlider = document.getElementById('timeSlider');
    if (timeSlider) {
        timeSlider.addEventListener('input', function (e) {
            segmentStart = parseInt(e.target.value);
            updateTimelineDisplay();
        });
    }

    // Обработчики для вкладки файлов
    const uploadBasePptx = document.getElementById('uploadBasePptx');
    if (uploadBasePptx) {
        uploadBasePptx.addEventListener('change', handleBasePptxUpload);
    }

    const uploadArtistPhotos = document.getElementById('uploadArtistPhotos');
    if (uploadArtistPhotos) {
        uploadArtistPhotos.addEventListener('change', handleArtistPhotosUpload);
    }

    // Горячие клавиши
    document.addEventListener('keydown', function (e) {
        if (document.getElementById('audioEditorModal')?.style.display === 'block') {
            switch (e.key) {
                case ' ':
                    e.preventDefault();
                    togglePlayback();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    moveSegment(5);
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    moveSegment(-5);
                    break;
                case 'Escape':
                    e.preventDefault();
                    stopPlayback();
                    break;
            }
        }

        // Горячие клавиши для фото модалки
        if (document.getElementById('photoModal')?.style.display === 'block') {
            switch (e.key) {
                case 'ArrowRight':
                    e.preventDefault();
                    nextPhoto();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    previousPhoto();
                    break;
                case 'Enter':
                    e.preventDefault();
                    saveCurrentPhoto();
                    break;
                case 'Escape':
                    e.preventDefault();
                    closePhotoModal();
                    break;
            }
        }
    });

    // Горячие клавиши для текстового поля скачивания
    const trackListTextarea = document.getElementById('trackList');
    if (trackListTextarea) {
        trackListTextarea.addEventListener('keydown', function (e) {
            if (e.ctrlKey && e.key === 'Enter') {
                downloadTrackList();
            }
        });
    }
}

// =========================
// INTERNET TRACK DOWNLOAD FUNCTIONS WITH IMPROVED PROGRESS
// =========================

async function downloadTrackList() {
    const trackListText = document.getElementById('trackList').value.trim();
    if (!trackListText) {
        showNotification('Введите список треков для скачивания', 'warning');
        return;
    }

    // Парсим список треков
    const tracksToDownload = parseTrackList(trackListText);
    if (tracksToDownload.length === 0) {
        showNotification('Не удалось распознать список треков', 'warning');
        return;
    }

    // Инициализируем прогресс
    downloadProgress = {
        total: tracksToDownload.length,
        current: 0,
        currentTrack: 'Подготовка к скачиванию...',
        isDownloading: true,
        results: [],
        failedTracks: [],
        duplicateTracks: [],
        successfulTracks: []
    };

    // Показываем прогресс бар
    showDownloadProgress();

    // Запускаем опрос статуса сразу
    startStatusPolling();

    try {
        // Запускаем скачивание
        const response = await fetch(`${API_BASE}/tracks/download-from-list`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_list: trackListText,
                auto_search_photos: document.getElementById('autoSearchPhotos').checked,
                use_smart_segments: document.getElementById('useSmartSegments').checked
            })
        });

        if (!response.ok) {
            throw new Error('Ошибка скачивания треков');
        }

        const result = await response.json();

        if (result.success) {
            const successCount = result.downloaded || result.results.filter(r => r.success).length;
            const duplicateCount = result.duplicates || result.results.filter(r => r.duplicate).length;
            const errorCount = result.failed || result.results.filter(r => !r.success && !r.duplicate).length;

            // Обновляем прогресс до 100%
            downloadProgress.current = downloadProgress.total;
            downloadProgress.currentTrack = `Завершено: ${successCount} успешно, ${duplicateCount} дубликатов, ${errorCount} ошибок`;
            downloadProgress.results = result.results || [];

            // Классифицируем результаты
            downloadProgress.successfulTracks = result.results.filter(r => r.success);
            downloadProgress.duplicateTracks = result.results.filter(r => r.duplicate);
            downloadProgress.failedTracks = result.results.filter(r => !r.success && !r.duplicate);

            downloadProgress.isDownloading = false;

            updateDownloadProgress();

            let message = `✅ Скачано ${successCount} из ${downloadProgress.total} треков`;
            if (duplicateCount > 0) message += `, ${duplicateCount} дубликатов`;
            if (errorCount > 0) message += `, ${errorCount} ошибок`;

            showNotification(message, duplicateCount > 0 || errorCount > 0 ? 'warning' : 'success');

            // Показываем детальные результаты
            showDownloadResults(result.results);

            // Обновляем список треков
            await loadTracks();
            updateTracksCount();
        } else {
            throw new Error(result.message || 'Ошибка скачивания');
        }

    } catch (error) {
        console.error('❌ Ошибка скачивания треков:', error);
        downloadProgress.isDownloading = false;
        updateDownloadProgress();
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    } finally {
        // Останавливаем опрос через 3 секунды после завершения
        setTimeout(() => {
            stopStatusPolling();
        }, 3000);
    }
}

function parseTrackList(trackListText) {
    const tracks = [];
    const lines = trackListText.trim().split('\n');

    for (let line of lines) {
        line = line.trim();
        if (!line) continue;

        // УДАЛЯЕМ РАЗЛИЧНЫЕ ФОРМАТЫ НУМЕРАЦИИ
        line = line
            .replace(/^\d+\.\s*/, '')     // "1. ", "2. ", "123. "
            .replace(/^\d+\)\s*/, '')     // "1) ", "2) "  
            .replace(/^-\s*/, '')         // "- ", "— "
            .replace(/^•\s*/, '')         // "• "
            .replace(/^\*\s*/, '');       // "* "

        // Убираем лишние символы
        line = line.replace(/[\(\)\[\]\{\}]/g, '').trim();

        let artist = '', title = '';

        // Пробуем разные разделители
        const separators = [' - ', ' – ', ' — ', ' | '];
        let found = false;

        for (let sep of separators) {
            if (line.includes(sep)) {
                const parts = line.split(sep, 2);
                if (parts.length === 2) {
                    artist = parts[0].trim();
                    title = parts[1].trim();
                    found = true;
                    break;
                }
            }
        }

        // Если разделитель не найден, пробуем другие форматы
        if (!found) {
            // Формат: "Название (Артист)"
            const match = line.match(/^(.+?)\s+\((.+?)\)$/);
            if (match) {
                title = match[1].trim();
                artist = match[2].trim();
                found = true;
            } else {
                // Если ничего не помогло, анализируем содержимое
                const words = line.split(' ');
                if (words.length >= 2) {
                    // Пробуем разные точки разделения
                    for (let i = 1; i < words.length; i++) {
                        const possibleArtist = words.slice(0, i).join(' ');
                        const possibleTitle = words.slice(i).join(' ');

                        if (looksLikeReasonableSplit(possibleArtist, possibleTitle)) {
                            artist = possibleArtist;
                            title = possibleTitle;
                            found = true;
                            break;
                        }
                    }
                }

                // Если всё ещё не нашли, используем всю строку как название
                if (!found) {
                    title = line;
                    artist = 'Неизвестный исполнитель';
                }
            }
        }

        if (artist || title) {
            tracks.push({
                original_line: line,
                artist: artist,
                title: title,
                search_query: artist && title ? `${artist} ${title}` : line
            });
        }
    }

    console.log(`🎵 Распознано ${tracks.length} треков из списка`);
    return tracks;
}


function startStatusPolling() {
    // Очищаем предыдущий интервал
    stopStatusPolling();

    statusPollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/download/status`);
            if (response.ok) {
                const status = await response.json();

                // Обновляем прогресс
                downloadProgress.current = status.current || 0;
                downloadProgress.total = status.total || downloadProgress.total;
                downloadProgress.currentTrack = status.current_track || downloadProgress.currentTrack;
                downloadProgress.results = status.results || downloadProgress.results;
                downloadProgress.isDownloading = status.is_running !== false;

                // Автоматически классифицируем результаты для отображения
                if (downloadProgress.results.length > 0) {
                    downloadProgress.successfulTracks = downloadProgress.results.filter(r => r.success);
                    downloadProgress.duplicateTracks = downloadProgress.results.filter(r => r.duplicate);
                    downloadProgress.failedTracks = downloadProgress.results.filter(r => !r.success && !r.duplicate);
                }

                updateDownloadProgress();

                console.log(`📊 Прогресс: ${downloadProgress.current}/${downloadProgress.total} - ${downloadProgress.currentTrack}`);

                // Если скачивание завершено, останавливаем опрос
                if (!downloadProgress.isDownloading && downloadProgress.current >= downloadProgress.total) {
                    console.log('✅ Скачивание завершено, останавливаем опрос');
                    stopStatusPolling();
                }
            }
        } catch (error) {
            console.error('Ошибка опроса статуса:', error);
        }
    }, 1500); // Опрашиваем каждые 1.5 секунды
}

function stopStatusPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
    }
}

function showDownloadProgress() {
    const progressSection = document.getElementById('listSearchProgress');
    if (progressSection) {
        progressSection.style.display = 'block';
    }
    updateDownloadProgress();
}

function updateDownloadProgress() {
    const progressStatus = document.getElementById('progressStatus');
    const progressCount = document.getElementById('progressCount');
    const progressFill = document.getElementById('progressFill');
    const progressDetails = document.getElementById('progressDetails');

    if (!progressStatus || !progressCount || !progressFill) return;

    const percent = downloadProgress.total > 0 ?
        Math.round((downloadProgress.current / downloadProgress.total) * 100) : 0;

    progressStatus.textContent = downloadProgress.currentTrack || 'Подготовка к скачиванию...';
    progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
    progressFill.style.width = `${percent}%`;

    if (downloadProgress.isDownloading) {
        // Добавляем анимацию пульсации
        progressFill.classList.add('pulsing');

        // Меняем цвет в зависимости от прогресса
        if (percent < 30) {
            progressFill.style.background = 'linear-gradient(90deg, #ef4444, #f59e0b)';
        } else if (percent < 70) {
            progressFill.style.background = 'linear-gradient(90deg, #f59e0b, #3b82f6)';
        } else {
            progressFill.style.background = 'linear-gradient(90deg, #3b82f6, #10b981)';
        }

        // Обновляем детали прогресса в реальном времени
        updateProgressDetails();
    } else {
        progressStatus.textContent = 'Скачивание завершено';
        progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
        progressFill.style.width = '100%';
        progressFill.style.background = downloadProgress.failedTracks.length > 0 || downloadProgress.duplicateTracks.length > 0 ?
            'linear-gradient(90deg, #f59e0b, #d97706)' :
            'linear-gradient(90deg, #10b981, #059669)';
        progressFill.classList.remove('pulsing');

        // Показываем финальные детали
        updateFinalResults();
    }
}

function updateProgressDetails() {
    const progressDetails = document.getElementById('progressDetails');
    if (!progressDetails) return;

    let detailsHTML = '<div class="progress-details-current">';

    // Текущий обрабатываемый трек
    if (downloadProgress.currentTrack && downloadProgress.currentTrack !== 'Подготовка к скачиванию...') {
        detailsHTML += `<div class="progress-detail-item progress-detail-processing">
            🔄 ${downloadProgress.currentTrack}
        </div>`;
    }

    // Последние 5 результатов с детализацией ошибок
    const recentResults = downloadProgress.results.slice(-8);
    if (recentResults.length > 0) {
        detailsHTML += '<div class="recent-results">';
        detailsHTML += '<div class="recent-results-title">Последние результаты:</div>';

        recentResults.forEach(result => {
            let statusClass, statusIcon, statusText;

            if (result.success) {
                statusClass = 'progress-detail-success';
                statusIcon = '✅';
                statusText = `${result.artist || ''} - ${result.title || ''}`;
            } else if (result.duplicate) {
                statusClass = 'progress-detail-warning';
                statusIcon = '⚠️';
                statusText = `${result.artist || ''} - ${result.title || ''}`;
                if (result.existing_track_id) {
                    statusText += ` (ID: ${result.existing_track_id})`;
                }
            } else {
                statusClass = 'progress-detail-error';
                statusIcon = '❌';
                statusText = `${result.artist || ''} - ${result.title || ''}`;
            }

            detailsHTML += `
                <div class="progress-detail-item ${statusClass}">
                    ${statusIcon} ${statusText}
                    ${result.error ? `<br><small class="error-detail">${result.error}</small>` : ''}
                </div>
            `;
        });
        detailsHTML += '</div>';
    }

    // Статистика по ходу выполнения
    const successCount = downloadProgress.results.filter(r => r.success).length;
    const duplicateCount = downloadProgress.results.filter(r => r.duplicate).length;
    const errorCount = downloadProgress.results.filter(r => !r.success && !r.duplicate).length;

    if (downloadProgress.results.length > 0) {
        detailsHTML += `
            <div class="progress-stats">
                <div class="stat-item stat-success">✅ ${successCount}</div>
                <div class="stat-item stat-warning">⚠️ ${duplicateCount}</div>
                <div class="stat-item stat-error">❌ ${errorCount}</div>
            </div>
        `;
    }

    detailsHTML += '</div>';
    progressDetails.innerHTML = detailsHTML;
}

function updateFinalResults() {
    const progressDetails = document.getElementById('progressDetails');
    if (!progressDetails) return;

    const successCount = downloadProgress.successfulTracks.length;
    const duplicateCount = downloadProgress.duplicateTracks.length;
    const errorCount = downloadProgress.failedTracks.length;

    let detailsHTML = '<div class="final-results">';
    detailsHTML += '<h4>Итоговые результаты:</h4>';

    // Сводная статистика
    detailsHTML += `
        <div class="results-summary">
            <div class="summary-item success">
                <span class="summary-icon">✅</span>
                <span class="summary-count">${successCount}</span>
                <span class="summary-label">Успешно</span>
            </div>
            ${duplicateCount > 0 ? `
            <div class="summary-item warning">
                <span class="summary-icon">⚠️</span>
                <span class="summary-count">${duplicateCount}</span>
                <span class="summary-label">Дубликаты</span>
            </div>
            ` : ''}
            ${errorCount > 0 ? `
            <div class="summary-item error">
                <span class="summary-icon">❌</span>
                <span class="summary-count">${errorCount}</span>
                <span class="summary-label">Ошибки</span>
            </div>
            ` : ''}
        </div>
    `;

    // Детали по дубликатам
    if (duplicateCount > 0) {
        detailsHTML += `
            <div class="results-section">
                <h5>🚫 Пропущенные дубликаты:</h5>
                <div class="failed-tracks-list">
                    ${downloadProgress.duplicateTracks.map(track => `
                        <div class="failed-track-item">
                            <span class="track-name">${track.artist || 'Неизвестный исполнитель'} - ${track.title || 'Без названия'}</span>
                            <span class="track-reason">Уже существует в медиатеке${track.existing_track_id ? ` (ID: ${track.existing_track_id})` : ''}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Детали по ошибкам
    if (errorCount > 0) {
        detailsHTML += `
            <div class="results-section">
                <h5>❌ Треки с ошибками:</h5>
                <div class="failed-tracks-list">
                    ${downloadProgress.failedTracks.map(track => `
                        <div class="failed-track-item">
                            <span class="track-name">${track.artist || 'Неизвестный исполнитель'} - ${track.title || 'Без названия'}</span>
                            <span class="track-reason">${track.error || 'Неизвестная ошибка'}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Успешные треки (только если их немного)
    if (successCount > 0 && successCount <= 10) {
        detailsHTML += `
            <div class="results-section">
                <h5>✅ Успешно скачаны:</h5>
                <div class="success-tracks-list">
                    ${downloadProgress.successfulTracks.map(track => `
                        <div class="success-track-item">
                            ${track.artist || 'Неизвестный исполнитель'} - ${track.title || 'Без названия'}
                            ${track.track_id ? ` (ID: ${track.track_id})` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    } else if (successCount > 10) {
        detailsHTML += `
            <div class="results-section">
                <h5>✅ Успешно скачаны: ${successCount} треков</h5>
            </div>
        `;
    }

    detailsHTML += '</div>';
    progressDetails.innerHTML = detailsHTML;
}

function showDownloadResults(results) {
    const progressDetails = document.getElementById('progressDetails');
    if (!progressDetails || !results) return;

    // Классифицируем результаты
    const successful = results.filter(r => r.success);
    const duplicates = results.filter(r => r.duplicate);
    const failed = results.filter(r => !r.success && !r.duplicate);

    let detailsHTML = '<div class="download-results"><h4>Детальные результаты:</h4>';

    // Группируем по статусам
    if (duplicates.length > 0) {
        detailsHTML += `
            <div class="result-group duplicates">
                <h5>🚫 Дубликаты (${duplicates.length}):</h5>
                ${duplicates.map((result, index) => `
                    <div class="result-item duplicate">
                        <span class="result-icon">⚠️</span>
                        <span class="result-track">${result.artist || 'Неизвестный исполнитель'} - ${result.title || 'Без названия'}</span>
                        <span class="result-detail">${result.error || 'Уже существует в медиатеке'}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    if (failed.length > 0) {
        detailsHTML += `
            <div class="result-group failed">
                <h5>❌ Ошибки (${failed.length}):</h5>
                ${failed.map((result, index) => `
                    <div class="result-item failed">
                        <span class="result-icon">❌</span>
                        <span class="result-track">${result.artist || 'Неизвестный исполнитель'} - ${result.title || 'Без названия'}</span>
                        <span class="result-detail">${result.error || 'Неизвестная ошибка'}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    if (successful.length > 0) {
        detailsHTML += `
            <div class="result-group successful">
                <h5>✅ Успешно (${successful.length}):</h5>
                ${successful.slice(0, 10).map((result, index) => `
                    <div class="result-item success">
                        <span class="result-icon">✅</span>
                        <span class="result-track">${result.artist || 'Неизвестный исполнитель'} - ${result.title || 'Без названия'}</span>
                        ${result.track_id ? `<span class="result-id">ID: ${result.track_id}</span>` : ''}
                    </div>
                `).join('')}
                ${successful.length > 10 ? `<div class="result-more">... и ещё ${successful.length - 10} треков</div>` : ''}
            </div>
        `;
    }

    detailsHTML += '</div>';
    progressDetails.innerHTML = detailsHTML;
}

function clearTrackList() {
    document.getElementById('trackList').value = '';
    showNotification('Список треков очищен', 'info');
}

// Функция для тестирования с разными типами ошибок
function testDownloadProgressWithErrors() {
    downloadProgress = {
        total: 8,
        current: 0,
        currentTrack: 'Начинаем тестовое скачивание...',
        isDownloading: true,
        results: [],
        failedTracks: [],
        duplicateTracks: [],
        successfulTracks: []
    };

    showDownloadProgress();

    const testTracks = [
        { artist: 'The Beatles', title: 'Yesterday', type: 'success' },
        { artist: 'Queen', title: 'Bohemian Rhapsody', type: 'duplicate', error: 'Трек уже существует (ID: 5)' },
        { artist: 'Michael Jackson', title: 'Billie Jean', type: 'error', error: 'Трек не найден в Яндекс.Музыке' },
        { artist: 'Madonna', title: 'Like a Virgin', type: 'success' },
        { artist: 'Led Zeppelin', title: 'Stairway to Heaven', type: 'error', error: 'Ошибка сети' },
        { artist: 'Abba', title: 'Dancing Queen', type: 'duplicate', error: 'Трек уже существует (ID: 12)' },
        { artist: 'Elvis Presley', title: 'Can\'t Help Falling in Love', type: 'success' },
        { artist: 'Whitney Houston', title: 'I Will Always Love You', type: 'error', error: 'Файл слишком большой' }
    ];

    let current = 0;

    const interval = setInterval(() => {
        if (current < downloadProgress.total) {
            const track = testTracks[current];
            downloadProgress.current = current + 1;
            downloadProgress.currentTrack = `${track.artist} - ${track.title}`;

            const result = {
                artist: track.artist,
                title: track.title,
                success: track.type === 'success',
                duplicate: track.type === 'duplicate',
                error: track.error
            };

            downloadProgress.results.push(result);

            // Классифицируем для итогов
            if (track.type === 'success') {
                downloadProgress.successfulTracks.push(result);
            } else if (track.type === 'duplicate') {
                downloadProgress.duplicateTracks.push(result);
            } else {
                downloadProgress.failedTracks.push(result);
            }

            updateDownloadProgress();
            current++;
        } else {
            clearInterval(interval);
            downloadProgress.isDownloading = false;
            updateDownloadProgress();
            showNotification('✅ Тест прогресс бара с ошибками завершен!', 'success');
        }
    }, 1000);
}

// =========================
// PRESENTATION GENERATION FUNCTIONS
// =========================

async function generatePresentation() {
    const status = document.getElementById("presentationStatus") || document.getElementById("presentation-status");
    const titleInput = document.getElementById("presentation-title");
    const title = titleInput ? titleInput.value.trim() : "";

    const makeBWCheckbox = document.getElementById("make-bw");
    const makeBW = !!(makeBWCheckbox && makeBWCheckbox.checked);

    if (!title) {
        if (status) {
            status.textContent = "⚠️ Пожалуйста, введите название презентации.";
            status.style.color = "#f87171";
        }
        return;
    }

    const generateBtn = document.getElementById('generatePresentationBtn');
    const originalText = generateBtn.innerHTML;

    try {
        if (status) {
            status.textContent = "⏳ Генерация презентации...";
            status.style.color = "#9ca3af";
        }

        generateBtn.disabled = true;
        generateBtn.innerHTML = "⏳ Генерация...";

        const payload = {
            title,
            design: { make_bw: makeBW }
        };

        const response = await fetch(`${API_BASE}/generate/presentation`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (status) {
                status.innerHTML = `✅ Презентация успешно создана!<br>
                <a href="${data.download_url}" class="download-link" download>
                    📥 Скачать презентацию
                </a>`;
                status.style.color = "#34d399";
            }
            showNotification('✅ Презентация успешно создана!', 'success');
        } else {
            const errorMsg = data.detail || data.message || "Не удалось создать презентацию";
            if (status) {
                status.textContent = "❌ Ошибка: " + errorMsg;
                status.style.color = "#f87171";
            }
            showNotification('❌ ' + errorMsg, 'error');
        }
    } catch (error) {
        console.error("Ошибка при генерации презентации:", error);
        if (status) {
            status.textContent = "❌ Ошибка соединения с сервером.";
            status.style.color = "#f87171";
        }
        showNotification('❌ Ошибка соединения с сервером', 'error');
    } finally {
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.innerHTML = originalText;
        }
    }
}

// Управление вкладками
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');

            if (btn.dataset.tab === 'status') {
                loadSystemStatus();
            } else if (btn.dataset.tab === 'presentation') {
                updateTracksCount();
            } else if (btn.dataset.tab === 'local') {
                loadLocalFilesInfo();
            }
        });
    });
}

// Загрузка треков
async function loadTracks() {
    showStatus('mediaStatus', '🔄 Загружаем список треков...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const tracks = await response.json();

        currentTracks = tracks;
        renderTracks(tracks);
        updateTracksCount();
        showStatus('mediaStatus', `✅ Загружено ${tracks.length} треков`, 'success');
    } catch (error) {
        console.error('Ошибка загрузки треков:', error);
        showStatus('mediaStatus', '❌ Ошибка загрузки треков', 'error');
    }
}

// Отображение треков
function renderTracks(tracks) {
    const container = document.getElementById('tracksList');

    if (!container) return;

    if (tracks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">🎵</div>
                <h3>Нет загруженных треков</h3>
                <p>Нажмите "Загрузить треки" чтобы добавить музыку</p>
            </div>
        `;
        return;
    }

    container.innerHTML = tracks.map(track => `
        <div class="track-item">
            <div class="col-id">${track.id}</div>
            <div class="col-artist">
                ${track.image_path ?
            `<img src="${API_BASE}/tracks/${track.id}/artist-photo?t=${Date.now()}" 
                          alt="${escapeHtml(track.artist)}" 
                          class="track-cover"
                          onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"
                          onload="this.nextElementSibling.style.display='none';">` :
            ''
        }
                <div class="track-cover-placeholder" style="${track.image_path ? 'display: none;' : ''}">🎵</div>
                <span>${escapeHtml(track.artist)}</span>
            </div>
            <div class="col-title">${escapeHtml(track.title)}</div>
            <div class="col-segment">
                <span class="segment-time">${formatTime(track.segment_start || 0)}</span>
                <span class="segment-duration">${track.segment_duration || 30}с</span>
            </div>
            <div class="col-actions">
                <button class="btn btn-secondary btn-small" onclick="openAudioEditor(${track.id})" title="Аудио редактор">
                    🎚️
                </button>
                <button class="btn btn-secondary btn-small" onclick="editTrack(${track.id})" title="Редактировать метаданные">
                    ✏️
                </button>
                <button class="btn btn-secondary btn-small" onclick="addArtistPhoto(${track.id})" title="Добавить фото артиста">
                    📷
                </button>
                <button class="btn btn-danger btn-small" onclick="deleteTrack(${track.id})" title="Удалить">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
}

// Загрузка файлов
async function handleFileUpload(event) {
    const files = Array.from(event.target.files || []);
    if (files.length === 0) return;

    const alreadyPlanned = uploadQueue.length + currentUploads.size;
    const allowed = Math.max(0, MAX_FILES_TOTAL - alreadyPlanned);
    const toEnqueue = files.slice(0, allowed);
    const skipped = files.length - toEnqueue.length;

    if (skipped > 0) {
        showNotification(`Лимит ${MAX_FILES_TOTAL} файлов. Пропущено: ${skipped}`, 'warning');
    }

    toEnqueue.forEach(file => {
        const id = ++uploadCounter;
        file.__id = id;
        uploadQueue.push(file);
        createUploadRow(file, id);
    });

    event.target.value = '';
    pumpUploadQueue();
    showStatus('mediaStatus', `🔄 План загрузок: ${toEnqueue.length}, активных сейчас: ${activeUploads}`, 'loading');
}

function pumpUploadQueue() {
    updateUploadSummaryText();
    while (activeUploads < MAX_CONCURRENT_UPLOADS && uploadQueue.length > 0) {
        const file = uploadQueue.shift();
        if (!file) break;
        uploadSingleFile(file);
    }
}

function uploadSingleFile(file) {
    const id = file.__id;
    const url = `${API_BASE}/tracks/upload`;

    const formData = new FormData();
    formData.append('files', file);

    const xhr = new XMLHttpRequest();
    currentUploads.set(id, { xhr, file });

    setUploadStatus(id, 'Подключение…');

    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const percent = Math.min(99, Math.round((e.loaded / e.total) * 100));
            setUploadProgress(id, percent);
            setUploadStatus(id, `Загрузка ${percent}%`);
        }
    };

    xhr.onloadstart = () => {
        activeUploads++;
        updateUploadSummaryText();
    };

    xhr.onerror = () => {
        finishUploadRow(id, false);
        currentUploads.delete(id);
        activeUploads = Math.max(0, activeUploads - 1);
        showStatus('mediaStatus', `❌ Ошибка загрузки: ${file.name}`, 'error');
        pumpUploadQueue();
    };

    xhr.onabort = () => {
        setUploadStatus(id, 'Отменено', 'warning');
        setUploadProgress(id, 0);
        currentUploads.delete(id);
        activeUploads = Math.max(0, activeUploads - 1);
        pumpUploadQueue();
        updateUploadSummaryText();
    };

    xhr.onload = async () => {
        let ok = (xhr.status >= 200 && xhr.status < 300);
        if (ok) {
            try {
                const res = JSON.parse(xhr.responseText || '{}');
                if (res.errors && res.errors.length) {
                    ok = false;
                }
            } catch {
            }
        }
        if (ok) {
            finishUploadRow(id, true);
        } else {
            finishUploadRow(id, false);
        }

        currentUploads.delete(id);
        activeUploads = Math.max(0, activeUploads - 1);

        try { await loadTracks(); } catch { }

        pumpUploadQueue();
        updateUploadSummaryText();
    };

    xhr.open('POST', url, true);
    xhr.send(formData);
}

function showUploadPanel(show) {
    const panel = uploadPanel();
    if (!panel) return;
    panel.style.display = show ? 'block' : 'none';
}

function updateUploadSummaryText() {
    const total = currentUploads.size + uploadQueue.length;
    const inFlight = activeUploads;
    const pending = uploadQueue.length;
    if (total === 0) {
        uploadSummary().textContent = 'Загрузок нет';
        cancelAllBtn().style.display = 'none';
        showUploadPanel(false);
    } else {
        uploadSummary().textContent = `Загрузки: выполняется ${inFlight}, в очереди ${pending} (всего ${total})`;
        cancelAllBtn().style.display = 'inline-flex';
        showUploadPanel(true);
    }
}

function createUploadRow(file, id) {
    const row = document.createElement('div');
    row.className = 'upload-row';
    row.id = `upload-row-${id}`;
    row.innerHTML = `
        <div class="upload-row-top">
            <span class="upload-file-name" title="${file.name}">${file.name}</span>
            <span class="upload-percent" id="upload-percent-${id}">0%</span>
        </div>
        <div class="upload-progressbar">
            <div class="upload-bar" id="upload-bar-${id}" style="width:0%"></div>
        </div>
        <div class="upload-row-bottom">
            <span class="upload-status" id="upload-status-${id}">Ожидание...</span>
            <button class="btn btn-small btn-danger" id="upload-cancel-${id}">Отмена</button>
        </div>
    `;
    uploadRows().appendChild(row);
    document.getElementById(`upload-cancel-${id}`).onclick = () => cancelSingleUpload(id);
    updateUploadSummaryText();
    return row;
}

function setUploadProgress(id, percent) {
    const bar = document.getElementById(`upload-bar-${id}`);
    const pct = document.getElementById(`upload-percent-${id}`);
    if (bar) bar.style.width = `${percent}%`;
    if (pct) pct.textContent = `${percent}%`;
}

function setUploadStatus(id, text, kind = 'info') {
    const el = document.getElementById(`upload-status-${id}`);
    if (!el) return;
    el.textContent = text;
    el.className = `upload-status ${kind}`;
}

function finishUploadRow(id, ok = true) {
    setUploadProgress(id, 100);
    setUploadStatus(id, ok ? 'Готово' : 'Ошибка', ok ? 'success' : 'error');
    const btn = document.getElementById(`upload-cancel-${id}`);
    if (btn) btn.disabled = true;
}

function removeUploadRow(id) {
    const row = document.getElementById(`upload-row-${id}`);
    if (row && row.parentElement) row.parentElement.removeChild(row);
    updateUploadSummaryText();
}

function cancelSingleUpload(id) {
    const rec = currentUploads.get(id);
    if (rec && rec.xhr) {
        try { rec.xhr.abort(); } catch (e) { }
    } else {
        uploadQueue = uploadQueue.filter(item => item.__id !== id);
        removeUploadRow(id);
        updateUploadSummaryText();
    }
}

function cancelAllUploads() {
    for (const [id, rec] of currentUploads.entries()) {
        try { rec.xhr && rec.xhr.abort(); } catch (e) { }
    }
    uploadQueue = [];
    currentUploads.clear();
    uploadRows().innerHTML = '';
    updateUploadSummaryText();
}

// =========================
// ARTIST PHOTO FUNCTIONS
// =========================

async function addArtistPhoto(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) {
        showNotification('Трек не найден', 'error');
        return;
    }

    currentPhotoTrackId = trackId;
    currentPhotoUrls = [];
    currentPhotoIndex = 0;

    document.getElementById('photoArtistName').textContent = track.artist;
    document.getElementById('photoPreview').style.display = 'none';
    document.getElementById('photoStatus').style.display = 'none';

    const previewContainer = document.getElementById('photoPreview');
    const existingNav = previewContainer.querySelector('.photo-navigation');
    if (existingNav) {
        existingNav.remove();
    }

    document.getElementById('photoModal').style.display = 'block';
}

async function searchArtistPhoto() {
    if (!currentPhotoTrackId || isSearchingPhotos) return;

    const track = currentTracks.find(t => t.id === currentPhotoTrackId);
    if (!track) return;

    isSearchingPhotos = true;
    showPhotoStatus('🔍 Ищем фото артиста...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentPhotoTrackId}/search-artist-photo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                artist: track.artist,
                get_multiple: true
            })
        });

        if (!response.ok) {
            throw new Error('Ошибка поиска фото');
        }

        const result = await response.json();

        if (result.success && result.photos && result.photos.length > 0) {
            currentPhotoUrls = result.photos;
            currentPhotoIndex = 0;

            if (result.cached) {
                showPhotoStatus(`✅ Найдено ${result.photos.length} кэшированных фото`, 'success');
            } else {
                showPhotoStatus(`✅ Найдено ${result.photos.length} фото`, 'success');
            }

            showCurrentPhoto();
        } else {
            showPhotoStatus('❌ Не удалось найти фото артиста', 'error');
        }

    } catch (error) {
        console.error('Ошибка поиска фото:', error);
        showPhotoStatus('❌ Ошибка поиска фото', 'error');
    } finally {
        isSearchingPhotos = false;
    }
}

function showCurrentPhoto() {
    if (currentPhotoUrls.length === 0) return;

    const photoUrl = currentPhotoUrls[currentPhotoIndex];
    const previewImg = document.getElementById('photoPreviewImage');
    const previewContainer = document.getElementById('photoPreview');

    previewImg.style.display = 'none';
    previewContainer.style.display = 'block';

    const img = new Image();
    img.onload = function () {
        previewImg.src = photoUrl;
        previewImg.style.display = 'block';
        updatePhotoNavigation();
    };
    img.onerror = function () {
        showPhotoStatus('❌ Ошибка загрузки изображения', 'error');
        previewContainer.style.display = 'none';
    };
    img.src = photoUrl;
}

function updatePhotoNavigation() {
    const previewContainer = document.getElementById('photoPreview');
    const existingNav = previewContainer.querySelector('.photo-navigation');

    if (existingNav) {
        existingNav.remove();
    }

    const navHtml = `
        <div class="photo-navigation">
            <div style="display: flex; gap: 8px; justify-content: center; align-items: center; margin-bottom: 10px;">
                <button class="btn btn-small" onclick="previousPhoto()" ${currentPhotoIndex === 0 ? 'disabled' : ''}>
                    ⬅️
                </button>
                <span style="color: var(--text-muted); font-weight: 600; min-width: 50px; text-align: center; font-size: 12px;">
                    ${currentPhotoIndex + 1} / ${currentPhotoUrls.length}
                </span>
                <button class="btn btn-small" onclick="nextPhoto()" ${currentPhotoIndex === currentPhotoUrls.length - 1 ? 'disabled' : ''}>
                    ➡️
                </button>
            </div>
            <div style="display: flex; gap: 6px; justify-content: center; flex-wrap: wrap;">
                <button class="btn btn-small btn-primary" onclick="saveCurrentPhoto()">
                    ✅ Сохранить
                </button>
                <button class="btn btn-small btn-secondary" onclick="searchArtistPhoto()" ${isSearchingPhotos ? 'disabled' : ''}>
                    🔄 Ещё
                </button>
                <button class="btn btn-small btn-warning" onclick="uploadArtistPhoto()">
                    📁 Своё
                </button>
            </div>
        </div>
    `;
    previewContainer.insertAdjacentHTML('beforeend', navHtml);
}

function previousPhoto() {
    if (currentPhotoIndex > 0) {
        currentPhotoIndex--;
        showCurrentPhoto();
    }
}

function nextPhoto() {
    if (currentPhotoIndex < currentPhotoUrls.length - 1) {
        currentPhotoIndex++;
        showCurrentPhoto();
    }
}

async function saveCurrentPhoto() {
    if (!currentPhotoTrackId || currentPhotoUrls.length === 0) return;

    const photoUrl = currentPhotoUrls[currentPhotoIndex];

    showPhotoStatus('💾 Сохраняем фото...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentPhotoTrackId}/save-artist-photo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                photo_url: photoUrl,
                artist: currentTracks.find(t => t.id === currentPhotoTrackId).artist
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || errorData.error || 'Ошибка сохранения фото');
        }

        const result = await response.json();

        if (result.success) {
            showPhotoStatus('✅ Фото артиста сохранено!', 'success');
            setTimeout(() => {
                closePhotoModal();
                loadTracks();
            }, 1500);
        } else {
            throw new Error(result.error || 'Неизвестная ошибка');
        }

    } catch (error) {
        console.error('❌ Ошибка сохранения фото:', error);
        showPhotoStatus(`❌ Ошибка: ${error.message}`, 'error');
    }
}

function uploadArtistPhoto() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';

    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        if (!file.type.startsWith('image/')) {
            showPhotoStatus('❌ Пожалуйста, выберите изображение', 'error');
            return;
        }

        showPhotoStatus('📤 Загружаем фото...', 'loading');

        const formData = new FormData();
        formData.append('photo', file);

        try {
            const response = await fetch(`${API_BASE}/tracks/${currentPhotoTrackId}/upload-artist-photo`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || errorData.error || 'Ошибка загрузки фото');
            }

            const result = await response.json();

            if (result.success) {
                showPhotoStatus('✅ Фото артиста загружено!', 'success');
                setTimeout(() => {
                    closePhotoModal();
                    loadTracks();
                }, 1500);
            } else {
                throw new Error(result.error || 'Неизвестная ошибка');
            }

        } catch (error) {
            console.error('❌ Ошибка загрузки фото:', error);
            showPhotoStatus(`❌ Ошибка: ${error.message}`, 'error');
        }
    };

    input.click();
}

function showPhotoStatus(message, type) {
    const statusElement = document.getElementById('photoStatus');
    if (!statusElement) return;
    statusElement.innerHTML = message;
    statusElement.className = `status ${type}`;
    statusElement.style.display = 'block';
}

function closePhotoModal() {
    const modal = document.getElementById('photoModal');
    if (modal) modal.style.display = 'none';
    currentPhotoTrackId = null;
    currentPhotoUrls = [];
    currentPhotoIndex = 0;
    isSearchingPhotos = false;
}

// =========================
// TRACK MANAGEMENT FUNCTIONS
// =========================

async function editTrack(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) {
        showNotification('Трек не найден', 'error');
        return;
    }

    currentEditingTrack = track;

    document.getElementById('editTrackId').value = track.id;
    document.getElementById('editArtist').value = track.artist;
    document.getElementById('editTitle').value = track.title;

    document.getElementById('editModal').style.display = 'block';
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
    currentEditingTrack = null;
    document.getElementById('editForm')?.reset();
}

async function saveTrack(event) {
    event.preventDefault();

    const trackId = parseInt(document.getElementById('editTrackId').value);
    const artist = document.getElementById('editArtist').value.trim();
    const title = document.getElementById('editTitle').value.trim();

    if (!artist || !title) {
        showNotification('Заполните все поля', 'warning');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/tracks/${trackId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist, title })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Ошибка обновления');
        }

        showNotification('Трек успешно обновлен', 'success');
        closeEditModal();
        await loadTracks();

    } catch (error) {
        console.error('Ошибка сохранения:', error);
        showNotification(`Ошибка: ${error.message}`, 'error');
    }
}

async function deleteTrack(trackId) {
    if (!confirm('Вы уверены, что хотите удалить этот трек?')) return;

    try {
        const response = await fetch(`${API_BASE}/tracks/${trackId}`, { method: 'DELETE' });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Ошибка удаления');
        }

        showNotification('Трек успешно удален', 'success');
        await loadTracks();

    } catch (error) {
        console.error('Ошибка удаления:', error);
        showNotification(`Ошибка: ${error.message}`, 'error');
    }
}

async function clearTracks() {
    if (!confirm('Вы уверены, что хотите очистить всю медиатеку? Это действие нельзя отменить.')) return;

    showStatus('mediaStatus', '🔄 Очищаем медиатеку...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks`, { method: 'DELETE' });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Ошибка очистки');
        }

        showStatus('mediaStatus', '✅ Медиатека очищена', 'success');
        await loadTracks();

    } catch (error) {
        console.error('Ошибка очистки:', error);
        showStatus('mediaStatus', `❌ Ошибка: ${error.message}`, 'error');
    }
}

// Загрузка статуса системы
async function loadSystemStatus() {
    const container = document.getElementById('systemStatus');
    if (!container) return;
    container.innerHTML = '<p>🔄 Загружаем информацию о системе...</p>';

    try {
        const response = await fetch(`${API_BASE}/status`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const status = await response.json();

        container.innerHTML = `
            <div class="system-status">
                <div class="status-item ${status.status === 'running' ? 'success' : 'error'}">
                    <span class="label">Статус приложения:</span>
                    <span class="value">${status.status === 'running' ? '✅ Работает' : '❌ Остановлено'}</span>
                </div>
                <div class="status-item ${status.tracks_count > 0 ? 'success' : 'warning'}">
                    <span class="label">Треков в медиатеке:</span>
                    <span class="value">${status.tracks_count}</span>
                </div>
                <div class="status-item ${status.tracks_with_photos > 0 ? 'success' : 'warning'}">
                    <span class="label">Треков с фото:</span>
                    <span class="value">${status.tracks_with_photos || 0}</span>
                </div>
                <div class="status-item ${status.musical_loto_ready ? 'success' : 'warning'}">
                    <span class="label">Готовность к лото:</span>
                    <span class="value">${status.musical_loto_ready ? '✅ Готово' : '❌ Недостаточно треков'}</span>
                </div>
                <div class="status-item">
                    <span class="label">Версия приложения:</span>
                    <span class="value">${status.version}</span>
                </div>
                <div class="status-item">
                    <span class="label">API сервер:</span>
                    <span class="value">✅ Активен</span>
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Ошибка загрузки статуса:', error);
        container.innerHTML = `
            <div class="status error">
                ❌ Ошибка загрузки статуса системы: ${error.message}
            </div>
        `;
    }
}

// ===== КЛЮЧЕВОЕ: корректный счётчик треков из /api/tracks/count =====
async function updateTracksCount() {
    try {
        const res = await fetch(`${API_BASE}/tracks/count`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const count = Number(data.count ?? 0);

        // Обновляем счетчик в презентации
        const countElement = document.getElementById('tracksCount');
        if (countElement) countElement.textContent = count;

        const readyStatus = document.getElementById('presentationReadyStatus');
        if (readyStatus) {
            if (count >= 1) {
                readyStatus.textContent = '✅ Готово к генерации';
                readyStatus.style.color = 'var(--success)';
            } else {
                readyStatus.textContent = '❌ Недостаточно треков';
                readyStatus.style.color = 'var(--error)';
            }
        }

        const generateBtn = document.getElementById('generatePresentationBtn');
        if (generateBtn) {
            generateBtn.disabled = count < 1;
            generateBtn.title = count < 1 ?
                'Добавьте хотя бы 1 трек в медиатеку' :
                'Сгенерировать презентацию';
        }

    } catch (e) {
        console.warn('Не удалось обновить счётчик треков:', e);
    }
}

function updateGenerateButtonState(count) {
    const btn = getGenerateBtn();
    if (!btn) return;

    const ready = count >= 40;
    btn.disabled = !ready;
    btn.title = ready
        ? 'Сгенерировать презентацию'
        : `Нужно минимум 40 треков (сейчас: ${count})`;
}

// Показать статус
function showStatus(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.innerHTML = message;
    element.className = `status ${type}`;
}

// =========================
// AUDIO EDITOR FUNCTIONS
// =========================

async function openAudioEditor(trackId) {
    console.log('Opening audio editor for track:', trackId);

    if (isGeneratingWaveform) {
        showNotification('Дождитесь завершения генерации waveform', 'warning');
        return;
    }

    currentEditorTrack = trackId;

    const track = await loadTrackInfo(trackId);
    if (!track) {
        showNotification('Ошибка загрузки трека', 'error');
        return;
    }

    segmentStart = track.segment_start || 0;
    segmentDuration = track.segment_duration || 30;
    totalTrackDuration = track.duration || 180;

    document.getElementById('audioEditorModal').style.display = 'block';

    updateTrackInfo(track);

    await loadWaveform(trackId);

    updateTimelineDisplay();

    document.getElementById('analysisInfo').style.display = 'none';

    initAudioPlayer();
}

function initAudioPlayer() {
    if (audioElement) {
        audioElement.pause();
        audioElement.remove();
    }

    audioElement = new Audio();
    audioElement.preload = 'none';
    audioElement.volume = currentVolume / 100;

    audioElement.addEventListener('ended', function () {
        stopPlayback();
    });

    audioElement.addEventListener('error', function (e) {
        console.error('Audio playback error:', e);
        showNotification('Ошибка воспроизведения аудио', 'error');
        stopPlayback();
    });

    audioElement.addEventListener('canplaythrough', function () {
        console.log('Audio is ready to play');
    });
}

function closeAudioEditor() {
    stopPlayback();
    document.getElementById('audioEditorModal').style.display = 'none';
    currentEditorTrack = null;
    isGeneratingWaveform = false;

    if (audioElement) {
        audioElement.remove();
        audioElement = null;
    }
}

async function loadTrackInfo(trackId) {
    try {
        const response = await fetch(`${API_BASE}/tracks`);
        if (!response.ok) throw new Error('Failed to load tracks');

        const tracks = await response.json();
        return tracks.find(t => t.id === trackId);
    } catch (error) {
        console.error('Error loading track info:', error);
        return null;
    }
}

function updateTrackInfo(track) {
    const infoElement = document.getElementById('editorTrackInfo');
    if (!infoElement) return;
    infoElement.innerHTML = `
        <h4>${escapeHtml(track.artist)} - ${escapeHtml(track.title)}</h4>
        <p>Файл: ${track.original_filename}</p>
        <p class="text-muted">Текущий отрезок: ${formatTime(track.segment_start || 0)} - ${formatTime((track.segment_start || 0) + (track.segment_duration || 30))}</p>
    `;

    const totalEl = document.getElementById('totalDurationDisplay');
    if (totalEl) totalEl.textContent = formatTime(totalTrackDuration);
}

async function loadWaveform(trackId) {
    if (isGeneratingWaveform) {
        console.log('Waveform generation already in progress');
        return;
    }

    const container = document.getElementById('waveformContainer');
    if (!container) return;
    container.innerHTML = '<div class="waveform-loading">Генерация waveform...</div>';

    isGeneratingWaveform = true;

    try {
        const response = await fetch(`${API_BASE}/tracks/${trackId}/waveform`);
        if (!response.ok) throw new Error('Failed to load waveform');

        const data = await response.json();

        if (data.waveform_data) {
            container.innerHTML = `
                <img src="${data.waveform_data}" alt="Waveform" class="waveform-image" 
                     onclick="handleWaveformClick(event)" 
                     onload="initSegmentMarker()"
                     onerror="handleWaveformError()">
                <div class="segment-marker" id="segmentMarker">
                    <div class="segment-handle segment-handle-left" id="handleLeft" 
                         onmousedown="startDrag(event, 'left')"></div>
                    <div class="segment-handle segment-handle-right" id="handleRight" 
                         onmousedown="startDrag(event, 'right')"></div>
                </div>
            `;
        } else {
            container.innerHTML = '<div class="waveform-loading">Waveform не доступен</div>';
        }
    } catch (error) {
        console.error('Error loading waveform:', error);
        container.innerHTML = '<div class="waveform-loading">Ошибка загрузки waveform</div>';
    } finally {
        isGeneratingWaveform = false;
    }
}

function handleWaveformError() {
    const container = document.getElementById('waveformContainer');
    if (container) container.innerHTML = '<div class="waveform-loading">Ошибка загрузки изображения waveform</div>';
    isGeneratingWaveform = false;
}

function initSegmentMarker() {
    updateSegmentMarker();
    const marker = document.getElementById('segmentMarker');
    if (marker) marker.style.display = 'block';
    isGeneratingWaveform = false;
}

function updateSegmentMarker() {
    const marker = document.getElementById('segmentMarker');
    const container = document.getElementById('waveformContainer');

    if (!marker || !container) return;

    const startPercent = (segmentStart / totalTrackDuration) * 100;
    const durationPercent = (segmentDuration / totalTrackDuration) * 100;

    marker.style.left = startPercent + '%';
    marker.style.width = durationPercent + '%';
}

function updateTimelineDisplay() {
    const startTime = segmentStart;
    const endTime = Math.min(segmentStart + segmentDuration, totalTrackDuration);

    const timeElements = [
        'timeDisplay',
        'segmentStartTime',
        'segmentEndTime',
        'segmentStartTimeDisplay',
        'segmentEndTimeDisplay'
    ];

    timeElements.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            if (id === 'timeDisplay') {
                element.textContent = `${formatTime(startTime)} - ${formatTime(endTime)}`;
            } else if (id.includes('Start')) {
                element.textContent = formatTime(startTime);
            } else if (id.includes('End')) {
                element.textContent = formatTime(endTime);
            }
        }
    });

    const durEl = document.getElementById('segmentDurationDisplay');
    if (durEl) durEl.textContent = `${segmentDuration} сек`;
    const prevInfo = document.getElementById('previewInfo');
    if (prevInfo) prevInfo.textContent = `Начните с ${formatTime(startTime)}, длительность ${segmentDuration} секунд`;

    const slider = document.getElementById('timeSlider');
    if (slider) {
        const maxValue = Math.max(0, totalTrackDuration - segmentDuration);
        slider.max = maxValue;
        slider.value = segmentStart;
        slider.disabled = maxValue <= 0;
    }

    updateSegmentMarker();
}

function moveSegment(seconds) {
    const newStart = segmentStart + seconds;

    if (newStart < 0) {
        segmentStart = 0;
    } else if (newStart + segmentDuration > totalTrackDuration) {
        segmentStart = totalTrackDuration - segmentDuration;
    } else {
        segmentStart = newStart;
    }

    updateTimelineDisplay();
}

function setSegmentToStart() {
    segmentStart = 0;
    updateTimelineDisplay();
}

function setSegmentToMiddle() {
    segmentStart = Math.max(0, (totalTrackDuration - segmentDuration) / 2);
    updateTimelineDisplay();
}

function setSegmentToEnd() {
    segmentStart = Math.max(0, totalTrackDuration - segmentDuration);
    updateTimelineDisplay();
}

async function suggestBestSegment() {
    if (!currentEditorTrack) return;

    try {
        showNotification('🔍 Анализируем аудио...', 'info');

        const response = await fetch(`${API_BASE}/tracks/${currentEditorTrack}/suggest-segment`);
        if (!response.ok) throw new Error('Failed to get suggestion');

        const data = await response.json();

        if (data.success && data.suggested_start !== undefined) {
            segmentStart = data.suggested_start;

            if (data.analysis_details) {
                showAnalysisResults(data.analysis_details);
            }

            updateTimelineDisplay();
            showNotification(`🎵 Найден отличный отрезок! Начало: ${formatTime(segmentStart)}`, 'success');
        } else {
            throw new Error('Invalid response format');
        }

    } catch (error) {
        console.error('Error getting segment suggestion:', error);
        showNotification('Ошибка анализа аудио', 'error');
    }
}

function showAnalysisResults(analysis) {
    const analysisInfo = document.getElementById('analysisInfo');
    const analysisResult = document.getElementById('analysisResult');

    if (!analysisInfo || !analysisResult) return;

    analysisInfo.style.display = 'block';

    let html = `
        <div style="margin-bottom: 10px;">
            <strong>Метод:</strong> ${analysis.method || 'неизвестно'}<br>
            <strong>Оценка:</strong> ${((analysis.score || 0) * 100).toFixed(1)}%
        </div>
        <div class="analysis-methods">
            <div class="method-item">
                <div class="method-name">🎵 Энергия</div>
                <div class="method-value">${analysis.energy_score ? (analysis.energy_score * 100).toFixed(0) + '%' : '—'}</div>
            </div>
            <div class="method-item">
                <div class="method-name">📊 Вариативность</div>
                <div class="method-value">${analysis.variability_score ? (analysis.variability_score * 100).toFixed(0) + '%' : '—'}</div>
            </div>
            <div class="method-item">
                <div class="method-name">⚡ Пики</div>
                <div class="method-value">${analysis.peaks_score ? (analysis.peaks_score * 100).toFixed(0) + '%' : '—'}</div>
            </div>
        </div>
    `;

    analysisResult.innerHTML = html;
}

async function playSegment() {
    if (!currentEditorTrack || isPlaying) return;

    try {
        const track = await loadTrackInfo(currentEditorTrack);
        if (!track) throw new Error('Track not found');

        const segmentUrl = `${API_BASE}/tracks/${currentEditorTrack}/segment-file?start_time=${segmentStart}&duration=${segmentDuration}`;

        console.log('Playing from URL:', segmentUrl);

        audioElement.src = segmentUrl;
        audioElement.currentTime = 0;

        const playPromise = audioElement.play();
        if (playPromise !== undefined) await playPromise;

        isPlaying = true;
        updatePlayButton();
        startPlaybackTimer();
        showNotification('Воспроизведение началось', 'success');

    } catch (error) {
        console.error('Error playing segment:', error);
        showNotification('Ошибка воспроизведения: ' + error.message, 'error');
        stopPlayback();
    }
}

function stopPlayback() {
    if (audioElement) {
        audioElement.pause();
        audioElement.currentTime = 0;
    }

    isPlaying = false;
    clearInterval(playbackInterval);
    updatePlayButton();
    const t = document.getElementById('playbackTime');
    if (t) t.textContent = '--:--';
}

function togglePlayback() {
    if (isPlaying) stopPlayback();
    else playSegment();
}

function updatePlayButton() {
    const playBtn = document.getElementById('playBtn');
    const stopBtn = document.getElementById('stopBtn');

    if (!playBtn || !stopBtn) return;

    if (isPlaying) {
        playBtn.style.display = 'none';
        stopBtn.style.display = 'block';
    } else {
        playBtn.style.display = 'block';
        stopBtn.style.display = 'none';
    }
}

function startPlaybackTimer() {
    let elapsed = 0;
    const playbackTimeElement = document.getElementById('playbackTime');
    if (!playbackTimeElement) return;

    playbackTimeElement.textContent = formatTime(elapsed);

    clearInterval(playbackInterval);

    playbackInterval = setInterval(() => {
        elapsed++;
        playbackTimeElement.textContent = formatTime(elapsed);

        if (elapsed >= segmentDuration) {
            stopPlayback();
        }
    }, 1000);
}

async function saveSegment() {
    if (!currentEditorTrack) return;

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentEditorTrack}/segment`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_time: segmentStart, duration: segmentDuration })
        });

        if (response.ok) {
            await response.json().catch(() => { });
            showNotification('Отрезок сохранен!', 'success');
            closeAudioEditor();
            await loadTracks();
        } else {
            throw new Error('Save failed');
        }
    } catch (error) {
        console.error('Error saving segment:', error);
        showNotification('Ошибка сохранения отрезка', 'error');
    }
}

function startDrag(event, type) {
    isDragging = true;
    dragType = type;
    dragStartX = event.clientX;
    initialSegmentStart = segmentStart;

    document.addEventListener('mousemove', handleDrag);
    document.addEventListener('mouseup', stopDrag);
    event.preventDefault();
}

function handleDrag(event) {
    if (!isDragging) return;

    const container = document.getElementById('waveformContainer');
    if (!container) return;

    const deltaX = event.clientX - dragStartX;
    const deltaPercent = (deltaX / container.offsetWidth) * 100;
    const deltaTime = (deltaPercent / 100) * totalTrackDuration;

    if (dragType === 'left') {
        segmentStart = Math.max(0, Math.min(initialSegmentStart + deltaTime, totalTrackDuration - segmentDuration));
    } else if (dragType === 'right') {
        const newDuration = segmentDuration + deltaTime;
        segmentDuration = Math.max(5, Math.min(newDuration, totalTrackDuration - segmentStart));
    }

    updateTimelineDisplay();
}

function stopDrag() {
    isDragging = false;
    dragType = null;

    document.removeEventListener('mousemove', handleDrag);
    document.removeEventListener('mouseup', stopDrag);
}

function handleWaveformClick(event) {
    if (isDragging) return;

    const container = document.getElementById('waveformContainer');
    if (!container) return;

    const clickX = event.offsetX;
    const clickPercent = (clickX / container.offsetWidth);
    const clickTime = clickPercent * totalTrackDuration;

    segmentStart = Math.max(0, Math.min(clickTime, totalTrackDuration - segmentDuration));
    updateTimelineDisplay();
}

// Volume Control Functions
function changeVolume(value) {
    currentVolume = parseInt(value);
    const volumeValueElement = document.getElementById('volumeValue');
    if (volumeValueElement) volumeValueElement.textContent = value + '%';

    if (audioElement) audioElement.volume = currentVolume / 100;

    updateVolumeIcon();
}

function toggleMute() {
    isMuted = !isMuted;
    if (audioElement) audioElement.muted = isMuted;
    updateVolumeIcon();
}

function updateVolumeIcon() {
    const icon = document.getElementById('volumeIcon');
    if (!icon) return;

    if (isMuted) icon.textContent = '🔇';
    else if (currentVolume === 0) icon.textContent = '🔇';
    else if (currentVolume < 30) icon.textContent = '🔈';
    else if (currentVolume < 70) icon.textContent = '🔉';
    else icon.textContent = '🔊';
}

// =========================
// LOCAL FILES MANAGEMENT FUNCTIONS
// =========================

async function loadLocalFilesInfo() {
    await loadBasePptxInfo();
    await loadArtistPhotos();
}

// Загрузка информации о base.pptx
async function loadBasePptxInfo() {
    try {
        const response = await fetch(`${API_BASE}/local/base-pptx`);
        const data = await response.json();

        const basePptxBlock = document.getElementById('basePptxBlock');
        if (!basePptxBlock) return;

        if (data.exists) {
            basePptxBlock.innerHTML = `
                <div class="file-info-card success">
                    <div class="file-icon">📄</div>
                    <div class="file-details">
                        <h4>base.pptx</h4>
                        <p>Размер: ${(data.size / 1024 / 1024).toFixed(2)} MB</p>
                        <p class="text-success">✅ Файл готов к использованию</p>
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-small btn-secondary" onclick="downloadBasePptx()">
                            📥 Скачать
                        </button>
                        <button class="btn btn-small btn-danger" onclick="deleteBasePptx()">
                            🗑️ Удалить
                        </button>
                    </div>
                </div>
            `;
        } else {
            basePptxBlock.innerHTML = `
                <div class="file-info-card error">
                    <div class="file-icon">❌</div>
                    <div class="file-details">
                        <h4>base.pptx</h4>
                        <p class="text-error">Файл не найден</p>
                        <p>Для генерации презентаций необходим файл base.pptx</p>
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-small btn-primary" onclick="downloadBasePptxFromDropbox()">
                            📥 Скачать из облака
                        </button>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Ошибка загрузки информации о base.pptx:', error);
    }
}

// Скачать base.pptx
async function downloadBasePptx() {
    try {
        const response = await fetch(`${API_BASE}/local/download-base-pptx`);
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'base.pptx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showNotification('base.pptx успешно скачан', 'success');
        } else {
            throw new Error('Ошибка скачивания');
        }
    } catch (error) {
        console.error('Ошибка скачивания base.pptx:', error);
        showNotification('Ошибка скачивания base.pptx', 'error');
    }
}

// Скачать base.pptx из Dropbox
async function downloadBasePptxFromDropbox() {
    try {
        showNotification('📥 Скачиваем base.pptx из Dropbox...', 'info');

        const response = await fetch(`${API_BASE}/dropbox/download-base-pptx`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showNotification('✅ base.pptx успешно скачан из Dropbox', 'success');
            await loadBasePptxInfo();
        } else {
            throw new Error(result.error || 'Ошибка скачивания');
        }
    } catch (error) {
        console.error('Ошибка скачивания base.pptx из Dropbox:', error);
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    }
}

// Удалить base.pptx
async function deleteBasePptx() {
    if (!confirm('Вы уверены, что хотите удалить base.pptx?')) return;

    try {
        // В реальном приложении здесь будет вызов API для удаления файла
        // Пока просто показываем сообщение
        showNotification('Функция удаления base.pptx будет реализована в будущем', 'info');
    } catch (error) {
        console.error('Ошибка удаления base.pptx:', error);
        showNotification('Ошибка удаления base.pptx', 'error');
    }
}

// Загрузка base.pptx
async function handleBasePptxUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.name.endsWith('.pptx')) {
        showNotification('Пожалуйста, выберите файл в формате .pptx', 'warning');
        return;
    }

    try {
        showNotification('📤 Загружаем base.pptx...', 'info');

        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/local/upload-base-pptx`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            showNotification('✅ base.pptx успешно загружен', 'success');
            await loadBasePptxInfo();
        } else {
            throw new Error(result.error || 'Ошибка загрузки');
        }
    } catch (error) {
        console.error('Ошибка загрузки base.pptx:', error);
        showNotification(`❌ Ошибка загрузки: ${error.message}`, 'error');
    }

    // Сбрасываем input
    event.target.value = '';
}

// Загрузка фото артистов
async function handleArtistPhotosUpload(event) {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;

    // Проверяем что все файлы - изображения
    const invalidFiles = files.filter(file => !file.type.startsWith('image/'));
    if (invalidFiles.length > 0) {
        showNotification('Пожалуйста, выбирайте только изображения', 'warning');
        return;
    }

    try {
        showNotification(`📤 Загружаем ${files.length} фото...`, 'info');

        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file);
        });

        const response = await fetch(`${API_BASE}/local/upload-artist-photos`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            showNotification(`✅ Успешно загружено ${result.uploaded.length} фото`, 'success');
            await loadArtistPhotos();
        } else {
            throw new Error(result.error || 'Ошибка загрузки');
        }
    } catch (error) {
        console.error('Ошибка загрузки фото артистов:', error);
        showNotification(`❌ Ошибка загрузки: ${error.message}`, 'error');
    }

    // Сбрасываем input
    event.target.value = '';
}

// Загрузка списка фото артистов
async function loadArtistPhotos() {
    try {
        const response = await fetch(`${API_BASE}/local/artist-photos`);
        const data = await response.json();

        const photosList = document.getElementById('artistPhotosList');
        const photosCount = document.getElementById('photosCount');

        if (!photosList) return;

        if (data.photos && data.photos.length > 0) {
            photosList.innerHTML = data.photos.map(photo => `
                <div class="artist-photo-card">
                    <div class="photo-preview">
                        <img src="${API_BASE}/local/artist-photo/${encodeURIComponent(photo.filename)}" 
                             alt="${photo.artist_name}" 
                             onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgdmlld0JveD0iMCAwIDEwMCAxMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiNmMWYxZjEiLz48dGV4dCB4PSI1MCIgeT0iNTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxMiIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPs6PzqPOlc6dzp/Oo86ZPC90ZXh0Pjwvc3ZnPg=='">
                    </div>
                    <div class="photo-info">
                        <h5>${escapeHtml(photo.artist_name)}</h5>
                        <p class="text-muted">${photo.size_mb || 'N/A'}</p>
                    </div>
                    <div class="photo-actions">
                        <button class="btn btn-small btn-danger" onclick="deleteArtistPhoto('${photo.filename}')">
                            🗑️
                        </button>
                    </div>
                </div>
            `).join('');

            if (photosCount) {
                photosCount.textContent = `${data.photos.length} фото`;
            }
        } else {
            photosList.innerHTML = `
                <div class="empty-state">
                    <div class="icon">🖼️</div>
                    <h3>Нет загруженных фото</h3>
                    <p>Загрузите фото артистов для использования в презентациях</p>
                </div>
            `;

            if (photosCount) {
                photosCount.textContent = '0 фото';
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки фото артистов:', error);
    }
}

// Обновить список фото
async function refreshArtistPhotos() {
    await loadArtistPhotos();
}

// Удалить фото артиста
async function deleteArtistPhoto(filename) {
    if (!confirm('Вы уверены, что хотите удалить это фото?')) return;

    try {
        const response = await fetch(`${API_BASE}/local/artist-photo/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            showNotification('Фото успешно удалено', 'success');
            await loadArtistPhotos();
        } else {
            throw new Error(result.error || 'Ошибка удаления');
        }
    } catch (error) {
        console.error('Ошибка удаления фото:', error);
        showNotification(`❌ Ошибка удаления: ${error.message}`, 'error');
    }
}

// Скачать фото артистов из Dropbox
async function downloadArtistPhotosFromDropbox() {
    try {
        showNotification('📥 Скачиваем фото артистов из Dropbox...', 'info');

        // В реальном приложении здесь будет вызов API для скачивания фото из Dropbox
        // Пока просто показываем сообщение
        showNotification('Функция скачивания фото из Dropbox будет реализована в будущем', 'info');
    } catch (error) {
        console.error('Ошибка скачивания фото из Dropbox:', error);
        showNotification('Ошибка скачивания фото из Dropbox', 'error');
    }
}

// Форматирование времени
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Утилиты
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Показать уведомление (тост)
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 16px;
        box-shadow: var(--shadow);
        z-index: 1001;
        max-width: 400px;
        animation: slideInRight 0.3s ease;
        border-left: 4px solid ${getNotificationColor(type)};
    `;

    notification.innerHTML = `
        <div class="notification-content">
            <span class="notification-icon">${getNotificationIcon(type)}</span>
            <span class="notification-message">${message}</span>
            <button class="notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
    `;

    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            .notification-content {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .notification-close {
                background: none;
                border: none;
                font-size: 18px;
                cursor: pointer;
                color: var(--text-muted);
                margin-left: auto;
            }
            .notification-close:hover {
                color: var(--text-light);
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentElement) notification.remove();
    }, 5000);
}

function getNotificationIcon(type) {
    const icons = { 'success': '✅', 'error': '❌', 'warning': '⚠️', 'info': 'ℹ️' };
    return icons[type] || 'ℹ️';
}

function getNotificationColor(type) {
    const colors = { 'success': '#16a34a', 'error': '#dc2626', 'warning': '#d97706', 'info': '#2563eb' };
    return colors[type] || '#2563eb';
}

// Вспомогательные функции для upload panel
function uploadPanel() { return document.getElementById('uploadProgressPanel'); }
function uploadRows() { return document.getElementById('uploadRows'); }
function uploadSummary() { return document.getElementById('uploadSummary'); }
function cancelAllBtn() { return document.getElementById('cancelAllUploadsBtn'); }

// Обработчик ошибок
window.addEventListener('error', function (e) {
    console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', function (e) {
    console.error('Unhandled promise rejection:', e.reason);
    e.preventDefault();
});

console.log('🎵 Music Loto Maker frontend загружен!');