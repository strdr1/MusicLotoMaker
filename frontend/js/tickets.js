// static/js/tickets.js - Полная версия с прогрессом и WebSocket

const API_BASE_URL = '/api';
let allTracks = [];
let autoRefreshInterval = null;
let progressWebSocket = null;

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

                    // Обновляем дополнительные элементы прогресса
                    const progressPercent = document.getElementById('progressPercent');
                    if (progressPercent) {
                        progressPercent.textContent = `${data.percent}%`;
                    }

                    const totalTickets = document.getElementById('totalTickets');
                    if (totalTickets) {
                        totalTickets.textContent = data.total;
                    }

                    // Добавляем детали в прогресс
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

    console.log('🔍 Парсинг данных треков:', data);

    // Пробуем разные форматы ответа
    if (Array.isArray(data)) {
        return data.map(track => ({
            id: track.id || track.track_id || Math.random().toString(36),
            title: track.title || track.name || 'Без названия',
            artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
        }));
    }

    if (typeof data === 'object') {
        // Формат {tracks: [...]}
        if (Array.isArray(data.tracks)) {
            return data.tracks.map(track => ({
                id: track.id || track.track_id || Math.random().toString(36),
                title: track.title || track.name || 'Без названия',
                artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
            }));
        }

        // Формат {data: [...]}
        if (Array.isArray(data.data)) {
            return data.data.map(track => ({
                id: track.id || track.track_id || Math.random().toString(36),
                title: track.title || track.name || 'Без названия',
                artist: track.artist || track.artist_name || 'Неизвестный исполнитель'
            }));
        }

        // Формат с другими ключами
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
        console.log('🔄 Загрузка треков для билетов...');

        // Сначала получаем статус
        const statusResp = await fetch('/api/tickets/status', {
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        });

        if (!statusResp.ok) {
            throw new Error(`HTTP ${statusResp.status} при получении статуса`);
        }

        const statusData = await statusResp.json();
        console.log('📊 Статус билетов:', statusData);

        // Затем загружаем треки
        const timestamp = Date.now();
        const tracksResp = await fetch(`/api/tracks?t=${timestamp}&force=${forceRefresh}`, {
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        });

        if (!tracksResp.ok) {
            throw new Error(`HTTP ${tracksResp.status} при получении треков`);
        }

        const tracksData = await tracksResp.json();
        console.log('🎵 Получены данные треков:', tracksData);

        // Парсим треки
        allTracks = parseTracksResponse(tracksData);
        console.log(`✅ Загружено треков: ${allTracks.length}`);

        // Если через API треков не получилось, пробуем альтернативные методы
        if (allTracks.length === 0) {
            console.log('🔄 Попытка альтернативного получения треков...');
            await tryAlternativeTrackLoading();
        }

        updateProgressStats();

    } catch (err) {
        console.error('❌ Ошибка загрузки треков:', err);
        // Пробуем альтернативные методы при ошибке
        await tryAlternativeTrackLoading();
        updateProgressStats();
        showNotification(`❌ Ошибка загрузки треков: ${err.message}`, 'error');
    }
}

/** Альтернативные методы загрузки треков */
async function tryAlternativeTrackLoading() {
    try {
        // Пробуем разные эндпоинты
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
                        console.log(`✅ Треки найдены через ${endpoint}: ${tracks.length}`);
                        allTracks = tracks;
                        return;
                    }
                }
            } catch (e) {
                console.log(`❌ Эндпоинт ${endpoint} не доступен:`, e.message);
            }
        }

        // Если все эндпоинты не сработали, используем заглушку из статуса
        const statusResp = await fetch('/api/tickets/status');
        if (statusResp.ok) {
            const status = await statusResp.json();
            if (status.tracks_count > 0) {
                console.log(`⚠️ Используем данные из статуса: ${status.tracks_count} треков`);
                // Создаем макетные треки на основе количества
                allTracks = Array.from({ length: status.tracks_count }, (_, i) => ({
                    id: `track-${i + 1}`,
                    title: `Трек ${i + 1}`,
                    artist: 'Исполнитель'
                }));
            }
        }
    } catch (err) {
        console.error('❌ Ошибка альтернативной загрузки:', err);
    }
}

/** Обновление статистики */
function updateProgressStats() {
    const countEl = document.getElementById('tracksCount');
    const statusEl = document.getElementById('generationStatus');

    if (countEl) {
        countEl.textContent = allTracks ? allTracks.length : 0;
    }

    if (statusEl) {
        if (!allTracks || allTracks.length === 0) {
            statusEl.textContent = '❌ Нет треков';
            statusEl.style.color = '#ef4444';
        } else if (allTracks.length < 36) {
            statusEl.textContent = `⚠️ Недостаточно треков (${allTracks.length}/36)`;
            statusEl.style.color = '#f59e0b';
        } else {
            statusEl.textContent = `✅ Готов к генерации (${allTracks.length} треков)`;
            statusEl.style.color = '#10b981';
        }
    }

    // Обновляем кнопку генерации
    const generateBtn = document.getElementById('generateTicketsBtn');
    if (generateBtn) {
        generateBtn.disabled = !allTracks || allTracks.length < 36;
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

        // Меняем цвет в зависимости от прогресса
        if (percent < 30) {
            progressBar.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
        } else if (percent < 70) {
            progressBar.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
        } else {
            progressBar.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        }
    }

    if (progressText) {
        progressText.textContent = message || `Генерация: ${current}/${total}`;
    }

    if (currentTicketEl) {
        currentTicketEl.textContent = current > 0 ? current : '-';
    }

    if (totalTicketsEl) {
        totalTicketsEl.textContent = total > 0 ? total : '-';
    }

    if (progressPercentEl) {
        const percent = total > 0 ? Math.round((current / total) * 100) : 0;
        progressPercentEl.textContent = `${percent}%`;
    }

    // Показываем/скрываем секцию прогресса
    const progressSection = document.getElementById('progressSection');
    if (progressSection) {
        if (current === 0 && total === 0) {
            progressSection.style.display = 'none';
        } else {
            progressSection.style.display = 'block';
        }
    }
}

/** Генерация билетов с прогресс-баром */
async function generateTickets() {
    const count = parseInt(document.getElementById('ticketsCount')?.value || '10', 10);
    if (isNaN(count) || count < 1 || count > 100) {
        showNotification('Количество билетов должно быть от 1 до 100', 'error');
        return;
    }
    if (!allTracks || allTracks.length < 36) {
        showNotification(`Недостаточно треков (${allTracks ? allTracks.length : 0}/36)`, 'error');
        return;
    }

    const btn = document.getElementById('generateTicketsBtn');
    const originalText = btn ? btn.textContent : '';

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Запуск...';
    }

    // Скрываем секцию скачивания предыдущих результатов
    const downloadSection = document.getElementById('downloadSection');
    if (downloadSection) {
        downloadSection.style.display = 'none';
    }

    try {
        // Сбрасываем прогресс
        updateProgressBar(0, count, 'Подготовка к генерации...');
        showNotification('🚀 Запуск генерации билетов...', 'info');

        const payload = {
            count,
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

        console.log('🎫 Отправка запроса на генерацию...', payload);

        const resp = await fetch('/api/tickets/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await resp.json();
        console.log('🎫 Ответ сервера:', result);

        if (resp.ok && result.success) {
            showNotification(`✅ ${result.message}`, 'success');

            // Показываем секцию скачивания
            if (downloadSection) {
                document.getElementById('downloadFileName').textContent = result.zip_file || '-';
                document.getElementById('downloadTicketsCount').textContent = result.tickets_count || count;
                document.getElementById('downloadTracksUsed').textContent = result.tracks_used || allTracks.length;
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
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }

    autoRefreshInterval = setInterval(() => {
        if (!document.hidden) {
            console.log('🔄 Авто-обновление треков...');
            loadTracksForTickets(false).catch(console.error);
        }
    }, 15000); // Каждые 15 секунд
}

/** Обновление при возвращении на вкладку */
function setupVisibilityHandler() {
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            console.log('📱 Возврат на вкладку - обновляем треки');
            loadTracksForTickets(true).catch(console.error);
        }
    });
}

/** Привязка событий */
function attachTicketEvents() {
    const genBtn = document.getElementById('generateTicketsBtn');
    if (genBtn) {
        genBtn.addEventListener('click', generateTickets);
    }

    const refreshBtn = document.getElementById('refreshTracksBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            showNotification('🔄 Принудительное обновление треков...', 'info');
            loadTracksForTickets(true).catch(console.error);
        });
    }

    // Обновление счетчика билетов
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

    // Кнопка скачивания билетов
    const downloadBtn = document.getElementById('downloadTicketsBtn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadGeneratedTickets);
    }

    console.log('✅ События билетов привязаны');
}

/** Инициализация модуля билетов */
function initializeTicketsModule() {
    console.log('🎫 Инициализация модуля билетов...');

    // Подключаем WebSocket для прогресса
    connectProgressWebSocket();

    // Проверяем, находимся ли мы на вкладке билетов
    const isTicketsTabActive = () => {
        const ticketsTab = document.querySelector('[data-tab="tickets"]');
        const ticketsContent = document.getElementById('tickets');
        return ticketsTab && ticketsTab.classList.contains('active') ||
            ticketsContent && ticketsContent.classList.contains('active');
    };

    // Загружаем треки сразу если вкладка активна
    if (isTicketsTabActive()) {
        console.log('🎫 Вкладка билетов активна - загружаем треки...');
        setTimeout(() => {
            loadTracksForTickets().catch(console.error);
        }, 500);
    }

    // Слушатель переключения вкладок
    const tabs = document.querySelectorAll('[data-tab]');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            const tabName = e.target.getAttribute('data-tab');
            if (tabName === 'tickets') {
                console.log('🎫 Переключение на вкладку билетов');
                setTimeout(() => {
                    loadTracksForTickets().catch(console.error);
                }, 100);
            }
        });
    });

    attachTicketEvents();
    startAutoRefresh();
    setupVisibilityHandler();

    console.log('🎫 Модуль билетов инициализирован');
}

/** Загрузка когда DOM готов */
document.addEventListener('DOMContentLoaded', () => {
    // Ждем немного чтобы убедиться что все элементы загружены
    setTimeout(() => {
        initializeTicketsModule();
    }, 100);
});

// Глобальные функции для отладки
window.ticketsDebug = {
    reloadTracks: () => {
        console.log('🔄 Принудительная перезагрузка треков...');
        loadTracksForTickets(true).catch(console.error);
    },
    showTrackCount: () => {
        console.log('📊 Треков в системе:', allTracks ? allTracks.length : 0);
        console.log('📊 Данные треков:', allTracks);
        return allTracks ? allTracks.length : 0;
    },
    getTracks: () => allTracks,
    testAPI: async () => {
        console.log('🧪 Тестирование API...');
        try {
            const resp = await fetch('/api/tickets/status');
            const data = await resp.json();
            console.log('📊 Статус API:', data);
            return data;
        } catch (err) {
            console.error('❌ Ошибка теста API:', err);
            return null;
        }
    },
    testWebSocket: () => {
        console.log('🔌 Тестирование WebSocket...');
        if (progressWebSocket) {
            console.log('WebSocket состояние:', progressWebSocket.readyState);
            console.log('WebSocket URL:', progressWebSocket.url);
        } else {
            console.log('WebSocket не подключен');
        }
    },
    simulateProgress: (current, total, message) => {
        console.log('🎭 Имитация прогресса:', { current, total, message });
        updateProgressBar(current, total, message);
    },
    clearProgress: () => {
        console.log('🧹 Очистка прогресса');
        updateProgressBar(0, 0, '');
        const downloadSection = document.getElementById('downloadSection');
        if (downloadSection) {
            downloadSection.style.display = 'none';
        }
    }
};