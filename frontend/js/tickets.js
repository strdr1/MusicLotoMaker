// static/js/tickets.js - Полная версия с прогрессом, WebSocket, кастомным списком треков и выбором раундов
const API_BASE_URL = '/api';
let allTracks = [];
let ticketsTrackList = []; // ← Новый список треков для билетов
let autoRefreshInterval = null;
let progressWebSocket = null;
let selectedRounds = 3; // По умолчанию 3 раунда

/** Подключение к WebSocket для прогресса */
function connectProgressWebSocket() {
    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/tickets/progress`;

        progressWebSocket = new WebSocket(wsUrl);

        progressWebSocket.onopen = () => {
            console.log('✅ WebSocket подключен для отслеживания прогресса');
            updateWebSocketStatus(true);
        };

        progressWebSocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'progress') {
                    updateProgressBar(data.current, data.total, data.message);
                    console.log(`📊 Прогресс: ${data.current}/${data.total} - ${data.message}`);

                    const progressPercent = document.getElementById('progressPercent');
                    if (progressPercent) {
                        progressPercent.textContent = `${data.percent}%`;
                    }

                    const totalTickets = document.getElementById('totalTickets');
                    if (totalTickets) {
                        totalTickets.textContent = data.total;
                    }

                    const progressDetails = document.getElementById('progressDetails');
                    if (progressDetails) {
                        progressDetails.textContent = data.message;
                        progressDetails.className = `progress-detail-item stage-${getProgressStage(data.message)}`;
                    }
                }
            } catch (err) {
                console.error('❌ Ошибка парсинга WebSocket сообщения:', err);
            }
        };

        progressWebSocket.onclose = () => {
            console.log('❌ WebSocket отключен, переподключение через 5 секунд...');
            updateWebSocketStatus(false);
            setTimeout(connectProgressWebSocket, 5000);
        };

        progressWebSocket.onerror = (error) => {
            console.error('❌ WebSocket ошибка:', error);
            updateWebSocketStatus(false);
        };

    } catch (err) {
        console.error('❌ Ошибка подключения WebSocket:', err);
        updateWebSocketStatus(false);
    }
}

/** Обновление статуса WebSocket */
function updateWebSocketStatus(connected) {
    let statusEl = document.getElementById('websocketStatus');
    if (!statusEl) {
        statusEl = document.createElement('div');
        statusEl.id = 'websocketStatus';
        statusEl.className = 'websocket-status';
        document.body.appendChild(statusEl);
    }

    if (connected) {
        statusEl.className = 'websocket-status websocket-connected';
        statusEl.innerHTML = '🔗 WebSocket подключен';
    } else {
        statusEl.className = 'websocket-status websocket-disconnected';
        statusEl.innerHTML = '🔌 WebSocket отключен';
    }
}

/** Определение стадии прогресса по сообщению */
function getProgressStage(message) {
    if (message.includes('Подготовка')) return 'preparing';
    if (message.includes('Генерация билета')) return 'generating';
    if (message.includes('Объединение')) return 'merging';
    if (message.includes('ZIP')) return 'archiving';
    if (message.includes('завершена') || message.includes('✅')) return 'completed';
    if (message.includes('Ошибка') || message.includes('❌')) return 'error';
    return 'generating';
}

/** Универсальный парсинг ответа с треками */
function parseTracksResponse(data) {
    if (!data) return [];

    if (Array.isArray(data)) {
        return data.map(track => ({
            id: track.id || track.track_id || Math.random().toString(36),
            title: track.title || track.name || 'Без названия',
            artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
        }));
    }

    if (typeof data === 'object') {
        if (Array.isArray(data.tracks)) {
            return data.tracks.map(track => ({
                id: track.id || track.track_id || Math.random().toString(36),
                title: track.title || track.name || 'Без названия',
                artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
            }));
        }

        if (Array.isArray(data.data)) {
            return data.data.map(track => ({
                id: track.id || track.track_id || Math.random().toString(36),
                title: track.title || track.name || 'Без названия',
                artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
            }));
        }

        for (const key in data) {
            if (Array.isArray(data[key]) && data[key].length > 0) {
                const firstItem = data[key][0];
                if (firstItem && (firstItem.title || firstItem.artist || firstItem.name)) {
                    return data[key].map(track => ({
                        id: track.id || track.track_id || Math.random().toString(36),
                        title: track.title || track.name || 'Без названия',
                        artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
                    }));
                }
            }
        }
    }

    console.warn('⚠️ Неизвестный формат данных треков:', data);
    return [];
}

/** Загрузка треков для билетов */
async function loadTracksForTickets(forceRefresh = false) {
    try {
        const timestamp = Date.now();
        const tracksResp = await fetch(`/api/tracks?t=${timestamp}&force=${forceRefresh}`, {
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });

        if (!tracksResp.ok) throw new Error(`HTTP ${tracksResp.status}`);
        const tracksData = await tracksResp.json();
        allTracks = parseTracksResponse(tracksData);
        console.log(`✅ Загружено треков: ${allTracks.length}`);

        if (allTracks.length === 0) await tryAlternativeTrackLoading();
        updateProgressStats();

    } catch (err) {
        console.error('❌ Ошибка загрузки треков:', err);
        await tryAlternativeTrackLoading();
        updateProgressStats();
        showNotification(`❌ Ошибка загрузки треков: ${err.message}`, 'error');
    }
}

/** Альтернативные методы загрузки треков */
async function tryAlternativeTrackLoading() {
    const endpoints = [
        '/api/tracks/list',
        '/api/tracks/all',
        '/api/media/tracks',
        '/api/library/tracks'
    ];

    for (const endpoint of endpoints) {
        try {
            const resp = await fetch(endpoint);
            if (resp.ok) {
                const data = await resp.json();
                const tracks = parseTracksResponse(data);
                if (tracks.length > 0) {
                    allTracks = tracks;
                    return;
                }
            }
        } catch (e) {
            console.log(`❌ Эндпоинт ${endpoint} не доступен:`, e.message);
        }
    }

    const statusResp = await fetch('/api/tickets/status');
    if (statusResp.ok) {
        const status = await statusResp.json();
        if (status.tracks_count > 0) {
            allTracks = Array.from({ length: status.tracks_count }, (_, i) => ({
                id: `track-${i + 1}`,
                title: `Трек ${i + 1}`,
                artist: 'Исполнитель'
            }));
        }
    }
}

/** Обновление статистики */
function updateProgressStats() {
    const actualTracks = ticketsTrackList.length > 0 ? ticketsTrackList : allTracks;
    const actualCount = actualTracks ? actualTracks.length : 0;

    const countEl = document.getElementById('tracksCount');
    const statusEl = document.getElementById('generationStatus');

    if (countEl) countEl.textContent = actualCount;

    if (statusEl) {
        if (actualCount === 0) {
            statusEl.textContent = '❌ Нет треков';
            statusEl.style.color = '#ef4444';
        } else if (actualCount < 36) {
            statusEl.textContent = `⚠️ Недостаточно треков (${actualCount}/36)`;
            statusEl.style.color = '#f59e0b';
        } else {
            statusEl.textContent = `✅ Готов к генерации (${actualCount} треков)`;
            statusEl.style.color = '#10b981';
        }
    }

    const generateBtn = document.getElementById('generateTicketsBtn');
    if (generateBtn) {
        generateBtn.disabled = actualCount < 36;
    }
}

/** Показать уведомление */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        z-index: 10000;
        max-width: 400px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
        transform: translateX(100%);
        opacity: 0;
        background: ${type === 'success' ? 'linear-gradient(135deg, #10b981, #059669)' :
            type === 'error' ? 'linear-gradient(135deg, #ef4444, #dc2626)' :
                type === 'warning' ? 'linear-gradient(135deg, #f59e0b, #d97706)' :
                    'linear-gradient(135deg, #3b82f6, #2563eb)'};
    `;

    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
        notification.style.opacity = '1';
    }, 100);

    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        notification.style.opacity = '0';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 4000);
}

/** Обновление прогресс-бара */
function updateProgressBar(current, total, message = '') {
    const progressBar = document.getElementById('generationProgress');
    const progressText = document.getElementById('progressText');
    const currentTicketEl = document.getElementById('currentTicket');
    const totalTicketsEl = document.getElementById('totalTickets');
    const progressPercentEl = document.getElementById('progressPercent');

    if (progressBar) {
        const percent = total > 0 ? Math.round((current / total) * 100) : 0;
        progressBar.style.width = `${percent}%`;
        progressBar.textContent = `${percent}%`;

        if (percent < 30) {
            progressBar.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
        } else if (percent < 70) {
            progressBar.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
        } else {
            progressBar.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        }
    }

    if (progressText) progressText.textContent = message || `Генерация: ${current}/${total}`;
    if (currentTicketEl) currentTicketEl.textContent = current > 0 ? current : '-';
    if (totalTicketsEl) totalTicketsEl.textContent = total > 0 ? total : '-';
    if (progressPercentEl) {
        const percent = total > 0 ? Math.round((current / total) * 100) : 0;
        progressPercentEl.textContent = `${percent}%`;
    }

    const progressSection = document.getElementById('progressSection');
    if (progressSection) {
        if (current === 0 && total === 0) {
            progressSection.style.display = 'none';
        } else {
            progressSection.style.display = 'block';
        }
    }
}

// === ФУНКЦИИ ДЛЯ КАСТОМНОГО СПИСКА ТРЕКОВ ===

function normalizeTrackString(str) {
    return str.toLowerCase().replace(/[^\wа-яё]/g, '');
}

function parseTicketsTrackList(trackListText) {
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
        for (let sep of separators) {
            if (line.includes(sep)) {
                const parts = line.split(sep, 2);
                artist = parts[0].trim();
                title = parts[1].trim();
                return { artist, title };
            }
        }
        artist = 'Неизвестный исполнитель';
        title = line;
        tracks.push({ artist, title });
    }
    return tracks;
}

async function validateTicketsTrackList() {
    const text = document.getElementById('ticketsTrackList')?.value || '';
    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
    const el = document.getElementById('ticketsTrackValidation');

    if (!lines.length) {
        if (el) el.style.display = 'none';
        ticketsTrackList = [];
        updateProgressStats();
        return;
    }

    const results = [];
    const valid = [];

    for (const line of lines) {
        let cleanLine = line
            .replace(/^\d+\.\s*/, '')
            .replace(/^\d+\)\s*/, '')
            .replace(/^[-•*]\s*/, '')
            .trim();

        let artist = '', title = '';
        const separators = [' - ', ' – ', ' — '];
        let foundSep = false;
        for (let sep of separators) {
            if (cleanLine.includes(sep)) {
                const parts = cleanLine.split(sep, 2);
                artist = parts[0].trim();
                title = parts[1].trim();
                foundSep = true;
                break;
            }
        }
        if (!foundSep) {
            artist = 'Неизвестный исполнитель';
            title = cleanLine;
        }

        const found = allTracks.find(t =>
            normalizeTrackString(t.artist) === normalizeTrackString(artist) &&
            normalizeTrackString(t.title) === normalizeTrackString(title)
        );

        results.push({ original: line, artist, title, found: !!found });
        if (found) valid.push(found);
    }

    let html = '<div class="validation-items">';
    results.forEach(r => {
        const cls = r.found ? 'valid-item' : 'invalid-item';
        const icon = r.found ? '✅' : '❌';
        html += `<div class="validation-item ${cls}">${icon} ${r.original}</div>`;
    });
    html += '</div>';

    if (el) {
        el.innerHTML = html;
        el.style.display = 'block';
    }

    ticketsTrackList = valid;
    updateProgressStats();
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

function clearTicketsTrackList() {
    const el = document.getElementById('ticketsTrackList');
    if (el) el.value = '';
    const val = document.getElementById('ticketsTrackValidation');
    if (val) val.style.display = 'none';
    ticketsTrackList = [];
    updateProgressStats();
}

function loadAllTracksToTicketsList() {
    if (!allTracks || allTracks.length === 0) {
        showNotification('Медиатека пуста', 'warning');
        return;
    }
    const list = allTracks.map(t => `${t.artist} - ${t.title}`).join('\n');
    const el = document.getElementById('ticketsTrackList');
    if (el) el.value = list;
    setTimeout(validateTicketsTrackList, 100);
}

// === ФУНКЦИИ ВЫБОРА РАУНДОВ ===

function updateRoundsSelection() {
    const rounds3 = document.getElementById('rounds3');
    const rounds2 = document.getElementById('rounds2');
    const currentRulesFile = document.getElementById('currentRulesFile');
    const downloadRoundsCount = document.getElementById('downloadRoundsCount');

    if (rounds3 && rounds3.checked) {
        selectedRounds = 3;
        if (currentRulesFile) currentRulesFile.textContent = 'tickerts_rule.png';
        if (downloadRoundsCount) downloadRoundsCount.textContent = '3';
    } else if (rounds2 && rounds2.checked) {
        selectedRounds = 2;
        if (currentRulesFile) currentRulesFile.textContent = 'tickerts_rule_2.png';
        if (downloadRoundsCount) downloadRoundsCount.textContent = '2';
    }

    console.log(`✅ Выбрано раундов: ${selectedRounds}`);
}

// === ОСНОВНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ ===

/** Генерация билетов с прогресс-баром */
async function generateTickets() {
    const count = parseInt(document.getElementById('ticketsCount')?.value || '10', 10);
    if (isNaN(count) || count < 1 || count > 100) {
        showNotification('Количество билетов должно быть от 1 до 100', 'error');
        return;
    }

    const actualTracks = ticketsTrackList.length > 0 ? ticketsTrackList : allTracks;

    if (ticketsTrackList.length > 0) {
        const inputText = document.getElementById('ticketsTrackList')?.value || '';
        const inputLines = inputText.split('\n').map(l => l.trim()).filter(l => l);
        if (inputLines.length !== ticketsTrackList.length) {
            const missingCount = inputLines.length - ticketsTrackList.length;
            showNotification(`❌ В списке ${missingCount} трек(ов) отсутствует в медиатеке! Исправьте список.`, 'error');
            return;
        }
    }

    if (!actualTracks || actualTracks.length < 36) {
        showNotification(`Недостаточно треков (${actualTracks ? actualTracks.length : 0}/36)`, 'error');
        return;
    }

    const btn = document.getElementById('generateTicketsBtn');
    const originalText = btn ? btn.textContent : '';

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Запуск...';
    }

    const downloadSection = document.getElementById('downloadSection');
    if (downloadSection) downloadSection.style.display = 'none';

    try {
        updateProgressBar(0, count, 'Подготовка к генерации...');
        showNotification('🚀 Запуск генерации билетов...', 'info');

        const payload = {
            count,
            rounds: selectedRounds, // ← добавляем количество раундов
            tracks: actualTracks,
            design: {
                font_family: 'Arial',
                title_size: 20,
                artist_size: 16,
                text_color: '#000000',
                accent_color: '#000000',
                bold: true,
                uppercase: true
            }
        };

        console.log(`🎯 Генерация билетов: ${count} шт, ${selectedRounds} раунда(ов)`);

        const resp = await fetch('/api/tickets/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await resp.json();

        if (resp.ok && result.success) {
            showNotification(`✅ ${result.message}`, 'success');

            if (downloadSection) {
                document.getElementById('downloadFileName').textContent = result.zip_file || '-';
                document.getElementById('downloadTicketsCount').textContent = result.tickets_count || count;
                document.getElementById('downloadTracksUsed').textContent = result.tracks_used || actualTracks.length;
                document.getElementById('downloadRoundsCount').textContent = selectedRounds || result.rounds || '3';
                downloadSection.style.display = 'block';
            }

        } else {
            throw new Error(result.message || result.detail || 'Ошибка генерации билетов');
        }

    } catch (err) {
        console.error('❌ Ошибка генерации:', err);
        updateProgressBar(0, count, '❌ Ошибка генерации');
        showNotification(`❌ ${err.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

/** Скачивание сгенерированных билетов */
function downloadGeneratedTickets() {
    const fileName = document.getElementById('downloadFileName').textContent;
    if (fileName && fileName !== '-') {
        const downloadUrl = `/api/tickets/download/${fileName}`;
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showNotification(`📥 Начинается скачивание: ${fileName}`, 'success');
    } else {
        showNotification('❌ Файл для скачивания не найден', 'error');
    }
}

/** Автоматическое обновление треков */
function startAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    autoRefreshInterval = setInterval(() => {
        if (!document.hidden) loadTracksForTickets(false).catch(console.error);
    }, 15000);
}

/** Обновление при возвращении на вкладку */
function setupVisibilityHandler() {
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) loadTracksForTickets(true).catch(console.error);
    });
}

/** Привязка событий */
function attachTicketEvents() {
    const genBtn = document.getElementById('generateTicketsBtn');
    if (genBtn) genBtn.addEventListener('click', generateTickets);

    const refreshBtn = document.getElementById('refreshTracksBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            showNotification('🔄 Принудительное обновление треков...', 'info');
            loadTracksForTickets(true).catch(console.error);
        });
    }

    const ticketsCountInput = document.getElementById('ticketsCount');
    const ticketsCountDisplay = document.getElementById('ticketsCountDisplay');
    if (ticketsCountInput && ticketsCountDisplay) {
        ticketsCountInput.addEventListener('input', () => {
            const value = parseInt(ticketsCountInput.value) || 1;
            if (value < 1) ticketsCountInput.value = 1;
            if (value > 100) ticketsCountInput.value = 100;
            ticketsCountDisplay.textContent = ticketsCountInput.value;
        });
        ticketsCountDisplay.textContent = ticketsCountInput.value || 10;
    }

    const downloadBtn = document.getElementById('downloadTicketsBtn');
    if (downloadBtn) downloadBtn.addEventListener('click', downloadGeneratedTickets);

    // Поддержка кастомного списка
    const ticketsTrackListInput = document.getElementById('ticketsTrackList');
    if (ticketsTrackListInput) {
        ticketsTrackListInput.addEventListener('input', debounce(validateTicketsTrackList, 500));
    }

    // Обработчики выбора раундов
    const rounds3 = document.getElementById('rounds3');
    const rounds2 = document.getElementById('rounds2');
    if (rounds3) rounds3.addEventListener('change', updateRoundsSelection);
    if (rounds2) rounds2.addEventListener('change', updateRoundsSelection);

    console.log('✅ События билетов привязаны');
}

/** Инициализация модуля билетов */
function initializeTicketsModule() {
    console.log('🎫 Инициализация модуля билетов...');
    connectProgressWebSocket();

    // Установка выбора раундов по умолчанию
    updateRoundsSelection();

    const isTicketsTabActive = () => {
        const ticketsContent = document.getElementById('tickets');
        return ticketsContent && ticketsContent.classList.contains('active');
    };

    if (isTicketsTabActive()) {
        setTimeout(() => loadTracksForTickets().catch(console.error), 500);
    }

    const tabs = document.querySelectorAll('[data-tab]');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            if (e.target.getAttribute('data-tab') === 'tickets') {
                setTimeout(() => loadTracksForTickets().catch(console.error), 100);
            }
        });
    });

    attachTicketEvents();
    startAutoRefresh();
    setupVisibilityHandler();
    console.log('🎫 Модуль билетов инициализирован');
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => initializeTicketsModule(), 100);
});

// Глобальные функции для отладки
window.ticketsDebug = {
    reloadTracks: () => {
        console.log('🔄 Принудительная перезагрузка треков...');
        loadTracksForTickets(true).catch(console.error);
    },
    getTracks: () => allTracks,
    getCustomTracks: () => ticketsTrackList,
    getSelectedRounds: () => selectedRounds
};