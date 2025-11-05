// static/js/tickets.js
// Исправленная версия: превью стабильно после получения >= 36 треков

const API_BASE_URL = '/api';
const TRACKS_ENDPOINTS = ['/api/tracks'];

const TICKETS_API = `/api/tickets/generate`;
let allTracks = [];
let previewTracks = []; // фиксированный кэш для превью (36 элементов)
let autoRefreshInterval = null;
let lastTrackCount = 0;
let previewCells = []; // Массив DOM-элементов ячеек для быстрого доступа

/** Установка значений по умолчанию */
function setDefaultTicketSettings() {
    console.log('🎨 Установка настроек билетов по умолчанию...');

    const elements = {
        't_text_color': '#666666',
        't_accent_color': '#000000',
        't_title_position': 0,
        't_artist_position': 90,
        't_vertical_padding': 5,
        't_bold': true,
        't_upper': false
    };

    Object.entries(elements).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            if (element.type === 'checkbox') {
                element.checked = value;
            } else {
                element.value = value;
            }
            console.log(`✅ ${id} = ${value}`);
        } else {
            console.warn(`❌ Элемент не найден: ${id}`);
        }
    });

    console.log('🎨 Настройки билетов установлены по умолчанию');
}

/** Показ отладочного сообщения внизу превью */
function setPreviewDebug(msg) {
    const grid = document.getElementById('ticketPreviewGrid');
    if (grid) {
        grid.innerHTML = `<div style="color:#f55; font-size:16px; padding:60px; text-align:center; white-space:pre-wrap; background:#1a1a1a; border-radius:8px; line-height:1.5;">${msg}</div>`;
    }
}

/** Обновление статистики в превью */
function updatePreviewStats() {
    const countEl = document.getElementById('previewTrackCount');
    const statusEl = document.getElementById('previewStatus');

    if (countEl) {
        countEl.textContent = allTracks ? allTracks.length : 0;
    }

    if (statusEl) {
        if (!allTracks || allTracks.length === 0) {
            statusEl.textContent = '❌ Нет треков';
            statusEl.style.color = '#ff5555';
        } else if (allTracks.length < 36) {
            statusEl.textContent = '⚠️ Недостаточно треков';
            statusEl.style.color = '#ffaa00';
        } else {
            statusEl.textContent = '✅ Готов к генерации';
            statusEl.style.color = '#55ff55';
        }
    }
}

/**
 * Формирование фиксированного набора превью.
 * Вызывается ТОЛЬКО когда allTracks изменился (количество или состав).
 * НЕ вызывается при изменении дизайна.
 */
function generateFixedPreviewTracks() {
    if (!allTracks || allTracks.length < 36) {
        previewTracks = [];
        console.log('❌ Недостаточно треков для фиксированного превью.');
        return;
    }

    // Генерируем новый фиксированный набор (берем первые 36 из allTracks)
    // Или можно сделать shuffle и взять первые 36, если хочется рандом, но фиксированный
    // Для полной фиксации используем первые 36
    previewTracks = allTracks.slice(0, 36);
    console.log('✅ Фиксированный набор превью обновлён (первые 36 треков из allTracks).');
}

/** Загрузка треков для билетов */
async function loadTracksForTickets(forceRefresh = false) {
    let lastErr = null;

    if (forceRefresh) {
        previewTracks = []; // Сбрасываем кэш при принудительном обновлении
        console.log('🔄 Принудительное обновление треков (сброс кэша превью)...');
    }

    for (const url of TRACKS_ENDPOINTS) {
        try {
            console.log('[tickets] попытка fetch', url);

            const timestamp = Date.now();
            const fetchUrl = `${url}?t=${timestamp}&force=${forceRefresh}`;

            const resp = await fetch(fetchUrl, {
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });

            if (!resp.ok) {
                lastErr = `HTTP ${resp.status} от ${url}`;
                console.warn('[tickets] non-ok response', lastErr);
                continue;
            }

            const data = await resp.json();
            console.log('[tickets] raw tracks data:', data);

            const arr = (() => {
                if (Array.isArray(data)) return data;
                if (Array.isArray(data.tracks)) return data.tracks;
                if (Array.isArray(data.data)) return data.data;
                for (const key in data) {
                    if (Array.isArray(data[key])) return data[key];
                }
                return null;
            })();

            if (!arr) {
                lastErr = `Неизвестный формат JSON от ${url}`;
                console.warn('[tickets] unknown format', data);
                continue;
            }

            const newTrackCount = arr.length;
            const tracksChanged = newTrackCount !== lastTrackCount;

            allTracks = arr;
            lastTrackCount = newTrackCount;

            console.log(`[tickets] загружено треков: ${allTracks.length} из ${url}, изменилось: ${tracksChanged}`);

            // Обновляем previewTracks ТОЛЬКО если треки изменились
            if (tracksChanged) {
                console.log('🔄 Кэш превью обновляется из-за изменения треков.');
                generateFixedPreviewTracks(); // Обновляем фиксированный набор
                updateTicketPreview(); // Пересоздаем превью, т.к. треки изменились
            } else {
                console.log('♻️ Кэш превью оставлен без изменений (tracks не изменились).');
            }

            updatePreviewStats();

            return; // успешно загрузили, выходим
        } catch (err) {
            lastErr = err.message || String(err);
            console.warn('[tickets] ошибка fetch', url, lastErr);
            continue;
        }
    }

    // если не удалось
    allTracks = [];
    previewTracks = [];
    const msg = `Не удалось получить треки.\nПоследняя ошибка: ${lastErr}\nПроверь /api/tracks на сервере (см. консоль).`;
    console.error('[tickets] все попытки неудачны', lastErr);
    setPreviewDebug(msg);
    updatePreviewStats();
    updateTicketPreview(); // Обновляем превью, чтобы показать ошибку
}

/** Автоматическое обновление треков каждые 10 секунд */
function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }

    autoRefreshInterval = setInterval(() => {
        if (!document.hidden) {
            console.log('🔄 Авто-обновление треков...');
            loadTracksForTickets(false).catch(console.error); // Не forceRefresh, только если изменились
        }
    }, 10000);

    console.log('✅ Авто-обновление треков запущено (каждые 10 сек)');
}

/** Остановка авто-обновления */
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        console.log('⏹️ Авто-обновление треков остановлено');
    }
}

/** Обновление при возвращении на вкладку */
function setupVisibilityHandler() {
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            console.log('📱 Возврат на вкладку - обновляем треки');
            loadTracksForTickets(true).catch(console.error); // forceRefresh при возврате
        }
    });
}

/** Чтение настроек UI */
function readTicketDesignFromUI() {
    return {
        font_family: document.getElementById('t_font')?.value || 'Helvetica',
        title_size: parseInt(document.getElementById('t_title_size')?.value || 11),
        artist_size: parseInt(document.getElementById('t_artist_size')?.value || 9),
        text_color: document.getElementById('t_text_color')?.value || '#666666',
        accent_color: document.getElementById('t_accent_color')?.value || '#000000',
        bold: document.getElementById('t_bold')?.checked || false,
        uppercase: document.getElementById('t_upper')?.checked || false,
        title_position: parseInt(document.getElementById('t_title_position')?.value || 0),
        artist_position: parseInt(document.getElementById('t_artist_position')?.value || 90),
        vertical_padding: parseInt(document.getElementById('t_vertical_padding')?.value || 5)
    };
}

/**
 * Создание или обновление превью.
 * Если previewTracks изменился, пересоздаем ячейки.
 * Если изменился только дизайн, обновляем стиль существующих ячеек.
 */
function updateTicketPreview() {
    console.log('🔄 Обновление превью билета (дизайн)...');

    const cfg = readTicketDesignFromUI();
    const previewCard = document.getElementById('ticketPreviewCard');
    const grid = document.getElementById('ticketPreviewGrid');
    const titleEl = document.getElementById('ticketPreviewTitle');

    if (!previewCard || !grid || !titleEl) {
        console.error('❌ Элементы превью не найдены');
        return;
    }

    // Обновляем заголовок (Билет №)
    titleEl.style.cssText = `
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        font-weight: 700;
        margin-bottom: 20px;
        font-size: 24px;
        padding: 12px;
        border-radius: 10px;
        text-align: center;
    `;
    titleEl.textContent = 'БИЛЕТ №1 — МУЗЫКАЛЬНОЕ ЛОТО';

    updatePreviewStats();

    if (!previewTracks || previewTracks.length < 36) {
        const needed = 36 - (previewTracks ? previewTracks.length : 0);
        setPreviewDebug(`❗ Для генерации билета требуется минимум 36 треков.\n\n` +
            `Найдено треков: ${previewTracks ? previewTracks.length : 0}\n` +
            `Необходимо ещё: ${needed} треков\n\n` +
            `Загрузите треки во вкладке "📁 Медиатека"`);
        return;
    }

    // --- КЛЮЧЕВАЯ ЛОГИКА: ---
    // Если ячейки еще не созданы или previewTracks изменился, создаем их заново.
    if (grid.childElementCount !== 36) { // Простая проверка, нет ли уже 36 ячеек
        console.log('🆕 Пересоздание ячеек превью...');
        grid.innerHTML = '';
        grid.style.display = 'grid';
        grid.style.gridTemplateColumns = 'repeat(6, 1fr)';
        grid.style.gap = '6px';
        grid.style.padding = '20px';
        grid.style.background = '#ffffff';
        grid.style.borderRadius = '12px';

        for (let i = 0; i < 36; i++) {
            const track = previewTracks[i] || { title: `Трек ${i + 1}`, artist: 'Артист' };
            const titleText = cfg.uppercase ? (track.title || `Трек ${i + 1}`).toUpperCase() : (track.title || `Трек ${i + 1}`);
            const artistText = cfg.uppercase ? (track.artist || 'Артист').toUpperCase() : (track.artist || 'Артист');

            const cell = document.createElement('div');
            cell.style.cssText = `
                display: flex;
                flex-direction: column;
                justify-content: flex-start;
                align-items: center;
                background: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: ${cfg.vertical_padding}px;
                min-height: 70px;
                box-sizing: border-box;
                position: relative;
                overflow: hidden;
            `;

            const textContainer = document.createElement('div');
            textContainer.style.cssText = `
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                padding: ${cfg.vertical_padding}px;
                box-sizing: border-box;
            `;

            const titleNode = document.createElement('div');
            titleNode.textContent = titleText;
            titleNode.style.cssText = `
                font-family: ${cfg.font_family};
                font-size: ${Math.max(6, cfg.title_size)}px;
                font-weight: ${cfg.bold ? '700' : '400'};
                color: ${cfg.accent_color};
                text-align: center;
                line-height: 1.1;
                white-space: normal;
                word-wrap: break-word;
                margin-top: ${cfg.title_position}%;
            `;

            const artistNode = document.createElement('div');
            artistNode.textContent = artistText;
            artistNode.style.cssText = `
                font-family: ${cfg.font_family};
                font-size: ${Math.max(6, cfg.artist_size)}px;
                color: ${cfg.text_color};
                opacity: 0.9;
                text-align: center;
                line-height: 1.1;
                white-space: normal;
                word-wrap: break-word;
                margin-top: auto;
                margin-bottom: ${100 - cfg.artist_position}%;
            `;

            textContainer.appendChild(titleNode);
            textContainer.appendChild(artistNode);
            cell.appendChild(textContainer);
            grid.appendChild(cell);
        }
    } else {
        // Ячейки уже созданы и previewTracks не изменился — обновляем только стиль
        console.log('🎨 Обновление стиля существующих ячеек...');
        const cells = grid.children; // Получаем коллекцию ячеек
        for (let i = 0; i < 36; i++) {
            const cell = cells[i];
            const track = previewTracks[i] || { title: `Трек ${i + 1}`, artist: 'Артист' };
            const titleText = cfg.uppercase ? (track.title || `Трек ${i + 1}`).toUpperCase() : (track.title || `Трек ${i + 1}`);
            const artistText = cfg.uppercase ? (track.artist || 'Артист').toUpperCase() : (track.artist || 'Артист');

            // Обновляем стиль ячейки
            cell.style.padding = `${cfg.vertical_padding}px`;

            // Обновляем текст и стиль внутри
            const textContainer = cell.firstChild;
            const titleNode = textContainer.firstChild;
            const artistNode = textContainer.lastChild;

            titleNode.textContent = titleText;
            titleNode.style.cssText = `
                font-family: ${cfg.font_family};
                font-size: ${Math.max(6, cfg.title_size)}px;
                font-weight: ${cfg.bold ? '700' : '400'};
                color: ${cfg.accent_color};
                text-align: center;
                line-height: 1.1;
                white-space: normal;
                word-wrap: break-word;
                margin-top: ${cfg.title_position}%;
            `;

            artistNode.textContent = artistText;
            artistNode.style.cssText = `
                font-family: ${cfg.font_family};
                font-size: ${Math.max(6, cfg.artist_size)}px;
                color: ${cfg.text_color};
                opacity: 0.9;
                text-align: center;
                line-height: 1.1;
                white-space: normal;
                word-wrap: break-word;
                margin-top: auto;
                margin-bottom: ${100 - cfg.artist_position}%;
            `;
        }
    }

    console.log('✅ Превью билета (дизайн) обновлено');
}

/** Показать уведомление */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position:fixed;
        top:20px;
        right:20px;
        padding:15px 20px;
        border-radius:8px;
        color:white;
        font-weight:bold;
        z-index:10000;
        max-width:400px;
        box-shadow:0 4px 12px rgba(0,0,0,0.3);
        transition:all 0.3s ease;
        transform:translateX(100%);
        opacity:0;
        background: ${type === 'success' ? 'linear-gradient(135deg, #10b981, #059669)' :
            type === 'error' ? 'linear-gradient(135deg, #ef4444, #dc2626)' :
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

/** Генерация билетов с автоматическим скачиванием */
async function generateTickets() {
    const count = parseInt(document.getElementById('ticketsCount')?.value || '10', 10);
    if (isNaN(count) || count < 1 || count > 100) {
        showNotification('Количество билетов должно быть от 1 до 100', 'error');
        return;
    }
    if (!allTracks || allTracks.length < 36) {
        showNotification('Недостаточно треков (минимум 36)', 'error');
        return;
    }

    const design = readTicketDesignFromUI();
    const btn = document.getElementById('generateTicketsBtn');
    const originalText = btn ? btn.textContent : '';

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Генерация...';
    }

    try {
        showNotification('🚀 Генерация билетов...', 'info');

        const payload = { count, design };
        const resp = await fetch('/api/tickets/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await resp.json();

        if (resp.ok && result.success && result.download_url) {
            showNotification(`✅ ${result.message}`, 'success');

            const fullUrl = result.download_url.startsWith('/')
                ? `${window.location.origin}${result.download_url}`
                : result.download_url;

            const link = document.createElement('a');
            link.href = fullUrl;
            link.download = result.zip_file;

            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            console.log('✅ Автоматическое скачивание запущено:', result.zip_file);

            const downloadSection = document.getElementById('downloadSection');
            if (downloadSection) {
                document.getElementById('downloadFileName').textContent = result.zip_file || '-';
                document.getElementById('downloadTicketsCount').textContent = result.tickets_count || count;
                document.getElementById('downloadTracksUsed').textContent = allTracks.length || 36;

                downloadSection.style.display = 'block';

                document.getElementById('downloadTicketsBtn').onclick = function () {
                    console.log('🎫 Повторное нажатие кнопки скачивания');
                    const link = document.createElement('a');
                    link.href = fullUrl;
                    link.download = result.zip_file;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                };
            }

        } else {
            throw new Error(result.message || 'Ошибка генерации билетов');
        }

    } catch (err) {
        console.error('❌ Ошибка генерации:', err);
        showNotification(`❌ ${err.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

/** Обновление значений слайдеров в реальном времени */
function setupSliderValueDisplays() {
    const sliders = [
        { id: 't_title_position', displayId: 'titlePositionValue' },
        { id: 't_artist_position', displayId: 'artistPositionValue' },
        { id: 't_vertical_padding', displayId: 'verticalPaddingValue' }
    ];

    sliders.forEach(({ id, displayId }) => {
        const slider = document.getElementById(id);
        const displayEl = document.getElementById(displayId);

        if (!slider || !displayEl) return;

        const updateValue = () => {
            let valueText = slider.value;
            if (id === 't_title_position' || id === 't_artist_position') {
                valueText += '%';
            } else if (id === 't_vertical_padding') {
                valueText += 'px';
            }
            displayEl.textContent = valueText;
        };

        updateValue();
        slider.addEventListener('input', updateValue);
    });
}

/**
 * Привязка событий.
 * Теперь updateTicketPreview вызывается при изменении дизайна, но она не пересоздает ячейки, а обновляет их стиль.
 */
function attachTicketSettingsEvents() {
    const designIds = [
        't_font', 't_title_size', 't_artist_size', 't_text_color',
        't_accent_color', 't_bold', 't_upper'
    ];

    designIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', updateTicketPreview); // Обновляем превью (стиль) при изменении
        }
    });

    // Слайдеры — обновляют preview с debounce, НО ТОЛЬКО СТИЛЬ
    ['t_title_position', 't_artist_position', 't_vertical_padding'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            let timeout;
            el.addEventListener('input', () => {
                clearTimeout(timeout);
                timeout = setTimeout(updateTicketPreview, 150); // 150ms debounce
            });
        }
    });

    const genBtn = document.getElementById('generateTicketsBtn');
    if (genBtn) genBtn.addEventListener('click', generateTickets);

    const refreshBtn = document.getElementById('refreshTracksBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadTracksForTickets(true).catch(console.error); // Принудительно обновляет треки и превью
            showNotification('🔄 Обновление треков...', 'info');
        });
    }

    // Обновление при изменении размера окна
    window.addEventListener('resize', updateTicketPreview);

    // Настройка отображения значений слайдеров
    setupSliderValueDisplays();

    console.log('✅ События билетов привязаны');
}

/** Инициализация */
document.addEventListener('DOMContentLoaded', () => {
    console.log('🎫 Инициализация модуля билетов...');

    setDefaultTicketSettings();
    attachTicketSettingsEvents();
    setupSliderValueDisplays();

    loadTracksForTickets().catch(e => {
        console.warn('[tickets] Ошибка загрузки треков:', e);
    });

    startAutoRefresh();
    setupVisibilityHandler();

    // Начальное обновление превью
    setTimeout(updateTicketPreview, 500);

    console.log('🎫 Модуль билетов инициализирован с авто-обновлением');
});

// Глобальные функции для отладки
window.ticketsDebug = {
    reloadTracks: () => {
        console.log('🔄 Принудительная перезагрузка треков...');
        loadTracksForTickets(true).catch(console.error);
    },
    showTrackCount: () => {
        console.log('📊 Треков в системе:', allTracks ? allTracks.length : 0);
        return allTracks ? allTracks.length : 0;
    },
    startAutoRefresh,
    stopAutoRefresh
};