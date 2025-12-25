// frontend/js/app.js
const API_BASE = '/api';
let currentTracks = [];
let presentationTrackList = [];
let currentEditingTrack = null;
let segmentStart = 0;
let segmentDuration = 30;
let totalTrackDuration = 0;
let isPlaying = false;
let playbackInterval = null;
let audioElement = null;
let isGeneratingWaveform = false;
const MAX_FILES_TOTAL = 120;
const MAX_CONCURRENT_UPLOADS = 6;
let uploadQueue = [];
let activeUploads = 0;
let currentUploads = new Map();
let uploadCounter = 0;
let currentVolume = 50;
let isMuted = false;
let currentPhotoTrackId = null;
let currentPhotoUrls = [];
let currentPhotoIndex = 0;
let isSearchingPhotos = false;
let downloadProgress = {
    total: 0,
    current: 0,
    currentTrack: '',
    isDownloading: false,
    results: []
};
let statusPollInterval = null;
let currentViewMode = 'compact';

// Делаем переменные глобальными для track_view_manager.js
window.currentTracks = currentTracks;
window.presentationTrackList = presentationTrackList;
window.currentViewMode = currentViewMode;
window.API_BASE = API_BASE;
// В самое начало app.js добавьте:
if (!window.currentViewMode) window.currentViewMode = 'compact';
if (!window.presentationTrackList) window.presentationTrackList = [];

// ===== helpers =====
const $ = (sel) =>
    document.querySelector(sel) ||
    document.querySelector(`[data-id="${sel.replace('#', '').replace('.', '')}"]`);
// Добавьте этот код в начало файла или в функцию инициализации
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();

    // Инициализация менеджера представления с задержкой
    setTimeout(function () {
        if (typeof initTrackViewManager === 'function') {
            initTrackViewManager();
        } else if (window.trackViewManager && typeof window.trackViewManager.initTrackViewManager === 'function') {
            window.trackViewManager.initTrackViewManager();
        }
    }, 1000);

    setInterval(updateTracksCount, 10000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateTracksCount();
    });
});
function getGenerateBtn() {
    return document.querySelector('[data-id="btn-generate"]') || document.getElementById('btn-generate') || document.querySelector('#presentation .btn-primary.btn-large');
}

let presentationWebSocket = null;

function connectPresentationWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/presentation/progress`;
    presentationWebSocket = new WebSocket(wsUrl);
    presentationWebSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'progress') {
            updatePresentationProgress(data.current, data.total, data.message);
        }
    };
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();
    initTrackViewManager();

    // авто-обновление счётчика каждые 10 сек
    setInterval(updateTracksCount, 10000);

    // обновляем при возвращении на вкладку браузера
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateTracksCount();
    });
});

function normalizeTrackString(str) {
    return str.toLowerCase().replace(/[^\wа-яё]/g, '');
}

function parsePresentationTrackList(trackListText) {
    const lines = trackListText.trim().split('\n').map(l => l.trim()).filter(l => l);
    const tracks = [];
    for (let line of lines) {
        line = line
            .replace(/^\d+\.\s*/, '')
            .replace(/^\d+\)\s*/, '')
            .replace(/^[-•*]\s*/, '')
            .trim();
        let artist = '', title = '';
        const separators = [' - ', ' – ', ' — '];
        let found = false;
        for (let sep of separators) {
            if (line.includes(sep)) {
                const parts = line.split(sep, 2);
                artist = parts[0].trim();
                title = parts[1].trim();
                found = true;
                break;
            }
        }
        if (!found) {
            artist = 'Неизвестный исполнитель';
            title = line;
        }
        tracks.push({ artist, title, original_line: line });
    }
    return tracks;
}

// === VALIDATION ===
async function validatePresentationTrackList() {
    const trackListText = document.getElementById('presentationTrackList').value;
    const tracks = parsePresentationTrackList(trackListText);
    const missingListEl = document.getElementById('missingTracksList');

    if (tracks.length === 0) {
        missingListEl.style.display = 'none';
        presentationTrackList = [];
        // ТОЛЬКО РЕНДЕРИМ, не обновляем статистику здесь
        renderPresentationTracksCompact([]);
        // Обновляем статистику отдельно
        setTimeout(() => updatePresentationMiniLibraryStats(), 100);
        return;
    }

    const missing = [];
    const valid = [];

    for (const t of tracks) {
        const found = currentTracks.find(tr =>
            normalizeTrackString(tr.artist) === normalizeTrackString(t.artist) &&
            normalizeTrackString(tr.title) === normalizeTrackString(t.title)
        );
        if (found) {
            valid.push({
                ...found,
                original_line: t.original_line
            });
        } else {
            missing.push(`${t.artist} - ${t.title}`);
        }
    }

    presentationTrackList = valid;
    window.presentationTrackList = valid; // Убедимся, что глобальная переменная обновлена

    if (missing.length > 0) {
        missingListEl.textContent = missing.join('\n');
        missingListEl.style.display = 'block';
    } else {
        missingListEl.style.display = 'none';
    }

    // РЕНДЕРИМ треки
    renderPresentationTracksCompact(valid);

    // Обновляем статистику отдельно с небольшой задержкой
    setTimeout(() => {
        if (typeof updatePresentationMiniLibraryStats === 'function') {
            updatePresentationMiniLibraryStats();
        }
    }, 100);
}

function updatePresentationDownloadProgress() {
    const progressStatus = document.getElementById('presentationProgressStatus');
    const progressCount = document.getElementById('presentationProgressCount');
    const progressFill = document.getElementById('presentationProgressFill');
    const progressDetails = document.getElementById('presentationProgressDetails');
    if (!progressStatus || !progressCount || !progressFill) return;

    const percent = downloadProgress.total > 0 ?
        Math.round((downloadProgress.current / downloadProgress.total) * 100) : 0;
    progressStatus.textContent = downloadProgress.currentTrack || 'Подготовка к скачиванию...';
    progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
    progressFill.style.width = `${percent}%`;

    if (downloadProgress.isDownloading) {
        progressFill.classList.add('pulsing');
        progressFill.style.background = 'var(--primary)';
    } else {
        progressStatus.textContent = 'Скачивание завершено';
        progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
        progressFill.style.width = '100%';
        progressFill.classList.remove('pulsing');

        if (downloadProgress.failedTracks.length > 0 || downloadProgress.duplicateTracks.length > 0) {
            progressFill.style.background = 'var(--warning)';
        } else {
            progressFill.style.background = 'var(--success)';
        }
        updatePresentationFinalResults();
    }

    updatePresentationProgressDetails();
}
function updatePresentationProgressDetails() {
    const progressDetails = document.getElementById('presentationProgressDetails');
    if (!progressDetails) return;
    let detailsHTML = '<div class="progress-details-current">';
    if (downloadProgress.currentTrack && downloadProgress.currentTrack !== 'Подготовка к скачиванию...') {
        detailsHTML += `<div class="progress-detail-item progress-detail-processing">
            🔄 ${downloadProgress.currentTrack}
        </div>`;
    }

    const recentResults = downloadProgress.results.slice(-5);
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
// Обновить финальные результаты в блоке презентации
function updatePresentationFinalResults() {
    const progressDetails = document.getElementById('presentationProgressDetails');
    if (!progressDetails) return;
    const successCount = downloadProgress.successfulTracks.length;
    const duplicateCount = downloadProgress.duplicateTracks.length;
    const errorCount = downloadProgress.failedTracks.length;
    let detailsHTML = '<div class="final-results">';
    detailsHTML += '<h4>Итоговые результаты:</h4>';

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
async function downloadMissingTracksFromPresentationList() {
    const missingEl = document.getElementById('missingTracksList');
    if (missingEl.style.display === 'none' || !missingEl.textContent.trim()) {
        showNotification('Нет недостающих треков', 'info');
        return;
    }

    // СОХРАНЯЕМ ТЕКСТ списка перед очисткой
    const trackListText = document.getElementById('presentationTrackList').value;

    // ПОЛНОСТЬЮ ОЧИЩАЕМ presentationTrackList
    presentationTrackList = [];
    renderPresentationTracksCompact([]);

    // Заполняем trackList для скачивания
    document.getElementById('trackList').value = missingEl.textContent;

    // Вызываем стандартную функцию скачивания
    await downloadTrackList();

    // Ждём и ВОССТАНАВЛИВАЕМ список с НОВЫМИ данными
    setTimeout(async () => {
        await loadTracks(); // Загружаем актуальные треки

        // ВОССТАНАВЛИВАЕМ оригинальный список для перевалидации
        document.getElementById('presentationTrackList').value = trackListText;
        await validatePresentationTrackList();

    }, 3000);
}

async function toggleProcessed(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) return;

    const newStatus = !track.processed;
    try {
        // Используем track_view_manager, если доступен
        if (typeof window.trackViewManager?.toggleProcessedStatus === 'function') {
            await window.trackViewManager.toggleProcessedStatus(trackId);
        } else {
            // fallback
            await fetch(`${API_BASE}/tracks/${trackId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ processed: newStatus })
            });
            track.processed = newStatus;
        }

        // Синхронизируем presentationTrackList
        const presTrack = presentationTrackList.find(t => t.id === trackId);
        if (presTrack) {
            presTrack.processed = newStatus;
        }

        // Обновляем оба списка
        renderTracks(currentTracks);
        renderPresentationTracksCompact(presentationTrackList);
        updatePresentationMiniLibraryStats();

        showNotification(`Трек помечен как ${newStatus ? 'обработанный' : 'необработанный'}`, 'info');
    } catch (error) {
        console.error('Ошибка обновления статуса:', error);
        showNotification('Ошибка обновления статуса', 'error');
    }
}


function loadProcessedTracksToList() {
    const processed = currentTracks.filter(t => t.processed);
    if (processed.length < 120) {
        showNotification(`Недостаточно обработанных треков: ${processed.length} из 120`, 'warning');
        return;
    }
    const shuffled = [...processed].sort(() => 0.5 - Math.random()).slice(0, 120);
    const list = shuffled.map(t => `${t.artist} - ${t.title}`).join('\n');
    document.getElementById('presentationTrackList').value = list;
    setTimeout(validatePresentationTrackList, 100);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function updatePresentationProgress(current, total, message = '') {
    const progressBar = document.getElementById('presentationProgressBar');
    const progressText = document.getElementById('presentationProgressText');
    const progressSection = document.getElementById('presentationProgress');
    
    if (!progressBar || !progressText || !progressSection) {
        console.log("Элементы прогресс-бара не найдены");
        return;
    }
    
    const percent = total > 0 ? Math.round((current / total) * 100) : 0;
    progressBar.style.width = `${percent}%`;
    progressBar.textContent = `${percent}%`;
    progressText.textContent = message || `Генерация: ${current}/${total}`;
    progressSection.style.display = 'block';
    
    // Цвет в зависимости от прогресса
    if (percent < 30) {
        progressBar.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
    } else if (percent < 70) {
        progressBar.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
    } else {
        progressBar.style.background = 'linear-gradient(135deg, #10b981, #059669)';
    }
}

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
    const presTrackList = document.getElementById('presentationTrackList');
    if (presTrackList) {
        presTrackList.addEventListener('input', debounce(validatePresentationTrackList, 500));
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
// IMPORT/EXPORT FUNCTIONS (COMPLETE)
// =========================
let operationsHistory = JSON.parse(localStorage.getItem('importExportHistory') || '[]');

// Загрузка статистики для экспорта
async function loadExportStats() {
    try {
        const response = await fetch(`${API_BASE}/export/info`);
        const data = await response.json();
        if (data.success) {
            const info = data.export_info;
            // Обновляем статистику - проверяем на undefined
            document.getElementById('statTracks').textContent = info.tracks_count || 0;
            document.getElementById('statImages').textContent = info.images_count || 0;
            document.getElementById('statDownloads').textContent = info.downloads_count || 0;
            // Используем actual_size_mb если есть, иначе estimated_size_mb
            const size = info.actual_size_mb || info.estimated_size_mb || 0;
            document.getElementById('totalSize').innerHTML = `Примерный размер: <strong>${size} MB</strong>`;
            updateOperationsHistory();
        } else {
            console.error('Ошибка загрузки статистики:', data.error);
        }
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// Показать прогресс операции
function showImportExportProgress(message, percent) {
    const progressSection = document.getElementById('importExportProgress');
    const statusElement = document.getElementById('importExportStatus');
    const percentElement = document.getElementById('importExportPercent');
    const progressBar = document.getElementById('importExportProgressBar');
    if (progressSection) {
        progressSection.style.display = 'block';
        statusElement.textContent = message;
        percentElement.textContent = `${percent}%`;
        progressBar.style.width = `${percent}%`;
        if (percent < 30) {
            progressBar.style.background = 'var(--warning)';
        } else if (percent < 70) {
            progressBar.style.background = 'var(--primary)';
        } else {
            progressBar.style.background = 'var(--success)';
        }
    }
}

// Скрыть прогресс
function hideImportExportProgress() {
    const progressSection = document.getElementById('importExportProgress');
    if (progressSection) {
        progressSection.style.display = 'none';
    }
}

// Добавить операцию в историю
function addOperationToHistory(type, filename, size, success = true) {
    const operation = {
        id: Date.now(),
        type: type,
        filename: filename,
        size: size,
        success: success,
        date: new Date().toLocaleString('ru-RU'),
        timestamp: Date.now()
    };
    operationsHistory.unshift(operation);
    operationsHistory = operationsHistory.slice(0, 10);
    localStorage.setItem('importExportHistory', JSON.stringify(operationsHistory));
    updateOperationsHistory();
}

// Обновить отображение истории операций
function updateOperationsHistory() {
    const operationsList = document.getElementById('operationsList');
    if (!operationsList) return;
    if (operationsHistory.length === 0) {
        operationsList.innerHTML = `
            <div class="empty-state">
                <div class="icon">📊</div>
                <p>Операции не выполнялись</p>
            </div>
        `;
        return;
    }
    operationsList.innerHTML = operationsHistory.map(op => `
        <div class="operation-item ${op.success ? '' : 'failed'}">
            <div class="operation-info">
                <div class="operation-icon ${op.type}">
                    ${op.type === 'export' ? '📤' : '📥'}
                </div>
                <div class="operation-details">
                    <div class="operation-type">
                        ${op.type === 'export' ? 'Экспорт данных' : 'Импорт данных'}
                        ${!op.success ? ' (Ошибка)' : ''}
                    </div>
                    <div class="operation-date">${op.date}</div>
                </div>
            </div>
            <div class="operation-size">
                ${op.size ? `${(op.size / 1024 / 1024).toFixed(1)} MB` : '—'}
            </div>
        </div>
    `).join('');
}

// Функция экспорта всех данных
async function exportAllData() {
    const exportBtn = document.getElementById('exportBtn');
    const originalText = exportBtn.innerHTML;
    try {
        exportBtn.disabled = true;
        exportBtn.innerHTML = '📦 Подготовка...';
        showImportExportProgress('Получение информации об экспорте...', 10);
        const infoResponse = await fetch(`${API_BASE}/export/info`);
        const infoData = await infoResponse.json();
        if (!infoData.success) {
            throw new Error(infoData.error || 'Ошибка получения информации');
        }
        const exportInfo = infoData.export_info;
        showImportExportProgress('Подтверждение операции...', 20);
        const confirmed = confirm(
            `Экспорт всех данных:
` +
            `🎵 Треков: ${exportInfo.tracks_count || 0}
` +
            `🖼️ Фото: ${exportInfo.images_count || 0}
` +
            `🎵 Аудиофайлов: ${exportInfo.downloads_count || 0}
` +
            `📊 Примерный размер: ${exportInfo.estimated_size_mb || exportInfo.actual_size_mb || 0} MB
` +
            `Продолжить экспорт?`
        );
        if (!confirmed) {
            showNotification('Экспорт отменен', 'info');
            hideImportExportProgress();
            return;
        }
        showImportExportProgress('Создание архива...', 40);
        showNotification('📦 Создание архива данных...', 'info');
        const response = await fetch(`${API_BASE}/export/all-data`);
        const result = await response.json();
        showImportExportProgress('Финальная обработка...', 80);
        if (result.success) {
            const downloadLink = document.createElement('a');
            downloadLink.href = result.download_url;
            downloadLink.download = result.filename;
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);
            showImportExportProgress('Экспорт завершен!', 100);
            addOperationToHistory('export', result.filename, result.size, true);
            showNotification(`✅ Экспорт завершен! Файл: ${result.filename}`, 'success');
            setTimeout(() => {
                showExportResults(result);
                hideImportExportProgress();
            }, 2000);
        } else {
            throw new Error(result.error || 'Ошибка экспорта');
        }
    } catch (error) {
        console.error('❌ Ошибка экспорта:', error);
        showImportExportProgress('Ошибка экспорта', 0);
        showNotification(`❌ Ошибка экспорта: ${error.message}`, 'error');
        addOperationToHistory('export', null, null, false);
        setTimeout(hideImportExportProgress, 3000);
    } finally {
        exportBtn.disabled = false;
        exportBtn.innerHTML = originalText;
    }
}

// Функция импорта всех данных
async function importAllData() {
    const importBtn = document.getElementById('importBtn');
    const originalText = importBtn.innerHTML;
    try {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.zip';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) {
                importBtn.disabled = false;
                importBtn.innerHTML = originalText;
                return;
            }
            await processImportFile(file, importBtn, originalText);
        };
        importBtn.disabled = true;
        importBtn.innerHTML = '📥 Выбор файла...';
        input.click();
    } catch (error) {
        console.error('❌ Ошибка импорта:', error);
        showNotification(`❌ Ошибка импорта: ${error.message}`, 'error');
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    }
}

// Обработка файла импорта с прогрессом
async function processImportFile(file, importBtn, originalText) {
    try {
        showImportExportProgress('Проверка файла...', 5);
        // ПРЕДУПРЕЖДЕНИЕ О БОЛЬШИХ ФАЙЛАХ
        if (file.size > 500 * 1024 * 1024) {
            const confirmed = confirm(
                `ВНИМАНИЕ! Большой файл (${(file.size / 1024 / 1024).toFixed(1)}MB)
` +
                `Импорт может занять несколько минут.
` +
                `Продолжить импорт?`
            );
            if (!confirmed) {
                showNotification('Импорт отменен', 'info');
                hideImportExportProgress();
                importBtn.disabled = false;
                importBtn.innerHTML = originalText;
                return;
            }
        }
        const confirmed = confirm(
            `ВНИМАНИЕ!
` +
            `Импорт данных ЗАМЕНИТ все текущие данные:
` +
            `• Метаданные треков
` +
            `• Фото артистов
` +
            `• Аудиофайлы
` +
            `Текущие данные будут потеряны!
` +
            `Продолжить импорт?`
        );
        if (!confirmed) {
            showNotification('Импорт отменен', 'info');
            hideImportExportProgress();
            importBtn.disabled = false;
            importBtn.innerHTML = originalText;
            return;
        }
        showImportExportProgress('Подготовка...', 10);
        showNotification('📥 Начало импорта данных...', 'info');
        const formData = new FormData();
        formData.append('file', file);
        // Используем XMLHttpRequest для отслеживания прогресса загрузки
        const xhr = new XMLHttpRequest();
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = Math.min(90, 10 + (e.loaded / e.total) * 80);
                showImportExportProgress(`Загрузка архива... ${Math.round(percent)}%`, percent);
            }
        };
        const importPromise = new Promise((resolve, reject) => {
            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const result = JSON.parse(xhr.responseText);
                        resolve(result);
                    } catch (e) {
                        reject(new Error('Ошибка parsing ответа'));
                    }
                } else {
                    reject(new Error(`HTTP error: ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error('Network error'));
            xhr.ontimeout = () => reject(new Error('Timeout'));
        });
        xhr.open('POST', `${API_BASE}/import/all-data`);
        xhr.timeout = 600000; // 10 минут таймаут
        xhr.send(formData);
        showImportExportProgress('Обработка архива...', 90);
        const result = await importPromise;
        showImportExportProgress('Завершение...', 95);
        if (result.success) {
            showImportExportProgress('Импорт завершен!', 100);
            addOperationToHistory('import', file.name, file.size, true);
            showNotification(`✅ Импорт завершен успешно!`, 'success');
            // Отложенная перезагрузка данных
            setTimeout(() => {
                loadTracks();
                loadLocalFilesInfo();
                updateTracksCount();
                loadSystemStatus();
                loadExportStats();
                hideImportExportProgress();
            }, 1000);
            // Показываем детали импорта
            showImportResults(result);
        } else {
            throw new Error(result.error || 'Ошибка импорта');
        }
    } catch (error) {
        console.error('❌ Ошибка обработки файла:', error);
        showImportExportProgress('Ошибка импорта', 0);
        showNotification(`❌ Ошибка импорта: ${error.message}`, 'error');
        addOperationToHistory('import', file ? file.name : null, file ? file.size : null, false);
        setTimeout(hideImportExportProgress, 3000);
    } finally {
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    }
}

// Показать результаты экспорта
function showExportResults(result) {
    const info = result.info || {};
    const message =
        `📊 Результаты экспорта:
` +
        `🎵 Треков: ${info.tracks_count || 'N/A'}
` +
        `🖼️ Фото: ${info.images_count || 'N/A'}
` +
        `🎵 Аудиофайлов: ${info.downloads_count || 'N/A'}
` +
        `📁 Файл: ${result.filename}
` +
        `📦 Размер: ${(result.size / 1024 / 1024).toFixed(2)} MB`;
    alert(message);
}

// Показать результаты импорта
function showImportResults(result) {
    const items = result.imported_items?.join('\n• ') || 'Нет данных';
    const message =
        `📊 Результаты импорта:
` +
        `Импортированные компоненты:
• ${items}
` +
        `🎵 Треков в медиатеке: ${result.tracks_count || 0}`;
    alert(message);
}

// Добавить HTML секцию импорта/экспорта в интерфейс
function addImportExportSection() {
    const statusTab = document.getElementById('status');
    if (!statusTab) return;
    // Проверяем, не добавлена ли уже секция
    if (document.getElementById('importExportSection')) return;
    const importExportHTML = `
        <div class="import-export-section" id="importExportSection">
            <div class="generator-card">
                <h2>📦 Импорт/Экспорт данных</h2>
                <p class="subtitle">Резервное копирование и восстановление всех данных системы</p>
                <div class="info-box" style="background: var(--info-bg); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <h4>🔄 Что входит в архивацию:</h4>
                    <div class="export-components">
                        <div class="component-item">
                            <span class="component-icon">📊</span>
                            <div class="component-info">
                                <strong>track_data.json</strong>
                                <span>Все метаданные треков</span>
                            </div>
                        </div>
                        <div class="component-item">
                            <span class="component-icon">🖼️</span>
                            <div class="component-info">
                                <strong>Папка images/</strong>
                                <span>Фото артистов</span>
                            </div>
                        </div>
                        <div class="component-item">
                            <span class="component-icon">🎵</span>
                            <div class="component-info">
                                <strong>Папка downloads/</strong>
                                <span>Аудиофайлы треков</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="import-export-stats" id="exportStats" style="margin-bottom: 20px;">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-icon">🎵</div>
                            <div class="stat-info">
                                <span class="stat-label">Треков</span>
                                <span class="stat-value" id="statTracks">0</span>
                            </div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-icon">🖼️</div>
                            <div class="stat-info">
                                <span class="stat-label">Фото</span>
                                <span class="stat-value" id="statImages">0</span>
                            </div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-icon">🎵</div>
                            <div class="stat-info">
                                <span class="stat-label">Аудиофайлов</span>
                                <span class="stat-value" id="statDownloads">0</span>
                            </div>
                        </div>
                    </div>
                    <div class="total-size" id="totalSize">
                        Примерный размер: <strong>0 MB</strong>
                    </div>
                </div>
                <div class="import-export-actions">
                    <button class="btn btn-primary btn-large" onclick="exportAllData()" id="exportBtn">
                        <span class="btn-icon">📤</span>
                        <span class="btn-text">Экспорт всех данных</span>
                    </button>
                    <button class="btn btn-warning btn-large" onclick="importAllData()" id="importBtn">
                        <span class="btn-icon">📥</span>
                        <span class="btn-text">Импорт данных</span>
                    </button>
                </div>
                <div class="warning-box">
                    <div class="warning-icon">⚠️</div>
                    <div class="warning-content">
                        <strong>Внимание!</strong> При импорте все текущие данные будут полностью заменены. 
                        Создавайте резервные копии перед импортом.
                    </div>
                </div>
                <!-- Прогресс-бар для операций -->
                <div id="importExportProgress" class="progress-section" style="display: none; margin-top: 20px;">
                    <div class="progress-header">
                        <span id="importExportStatus">Обработка...</span>
                        <span id="importExportPercent">0%</span>
                    </div>
                    <div class="progress-container">
                        <div class="progress-bar" id="importExportProgressBar" style="width: 0%"></div>
                    </div>
                </div>
                <!-- История операций -->
                <div class="operations-history" style="margin-top: 25px;">
                    <h4>📋 Последние операции:</h4>
                    <div id="operationsList" class="operations-list">
                        <div class="empty-state">
                            <div class="icon">📊</div>
                            <p>Операции не выполнялись</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    // Вставляем после основного контента статуса
    const statusContent = statusTab.querySelector('.generator-card');
    if (statusContent) {
        statusContent.insertAdjacentHTML('afterend', importExportHTML);
    } else {
        statusTab.innerHTML += importExportHTML;
    }
    // Загружаем статистику
    loadExportStats();
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    // Добавляем секцию импорта/экспорта
    setTimeout(addImportExportSection, 1000);
    // Обновляем статистику при переключении на вкладку статуса
    const statusTab = document.querySelector('[data-tab="status"]');
    if (statusTab) {
        statusTab.addEventListener('click', function () {
            setTimeout(loadExportStats, 500);
        });
    }
});

// Обновляем инициализацию вкладок
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');
            if (btn.dataset.tab === 'status') {
                loadSystemStatus();
                loadExportStats(); // Загружаем статистику экспорта
            } else if (btn.dataset.tab === 'presentation') {
                updateTracksCount();
            } else if (btn.dataset.tab === 'local') {
                loadLocalFilesInfo();
            }
        });
    });
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

                // ОБНОВЛЯЕМ ОБА ПРОГРЕСС-БАРА
                updateDownloadProgress(); // основной
                updatePresentationDownloadProgress(); // презентация

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
    // ❗️ НЕ МЕНЯЕМ ЦВЕТ ПРОГРЕСС-БАРА ВО ВРЕМЯ СКАЧИВАНИЯ
    if (downloadProgress.isDownloading) {
        progressFill.classList.add('pulsing');
        // Используем однотонный синий цвет
        progressFill.style.background = 'var(--primary)';
    } else {
        // Только после завершения меняем цвет
        progressStatus.textContent = 'Скачивание завершено';
        progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
        progressFill.style.width = '100%';
        progressFill.classList.remove('pulsing');
        // Определяем цвет по результатам
        if (downloadProgress.failedTracks.length > 0 || downloadProgress.duplicateTracks.length > 0) {
            progressFill.style.background = 'var(--warning)'; // оранжевый
        } else {
            progressFill.style.background = 'var(--success)'; // зелёный
        }
        updateFinalResults();
    }
    updateProgressDetails(); // Обновляем детали
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

// =========================
// PRESENTATION GENERATION FUNCTIONS
// =========================
// Получить список недостающих треков
function updatePresentationMiniLibraryStats() {
    const presentationStats = document.getElementById('presentationStats');
    const presentationDetails = document.getElementById('presentationStatsDetails');
    const tracksCountElement = document.getElementById('presentationTracksCount');

    if (!presentationStats || !presentationDetails) return;

    try {
        // Получаем данные из текстового поля
        const trackListText = document.getElementById('presentationTrackList').value.trim();
        const lines = trackListText ? trackListText.split('\n').filter(l => l.trim()) : [];
        const totalInList = lines.length;

        // Данные из мини-медиатеки
        const foundInLibrary = presentationTrackList ? presentationTrackList.length : 0;
        const notFound = Math.max(0, totalInList - foundInLibrary);

        // Статистика по обработке
        const processed = presentationTrackList ?
            presentationTrackList.filter(t => t.processed).length : 0;
        const unprocessed = foundInLibrary - processed;
        const processedPercentage = foundInLibrary > 0 ?
            Math.round((processed / foundInLibrary) * 100) : 0;

        // Цвета для индикации
        const getColor = (value, threshold1 = 50, threshold2 = 80) => {
            if (value >= threshold2) return "#10b981"; // success
            if (value >= threshold1) return "#f59e0b"; // warning
            return "#ef4444"; // error
        };

        const foundPercentage = totalInList > 0 ? (foundInLibrary / totalInList) * 100 : 0;
        const foundColor = getColor(foundPercentage, 70, 90);
        const processedColor = getColor(processedPercentage, 50, 80);

        // Основная статистика (компактная)
        presentationStats.innerHTML = `
            <div class="presentation-mini-stats">
                <div class="stats-grid compact">
                    <div class="stat-card">
                        <div class="stat-icon">📋</div>
                        <div class="stat-info">
                            <span class="stat-label">Всего в списке</span>
                            <span class="stat-value">${totalInList}</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon" style="color: ${foundColor}">${foundInLibrary >= totalInList ? '✅' : '🔍'}</div>
                        <div class="stat-info">
                            <span class="stat-label">Найдено</span>
                            <span class="stat-value" style="color: ${foundColor}">${foundInLibrary}</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">⚙️</div>
                        <div class="stat-info">
                            <span class="stat-label">Обработано</span>
                            <span class="stat-value" style="color: ${processedColor}">${processedPercentage}%</span>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Детальная статистика
        presentationDetails.innerHTML = `
            <div class="detailed-stats">
                <h4>📊 Статистика мини-медиатеки:</h4>
                <div class="stats-grid-detailed">
                    <div class="stat-detailed">
                        <span class="stat-label-detailed">Всего треков в списке:</span>
                        <span class="stat-value-detailed">${totalInList}</span>
                    </div>
                    <div class="stat-detailed">
                        <span class="stat-label-detailed">✅ Найдено в медиатеке:</span>
                        <span class="stat-value-detailed" style="color: ${foundColor}">${foundInLibrary} ${foundInLibrary >= totalInList ? '🎉' : ''}</span>
                    </div>
                    <div class="stat-detailed">
                        <span class="stat-label-detailed">❌ Не найдено:</span>
                        <span class="stat-value-detailed" style="color: ${notFound > 0 ? '#ef4444' : '#6b7280'}">${notFound}</span>
                    </div>
                    <div class="stat-detailed">
                        <span class="stat-label-detailed">⚙️ Обработано:</span>
                        <span class="stat-value-detailed" style="color: ${processedColor}">${processed} из ${foundInLibrary} (${processedPercentage}%)</span>
                    </div>
                    <div class="stat-detailed">
                        <span class="stat-label-detailed">⏳ Не обработано:</span>
                        <span class="stat-value-detailed">${unprocessed}</span>
                    </div>
                </div>
            </div>
        `;

        // Обновляем счетчик треков в заголовке
        if (tracksCountElement) {
            tracksCountElement.textContent = foundInLibrary;
        }

        // Обновляем индикатор готовности к генерации
        updatePresentationReadinessIndicators(foundInLibrary, totalInList);

    } catch (error) {
        console.error('Ошибка обновления статистики мини-медиатеки:', error);
    }
}


// Обновление индикаторов готовности к презентации
function updatePresentationReadinessIndicators(inPresentation, totalInList) {
    const readyStatus = document.getElementById('presentationReadyStatus');
    const generateBtn = document.getElementById('generatePresentationBtn');

    if (readyStatus) {
        if (inPresentation >= 120) {
            readyStatus.innerHTML = `
                <span style="color: var(--success);">
                    ✅ Готово к генерации! (${inPresentation} треков)
                </span>
            `;
        } else if (inPresentation >= 40) {
            readyStatus.innerHTML = `
                <span style="color: var(--warning);">
                    ⚠️ Минимально готово (${inPresentation} из 120 треков)
                </span>
            `;
        } else {
            readyStatus.innerHTML = `
                <span style="color: var(--error);">
                    ❌ Недостаточно треков (${inPresentation} из 40 минимум)
                </span>
            `;
        }
    }

    if (generateBtn) {
        const isReady = inPresentation >= 40;
        generateBtn.disabled = !isReady;
        generateBtn.title = isReady ?
            `Сгенерировать презентацию из ${inPresentation} треков` :
            `Добавьте хотя бы 40 треков в список (сейчас: ${inPresentation})`;

        // Визуальная индикация
        if (isReady) {
            generateBtn.classList.remove('btn-disabled');
            generateBtn.classList.add('btn-success');
        } else {
            generateBtn.classList.add('btn-disabled');
            generateBtn.classList.remove('btn-success');
        }
    }
}
function getMissingTracks() {
    const trackListText = document.getElementById('presentationTrackList').value;
    if (!trackListText.trim()) return [];
    const tracksToCheck = parsePresentationTrackList(trackListText);
    const missing = [];
    for (const t of tracksToCheck) {
        const found = currentTracks.find(tr =>
            normalizeTrackString(tr.artist) === normalizeTrackString(t.artist) &&
            normalizeTrackString(tr.title) === normalizeTrackString(t.title)
        );
        if (!found) {
            missing.push(`${t.artist} - ${t.title}`);
        }
    }
    return missing;
}

// Скачать недостающие треки
async function downloadMissingTracks() {
    const missingTracks = getMissingTracks();
    if (missingTracks.length === 0) {
        showNotification('Нет недостающих треков', 'info');
        return;
    }

    // Создаем строку для скачивания
    const trackListText = missingTracks.join('\n');
    document.getElementById('trackList').value = trackListText;

    // Инициализируем прогресс
    downloadProgress = {
        total: missingTracks.length,
        current: 0,
        currentTrack: 'Подготовка к скачиванию...',
        isDownloading: true,
        results: [],
        failedTracks: [],
        duplicateTracks: [],
        successfulTracks: []
    };

    // Показываем прогресс
    showDownloadProgressInPresentation();

    try {
        const response = await fetch(`${API_BASE}/tracks/download-from-list`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_list: trackListText,
                auto_search_photos: document.getElementById('autoSearchPhotos').checked,
                use_smart_segments: document.getElementById('useSmartSegments').checked
            })
        });
        if (!response.ok) throw new Error('Ошибка скачивания треков');

        const result = await response.json();
        if (result.success) {
            const successCount = result.downloaded || result.results.filter(r => r.success).length;
            const duplicateCount = result.duplicates || result.results.filter(r => r.duplicate).length;
            const errorCount = result.failed || result.results.filter(r => !r.success && !r.duplicate).length;

            // Обновляем прогресс
            downloadProgress.current = downloadProgress.total;
            downloadProgress.currentTrack = `Завершено: ${successCount} успешно, ${duplicateCount} дубликатов, ${errorCount} ошибок`;
            downloadProgress.results = result.results || [];

            // Классифицируем результаты
            downloadProgress.successfulTracks = result.results.filter(r => r.success);
            downloadProgress.duplicateTracks = result.results.filter(r => r.duplicate);
            downloadProgress.failedTracks = result.results.filter(r => !r.success && !r.duplicate);
            downloadProgress.isDownloading = false;

            updateDownloadProgressInPresentation();
            let message = `✅ Скачано ${successCount} из ${downloadProgress.total} треков`;
            if (duplicateCount > 0) message += `, ${duplicateCount} дубликатов`;
            if (errorCount > 0) message += `, ${errorCount} ошибок`;
            showNotification(message, duplicateCount > 0 || errorCount > 0 ? 'warning' : 'success');

            // Обновляем список треков в презентации
            setTimeout(validatePresentationTrackList, 100);

            // Обновляем медиатеку
            await loadTracks();
            updateTracksCount();
        } else {
            throw new Error(result.message || 'Ошибка скачивания');
        }
    } catch (error) {
        console.error('❌ Ошибка скачивания треков:', error);
        downloadProgress.isDownloading = false;
        updateDownloadProgressInPresentation();
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    } finally {
        // Останавливаем опрос через 3 секунды
        setTimeout(() => {
            stopStatusPolling();
        }, 3000);
    }
}

// Очистить список для скачивания
function clearDownloadList() {
    document.getElementById('trackList').value = '';
    showNotification('Список для скачивания очищен', 'info');
}

// Показать прогресс в блоке презентации
function showDownloadProgressInPresentation() {
    const progressSection = document.getElementById('downloadStatus');
    if (progressSection) {
        progressSection.style.display = 'block';
    }
    updateDownloadProgressInPresentation();
}

// Обновить прогресс в блоке презентации
function updateDownloadProgressInPresentation() {
    const progressStatus = document.getElementById('downloadProgressStatus');
    const progressCount = document.getElementById('downloadProgressCount');
    const progressFill = document.getElementById('downloadProgressFill');
    const progressDetails = document.getElementById('downloadDetails');
    if (!progressStatus || !progressCount || !progressFill) return;

    const percent = downloadProgress.total > 0 ?
        Math.round((downloadProgress.current / downloadProgress.total) * 100) : 0;
    progressStatus.textContent = downloadProgress.currentTrack || 'Подготовка к скачиванию...';
    progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
    progressFill.style.width = `${percent}%`;

    if (downloadProgress.isDownloading) {
        progressFill.classList.add('pulsing');
        progressFill.style.background = 'var(--primary)';
    } else {
        progressStatus.textContent = 'Скачивание завершено';
        progressCount.textContent = `${downloadProgress.current}/${downloadProgress.total}`;
        progressFill.style.width = '100%';
        progressFill.classList.remove('pulsing');

        if (downloadProgress.failedTracks.length > 0 || downloadProgress.duplicateTracks.length > 0) {
            progressFill.style.background = 'var(--warning)';
        } else {
            progressFill.style.background = 'var(--success)';
        }
        updateFinalResultsInPresentation();
    }

    updateProgressDetailsInPresentation();
}

// Обновить детали в блоке презентации
function updateProgressDetailsInPresentation() {
    const progressDetails = document.getElementById('downloadDetails');
    if (!progressDetails) return;
    let detailsHTML = '<div class="progress-details-current">';
    if (downloadProgress.currentTrack && downloadProgress.currentTrack !== 'Подготовка к скачиванию...') {
        detailsHTML += `<div class="progress-detail-item progress-detail-processing">
            🔄 ${downloadProgress.currentTrack}
        </div>`;
    }

    const recentResults = downloadProgress.results.slice(-5);
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

// Обновить финальные результаты в блоке презентации
function updateFinalResultsInPresentation() {
    const progressDetails = document.getElementById('downloadDetails');
    if (!progressDetails) return;
    const successCount = downloadProgress.successfulTracks.length;
    const duplicateCount = downloadProgress.duplicateTracks.length;
    const errorCount = downloadProgress.failedTracks.length;
    let detailsHTML = '<div class="final-results">';
    detailsHTML += '<h4>Итоговые результаты:</h4>';

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


// Функция для очистки списка для скачивания
function clearDownloadList() {
    document.getElementById('missingTracksDisplay').textContent = '';
    document.getElementById('missingTracksList').style.display = 'none';
    document.getElementById('downloadProgressSection').style.display = 'none';
}

// Функция для скачивания недостающих треков
async function downloadMissingTracks() {
    const missingEl = document.getElementById('missingTracksDisplay');
    const downloadProgressSection = document.getElementById('downloadProgressSection');
    const progressStatus = document.getElementById('progressStatus');
    const progressCount = document.getElementById('progressCount');
    const progressFill = document.getElementById('progressFill');
    const progressDetails = document.getElementById('progressDetails');

    // Получаем список недостающих треков
    const missingText = missingEl.textContent.trim();
    if (!missingText) {
        showNotification('Нет треков для скачивания', 'warning');
        return;
    }

    // Инициализируем прогресс
    downloadProgress = {
        total: 0,
        current: 0,
        currentTrack: '',
        isDownloading: false,
        results: [],
        failedTracks: [],
        duplicateTracks: [],
        successfulTracks: []
    };

    // Показываем прогресс бар
    downloadProgressSection.style.display = 'block';
    progressStatus.textContent = 'Подготовка...';
    progressCount.textContent = '0/0';
    progressFill.style.width = '0%';
    progressDetails.innerHTML = '';

    try {
        // Парсим список недостающих треков
        const tracksToDownload = parseTrackList(missingText);
        if (tracksToDownload.length === 0) {
            throw new Error('Не удалось распознать список треков');
        }

        // Инициализируем статус
        downloadProgress.total = tracksToDownload.length;
        downloadProgress.current = 0;
        downloadProgress.currentTrack = 'Подготовка к скачиванию...';
        downloadProgress.isDownloading = true;

        // Запускаем скачивание
        const response = await fetch(`${API_BASE}/tracks/download-from-list`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_list: missingText,
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
            downloadProgress.successfulTracks = result.results.filter(r => r.success);
            downloadProgress.duplicateTracks = result.results.filter(r => r.duplicate);
            downloadProgress.failedTracks = result.results.filter(r => !r.success && !r.duplicate);
            downloadProgress.isDownloading = false;

            updateDownloadProgress(); // Обновляем прогресс-бар

            let message = `✅ Скачано ${successCount} из ${downloadProgress.total} треков`;
            if (duplicateCount > 0) message += `, ${duplicateCount} дубликатов`;
            if (errorCount > 0) message += `, ${errorCount} ошибок`;
            showNotification(message, duplicateCount > 0 || errorCount > 0 ? 'warning' : 'success');

            // Обновляем список треков в медиатеке
            await loadTracks();

            // После скачивания, снова валидируем основной список
            await validatePresentationTrackList();

            // Обновляем счетчик треков
            updateTracksCount();

        } else {
            throw new Error(result.message || 'Ошибка скачивания');
        }
    } catch (error) {
        console.error('❌ Ошибка скачивания треков:', error);
        downloadProgress.isDownloading = false;
        updateDownloadProgress(); // Обновляем прогресс-бар
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    } finally {
        // Скрываем прогресс-бар через 3 секунды
        setTimeout(() => {
            downloadProgressSection.style.display = 'none';
        }, 3000);
    }
}
function clearPresentationTrackList() {
    document.getElementById('presentationTrackList').value = '';
    document.getElementById('presentationTrackValidation').style.display = 'none';
    document.getElementById('missingTracksList').style.display = 'none';
    document.getElementById('downloadMissingBtn').disabled = true;
    presentationTrackList = [];
}
function loadAllTracksToPresentationList() {
    if (!currentTracks || currentTracks.length === 0) {
        showNotification('Медиатека пуста', 'warning');
        return;
    }
    const list = currentTracks.map(t => `${t.artist} - ${t.title}`).join('\n');
    document.getElementById('presentationTrackList').value = list;
    setTimeout(validatePresentationTrackList, 100);
}

async function generatePresentation() {
    const status = document.getElementById("presentation-status");
    const titleInput = document.getElementById("presentation-title");
    const title = titleInput ? titleInput.value.trim() : "";
    const makeBWCheckbox = document.getElementById("make-bw");
    const makeBW = !!(makeBWCheckbox && makeBWCheckbox.checked);

    if (!title) {
        if (status) {
            status.textContent = "⚠️ Пожалуйста, введите название презентации.";
            status.style.color = "#f87171";
        } else {
            showNotification("⚠️ Пожалуйста, введите название презентации.", "warning");
        }
        return;
    }

    const generateBtn = document.getElementById('generatePresentationBtn');
    const originalText = generateBtn.innerHTML;

    try {
        updatePresentationProgress(0, 1, 'Подготовка...');

        if (status) {
            status.textContent = "⏳ Генерация презентации...";
            status.style.color = "#9ca3af";
        }

        generateBtn.disabled = true;
        generateBtn.innerHTML = "⏳ Генерация...";

        if (presentationTrackList.length === 0) {
            if (status) {
                status.textContent = "⚠️ Нет валидных треков для генерации";
                status.style.color = "#f87171";
            } else {
                showNotification("⚠️ Нет валидных треков для генерации", "warning");
            }
            return;
        }

        const payload = {
            title,
            design: { make_bw: makeBW },
            tracks: presentationTrackList
        };

        console.log("📤 Отправляем запрос на генерацию:", payload);

        const response = await fetch(`${API_BASE}/generate/presentation`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        console.log("📥 Ответ от сервера:", data);

        if (response.ok && data.success) {
            updatePresentationProgress(1, 1, '✅ Завершено');

            if (status) {
                status.innerHTML = `✅ Презентация успешно создана!<br>
                <a href="${data.download_url}" class="download-link" download>
                    📥 Скачать презентацию
                </a>`;
                status.style.color = "#34d399";
            }

            showNotification('✅ Презентация успешно создана!', 'success');

            // Автоматическое скачивание
            if (data.download_url) {
                setTimeout(() => {
                    const downloadLink = document.createElement('a');
                    downloadLink.href = data.download_url;
                    downloadLink.download = data.filename || 'presentation.pptx';
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    document.body.removeChild(downloadLink);
                }, 1000);
            }

        } else {
            updatePresentationProgress(0, 1, '❌ Ошибка');
            const errorMsg = data.detail || data.message || "Не удалось создать презентацию";

            if (status) {
                status.textContent = "❌ Ошибка: " + errorMsg;
                status.style.color = "#f87171";
            } else {
                showNotification('❌ ' + errorMsg, 'error');
            }
        }
    } catch (error) {
        console.error("❌ Ошибка при генерации презентации:", error);
        updatePresentationProgress(0, 1, '❌ Ошибка соединения');

        if (status) {
            status.textContent = "❌ Ошибка соединения с сервером.";
            status.style.color = "#f87171";
        } else {
            showNotification('❌ Ошибка соединения с сервером', 'error');
        }
    } finally {
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.innerHTML = originalText;
        }
    }
}
// Рендер треков ТОЛЬКО для вкладки Презентация (мини-медиатека)
// Мини-медиатека ТОЛЬКО с треками из списка
function renderPresentationTracksCompact(tracks) {
    const container = document.getElementById('presentationTracksList');
    if (!container) return;

    if (tracks.length === 0) {
        container.innerHTML = '<div style="padding: 12px; color: var(--text-muted);">— нет треков</div>';
        return;
    }

    // НЕ вызываем updatePresentationMiniLibraryStats() здесь!
    // Обновляем только DOM

    container.innerHTML = tracks.map(track => {
        const isProcessed = track.processed;
        const hasPhoto = track.image_path;
        const isPlaying = window.currentPlayingTrackId === track.id;

        return `
        <div class="track-item draggable ${isProcessed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" data-track-id="${track.id}">
            <div class="col-id">${track.id}</div>
            <div class="col-artist">
                <div class="track-cover-container">
                    ${hasPhoto ?
                `<img src="${API_BASE}/tracks/${track.id}/artist-photo?t=${Date.now()}" 
                              alt="${escapeHtml(track.artist)}"
                              class="track-cover"
                              onerror="this.style.display='none'"
                              onclick="openPhotoEditor(${track.id})">` :
                `<div class="track-cover empty" 
                              onclick="openPhotoEditor(${track.id})"
                              style="cursor: pointer; width: 40px; height: 40px; background: var(--bg-secondary); border-radius: 4px;"></div>`
            }
                </div>
                <span>${escapeHtml(track.artist)}</span>
                ${isProcessed ? '<span class="track-processed-badge">✅</span>' : ''}
                ${isPlaying ? '<span class="playing-indicator-small">🔊</span>' : ''}
            </div>
            <div class="col-title">${escapeHtml(track.title)}</div>
            <div class="col-segment">
                <span class="segment-time">${formatTime(track.segment_start || 0)}</span>
                <span class="segment-duration">${track.segment_duration || 30}с</span>
            </div>
            <div class="col-actions">
                <button class="btn btn-secondary btn-small play-btn-presentation" data-track-id="${track.id}" 
                        onclick="playTrackSegment(${track.id})" title="${isPlaying ? 'Остановить воспроизведение' : 'Воспроизвести отрывок'}">
                    ${isPlaying ? '⏹️' : '▶️'}
                </button>
                <button class="btn btn-secondary btn-small" onclick="openAudioEditor(${track.id})">🎚️</button>
                <button class="btn btn-secondary btn-small" onclick="editTrack(${track.id})">✏️</button>
                <button class="btn ${isProcessed ? 'btn-warning' : 'btn-success'} btn-small" onclick="toggleProcessed(${track.id})">
                    ${isProcessed ? '❌' : '✅'}
                </button>
                <button class="btn btn-danger btn-small" onclick="removeFromPresentationList(${track.id})">🗑️</button>
            </div>
        </div>
        `;
    }).join('');

    addCleanTrackCoverStyles();
}
function updatePresentationStats() {
    // Эта функция теперь реализована в track_view_manager.js
    // Просто вызываем соответствующую функцию если она существует
    if (typeof window.updateGlobalStats === 'function') {
        window.updateGlobalStats();
    }
}
// Обертка для функции из track_view_manager.js
window.playTrackSegment = function (trackId) {
    if (typeof window.playTrackSegment === 'function') {
        return window.playTrackSegment(trackId);
    }
    // Запасная реализация если функция не загружена
    alert('Функция воспроизведения недоступна');
};
// Обертка для функции из track_view_manager.js
window.stopGlobalPlayback = function () {
    if (typeof window.stopGlobalPlayback === 'function') {
        return window.stopGlobalPlayback();
    }
};

// Чистые стили без placeholder'ов
function addCleanTrackCoverStyles() {
    if (document.getElementById('clean-track-cover-styles')) return;

    const styles = `
        <style id="clean-track-cover-styles">
            .track-cover-container {
                position: relative;
                display: inline-block;
                margin-right: 8px;
            }
            .track-cover {
                width: 40px;
                height: 40px;
                object-fit: cover;
                border-radius: 4px;
                cursor: pointer;
                border: 1px solid var(--border);
            }
            .track-cover.empty {
                background: var(--bg-secondary);
                border: 1px dashed var(--border);
            }
            .track-cover.empty:hover {
                background: var(--bg-tertiary);
            }
            .col-artist {
                display: flex;
                align-items: center;
                min-width: 200px;
            }
        </style>
    `;
    document.head.insertAdjacentHTML('beforeend', styles);
}
function removeDeletedTrack(trackId) {
    presentationTrackList = presentationTrackList.filter(track => track.id !== trackId);
    updatePresentationTrackListField();
    validatePresentationTrackList();
    showNotification('Трек удален из списка презентации', 'info');
}

function removeFromPresentationList(trackId) {
    if (!confirm('Удалить этот трек из списка презентации?')) return;

    // Удаляем трек из presentationTrackList
    presentationTrackList = presentationTrackList.filter(track => track.id !== trackId);

    // Обновляем текстовое поле
    updatePresentationTrackListField();

    // Перевалидируем список
    validatePresentationTrackList();

    showNotification('Трек удален из списка презентации', 'info');
}

function updatePresentationTrackListField() {
    const trackListText = presentationTrackList.map(track => `${track.artist} - ${track.title}`).join('\n');
    document.getElementById('presentationTrackList').value = trackListText;
}
// =========================
// TRACK MANAGEMENT FUNCTIONS
// =========================
function refreshPresentationData() {
    // УБЕРИТЕ эту функцию или закомментируйте - она вызывает проблемы
    /*
    if (presentationTrackList && presentationTrackList.length > 0) {
        const updatedTracks = presentationTrackList.map(pTrack => {
            return currentTracks.find(t => t.id === pTrack.id) || pTrack;
        });
        presentationTrackList = updatedTracks;
        window.presentationTrackList = updatedTracks;

        if (typeof window.renderPresentationTracksCompact === 'function') {
            window.renderPresentationTracksCompact(updatedTracks);
        } else {
            renderPresentationTracksCompact(updatedTracks);
        }

        if (typeof updatePresentationMiniLibraryStats === 'function') {
            updatePresentationMiniLibraryStats();
        }
    }
    */

    // Вместо этого просто обновляем статистику если нужно
    if (presentationTrackList && presentationTrackList.length > 0) {
        setTimeout(() => {
            if (typeof updatePresentationMiniLibraryStats === 'function') {
                updatePresentationMiniLibraryStats();
            }
        }, 100);
    }
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
        window.currentTracks = tracks;

        // Используем функцию из track_view_manager.js
        if (typeof window.renderTracks === 'function') {
            window.renderTracks(tracks);
        }

        // НЕ ВЫЗЫВАЕМ refreshPresentationData() - она ломает треки
        // refreshPresentationData();

        updateTracksCount();

        // Вместо этого проверяем и обновляем только статистику презентации
        if (document.getElementById('presentation').classList.contains('active')) {
            setTimeout(() => {
                // Перевалидируем список если он есть
                const trackListText = document.getElementById('presentationTrackList').value;
                if (trackListText && trackListText.trim()) {
                    validatePresentationTrackList();
                } else {
                    // Просто обновляем статистику
                    if (typeof updatePresentationMiniLibraryStats === 'function') {
                        updatePresentationMiniLibraryStats();
                    }
                }
            }, 500);
        }

        showStatus('mediaStatus', `✅ Загружено ${tracks.length} треков`, 'success');
    } catch (error) {
        console.error('Ошибка загрузки треков:', error);
        showStatus('mediaStatus', '❌ Ошибка загрузки треков', 'error');
    }
}


// Отображение треков - теперь делегируется track_view_manager.js
function renderTracks(tracks) {
    // Используем функцию из track_view_manager.js для отображения
    if (typeof window.renderFilteredTracks === 'function') {
        window.renderFilteredTracks();
    } else {
        // Запасной вариант для обратной совместимости
        if (currentViewMode === 'detailed') {
            if (typeof window.renderTracksDetailed === 'function') {
                window.renderTracksDetailed(tracks);
            }
        } else {
            if (typeof window.renderTracksCompact === 'function') {
                window.renderTracksCompact(tracks);
            }
        }
    }
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

    // БЕЗОПАСНОЕ обновление элементов модального окна
    try {
        const artistNameEl = document.getElementById('photoArtistName');
        const photoPreviewEl = document.getElementById('photoPreview');
        const photoStatusEl = document.getElementById('photoStatus');

        if (artistNameEl) artistNameEl.textContent = track.artist;
        if (photoPreviewEl) photoPreviewEl.style.display = 'none';
        if (photoStatusEl) {
            photoStatusEl.style.display = 'none';
            photoStatusEl.textContent = '';
        }

        // Удаляем существующую навигацию если есть
        const existingNav = photoPreviewEl?.querySelector('.photo-navigation');
        if (existingNav) {
            existingNav.remove();
        }

        document.getElementById('photoModal').style.display = 'block';
    } catch (error) {
        console.error('Ошибка при открытии модального окна фото:', error);
        showNotification('Ошибка открытия редактора фото', 'error');
    }
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

        // Обновляем данные в currentTracks
        const track = currentTracks.find(t => t.id === trackId);
        if (track) {
            track.artist = artist;
            track.title = title;
        }

        // Синхронизируем с presentationTrackList
        const presTrack = presentationTrackList.find(t => t.id === trackId);
        if (presTrack) {
            presTrack.artist = artist;
            presTrack.title = title;
        }

        // Обновляем обе медиатеки
        renderTracks(currentTracks);
        renderPresentationTracksCompact(presentationTrackList);
        updatePresentationMiniLibraryStats(); // Обязательно!

        showNotification('Трек успешно обновлен', 'success');
        closeEditModal();
    } catch (error) {
        console.error('Ошибка сохранения:', error);
        showNotification(`Ошибка: ${error.message}`, 'error');
    }
}

async function deleteTrack(trackId) {
    if (!confirm('Вы уверены, что хотите удалить этот трек?')) return;

    try {
        showNotification('🔄 Удаляем трек...', 'info');

        const response = await fetch(`${API_BASE}/tracks/${trackId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Ошибка удаления');
        }

        const result = await response.json();

        // УДАЛЯЕМ трек из currentTracks
        currentTracks = currentTracks.filter(track => track.id !== trackId);

        // УДАЛЯЕМ трек из presentationTrackList если он там есть
        presentationTrackList = presentationTrackList.filter(track => track.id !== trackId);

        // ОБНОВЛЯЕМ ОТОБРАЖЕНИЯ
        renderTracks(currentTracks);

        // ОБНОВЛЯЕМ МЕДИАТЕКУ ПРЕЗЕНТАЦИИ
        if (presentationTrackList.length === 0) {
            document.getElementById('presentationTrackList').value = '';
            const presentationContainer = document.getElementById('presentationTracksList');
            if (presentationContainer) {
                presentationContainer.innerHTML = '<div style="padding: 12px; color: var(--text-muted);">— нет треков</div>';
            }
        } else {
            renderPresentationTracksCompact(presentationTrackList);
            updatePresentationTrackListField();
        }

        // ОБНОВЛЯЕМ СЧЕТЧИКИ
        updateTracksCount();

        showNotification(`✅ Трек удален${result.artist ? ` (${result.artist})` : ''}`, 'success');

    } catch (error) {
        console.error('Ошибка удаления:', error);
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    }
}
function updatePresentationTrackListField() {
    if (presentationTrackList && presentationTrackList.length > 0) {
        const trackListText = presentationTrackList.map(track => `${track.artist} - ${track.title}`).join('\n');
        document.getElementById('presentationTrackList').value = trackListText;
    } else {
        document.getElementById('presentationTrackList').value = '';
    }
}

async function clearTracks() {
    if (!confirm('Вы уверены, что хотите очистить всю медиатеку?\n\n' +
        '✅ Будет выполнено:\n' +
        '• Удалены все треки\n' +
        '• Очищен кеш фото\n' +
        '• Удалены файлы фото\n' +
        '• Сброшены все списки\n\n' +
        'Это действие нельзя отменить!')) return;

    showStatus('mediaStatus', '🔄 Очищаем медиатеку, кеш фото и файлы...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Ошибка очистки');
        }

        const result = await response.json();

        // ПОЛНОСТЬЮ ОЧИЩАЕМ ВСЕ ДАННЫЕ
        currentTracks = [];
        presentationTrackList = [];

        // ОЧИЩАЕМ ВСЕ ОТОБРАЖЕНИЯ
        document.getElementById('presentationTrackList').value = '';
        document.getElementById('missingTracksList').style.display = 'none';

        // ОЧИЩАЕМ МЕДИАТЕКУ ПРЕЗЕНТАЦИИ
        const presentationContainer = document.getElementById('presentationTracksList');
        if (presentationContainer) {
            presentationContainer.innerHTML = '<div style="padding: 12px; color: var(--text-muted);">— нет треков</div>';
        }

        // ОБНОВЛЯЕМ ОСНОВНУЮ МЕДИАТЕКУ
        renderTracks([]);

        // ОБНОВЛЯЕМ СЧЕТЧИКИ
        updateTracksCount();

        showStatus('mediaStatus',
            `✅ Медиатека очищена! Удалено: ${result.tracks_deleted || 0} треков, ` +
            `${result.cache_cleared || 0} записей кеша, ` +
            `${result.images_cleared || 0} файлов фото`,
            'success');

        // Показываем итоговое уведомление
        showNotification(
            `🧹 Очистка завершена! Удалено: ${result.tracks_deleted || 0} треков, ` +
            `${result.cache_cleared || 0} записей кеша`,
            'success'
        );

    } catch (error) {
        console.error('Ошибка очистки:', error);
        showStatus('mediaStatus', `❌ Ошибка: ${error.message}`, 'error');
        showNotification(`❌ Ошибка очистки: ${error.message}`, 'error');
    }
}
// =========================
// BATCH DELETE FUNCTIONS WITH CACHE CLEARING
// =========================

async function deleteSelectedTracks() {
    const selectedTracks = getSelectedTrackIds();
    if (selectedTracks.length === 0) {
        showNotification('Выберите треки для удаления', 'warning');
        return;
    }

    if (!confirm(`Удалить ${selectedTracks.length} выбранных треков?\n\nКеш фото для этих треков будет автоматически очищен.`)) return;

    try {
        showNotification(`🔄 Удаляем ${selectedTracks.length} треков...`, 'info');

        let deletedCount = 0;
        let errors = [];

        // Удаляем каждый трек по отдельности для очистки кеша
        for (const trackId of selectedTracks) {
            try {
                const response = await fetch(`${API_BASE}/tracks/${trackId}`, { method: 'DELETE' });
                if (response.ok) {
                    deletedCount++;

                    // Удаляем из локальных массивов
                    currentTracks = currentTracks.filter(track => track.id !== trackId);
                    presentationTrackList = presentationTrackList.filter(track => track.id !== trackId);

                } else {
                    errors.push(`Трек ${trackId}`);
                }
            } catch (error) {
                errors.push(`Трек ${trackId}: ${error.message}`);
            }
        }

        // Обновляем интерфейс
        renderTracks(currentTracks);
        updatePresentationTrackListField();
        updateTracksCount();

        if (errors.length === 0) {
            showNotification(`✅ Успешно удалено ${deletedCount} треков`, 'success');
        } else {
            showNotification(`✅ Удалено ${deletedCount} треков, ошибок: ${errors.length}`, 'warning');
        }

    } catch (error) {
        console.error('Ошибка массового удаления:', error);
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    }
}

// Вспомогательная функция для получения выбранных треков
function getSelectedTrackIds() {
    const selectedCheckboxes = document.querySelectorAll('.track-select:checked');
    return Array.from(selectedCheckboxes).map(cb => parseInt(cb.closest('.track-item').dataset.trackId));
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
        const countElement = document.getElementById('tracksCount');
        if (countElement) countElement.textContent = count;

        // Обновляем глобальную статистику через track_view_manager
        if (window.trackViewManager && typeof window.trackViewManager.updateGlobalStats === 'function') {
            window.trackViewManager.updateGlobalStats();
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
// AUDIO EDITOR FUNCTIONS (с раздельными полями минут/секунд)
// =========================

(function () {
    console.log('🎬 Аудио-редактор инициализируется');

    // Локальные переменные для аудио-редактора
    let isSegmentDragging = false;
    let segmentDragStartX = 0;
    let initialSegmentStartDrag = 0;
    let isDragging = false;
    let dragType = null;
    let dragStartX = 0;
    let initialSegmentStart = 0;
    let initialSegmentDuration = 0;
    let isUpdatingSegment = false;
    let currentEditorTrack = null;
    let segmentStart = 0;
    let segmentDuration = 30;
    let totalTrackDuration = 180;
    let isGeneratingWaveform = false;
    let currentVolume = 50;
    let isMuted = false;

    // Переменные для ползунка воспроизведения
    let isPlaybackSliderDragging = false;
    let wasPlayingBeforeDrag = false;

    // Флаг для предотвращения множественных вызовов seek
    let isSeeking = false;
    let pendingSeekPosition = null;

    // Текущая позиция воспроизведения (визуальная)
    let currentPlaybackPosition = 0;

    // Функции для работы с форматом времени
    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    function parseTime(minutes, seconds) {
        return parseInt(minutes || 0) * 60 + parseInt(seconds || 0);
    }

    function splitTime(seconds) {
        return {
            minutes: Math.floor(seconds / 60),
            seconds: Math.floor(seconds % 60)
        };
    }

    // Обновление индикатора текущей секунды
    function updateCurrentSecondIndicator(currentTime) {
        const indicator = document.getElementById('secondIndicator');
        const timeLabel = document.getElementById('currentTimeLabel');

        if (indicator && segmentDuration > 0 && timeLabel) {
            // currentTime - это визуальная позиция (0-30 секунд для всего отрезка)
            const percent = (currentTime / segmentDuration) * 100;

            if (indicator) {
                indicator.style.left = `${percent}%`;
            }

            const absoluteTime = segmentStart + currentTime;
            timeLabel.textContent = formatTime(absoluteTime);

            const waveformWrapper = document.querySelector('.waveform-wrapper');
            if (waveformWrapper) {
                const containerWidth = waveformWrapper.offsetWidth;
                const segmentStartPercent = (segmentStart / totalTrackDuration) * 100;
                const segmentWidthPercent = (segmentDuration / totalTrackDuration) * 100;

                const segmentStartPx = (segmentStartPercent / 100) * containerWidth;
                const segmentWidthPx = (segmentWidthPercent / 100) * containerWidth;
                const positionInSegmentPx = (percent / 100) * segmentWidthPx;
                const absolutePositionPx = segmentStartPx + positionInSegmentPx;

                const labelWidth = timeLabel.offsetWidth;
                let leftPosition = absolutePositionPx;

                if (leftPosition - labelWidth / 2 < 0) {
                    leftPosition = labelWidth / 2;
                } else if (leftPosition + labelWidth / 2 > containerWidth) {
                    leftPosition = containerWidth - labelWidth / 2;
                }

                timeLabel.style.left = `${leftPosition}px`;
                timeLabel.style.transform = 'translateX(-50%)';
            }

            const currentAbsoluteTime = document.getElementById('currentAbsoluteTime');
            if (currentAbsoluteTime) {
                currentAbsoluteTime.textContent = formatTime(absoluteTime);
            }
        }
    }

    // Сброс метки времени в начало
    function resetTimeLabel() {
        console.log('🔄 resetTimeLabel вызван');
        const indicator = document.getElementById('secondIndicator');
        const timeLabel = document.getElementById('currentTimeLabel');

        if (indicator) {
            indicator.style.left = '0%';
            console.log('📊 Индикатор сброшен в 0%');
        }

        if (timeLabel) {
            timeLabel.textContent = formatTime(segmentStart);
            console.log('📊 Метка времени сброшена на:', formatTime(segmentStart));

            const waveformWrapper = document.querySelector('.waveform-wrapper');
            if (waveformWrapper) {
                const segmentStartPercent = (segmentStart / totalTrackDuration) * 100;
                const containerWidth = waveformWrapper.offsetWidth;
                const segmentStartPx = (segmentStartPercent / 100) * containerWidth;

                const labelWidth = timeLabel.offsetWidth;
                let leftPosition = segmentStartPx;

                if (leftPosition - labelWidth / 2 < 0) {
                    leftPosition = labelWidth / 2;
                } else if (leftPosition + labelWidth / 2 > containerWidth) {
                    leftPosition = containerWidth - labelWidth / 2;
                }

                timeLabel.style.left = `${leftPosition}px`;
                timeLabel.style.transform = 'translateX(-50%)';
            }
        }

        // Сбрасываем позицию
        currentPlaybackPosition = 0;
    }

    // Обновление отображения отрезка
    function updateSegmentDisplay() {
        console.log('🔄 updateSegmentDisplay вызван, isUpdatingSegment:', isUpdatingSegment);
        if (isUpdatingSegment) return;
        isUpdatingSegment = true;

        try {
            const startTimeFormatted = formatTime(segmentStart);
            const endTimeFormatted = formatTime(segmentStart + segmentDuration);

            const segmentDisplay = document.getElementById('segmentDisplay');
            if (segmentDisplay) {
                segmentDisplay.textContent = `${startTimeFormatted}-${endTimeFormatted}`;
                console.log('📊 Отрезок обновлен:', segmentDisplay.textContent);
            }

            // Обновляем раздельные поля ввода для начала
            const startTimeSplit = splitTime(segmentStart);
            const startMinutesInput = document.getElementById('startTimeMinutes');
            const startSecondsInput = document.getElementById('startTimeSeconds');

            if (startMinutesInput) startMinutesInput.value = startTimeSplit.minutes;
            if (startSecondsInput) startSecondsInput.value = startTimeSplit.seconds;

            // Обновляем раздельные поля ввода для длительности
            const durationTimeSplit = splitTime(segmentDuration);
            const durationMinutesInput = document.getElementById('durationTimeMinutes');
            const durationSecondsInput = document.getElementById('durationTimeSeconds');
            const segmentDurationMinutesInput = document.getElementById('segmentDurationMinutes');
            const segmentDurationSecondsInput = document.getElementById('segmentDurationSeconds');

            if (durationMinutesInput) durationMinutesInput.value = durationTimeSplit.minutes;
            if (durationSecondsInput) durationSecondsInput.value = durationTimeSplit.seconds;
            if (segmentDurationMinutesInput) segmentDurationMinutesInput.value = durationTimeSplit.minutes;
            if (segmentDurationSecondsInput) segmentDurationSecondsInput.value = durationTimeSplit.seconds;

            // Обновляем отображение конечного времени
            const endTimeSplit = splitTime(segmentStart + segmentDuration);
            const endMinutesDisplay = document.getElementById('endTimeMinutesDisplay');
            const endSecondsDisplay = document.getElementById('endSecondsDisplay');

            if (endMinutesDisplay) endMinutesDisplay.textContent = endTimeSplit.minutes.toString().padStart(2, '0');
            if (endSecondsDisplay) endSecondsDisplay.textContent = endTimeSplit.seconds.toString().padStart(2, '0');
        } finally {
            isUpdatingSegment = false;
            console.log('✅ updateSegmentDisplay завершен');
        }
    }

    // Настройка обработчиков ввода для раздельных полей
    function setupSplitTimeInputHandlers() {
        console.log('🔄 Настройка обработчиков ввода для раздельных полей');

        // Простая функция для добавления стрелочек
        function addArrowsToInput(inputId, minValue, maxValue, step = 1) {
            const input = document.getElementById(inputId);
            if (!input) return;

            const parent = input.parentNode;

            // Создаем обертку
            const wrapper = document.createElement('div');
            wrapper.className = 'number-input-wrapper';

            parent.insertBefore(wrapper, input);
            wrapper.appendChild(input);

            // Создаем стрелочки
            const arrows = document.createElement('div');
            arrows.className = 'input-arrows';

            const upArrow = document.createElement('button');
            upArrow.type = 'button';
            upArrow.className = 'arrow-btn up';
            upArrow.innerHTML = '▲';

            const downArrow = document.createElement('button');
            downArrow.type = 'button';
            downArrow.className = 'arrow-btn down';
            downArrow.innerHTML = '▼';

            arrows.appendChild(upArrow);
            arrows.appendChild(downArrow);
            wrapper.appendChild(arrows);

            // Добавляем минимальные стили
            const styleId = 'time-input-simple-styles';
            if (!document.getElementById(styleId)) {
                const style = document.createElement('style');
                style.id = styleId;
                style.textContent = `
            .number-input-wrapper {
                position: relative;
                display: inline-block;
                width: 100px; /* ШИРЕ */
                vertical-align: middle;
            }
            
            .number-input-wrapper input {
                width: 100%;
                padding: 8px 30px 8px 10px !important;
                box-sizing: border-box !important;
                font-size: 14px;
                text-align: center;
            }
            
            .input-arrows {
                position: absolute;
                right: 2px;
                top: 2px;
                bottom: 2px;
                width: 24px;
                display: flex;
                flex-direction: column;
                background: transparent; /* ПРОЗРАЧНЫЙ */
                z-index: 2;
            }
            
            .arrow-btn {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #666;
                cursor: pointer;
                border: none;
                background: transparent; /* ПРОЗРАЧНЫЙ */
                padding: 0;
                font-size: 10px;
            }
            
            .arrow-btn:hover {
                color: #000;
            }
            
            .arrow-btn.up {
                border-bottom: 1px solid #eee;
            }
            
            .arrow-btn.down {
                border-top: 1px solid #eee;
            }
        `;
                document.head.appendChild(style);
            }

            // Обработчики
            upArrow.addEventListener('click', (e) => {
                e.preventDefault();
                let value = parseInt(input.value) || 0;
                value = Math.min(maxValue, value + step);
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });

            downArrow.addEventListener('click', (e) => {
                e.preventDefault();
                let value = parseInt(input.value) || 0;
                value = Math.max(minValue, value - step);
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });

            // Клавиатура
            input.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    upArrow.click();
                } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    downArrow.click();
                }
            });
        }

        // Обработчик для полей начала
        const startMinutesInput = document.getElementById('startTimeMinutes');
        const startSecondsInput = document.getElementById('startTimeSeconds');

        if (startMinutesInput && startSecondsInput) {
            // Добавляем стрелочки
            addArrowsToInput('startTimeMinutes', 0, 59, 1);
            addArrowsToInput('startTimeSeconds', 0, 59, 1);

            const updateStartTime = () => {
                console.log('📝 Поля начала изменены:', startMinutesInput.value, startSecondsInput.value);
                const minutes = parseInt(startMinutesInput.value) || 0;
                const seconds = parseInt(startSecondsInput.value) || 0;
                segmentStart = minutes * 60 + seconds;
                segmentStart = Math.max(0, Math.min(totalTrackDuration - segmentDuration, segmentStart));
                applyInputChanges();
            };

            startMinutesInput.addEventListener('change', updateStartTime);
            startSecondsInput.addEventListener('change', updateStartTime);
            startMinutesInput.addEventListener('input', updateStartTime);
            startSecondsInput.addEventListener('input', updateStartTime);
        }

        // Обработчик для полей длительности
        const durationMinutesInput = document.getElementById('durationTimeMinutes');
        const durationSecondsInput = document.getElementById('durationTimeSeconds');
        const segmentDurationMinutesInput = document.getElementById('segmentDurationMinutes');
        const segmentDurationSecondsInput = document.getElementById('segmentDurationSeconds');

        if (durationMinutesInput && durationSecondsInput) {
            addArrowsToInput('durationTimeMinutes', 0, 2, 1);
            addArrowsToInput('durationTimeSeconds', 0, 59, 1);
        }

        if (segmentDurationMinutesInput && segmentDurationSecondsInput) {
            addArrowsToInput('segmentDurationMinutes', 0, 2, 1);
            addArrowsToInput('segmentDurationSeconds', 0, 59, 1);
        }

        const updateDurationTime = () => {
            console.log('📝 Поля длительности изменены');
            let minutes = 0;
            let seconds = 0;

            if (durationMinutesInput && durationSecondsInput) {
                minutes = parseInt(durationMinutesInput.value) || 0;
                seconds = parseInt(durationSecondsInput.value) || 0;
            } else if (segmentDurationMinutesInput && segmentDurationSecondsInput) {
                minutes = parseInt(segmentDurationMinutesInput.value) || 0;
                seconds = parseInt(segmentDurationSecondsInput.value) || 0;
            }

            segmentDuration = minutes * 60 + seconds;
            segmentDuration = Math.max(5, Math.min(120, segmentDuration));

            // Синхронизируем оба набора полей
            if (durationMinutesInput && segmentDurationMinutesInput) {
                const timeSplit = splitTime(segmentDuration);
                durationMinutesInput.value = timeSplit.minutes;
                durationSecondsInput.value = timeSplit.seconds;
                segmentDurationMinutesInput.value = timeSplit.minutes;
                segmentDurationSecondsInput.value = timeSplit.seconds;
            }

            applyInputChanges();
        };

        if (durationMinutesInput && durationSecondsInput) {
            durationMinutesInput.addEventListener('change', updateDurationTime);
            durationSecondsInput.addEventListener('change', updateDurationTime);
            durationMinutesInput.addEventListener('input', updateDurationTime);
            durationSecondsInput.addEventListener('input', updateDurationTime);
        }

        if (segmentDurationMinutesInput && segmentDurationSecondsInput) {
            segmentDurationMinutesInput.addEventListener('change', updateDurationTime);
            segmentDurationSecondsInput.addEventListener('change', updateDurationTime);
            segmentDurationMinutesInput.addEventListener('input', updateDurationTime);
            segmentDurationSecondsInput.addEventListener('input', updateDurationTime);
        }
    }

    // Функция для обновления визуальной индикации
    function updatePlaybackIndicator(value) {
        console.log('📊 Обновление индикатора воспроизведения:', value);
        const percent = parseFloat(value);
        const currentTime = (percent / 100) * segmentDuration;

        // Обновляем позицию
        currentPlaybackPosition = currentTime;

        // Обновляем красную полоску
        const secondIndicator = document.getElementById('secondIndicator');
        if (secondIndicator) {
            secondIndicator.style.left = `${percent}%`;
            console.log('📊 Красная полоска перемещена на:', percent + '%');
        }

        // Обновляем метку времени
        const timeLabel = document.getElementById('currentTimeLabel');
        if (timeLabel) {
            const absoluteTime = segmentStart + currentTime;
            timeLabel.textContent = formatTime(absoluteTime);
            console.log('📊 Метка времени обновлена:', timeLabel.textContent);

            // Позиционируем метку
            const waveformWrapper = document.querySelector('.waveform-wrapper');
            if (waveformWrapper) {
                const containerWidth = waveformWrapper.offsetWidth;
                const segmentStartPercent = (segmentStart / totalTrackDuration) * 100;
                const segmentWidthPercent = (segmentDuration / totalTrackDuration) * 100;

                const segmentStartPx = (segmentStartPercent / 100) * containerWidth;
                const segmentWidthPx = (segmentWidthPercent / 100) * containerWidth;
                const positionInSegmentPx = (percent / 100) * segmentWidthPx;
                const absolutePositionPx = segmentStartPx + positionInSegmentPx;

                const labelWidth = timeLabel.offsetWidth;
                let leftPosition = absolutePositionPx;

                if (leftPosition - labelWidth / 2 < 0) {
                    leftPosition = labelWidth / 2;
                } else if (leftPosition + labelWidth / 2 > containerWidth) {
                    leftPosition = containerWidth - labelWidth / 2;
                }

                timeLabel.style.left = `${leftPosition}px`;
                timeLabel.style.transform = 'translateX(-50%)';
            }
        }

        // Обновляем время воспроизведения в плеере
        const timeEl = document.getElementById('playbackTime');
        if (timeEl) {
            timeEl.textContent = formatTime(currentTime);
            console.log('📊 Время воспроизведения обновлено:', timeEl.textContent);
        }
    }

    // Функция для плавного перехода к новой позиции
    async function seekToPosition(value) {
        if (isSeeking) {
            pendingSeekPosition = value;
            return;
        }

        isSeeking = true;
        console.log('🎵 seekToPosition:', value);

        const percent = parseFloat(value) / 100;
        const targetTime = percent * segmentDuration;

        try {
            console.log('📊 Переход к позиции:', {
                targetPosition: targetTime,
                segmentStart: segmentStart,
                segmentDuration: segmentDuration
            });

            // Останавливаем текущее воспроизведение
            if (audioPlayer.isPlaying) {
                audioPlayer.pause();
            }

            // Загружаем новый сегмент с нужной позиции
            console.log('🔄 Загружаем сегмент с позиции:', targetTime);

            // Создаем URL с отсечением начала
            const segmentUrl = `${API_BASE}/tracks/${currentEditorTrack}/segment-file?start_time=${segmentStart + targetTime}&duration=${segmentDuration - targetTime}&nocache=${Date.now()}`;

            console.log('🔗 Новый URL сегмента:', segmentUrl);

            // Загружаем урезанный сегмент
            await audioPlayer.loadSegmentWithOffset(currentEditorTrack, segmentStart, segmentDuration, targetTime, segmentUrl);

            // Обновляем визуальную индикацию
            updatePlaybackIndicator(value);

            // Запускаем воспроизведение
            await audioPlayer.play();

            console.log('✅ Переход к позиции завершен');

        } catch (error) {
            console.error('❌ Ошибка перехода к позиции:', error);
        } finally {
            isSeeking = false;

            // Обрабатываем отложенный запрос
            if (pendingSeekPosition !== null) {
                const pendingValue = pendingSeekPosition;
                pendingSeekPosition = null;
                setTimeout(() => seekToPosition(pendingValue), 100);
            }
        }
    }

    // Настройка ползунка воспроизведения
    function setupPlaybackSlider() {
        console.log('🔄 Настройка ползунка воспроизведения');
        const playbackSlider = document.getElementById('playbackSlider');

        if (!playbackSlider) {
            console.warn('⚠️ Ползунок воспроизведения не найден');
            return;
        }

        // Удаляем старые обработчики из HTML атрибутов
        playbackSlider.removeAttribute('oninput');
        playbackSlider.removeAttribute('onchange');
        console.log('✅ Старые обработчики HTML удалены');

        // Сбрасываем состояние
        isPlaybackSliderDragging = false;
        wasPlayingBeforeDrag = false;

        // Обработчик начала перетаскивания
        playbackSlider.addEventListener('mousedown', function (e) {
            console.log('🎛️ Ползунок: начало перетаскивания мышью');
            isPlaybackSliderDragging = true;
            wasPlayingBeforeDrag = audioPlayer.isPlaying;

            if (audioPlayer.isPlaying) {
                audioPlayer.pause();
            }

            // Обрабатываем первое движение
            handlePlaybackSliderMove(e);

            document.addEventListener('mousemove', handlePlaybackSliderMove);
            document.addEventListener('mouseup', handlePlaybackSliderMouseUp);
        });

        // Обработчик для касаний
        playbackSlider.addEventListener('touchstart', function (e) {
            console.log('🎛️ Ползунок: начало перетаскивания касанием');
            isPlaybackSliderDragging = true;
            wasPlayingBeforeDrag = audioPlayer.isPlaying;

            if (audioPlayer.isPlaying) {
                audioPlayer.pause();
            }

            handlePlaybackSliderTouchMove(e);
            e.preventDefault();
        });

        function handlePlaybackSliderMove(e) {
            if (!isPlaybackSliderDragging) return;

            const rect = playbackSlider.getBoundingClientRect();
            let percent = (e.clientX - rect.left) / rect.width;
            percent = Math.max(0, Math.min(1, percent));
            const value = percent * 100;

            playbackSlider.value = value;
            updatePlaybackIndicator(value);
        }

        function handlePlaybackSliderTouchMove(e) {
            if (!isPlaybackSliderDragging) return;

            const rect = playbackSlider.getBoundingClientRect();
            const touch = e.touches[0];
            let percent = (touch.clientX - rect.left) / rect.width;
            percent = Math.max(0, Math.min(1, percent));
            const value = percent * 100;

            playbackSlider.value = value;
            updatePlaybackIndicator(value);
            e.preventDefault();
        }

        function handlePlaybackSliderMouseUp(e) {
            console.log('🎛️ Ползунок: окончание перетаскивания мышью');

            document.removeEventListener('mousemove', handlePlaybackSliderMove);
            document.removeEventListener('mouseup', handlePlaybackSliderMouseUp);

            if (isPlaybackSliderDragging) {
                isPlaybackSliderDragging = false;
                setTimeout(() => {
                    seekToPosition(playbackSlider.value);
                }, 10);
            }
        }

        // Обработчики для тач-устройств
        playbackSlider.addEventListener('touchend', function (e) {
            console.log('🎛️ Ползунок: окончание перетаскивания касанием');

            if (isPlaybackSliderDragging) {
                isPlaybackSliderDragging = false;
                setTimeout(() => {
                    seekToPosition(playbackSlider.value);
                }, 10);
            }
            e.preventDefault();
        });

        playbackSlider.addEventListener('touchcancel', function (e) {
            console.log('🎛️ Ползунок: отмена перетаскивания касанием');
            isPlaybackSliderDragging = false;
        });

        // Экспортируем функцию для глобального доступа
        window.seekToPosition = seekToPosition;
    }

    // Открытие аудио-редактора
    window.openAudioEditor = async function (trackId) {
        console.log('🚪 Открытие аудио-редактора для трека:', trackId);

        if (isGeneratingWaveform) {
            console.warn('⚠️ Дождитесь завершения генерации waveform');
            showNotification('Дождитесь завершения генерации waveform', 'warning');
            return;
        }

        currentEditorTrack = trackId;
        const track = await loadTrackInfo(trackId);
        if (!track) {
            console.error('❌ Ошибка загрузки трека');
            showNotification('Ошибка загрузки трека', 'error');
            return;
        }

        segmentStart = track.segment_start || 0;
        segmentDuration = track.segment_duration || 30;
        totalTrackDuration = track.duration || 180;
        console.log('📊 Параметры трека:', {
            segmentStart, segmentDuration, totalTrackDuration
        });

        const modal = document.getElementById('audioEditorModal');
        modal.classList.add('audio-modal-fullscreen');
        modal.style.display = 'block';

        document.body.style.overflow = 'hidden';

        updateTrackInfo(track);
        await loadWaveform(trackId);

        updateSegmentDisplay();

        // Настраиваем обработчики ввода для раздельных полей
        setupSplitTimeInputHandlers();

        // Настраиваем слайдер времени
        const timeSlider = document.getElementById('timeSlider');
        if (timeSlider) {
            timeSlider.max = Math.max(0, totalTrackDuration - segmentDuration);
            timeSlider.value = segmentStart;
            console.log('🎛️ Слайдер времени установлен:', segmentStart);

            timeSlider.addEventListener('input', function () {
                console.log('🎛️ Слайдер времени изменен:', this.value);
                segmentStart = parseFloat(this.value);
                if (!isUpdatingSegment) {
                    isUpdatingSegment = true;
                    try {
                        updateSegmentDisplay();
                    } finally {
                        isUpdatingSegment = false;
                    }
                }

                updateTimelineDisplay();
            });
        }

        updateTimelineDisplay();
        document.getElementById('analysisInfo').style.display = 'none';

        audioPlayer.init();
        await audioPlayer.loadSegment(trackId, segmentStart, segmentDuration);
        initSegmentDrag();
        resetTimeLabel();

        // Настраиваем ползунок воспроизведения
        setupPlaybackSlider();
        console.log('✅ Аудио-редактор открыт');
    };

    // Автоматическое применение изменений
    function applyInputChanges() {
        console.log('🔄 applyInputChanges вызван');
        // Корректируем значения
        segmentStart = Math.max(0, Math.min(totalTrackDuration - segmentDuration, segmentStart));
        segmentDuration = Math.max(5, Math.min(120, segmentDuration));
        console.log('📊 Корректированные значения:', { segmentStart, segmentDuration });

        // Обновляем слайдер
        const timeSlider = document.getElementById('timeSlider');
        if (timeSlider) {
            timeSlider.max = Math.max(0, totalTrackDuration - segmentDuration);
            timeSlider.value = Math.min(segmentStart, timeSlider.max);
            console.log('🎛️ Слайдер времени обновлен:', timeSlider.value);
        }

        // Обновляем отображение
        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();

        // Перезагружаем сегмент в плеере если он активен
        if (audioPlayer.currentTrackId === currentEditorTrack) {
            console.log('🔄 Перезагрузка сегмента в плеере');
            reloadSegmentInPlayer();
        }

        resetTimeLabel();
        console.log('✅ applyInputChanges завершен');
    }

    // Утилиты для аудиоплеера
    const audioPlayer = {
        element: null,
        isPlaying: false,
        currentTrackId: null,
        pausedPosition: 0,
        currentSegmentStart: 0,
        currentSegmentDuration: 0,
        currentOffset: 0,
        isAudioInitialized: false,

        init: function () {
            console.log('🎵 Инициализация аудиоплеера');
            if (!this.element) {
                this.element = new Audio();
                this.element.preload = 'auto';
                this.setVolume(currentVolume);
                console.log('✅ Аудио элемент создан');

                this.element.addEventListener('timeupdate', () => {
                    if (!isPlaybackSliderDragging) {
                        const visualTime = this.currentOffset + this.element.currentTime;
                        const playbackSlider = document.getElementById('playbackSlider');
                        if (playbackSlider) {
                            const percent = (visualTime / segmentDuration) * 100;
                            playbackSlider.value = Math.min(100, Math.max(0, percent));
                        }
                        updateCurrentSecondIndicator(visualTime);
                        const timeEl = document.getElementById('playbackTime');
                        if (timeEl) {
                            timeEl.textContent = formatTime(visualTime);
                        }
                    }
                });

                this.element.addEventListener('ended', () => {
                    console.log('⏹️ Воспроизведение завершено');
                    this.stop();
                });

                this.element.addEventListener('loadeddata', () => {
                    console.log('✅ Аудио загружено');
                    this.isAudioInitialized = true;
                });

                this.element.addEventListener('error', (e) => {
                    console.error('❌ Ошибка аудио:', e);
                    this.stop();
                });

                this.element.addEventListener('pause', () => {
                    if (this.element.currentTime > 0) {
                        this.pausedPosition = this.element.currentTime;
                    }
                });
            }
        },

        loadSegment: async function (trackId, startTime, duration, startPosition = 0) {
            try {
                console.log('🔄 Загрузка сегмента:', {
                    trackId, startTime, duration, startPosition
                });

                this.currentTrackId = trackId;
                this.currentSegmentStart = startTime;
                this.currentSegmentDuration = duration;
                this.currentOffset = 0;

                const segmentUrl = `${API_BASE}/tracks/${trackId}/segment-file?start_time=${startTime}&duration=${duration}&nocache=${Date.now()}`;
                console.log('🔄 Загружаем сегмент:', segmentUrl);

                this.stop();
                this.element.src = segmentUrl;

                await new Promise((resolve, reject) => {
                    const onCanPlay = () => {
                        this.element.removeEventListener('canplay', onCanPlay);
                        resolve();
                    };
                    const onError = (e) => {
                        this.element.removeEventListener('error', onError);
                        reject(new Error('Failed to load audio'));
                    };
                    this.element.addEventListener('canplay', onCanPlay);
                    this.element.addEventListener('error', onError);
                    setTimeout(() => resolve(), 3000);
                });

                console.log('✅ Сегмент загружен');
                return true;
            } catch (error) {
                console.error('❌ Ошибка загрузки сегмента:', error);
                return false;
            }
        },

        loadSegmentWithOffset: async function (trackId, segmentStartTime, segmentDuration, offset, segmentUrl) {
            try {
                console.log('🔄 Загрузка сегмента со смещением:', {
                    trackId, segmentStartTime, segmentDuration, offset
                });

                this.currentTrackId = trackId;
                this.currentSegmentStart = segmentStartTime;
                this.currentSegmentDuration = segmentDuration;
                this.currentOffset = offset;

                this.stop();
                this.element.src = segmentUrl;

                await new Promise((resolve, reject) => {
                    const onCanPlay = () => {
                        this.element.removeEventListener('canplay', onCanPlay);
                        resolve();
                    };
                    const onError = (e) => {
                        this.element.removeEventListener('error', onError);
                        reject(new Error('Failed to load audio'));
                    };
                    this.element.addEventListener('canplay', onCanPlay);
                    this.element.addEventListener('error', onError);
                    setTimeout(() => resolve(), 3000);
                });

                console.log('✅ Сегмент со смещением загружен');
                return true;
            } catch (error) {
                console.error('❌ Ошибка загрузки сегмента со смещением:', error);
                return false;
            }
        },

        play: async function () {
            console.log('▶️ play() вызван:', {
                isPlaying: this.isPlaying,
                pausedPosition: this.pausedPosition
            });

            if (!this.element || !this.element.src) {
                console.warn('⚠️ Аудио не загружено');
                return;
            }

            try {
                if (this.pausedPosition > 0) {
                    this.element.currentTime = this.pausedPosition;
                    this.pausedPosition = 0;
                }

                await this.element.play();
                this.isPlaying = true;
                updatePlayButton();
                return Promise.resolve();
            } catch (error) {
                console.error('❌ Ошибка воспроизведения:', error);
                this.stop();
                return Promise.reject(error);
            }
        },

        pause: function () {
            console.log('⏸️ pause() вызван');
            if (this.element) {
                if (this.element.currentTime > 0) {
                    this.pausedPosition = this.element.currentTime;
                }
                this.element.pause();
                this.isPlaying = false;
                updatePlayButton();
            }
        },

        stop: function () {
            console.log('⏹️ stop() вызван');
            if (this.element) {
                this.element.pause();
                this.element.currentTime = 0;
                this.pausedPosition = 0;
            }
            this.isPlaying = false;
            updatePlayButton();
            resetTimeLabel();
        },

        setVolume: function (value) {
            console.log('🔊 Установка громкости:', value);
            if (this.element) {
                this.element.volume = value / 100;
            }
        },

        continuePlayback: function () {
            console.log('▶️ continuePlayback() вызван');
            if (!this.element.src) {
                console.warn('⚠️ Аудио не загружено для continuePlayback');
                return;
            }
            return this.play();
        },

        isSameSegment: function (startTime, duration) {
            return this.currentTrackId === currentEditorTrack &&
                this.currentSegmentStart === startTime &&
                this.currentSegmentDuration === duration &&
                this.element.src &&
                this.element.src.includes(`start_time=${startTime}`);
        }
    };

    // Загрузка waveform
    async function loadWaveform(trackId) {
        console.log('🔄 Загрузка waveform для трека:', trackId);
        if (isGeneratingWaveform) {
            console.log('⏳ Waveform уже генерируется');
            return;
        }
        const container = document.getElementById('waveformContainer');
        if (!container) {
            console.warn('⚠️ Контейнер waveform не найден');
            return;
        }

        container.innerHTML = '<div class="waveform-loading">Генерация waveform...</div>';
        isGeneratingWaveform = true;

        try {
            const response = await fetch(`${API_BASE}/tracks/${trackId}/waveform`);
            if (!response.ok) throw new Error('Failed to load waveform');
            const data = await response.json();
            if (data.waveform_data) {
                container.innerHTML = `
                    <div class="waveform-image-container">
                        <img src="${data.waveform_data}" alt="Waveform" class="waveform-image" 
                             onclick="handleWaveformClick(event)" 
                             onload="initWaveformInteractions()"
                             onerror="handleWaveformError()">
                        
                        <div class="segment-marker" id="segmentMarker">
                            <div class="segment-handle segment-handle-left" id="handleLeft" 
                                 onmousedown="startDrag(event, 'left')"></div>
                            <div class="segment-content" id="segmentContent">
                                <div class="segment-drag-handle" id="segmentDragHandle">⋮⋮</div>
                                <div class="segment-duration-badge">${formatTime(segmentDuration)}</div>
                            </div>
                            <div class="segment-handle segment-handle-right" id="handleRight" 
                                 onmousedown="startDrag(event, 'right')"></div>
                        </div>
                        
                        <div class="second-indicator-container" id="secondIndicatorContainer">
                            <div class="second-indicator" id="secondIndicator"></div>
                        </div>
                    </div>
                `;
                initSegmentDrag();
                setTimeout(() => {
                    updateSegmentMarker();
                    resetTimeLabel();
                }, 100);
                console.log('✅ Waveform загружен');
            } else {
                container.innerHTML = '<div class="waveform-loading">Waveform не доступен</div>';
            }
        } catch (error) {
            console.error('❌ Ошибка загрузки waveform:', error);
            container.innerHTML = '<div class="waveform-loading">Ошибка загрузки waveform</div>';
        } finally {
            isGeneratingWaveform = false;
        }
    }

    // Обновление маркера отрезка
    function updateSegmentMarker() {
        console.log('🔄 Обновление маркера отрезка');
        const marker = document.getElementById('segmentMarker');
        const container = document.getElementById('waveformContainer');
        const indicatorContainer = document.getElementById('secondIndicatorContainer');

        if (!marker || !container) return;

        const startPercent = (segmentStart / totalTrackDuration) * 100;
        const durationPercent = (segmentDuration / totalTrackDuration) * 100;

        marker.style.left = startPercent + '%';
        marker.style.width = durationPercent + '%';

        if (indicatorContainer) {
            indicatorContainer.style.left = startPercent + '%';
            indicatorContainer.style.width = durationPercent + '%';
            indicatorContainer.style.display = 'block';
        }

        const durationBadge = document.querySelector('.segment-duration-badge');
        if (durationBadge) {
            durationBadge.textContent = formatTime(segmentDuration);
        }
    }

    // Перезагрузка сегмента в плеере
    async function reloadSegmentInPlayer() {
        console.log('🔄 Перезагрузка сегмента в плеере');
        if (audioPlayer.currentTrackId === currentEditorTrack) {
            const wasPlaying = audioPlayer.isPlaying;
            const currentPosition = audioPlayer.element ? audioPlayer.element.currentTime : 0;

            await audioPlayer.loadSegment(currentEditorTrack, segmentStart, segmentDuration, currentPosition);
            resetTimeLabel();

            if (wasPlaying) {
                await audioPlayer.play();
            }
        }
    }

    // Обновление timeline
    function updateTimelineDisplay() {
        console.log('🔄 Обновление timeline');
        const startTime = Math.round(segmentStart * 10) / 10;
        const endTime = Math.round(Math.min(segmentStart + segmentDuration, totalTrackDuration) * 10) / 10;

        const startFormatted = formatTime(startTime);
        const endFormatted = formatTime(endTime);

        const segmentStartEl = document.getElementById('segmentStartTime');
        const segmentEndEl = document.getElementById('segmentEndTime');
        const timeSliderValueEl = document.getElementById('timeSliderValue');

        if (segmentStartEl) segmentStartEl.textContent = startFormatted;
        if (segmentEndEl) segmentEndEl.textContent = endFormatted;
        if (timeSliderValueEl) timeSliderValueEl.textContent = startFormatted;

        const playbackTotalEl = document.getElementById('playbackTotal');
        if (playbackTotalEl) {
            playbackTotalEl.textContent = formatTime(segmentDuration);
        }

        const slider = document.getElementById('timeSlider');
        if (slider) {
            const maxValue = Math.max(0, totalTrackDuration - segmentDuration);
            slider.max = Math.round(maxValue * 10) / 10;
            slider.value = Math.round(segmentStart * 10) / 10;
            slider.disabled = maxValue <= 0;
        }

        updateSegmentMarker();
        resetTimeLabel();
    }

    // Обновление информации о треке
    function updateTrackInfo(track) {
        console.log('🔄 Обновление информации о треке:', track);
        const infoElement = document.getElementById('editorTrackInfo');
        if (!infoElement) return;
        infoElement.innerHTML = `
            <h4>${escapeHtml(track.artist)} - ${escapeHtml(track.title)}</h4>
            <p>Файл: ${track.original_filename}</p>
        `;
        const totalEl = document.getElementById('totalDurationDisplay');
        if (totalEl) totalEl.textContent = formatTime(totalTrackDuration);
    }

    // Инициализация перетаскивания сегмента
    function initSegmentDrag() {
        console.log('🔄 Инициализация перетаскивания сегмента');
        setTimeout(() => {
            const marker = document.getElementById('segmentMarker');
            const dragHandle = marker ? marker.querySelector('.segment-drag-handle') : null;

            if (marker && dragHandle) {
                dragHandle.addEventListener('mousedown', startSegmentDrag);
                marker.addEventListener('mousedown', function (e) {
                    if (!e.target.classList.contains('segment-handle')) {
                        startSegmentDrag(e);
                    }
                });

                const handleLeft = document.getElementById('handleLeft');
                const handleRight = document.getElementById('handleRight');

                if (handleLeft) {
                    handleLeft.addEventListener('mousedown', function (e) {
                        startResizeDrag(e, 'left');
                    });
                }

                if (handleRight) {
                    handleRight.addEventListener('mousedown', function (e) {
                        startResizeDrag(e, 'right');
                    });
                }
            } else {
                setTimeout(initSegmentDrag, 200);
            }
        }, 100);
    }

    // Функции для изменения размера сегмента
    function startResizeDrag(event, side) {
        console.log('🎯 Начало изменения размера сегмента:', side);
        event.preventDefault();
        event.stopPropagation();

        isDragging = true;
        dragType = side;
        dragStartX = event.clientX;
        initialSegmentStart = segmentStart;
        initialSegmentDuration = segmentDuration;

        document.addEventListener('mousemove', handleResizeDrag);
        document.addEventListener('mouseup', stopResizeDrag);
    }

    function handleResizeDrag(event) {
        if (!isDragging) return;

        const container = document.getElementById('waveformContainer');
        if (!container) return;

        const rect = container.getBoundingClientRect();
        const deltaX = event.clientX - dragStartX;
        const deltaPercent = (deltaX / container.offsetWidth) * 100;
        const deltaTime = (deltaPercent / 100) * totalTrackDuration;

        if (dragType === 'left') {
            let newStart = initialSegmentStart + deltaTime;
            newStart = Math.max(0, Math.min(newStart, segmentStart + segmentDuration - 5));
            const deltaDuration = initialSegmentStart - newStart;

            segmentStart = Math.round(newStart * 10) / 10;
            segmentDuration = Math.round((initialSegmentDuration + deltaDuration) * 10) / 10;

        } else if (dragType === 'right') {
            let newDuration = initialSegmentDuration + deltaTime;
            newDuration = Math.max(5, Math.min(newDuration, totalTrackDuration - segmentStart));

            segmentDuration = Math.round(newDuration * 10) / 10;
        }

        segmentDuration = Math.max(5, Math.min(segmentDuration, 120));

        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();
    }

    function stopResizeDrag() {
        console.log('✅ Остановка изменения размера сегмента');
        isDragging = false;
        dragType = null;
        document.removeEventListener('mousemove', handleResizeDrag);
        document.removeEventListener('mouseup', stopResizeDrag);

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    }

    function startSegmentDrag(event) {
        console.log('🎯 Начало перетаскивания сегмента');
        if (event.target.classList.contains('segment-handle')) {
            return;
        }

        isSegmentDragging = true;
        segmentDragStartX = event.clientX;
        initialSegmentStartDrag = segmentStart;

        document.addEventListener('mousemove', handleSegmentDrag);
        document.addEventListener('mouseup', stopSegmentDrag);
        event.preventDefault();
    }

    function handleSegmentDrag(event) {
        if (!isSegmentDragging) return;

        const container = document.getElementById('waveformContainer');
        if (!container) return;

        const rect = container.getBoundingClientRect();
        const deltaX = event.clientX - segmentDragStartX;
        const deltaPercent = (deltaX / container.offsetWidth) * 100;
        const deltaTime = (deltaPercent / 100) * totalTrackDuration;

        let newStart = initialSegmentStartDrag + deltaTime;
        newStart = Math.max(0, Math.min(newStart, totalTrackDuration - segmentDuration));

        if (segmentStart !== newStart) {
            segmentStart = newStart;
            updateTimelineDisplay();
            updateSegmentDisplay();
            updateSegmentMarker();
        }
    }

    function stopSegmentDrag() {
        console.log('✅ Остановка перетаскивания сегмента');
        isSegmentDragging = false;
        document.removeEventListener('mousemove', handleSegmentDrag);
        document.removeEventListener('mouseup', stopSegmentDrag);

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    }

    // Обновление кнопки воспроизведения
    function updatePlayButton() {
        console.log('🔄 Обновление кнопки воспроизведения, isPlaying:', audioPlayer.isPlaying);
        const playBtn = document.getElementById('playBtn');
        const stopBtn = document.getElementById('stopBtn');
        const playIcon = document.getElementById('playIcon');
        const playText = document.getElementById('playText');

        if (!playBtn || !stopBtn) return;

        if (audioPlayer.isPlaying) {
            playBtn.style.display = 'none';
            stopBtn.style.display = 'block';
            if (playIcon) playIcon.textContent = '⏸️';
            if (playText) playText.textContent = 'Пауза';
        } else {
            playBtn.style.display = 'block';
            stopBtn.style.display = 'none';
            if (playIcon) playIcon.textContent = '▶️';
            if (playText) playText.textContent = 'Воспроизвести';
        }
    }

    // Управление воспроизведением
    window.togglePlayback = function () {
        console.log('🎵 togglePlayback() вызван');

        if (!currentEditorTrack) {
            console.warn('⚠️ Нет текущего трека');
            return;
        }

        if (audioPlayer.isPlaying) {
            console.log('⏸️ Трек играет, ставим на паузу');
            audioPlayer.pause();
        } else {
            console.log('▶️ Трек на паузе, запускаем воспроизведение');

            const needsNewSegment = !audioPlayer.element ||
                !audioPlayer.element.src ||
                !audioPlayer.isSameSegment(segmentStart, segmentDuration);

            if (needsNewSegment) {
                console.log('🔄 Нужен новый сегмент, загружаем...');
                const startPosition = audioPlayer.pausedPosition > 0 ? audioPlayer.pausedPosition : 0;

                audioPlayer.loadSegment(currentEditorTrack, segmentStart, segmentDuration, startPosition)
                    .then(() => {
                        console.log('✅ Сегмент загружен, запускаем воспроизведение');
                        return audioPlayer.play();
                    })
                    .catch(error => {
                        console.error('❌ Ошибка загрузки или воспроизведения:', error);
                    });
            } else {
                console.log('🎯 Тот же сегмент, продолжаем воспроизведение');
                audioPlayer.continuePlayback();
            }
        }
    };

    window.stopPlayback = function () {
        console.log('⏹️ stopPlayback() вызван');
        audioPlayer.stop();
    };

    // Управление отрезком (оставляем для совместимости)
    window.moveSegment = function (seconds) {
        console.log('🎯 Перемещение отрезка на:', seconds, 'секунд');
        const newStart = segmentStart + seconds;
        if (newStart < 0) {
            segmentStart = 0;
        } else if (newStart + segmentDuration > totalTrackDuration) {
            segmentStart = totalTrackDuration - segmentDuration;
        } else {
            segmentStart = newStart;
        }
        segmentStart = Math.round(segmentStart * 10) / 10;
        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    };

    window.setSegmentToStart = function () {
        console.log('🎯 Установка отрезка в начало');
        segmentStart = 0;
        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    };

    window.setSegmentToMiddle = function () {
        console.log('🎯 Установка отрезка в середину');
        segmentStart = Math.max(0, (totalTrackDuration - segmentDuration) / 2);
        segmentStart = Math.round(segmentStart * 10) / 10;
        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    };

    window.setSegmentToEnd = function () {
        console.log('🎯 Установка отрезка в конец');
        segmentStart = Math.max(0, totalTrackDuration - segmentDuration);
        segmentStart = Math.round(segmentStart * 10) / 10;
        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    };

    window.saveSegment = async function () {
        if (!currentEditorTrack) {
            showNotification('Нет активного трека', 'error');
            return;
        }

        try {
            showNotification('💾 Сохраняем отрезок...', 'info');

            const response = await fetch(`${API_BASE}/tracks/${currentEditorTrack}/segment`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_time: Math.round(segmentStart * 10) / 10,
                    duration: Math.round(segmentDuration * 10) / 10
                })
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || err.error || 'Ошибка сохранения');
            }

            const result = await response.json();

            if (result.success) {
                const track = currentTracks.find(t => t.id === currentEditorTrack);
                if (track) {
                    track.segment_start = segmentStart;
                    track.segment_duration = segmentDuration;
                }

                const presTrack = presentationTrackList.find(t => t.id === currentEditorTrack);
                if (presTrack) {
                    presTrack.segment_start = segmentStart;
                    presTrack.segment_duration = segmentDuration;
                }

                await loadTracks();

                if (typeof window.renderTracks === 'function') {
                    window.renderTracks(currentTracks);
                }

                if (typeof window.renderPresentationTracksCompact === 'function') {
                    window.renderPresentationTracksCompact(presentationTrackList);
                }

                if (typeof updatePresentationMiniLibraryStats === 'function') {
                    updatePresentationMiniLibraryStats();
                }

                showNotification('✅ Отрезок сохранен!', 'success');

                setTimeout(() => {
                    closeAudioEditor();
                }, 1000);

            } else {
                throw new Error(result.error || 'Неизвестная ошибка');
            }

        } catch (error) {
            console.error('❌ Ошибка сохранения отрезка:', error);
            showNotification(`❌ Ошибка: ${error.message}`, 'error');
        }
    };

    window.startDrag = function (event, type) {
        isDragging = true;
        dragType = null;
        dragStartX = event.clientX;
        initialSegmentStart = segmentStart;
        initialSegmentDuration = segmentDuration;

        document.addEventListener('mousemove', handleDrag);
        document.addEventListener('mouseup', stopDrag);
        event.preventDefault();
    };

    function handleDrag(event) {
        if (!isDragging) return;

        const container = document.getElementById('waveformContainer');
        if (!container) return;

        const rect = container.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const clickPercent = (clickX / container.offsetWidth);
        const clickTime = clickPercent * totalTrackDuration;

        if (dragType === 'left') {
            const newStart = Math.max(0, Math.min(clickTime, segmentStart + segmentDuration - 5));
            segmentStart = Math.round(newStart * 10) / 10;
            segmentDuration = Math.round((initialSegmentDuration - (newStart - initialSegmentStart)) * 10) / 10;
        } else if (dragType === 'right') {
            const newEnd = Math.max(segmentStart + 5, Math.min(clickTime, totalTrackDuration));
            segmentDuration = Math.round((newEnd - segmentStart) * 10) / 10;
        }

        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();
    }

    function stopDrag() {
        isDragging = false;
        dragType = null;
        document.removeEventListener('mousemove', handleDrag);
        document.removeEventListener('mouseup', stopDrag);

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    }

    window.handleWaveformClick = function (event) {
        console.log('🎯 Клик по waveform');

        if (isDragging || isSegmentDragging) {
            return;
        }

        const container = document.getElementById('waveformContainer');
        if (!container) return;

        const rect = container.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const clickPercent = (clickX / container.offsetWidth);
        const clickTime = clickPercent * totalTrackDuration;

        const maxStart = totalTrackDuration - segmentDuration;
        segmentStart = Math.max(0, Math.min(clickTime, maxStart));
        segmentStart = Math.round(segmentStart * 10) / 10;

        updateTimelineDisplay();
        updateSegmentDisplay();
        updateSegmentMarker();

        if (audioPlayer.currentTrackId === currentEditorTrack) {
            reloadSegmentInPlayer();
        }
    };

    window.changeVolume = function (value) {
        currentVolume = parseInt(value);
        const volumeValueElement = document.getElementById('volumeValue');
        if (volumeValueElement) volumeValueElement.textContent = value + '%';
        audioPlayer.setVolume(currentVolume);
        updateVolumeIcon();
    };

    window.toggleMute = function () {
        isMuted = !isMuted;
        if (audioPlayer.element) audioPlayer.element.muted = isMuted;
        updateVolumeIcon();
    };

    function updateVolumeIcon() {
        const icon = document.getElementById('volumeIcon');
        if (!icon) return;
        if (isMuted) icon.textContent = '🔇';
        else if (currentVolume === 0) icon.textContent = '🔇';
        else if (currentVolume < 30) icon.textContent = '🔈';
        else if (currentVolume < 70) icon.textContent = '🔉';
        else icon.textContent = '🔊';
    }

    window.closeAudioEditor = function () {
        console.log('🚪 Закрытие аудио-редактора');
        audioPlayer.stop();
        const modal = document.getElementById('audioEditorModal');
        modal.style.display = 'none';
        modal.classList.remove('audio-modal-fullscreen');

        document.body.style.overflow = '';

        currentEditorTrack = null;
        isGeneratingWaveform = false;
        isPlaybackSliderDragging = false;
        isSeeking = false;
        pendingSeekPosition = null;
        currentPlaybackPosition = 0;
    };

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

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "<")
            .replace(/>/g, ">")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    window.handleWaveformError = function () {
        const container = document.getElementById('waveformContainer');
        if (container) container.innerHTML = '<div class="waveform-loading">Ошибка загрузки изображения waveform</div>';
        isGeneratingWaveform = false;
    };

    window.initWaveformInteractions = function () {
        updateSegmentMarker();
        const marker = document.getElementById('segmentMarker');
        if (marker) marker.style.display = 'flex';
        isGeneratingWaveform = false;
    };

    window.suggestBestSegment = async function () {
        if (!currentEditorTrack) return;
        try {
            showNotification('🔍 Анализируем аудио...', 'info');
            const response = await fetch(`${API_BASE}/tracks/${currentEditorTrack}/suggest-segment`);
            if (!response.ok) throw new Error('Failed to get suggestion');
            const data = await response.json();
            if (data.success && data.suggested_start !== undefined) {
                segmentStart = Math.round(data.suggested_start * 10) / 10;
                if (data.analysis_details) {
                    showAnalysisResults(data.analysis_details);
                }
                updateTimelineDisplay();
                updateSegmentDisplay();
                updateSegmentMarker();

                if (audioPlayer.currentTrackId === currentEditorTrack) {
                    reloadSegmentInPlayer();
                }

                showNotification(`🎵 Найден отличный отрезок! Начало: ${formatTime(segmentStart)}`, 'success');
            } else {
                throw new Error('Invalid response format');
            }
        } catch (error) {
            console.error('Error getting segment suggestion:', error);
            showNotification('Ошибка анализа аудио', 'error');
        }
    };

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

    window.toggleAnalysis = function () {
        const analysis = document.getElementById('analysisInfo');
        if (analysis.classList.contains('open')) {
            analysis.classList.remove('open');
        } else {
            analysis.classList.add('open');
        }
    };

    // Функция для управления ползунком воспроизведения из HTML
    window.seekAudio = function (value, final = false) {
        console.log('🎵 seekAudio вызван:', { value, final });
        const playbackSlider = document.getElementById('playbackSlider');
        if (!playbackSlider) return;

        playbackSlider.value = value;
        const percent = parseFloat(value);
        const secondIndicator = document.getElementById('secondIndicator');
        if (secondIndicator) {
            secondIndicator.style.left = `${percent}%`;
        }

        const currentTime = (percent / 100) * segmentDuration;
        const timeEl = document.getElementById('playbackTime');
        if (timeEl) {
            timeEl.textContent = formatTime(currentTime);
        }

        if (final) {
            if (typeof window.seekToPosition === 'function') {
                window.seekToPosition(value);
            }
            isPlaybackSliderDragging = false;
            wasPlayingBeforeDrag = false;
        }
    };

    // Экспорт функций
    window.formatTime = formatTime;
    window.escapeHtml = escapeHtml;

    console.log('✅ Аудио-редактор инициализирован');
})();

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
        .replace(/</g, "<")
        .replace(/>/g, ">")
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

// =========================
// TRACK ID MANAGEMENT (FULL IMPLEMENTATION)
// =========================
// Создание модального окна изменения ID (динамически, если ещё не создано)
function ensureChangeIdModalExists() {
    if (document.getElementById('changeIdModal')) return;
    const modalHTML = `
        <div id="changeIdModal" class="modal" style="display:none;">
            <div class="modal-content" style="max-width: 500px; width: 90%;">
                <div class="modal-header">
                    <h3>#️⃣ Изменить ID трека</h3>
                    <span class="close" onclick="closeChangeIdModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <p><strong>Трек:</strong> <span id="changeIdTrackInfo">—</span></p>
                    <div class="form-group" style="margin-top: 16px;">
                        <label for="changeIdNewId">Новый ID:</label>
                        <input type="number" id="changeIdNewId" class="form-input" min="1" placeholder="Введите новый ID" required>
                        <small class="text-muted">Если указать ID другого трека — они поменяются местами</small>
                    </div>
                </div>
                <div class="modal-actions" style="margin-top: 20px; display: flex; gap: 10px;">
                    <button class="btn btn-primary" onclick="changeTrackId()">💾 Сохранить</button>
                    <button class="btn btn-secondary" onclick="closeChangeIdModal()">❌ Отмена</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

// Открытие модального окна изменения ID
function openChangeIdModal(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) {
        showNotification('Трек не найден', 'error');
        return;
    }
    ensureChangeIdModalExists();
    document.getElementById('changeIdCurrentId')?.remove(); // удаляем скрытый input, если был
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.id = 'changeIdCurrentId';
    hiddenInput.value = trackId;
    document.querySelector('#changeIdModal .modal-body').prepend(hiddenInput);
    document.getElementById('changeIdNewId').value = '';
    document.getElementById('changeIdTrackInfo').textContent = `${track.artist} - ${track.title}`;
    document.getElementById('changeIdModal').style.display = 'block';
}

// Закрытие модального окна изменения ID
function closeChangeIdModal() {
    document.getElementById('changeIdModal').style.display = 'none';
}

// Изменение или обмен ID
async function changeTrackId() {
    const currentId = parseInt(document.getElementById('changeIdCurrentId').value);
    const newIdInput = document.getElementById('changeIdNewId').value.trim();
    const newId = parseInt(newIdInput);
    if (!newIdInput || isNaN(newId) || newId < 1) {
        showNotification('Введите корректный ID (целое число ≥ 1)', 'warning');
        return;
    }
    if (newId === currentId) {
        showNotification('Новый ID должен отличаться от текущего', 'warning');
        return;
    }
    try {
        const existingTrack = currentTracks.find(t => t.id === newId);
        if (existingTrack) {
            // Обмен ID
            const confirmed = confirm(
                `ID ${newId} уже занят треком:
` +
                `"${existingTrack.artist} - ${existingTrack.title}"
` +
                `Вы уверены, что хотите поменять их местами?`
            );
            if (!confirmed) return;
            const response = await fetch(`${API_BASE}/tracks/swap-ids`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ track1_id: currentId, track2_id: newId })
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || 'Не удалось поменять ID местами');
            }
            showNotification(`✅ ID ${currentId} и ${newId} успешно поменяны местами`, 'success');
        } else {
            // Простое изменение ID
            const response = await fetch(`${API_BASE}/tracks/${currentId}/change-id`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_id: newId })
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || 'Не удалось изменить ID');
            }
            showNotification(`✅ ID изменён: ${currentId} → ${newId}`, 'success');
        }
        closeChangeIdModal();
        await loadTracks();
    } catch (error) {
        console.error('Ошибка изменения ID:', error);
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    }
}

// Уплотнение ID (compact)
async function compactTrackIds() {
    if (!confirm('Вы уверены?\nВсе ID станут последовательными: 1, 2, 3, ..., N\nЭто действие нельзя отменить.')) {
        return;
    }
    try {
        showNotification('🔄 Уплотнение ID...', 'info');
        const response = await fetch(`${API_BASE}/tracks/compact`, { method: 'POST' });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Ошибка уплотнения');
        }
        const result = await response.json();
        if (result.success) {
            showNotification('✅ ID успешно уплотнены!', 'success');
            await loadTracks();
        } else {
            throw new Error('Неизвестная ошибка');
        }
    } catch (error) {
        console.error('Ошибка уплотнения:', error);
        showNotification(`❌ ${error.message}`, 'error');
    }
}

// Добавление кнопки "Изменить ID" в колонку ID
function enhanceTrackListWithIdEdit() {
    const trackItems = document.querySelectorAll('.track-item .col-id:not(:has(.btn-id-change))');
    trackItems.forEach(col => {
        const idText = col.textContent.trim();
        if (!isNaN(parseInt(idText))) {
            col.textContent = '';
            const idSpan = document.createElement('span');
            idSpan.textContent = idText;
            const btn = document.createElement('button');
            btn.className = 'btn-id-change';
            btn.title = 'Изменить ID';
            btn.textContent = '#️⃣';
            btn.onclick = () => openChangeIdModal(parseInt(idText));
            col.appendChild(idSpan);
            col.appendChild(btn);
        }
    });
}

// Добавление кнопок управления ID в тулбар
function addIdManagementToolbarButtons() {
    const toolbar = document.querySelector('.toolbar');
    if (!toolbar || document.getElementById('compactTrackIdsBtn')) return;
    const buttonsHTML = `
        <div class="toolbar-separator" style="width: 1px; height: 24px; background: var(--border); margin: 0 12px;"></div>
        <button class="btn btn-info" id="compactTrackIdsBtn" onclick="compactTrackIds()" title="Убрать пропуски в нумерации">
            📦 Уплотнить ID
        </button>
    `;
    toolbar.insertAdjacentHTML('beforeend', buttonsHTML);
}

// =========================
// DRAG-AND-DROP REORDERING (WITH PLACEHOLDER & VISUAL FEEDBACK)
// =========================
let draggedItem = null;
let placeholder = null;

function setupDragHandlers() {
    const container = document.getElementById('tracksList');
    if (!container) return;

    const items = container.querySelectorAll('.track-item');
    items.forEach(item => {
        item.setAttribute('draggable', true);

        item.addEventListener('dragstart', (e) => {
            draggedItem = item;
            // Создаём placeholder той же высоты
            placeholder = document.createElement('div');
            placeholder.className = 'track-item placeholder';
            placeholder.style.height = `${item.offsetHeight}px`;

            // Визуальный фидбек
            setTimeout(() => {
                item.classList.add('dragging');
                item.style.display = 'none'; // скрываем оригинал
            }, 0);

            e.dataTransfer.effectAllowed = 'move';
        });

        item.addEventListener('dragend', async () => {
            if (!draggedItem || !container) return;

            // Убираем все временные классы
            container.querySelectorAll('.track-item').forEach(el => {
                el.classList.remove('before-placeholder', 'after-placeholder');
            });

            // Вставляем реальный элемент на место placeholder
            if (placeholder.parentNode) {
                placeholder.replaceWith(draggedItem);
            } else {
                container.appendChild(draggedItem);
            }

            draggedItem.classList.remove('dragging');
            draggedItem.style.display = ''; // показываем обратно
            draggedItem = null;
            placeholder = null;

            // Сохраняем новый порядок
            await saveTrackOrder();
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            if (!draggedItem || !container || item === draggedItem) return;

            const rect = item.getBoundingClientRect();
            const mouseY = e.clientY;
            const midpoint = rect.top + rect.height / 2;

            // Очищаем предыдущие подсказки
            container.querySelectorAll('.track-item').forEach(el => {
                el.classList.remove('before-placeholder', 'after-placeholder');
            });

            // Вставляем placeholder ДО или ПОСЛЕ текущего элемента
            if (mouseY < midpoint) {
                // Вставить ДО
                if (item.previousElementSibling !== placeholder) {
                    item.parentNode.insertBefore(placeholder, item);
                }
                // Подсвечиваем "расхождение"
                item.classList.add('after-placeholder');
                const prev = item.previousElementSibling;
                if (prev && !prev.classList.contains('placeholder')) {
                    prev.classList.add('before-placeholder');
                }
            } else {
                // Вставить ПОСЛЕ
                if (item.nextElementSibling !== placeholder) {
                    item.parentNode.insertBefore(placeholder, item.nextElementSibling);
                }
                item.classList.add('before-placeholder');
                const next = item.nextElementSibling;
                if (next && !next.classList.contains('placeholder')) {
                    next.classList.add('after-placeholder');
                }
            }
        });

        item.addEventListener('dragenter', (e) => {
            e.preventDefault();
        });
    });
}

async function saveTrackOrder() {
    const container = document.getElementById('tracksList');
    if (!container) return;

    // Берём элементы в том порядке, в котором они находятся в DOM
    const items = Array.from(container.children);
    const trackIdsInOrder = items.map(item => parseInt(item.dataset.trackId));

    try {
        const response = await fetch(`${API_BASE}/tracks/reorder-by-ids`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ track_ids: trackIdsInOrder })
        });

        if (!response.ok) throw new Error('Не удалось сохранить порядок');

        showNotification('✅ Порядок треков сохранён и ID уплотнены', 'success');
        await loadTracks(); // обновит список в правильном порядке
    } catch (err) {
        console.error('Ошибка сохранения порядка:', err);
        showNotification('❌ Ошибка сохранения порядка', 'error');
    }
}

// =========================
// YANDEX TOKEN MANAGEMENT FUNCTIONS
// =========================

let yandexTokenStatus = {
    has_token: false,
    is_valid: false,
    message: "Не проверено"
};

// Загрузить статус Яндекс токена
async function loadYandexTokenStatus() {
    try {
        const response = await fetch(`${API_BASE}/yandex/token/status`);
        const data = await response.json();

        if (data.success) {
            yandexTokenStatus = data.status;
            updateYandexTokenDisplay();
        } else {
            console.error('Ошибка загрузки статуса токена:', data.error);
        }
    } catch (error) {
        console.error('Ошибка загрузки статуса Яндекс токена:', error);
    }
}

// Обновить отображение статуса токена
function updateYandexTokenDisplay() {
    const statusElement = document.getElementById('yandexTokenStatus');
    const accountInfoElement = document.getElementById('yandexAccountInfo');
    const manageSection = document.getElementById('yandexTokenManage');
    const formSection = document.getElementById('yandexTokenForm');

    if (!statusElement) return;

    let statusHTML = '';
    let accountHTML = '';

    if (yandexTokenStatus.has_token) {
        if (yandexTokenStatus.is_valid) {
            statusHTML = `
                <div class="token-status valid">
                    <span class="status-icon">✅</span>
                    <span class="status-text">${yandexTokenStatus.message}</span>
                </div>
            `;

            if (yandexTokenStatus.account_info) {
                accountHTML = `
                    <div class="account-info">
                        <div class="info-item">
                            <span class="label">Логин:</span>
                            <span class="value">${yandexTokenStatus.account_info.login || 'Неизвестно'}</span>
                        </div>
                        <div class="info-item">
                            <span class="label">UID:</span>
                            <span class="value">${yandexTokenStatus.account_info.uid || 'Неизвестно'}</span>
                        </div>
                    </div>
                `;
            }
        } else {
            statusHTML = `
                <div class="token-status invalid">
                    <span class="status-icon">❌</span>
                    <span class="status-text">${yandexTokenStatus.message}</span>
                </div>
            `;
        }
    } else {
        statusHTML = `
            <div class="token-status missing">
                <span class="status-icon">⚠️</span>
                <span class="status-text">${yandexTokenStatus.message}</span>
            </div>
        `;
    }

    statusElement.innerHTML = statusHTML;

    if (accountInfoElement) {
        accountInfoElement.innerHTML = accountHTML;
    }

    // Показываем/скрываем секции в зависимости от наличия токена
    if (manageSection) {
        manageSection.style.display = yandexTokenStatus.has_token ? 'block' : 'none';
    }
    if (formSection) {
        formSection.style.display = yandexTokenStatus.has_token ? 'none' : 'block';
    }
}

// Сохранить Яндекс токен
async function saveYandexToken() {
    const tokenInput = document.getElementById('yandexTokenInput');
    if (!tokenInput) return;

    const token = tokenInput.value.trim();
    if (!token) {
        showNotification('Введите Яндекс токен', 'warning');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/yandex/token/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
        });

        const data = await response.json();

        if (data.success) {
            showNotification(data.message, 'success');
            tokenInput.value = '';
            // Обновляем статус
            await loadYandexTokenStatus();
        } else {
            showNotification(`❌ ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Ошибка сохранения Яндекс токена:', error);
        showNotification('❌ Ошибка сохранения токена', 'error');
    }
}

// Удалить Яндекс токен
async function deleteYandexToken() {
    if (!confirm('Вы уверены, что хотите удалить Яндекс токен?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/yandex/token/delete`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            showNotification(data.message, 'success');
            // Обновляем статус
            await loadYandexTokenStatus();
        } else {
            showNotification(`❌ ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Ошибка удаления Яндекс токена:', error);
        showNotification('❌ Ошибка удаления токена', 'error');
    }
}

// Показать/скрыть форму ввода токена
function toggleTokenForm() {
    const form = document.getElementById('yandexTokenForm');
    const manage = document.getElementById('yandexTokenManage');

    if (form && manage) {
        if (form.style.display === 'none') {
            form.style.display = 'block';
            manage.style.display = 'none';
        } else {
            form.style.display = 'none';
            manage.style.display = 'block';
        }
    }
}

// Показать информацию о получении токена
function showTokenHelp() {
    const helpText = `
🎵 Как получить Яндекс токен:

1. Откройте Яндекс.Музыку в браузере
2. Нажмите F12 → вкладка "Network" (Сеть)
3. Обновите страницу (F5)
4. Найдите запросы к api.music.yandex.net
5. В заголовках запроса найдите "Authorization"
6. Скопируйте токен (после слова "OAuth")

📝 Пример:
Authorization: OAuth y0_AgAAAABv6Kb3AAABcQAAAAECbS4YAAd7vVKb3Y63eSEXAmAbC5SfQ

⚠️ Внимание:
• Никому не передавайте свой токен
• Токен дает доступ к вашему аккаунту
• Сохраняйте токен в безопасном месте
    `;

    alert(helpText);
}

// Добавляем HTML секцию Яндекс токена в интерфейс
function addYandexTokenSection() {
    const statusTab = document.getElementById('status');
    if (!statusTab) return;

    // Проверяем, не добавлена ли уже секция
    if (document.getElementById('yandexTokenSection')) return;

    const yandexTokenHTML = `
        <div class="yandex-token-section" id="yandexTokenSection">
            <div class="generator-card">
                <h2>🎵 Яндекс.Музыка Токен</h2>
                <p class="subtitle">Управление токеном для доступа к Яндекс.Музыке</p>
                
                <div class="token-status-card">
                    <h4>📊 Статус токена:</h4>
                    <div id="yandexTokenStatus" class="token-status-container">
                        <div class="token-status loading">
                            <span class="status-icon">🔄</span>
                            <span class="status-text">Загрузка...</span>
                        </div>
                    </div>
                    <div id="yandexAccountInfo" class="account-info-container"></div>
                </div>
                
                <div class="token-form-section" id="yandexTokenForm" style="display: none;">
                    <div class="form-group">
                        <label for="yandexTokenInput">Токен Яндекс.Музыки:</label>
                        <input type="password" id="yandexTokenInput" class="form-input" 
                               placeholder="OAuth y0_AgAAAABv6Kb3AAABcQAAAAECbS4YAAd7vVKb3Y63eSEXAmAbC5SfQ">
                        <small class="text-muted">
                            🔒 Токен сохраняется локально и используется только для скачивания треков
                        </small>
                    </div>
                    <div class="form-actions">
                        <button class="btn btn-primary" onclick="saveYandexToken()">
                            💾 Сохранить токен
                        </button>
                        <button class="btn btn-secondary" onclick="showTokenHelp()">
                            ❓ Как получить токен?
                        </button>
                    </div>
                </div>
                
                <div class="token-management" id="yandexTokenManage" style="display: none;">
                    <div class="management-actions">
                        <button class="btn btn-warning" onclick="toggleTokenForm()">
                            🔄 Изменить токен
                        </button>
                        <button class="btn btn-danger" onclick="deleteYandexToken()">
                            🗑️ Удалить токен
                        </button>
                        <button class="btn btn-secondary" onclick="showTokenHelp()">
                            ❓ Помощь
                        </button>
                    </div>
                </div>
                
                
            </div>
        </div>
    `;

    // Вставляем после основного контента статуса
    const statusContent = statusTab.querySelector('.generator-card');
    if (statusContent) {
        statusContent.insertAdjacentHTML('afterend', yandexTokenHTML);
    } else {
        statusTab.innerHTML += yandexTokenHTML;
    }

    // Загружаем статус токена
    loadYandexTokenStatus();
}
// Функция для обновления всех статистик
async function updateAllStats() {
    try {
        // Обновляем счетчик треков
        await updateTracksCount();

        // Обновляем глобальную статистику через track_view_manager
        if (window.trackViewManager && typeof window.trackViewManager.updateGlobalStats === 'function') {
            window.trackViewManager.updateGlobalStats();
        }

        // Обновляем статистику презентации - ТОЛЬКО ЕСЛИ ЕСТЬ ТРЕКИ В СПИСКЕ
        if (window.trackViewManager && typeof window.trackViewManager.updatePresentationFilterStats === 'function') {
            // Проверяем, есть ли треки в списке презентаций
            const hasPresentationTracks = window.trackViewManager.getPresentationList &&
                window.trackViewManager.getPresentationList() &&
                window.trackViewManager.getPresentationList().length > 0;

            if (hasPresentationTracks) {
                window.trackViewManager.updatePresentationFilterStats();
            }
        }

        // Если активна вкладка презентации, обновляем фильтры - ТОЛЬКО ЕСЛИ ЕСТЬ ТРЕКИ
        const presentationTab = document.getElementById('presentation');
        if (presentationTab && presentationTab.classList.contains('active')) {
            if (window.trackViewManager && typeof window.trackViewManager.applyPresentationFilters === 'function') {
                // Проверяем, есть ли треки в списке
                const hasPresentationTracks = window.trackViewManager.getPresentationList &&
                    window.trackViewManager.getPresentationList() &&
                    window.trackViewManager.getPresentationList().length > 0;

                if (hasPresentationTracks) {
                    window.trackViewManager.applyPresentationFilters();
                }
            }
        }

    } catch (error) {
        console.error('Ошибка обновления статистики:', error);
    }
}
// =========================
// ROUNDS CONFIGURATION (НОВЫЙ БЛОК)
// =========================

let roundsConfig = {
    count: 1,
    tracksPerRound: [40] // По умолчанию: 1 раунд, 40 треков
};

// Инициализация управления раундами
function initRoundsControls() {
    const roundsCountSlider = document.getElementById('roundsCountSlider');
    const roundsCountInput = document.getElementById('roundsCount');
    const roundsCountText = document.getElementById('roundsCountText');

    if (!roundsCountSlider || !roundsCountInput) return;

    // Обработчик слайдера
    roundsCountSlider.addEventListener('input', function () {
        const value = parseInt(this.value);
        roundsCountInput.value = value;
        updateRoundsCount(value);
    });

    // Обработчик числового поля
    roundsCountInput.addEventListener('change', function () {
        let value = parseInt(this.value);
        if (value < 1) value = 1;
        if (value > 3) value = 3;
        this.value = value;
        roundsCountSlider.value = value;
        updateRoundsCount(value);
    });

    // Инициализация конфигурации треков для каждого раунда
    updateRoundsUI();
    updateRoundsSummary();
}

// Обновление количества раундов
function updateRoundsCount(count) {
    roundsConfig.count = count;

    // Обновляем текстовое отображение
    const roundsCountText = document.getElementById('roundsCountText');
    if (roundsCountText) {
        roundsCountText.textContent = count === 1 ? '1 раунд' : `${count} раунда`;
    }

    // Обновляем интерфейс настройки треков для раундов
    updateRoundsUI();
    updateRoundsSummary();
    updateGenerateButtonState();
}

// Обновление UI для настройки треков по раундам
function updateRoundsUI() {
    const container = document.getElementById('roundsTracksContainer');
    if (!container) return;

    let html = '';

    for (let i = 1; i <= roundsConfig.count; i++) {
        // Получаем текущее значение треков для этого раунда
        const currentTracks = roundsConfig.tracksPerRound[i - 1] || (i === 1 ? 40 : 0);

        // Определяем диапазон слайдов
        let slideRange = '';
        if (i === 1) slideRange = '5-44';
        else if (i === 2) slideRange = '48-87';
        else if (i === 3) slideRange = '91-130';

        html += `
            <div style="background: var(--bg-card); padding: 10px; border-radius: 6px; border: 1px solid var(--border); margin-bottom: 10px;">
                <h4 style="margin-top: 0; margin-bottom: 10px;">Раунд ${i}:</h4>
                <div>
                    <label style="display: block; margin-bottom: 5px;">Количество треков:</label>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <input type="range" class="roundTracksSlider" data-round="${i}" min="1" max="40" value="${currentTracks}" style="flex: 1; height: 6px;">
                        <input type="number" class="roundTracksInput" data-round="${i}" min="1" max="40" value="${currentTracks}" style="width: 80px; padding: 5px;">
                        <span class="roundTracksBadge" data-round="${i}" style="background: ${currentTracks > 0 ? 'var(--success)' : 'var(--warning)'}; color: white; padding: 2px 10px; border-radius: 12px; font-size: 14px;">${currentTracks}</span>
                    </div>
                    <small style="color: var(--text-muted); font-size: 12px;">Слайды: ${slideRange}</small>
                </div>
            </div>
        `;
    }

    container.innerHTML = html;

    // Добавляем обработчики для новых элементов
    document.querySelectorAll('.roundTracksSlider').forEach(slider => {
        slider.addEventListener('input', function () {
            const roundNum = parseInt(this.dataset.round);
            const value = parseInt(this.value);
            updateRoundTracks(roundNum, value);
        });
    });

    document.querySelectorAll('.roundTracksInput').forEach(input => {
        input.addEventListener('change', function () {
            const roundNum = parseInt(this.dataset.round);
            let value = parseInt(this.value);
            if (value < 1) value = 1;
            if (value > 40) value = 40;
            this.value = value;
            updateRoundTracks(roundNum, value);
        });
    });
}

// Обновление количества треков в раунде
function updateRoundTracks(roundNum, tracks) {
    // Обновляем массив конфигурации
    if (!roundsConfig.tracksPerRound[roundNum - 1]) {
        roundsConfig.tracksPerRound[roundNum - 1] = tracks;
    } else {
        roundsConfig.tracksPerRound[roundNum - 1] = tracks;
    }

    // Обновляем связанные элементы
    const slider = document.querySelector(`.roundTracksSlider[data-round="${roundNum}"]`);
    const input = document.querySelector(`.roundTracksInput[data-round="${roundNum}"]`);
    const badge = document.querySelector(`.roundTracksBadge[data-round="${roundNum}"]`);

    if (slider) slider.value = tracks;
    if (input) input.value = tracks;
    if (badge) {
        badge.textContent = tracks;
        badge.style.background = tracks > 0 ? 'var(--success)' : 'var(--warning)';
    }

    updateRoundsSummary();
    updateGenerateButtonState();
}

// Обновление сводки по раундам
function updateRoundsSummary() {
    const summaryElement = document.getElementById('roundsSummaryContent');
    const totalTracksNeededElement = document.getElementById('totalTracksNeeded');
    const availableTracksElement = document.getElementById('availableTracksInList');

    if (!summaryElement) return;

    // Вычисляем общее количество нужных треков
    let totalTracksNeeded = 0;
    let summaryHTML = '';

    for (let i = 1; i <= 3; i++) {
        const tracksInRound = roundsConfig.tracksPerRound[i - 1] || 0;
        let slideRange = '';

        if (i === 1) slideRange = '5-44';
        else if (i === 2) slideRange = '48-87';
        else if (i === 3) slideRange = '91-130';

        const isActive = i <= roundsConfig.count;
        const tracksText = isActive ? `<strong>${tracksInRound} треков</strong>` : '<em>отключен</em>';

        summaryHTML += `<div>Раунд ${i}: ${tracksText} (слайды ${slideRange})</div>`;

        if (isActive) {
            totalTracksNeeded += tracksInRound;
        }
    }

    // Обновляем элементы
    summaryElement.innerHTML = summaryHTML;

    if (totalTracksNeededElement) {
        totalTracksNeededElement.textContent = totalTracksNeeded;
    }

    if (availableTracksElement) {
        const trackListText = document.getElementById('presentationTrackList').value.trim();
        const tracksInList = trackListText ? trackListText.split('\n').filter(l => l.trim()).length : 0;
        availableTracksElement.textContent = tracksInList;

        // Подсвечиваем цветом
        if (availableTracksElement.parentElement) {
            if (tracksInList >= totalTracksNeeded) {
                availableTracksElement.parentElement.style.color = 'var(--success)';
            } else {
                availableTracksElement.parentElement.style.color = 'var(--error)';
            }
        }
    }

    // Обновляем кнопку генерации
    updateGenerateButtonState();
}

// Обновление состояния кнопки генерации (модифицированная)
function updateGenerateButtonState() {
    const generateBtn = document.getElementById('generatePresentationBtn');
    if (!generateBtn) return;

    // Вычисляем общее количество нужных треков
    const totalTracksNeeded = roundsConfig.tracksPerRound.slice(0, roundsConfig.count).reduce((a, b) => a + b, 0);

    const trackListText = document.getElementById('presentationTrackList').value.trim();
    const tracksInList = trackListText ? trackListText.split('\n').filter(l => l.trim()).length : 0;

    const hasEnoughTracks = tracksInList >= totalTracksNeeded;
    const hasTitle = document.getElementById('presentation-title')?.value.trim().length > 0;

    generateBtn.disabled = !hasEnoughTracks || !hasTitle;

    if (!hasEnoughTracks) {
        const missing = totalTracksNeeded - tracksInList;
        generateBtn.title = `Нужно еще ${missing} треков (в списке: ${tracksInList})`;
    } else if (!hasTitle) {
        generateBtn.title = 'Введите название презентации';
    } else {
        generateBtn.title = `Сгенерировать презентацию с ${roundsConfig.count} раундами`;
    }
}

// Модифицированная функция генерации презентации (полностью совместимая)
async function generatePresentation() {
    const status = document.getElementById("presentation-status");
    const titleInput = document.getElementById("presentation-title");
    const title = titleInput ? titleInput.value.trim() : "";
    const makeBWCheckbox = document.getElementById("make-bw");
    const makeBW = !!(makeBWCheckbox && makeBWCheckbox.checked);

    if (!title) {
        if (status) {
            status.textContent = "⚠️ Пожалуйста, введите название презентации.";
            status.style.color = "#f87171";
        } else {
            showNotification("⚠️ Пожалуйста, введите название презентации.", "warning");
        }
        return;
    }

    // Проверяем что в списке достаточно треков
    const totalTracksNeeded = roundsConfig.tracksPerRound.slice(0, roundsConfig.count).reduce((a, b) => a + b, 0);
    const trackListText = document.getElementById('presentationTrackList').value.trim();
    const tracksInList = trackListText ? trackListText.split('\n').filter(l => l.trim()).length : 0;

    if (tracksInList < totalTracksNeeded) {
        const missing = totalTracksNeeded - tracksInList;
        showNotification(`Недостаточно треков в списке: нужно еще ${missing}`, 'error');
        return;
    }

    const generateBtn = document.getElementById('generatePresentationBtn');
    const originalText = generateBtn.innerHTML;

    try {
        updatePresentationProgress(0, 1, 'Подготовка...');

        if (status) {
            status.textContent = "⏳ Генерация презентации...";
            status.style.color = "#9ca3af";
        }

        generateBtn.disabled = true;
        generateBtn.innerHTML = "⏳ Генерация...";

        // Используем существующий presentationTrackList
        if (presentationTrackList.length === 0) {
            if (status) {
                status.textContent = "⚠️ Нет валидных треков для генерации";
                status.style.color = "#f87171";
            } else {
                showNotification("⚠️ Нет валидных треков для генерации", "warning");
            }
            return;
        }

        // Берем только нужное количество треков
        const tracksForPresentation = presentationTrackList.slice(0, totalTracksNeeded);

        // Подготавливаем конфигурацию раундов
        const roundsConfigForApi = [];
        for (let i = 0; i < roundsConfig.count; i++) {
            roundsConfigForApi.push(roundsConfig.tracksPerRound[i] || 0);
        }

        const payload = {
            title,
            design: { make_bw: makeBW },
            tracks: tracksForPresentation,
            rounds_config: roundsConfigForApi,
            rounds_count: roundsConfig.count
        };

        console.log("📤 Отправляем запрос на генерацию:", payload);

        const response = await fetch(`${API_BASE}/generate/presentation`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        console.log("📥 Ответ от сервера:", data);

        if (response.ok && data.success) {
            updatePresentationProgress(1, 1, '✅ Завершено');

            if (status) {
                status.innerHTML = `✅ Презентация успешно создана!<br>
                <a href="${data.download_url}" class="download-link" download>
                    📥 Скачать презентацию
                </a>`;
                status.style.color = "#34d399";
            }

            showNotification(`✅ Презентация с ${roundsConfig.count} раундами успешно создана!`, 'success');

            // Автоматическое скачивание
            if (data.download_url) {
                setTimeout(() => {
                    const downloadLink = document.createElement('a');
                    downloadLink.href = data.download_url;
                    downloadLink.download = data.filename || 'presentation.pptx';
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    document.body.removeChild(downloadLink);
                }, 1000);
            }

        } else {
            updatePresentationProgress(0, 1, '❌ Ошибка');
            const errorMsg = data.detail || data.message || "Не удалось создать презентацию";

            if (status) {
                status.textContent = "❌ Ошибка: " + errorMsg;
                status.style.color = "#f87171";
            } else {
                showNotification('❌ ' + errorMsg, 'error');
            }
        }
    } catch (error) {
        console.error("❌ Ошибка при генерации презентации:", error);
        updatePresentationProgress(0, 1, '❌ Ошибка соединения');

        if (status) {
            status.textContent = "❌ Ошибка соединения с сервером.";
            status.style.color = "#f87171";
        } else {
            showNotification('❌ Ошибка соединения с сервером', 'error');
        }
    } finally {
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.innerHTML = originalText;
        }
    }
}

// Добавляем вызов инициализации в существующий код
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();

    // Инициализируем управление раундами (НОВОЕ)
    initRoundsControls();

    // Инициализация менеджера представления с задержкой
    setTimeout(function () {
        if (typeof initTrackViewManager === 'function') {
            initTrackViewManager();
        } else if (window.trackViewManager && typeof window.trackViewManager.initTrackViewManager === 'function') {
            window.trackViewManager.initTrackViewManager();
        }
    }, 1000);

    setInterval(updateTracksCount, 10000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateTracksCount();
    });
});

// Обновляем функцию валидации списка треков для учета раундов
async function validatePresentationTrackList() {
    const trackListText = document.getElementById('presentationTrackList').value;
    const tracks = parsePresentationTrackList(trackListText);
    const missingListEl = document.getElementById('missingTracksList');

    if (tracks.length === 0) {
        missingListEl.style.display = 'none';
        presentationTrackList = [];
        renderPresentationTracksCompact([]);
        updateRoundsSummary(); // Обновляем сводку по раундам
        return;
    }

    const missing = [];
    const valid = [];

    for (const t of tracks) {
        const found = currentTracks.find(tr =>
            normalizeTrackString(tr.artist) === normalizeTrackString(t.artist) &&
            normalizeTrackString(tr.title) === normalizeTrackString(t.title)
        );
        if (found) {
            valid.push({
                ...found,
                original_line: t.original_line
            });
        } else {
            missing.push(`${t.artist} - ${t.title}`);
        }
    }

    presentationTrackList = valid;
    window.presentationTrackList = valid;

    if (missing.length > 0) {
        missingListEl.textContent = missing.join('\n');
        missingListEl.style.display = 'block';
    } else {
        missingListEl.style.display = 'none';
    }

    renderPresentationTracksCompact(valid);
    updateRoundsSummary(); // Обновляем сводку по раундам

    // Обновляем статистику отдельно с небольшой задержкой
    setTimeout(() => {
        if (typeof updatePresentationMiniLibraryStats === 'function') {
            updatePresentationMiniLibraryStats();
        }
    }, 100);
}

// Добавляем обработчик для поля названия
const titleInput = document.getElementById('presentation-title');
if (titleInput) {
    titleInput.addEventListener('input', updateGenerateButtonState);
}
// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();

    // Инициализация менеджера представления с задержкой
    setTimeout(function () {
        if (typeof initTrackViewManager === 'function') {
            initTrackViewManager();
        } else if (window.trackViewManager && typeof window.trackViewManager.initTrackViewManager === 'function') {
            window.trackViewManager.initTrackViewManager();
        }
    }, 1000);

    // Обновляем статистику каждые 10 секунд
    setInterval(updateAllStats, 10000);

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateAllStats();
    });
});

// Экспорт в глобальную область
window.saveYandexToken = saveYandexToken;
window.deleteYandexToken = deleteYandexToken;
window.toggleTokenForm = toggleTokenForm;
window.showTokenHelp = showTokenHelp;
window.loadYandexTokenStatus = loadYandexTokenStatus;

// Экспорт функций управления отображением
window.toggleViewMode = toggleViewMode;
window.startInlineEdit = startInlineEdit;

console.log('🎵 Music Loto Maker frontend загружен!');