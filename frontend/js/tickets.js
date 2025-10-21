// static/js/tickets.js
// Исправленная версия - сохраняем один набор треков для превью

const API_BASE_URL = (typeof API_BASE !== 'undefined') ? API_BASE : 'http://127.0.0.1:8000';
const TRACKS_ENDPOINTS = [
    `${API_BASE_URL}/api/tracks`,
    `${API_BASE_URL}/tracks`,
    `/api/tracks`,
    `/tracks`
];

const TICKETS_API = `${API_BASE_URL}/api/tickets/generate`;
let allTracks = [];
let previewTracks = []; // Сохраняем один набор для превью

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

/** Генерация случайного набора треков для превью (только один раз) */
function generateRandomPreviewTracks() {
    if (!allTracks || allTracks.length < 36) {
        return [];
    }

    // Если превью треки еще не созданы - создаем один раз
    if (previewTracks.length === 0) {
        const shuffled = [...allTracks].sort(() => Math.random() - 0.5);
        previewTracks = shuffled.slice(0, 36);
        console.log('🎲 Сгенерирован новый набор превью треков');
    }

    return previewTracks;
}

/** Перегенерировать превью треки (при явном вызове) */
function regeneratePreviewTracks() {
    if (allTracks && allTracks.length >= 36) {
        const shuffled = [...allTracks].sort(() => Math.random() - 0.5);
        previewTracks = shuffled.slice(0, 36);
        console.log('🔄 Превью треки перегенерированы');
        updateTicketPreview();
    }
}

/** Попытаться загрузить треки с разных эндпоинтов */
async function loadTracksForTickets() {
    let lastErr = null;
    for (const url of TRACKS_ENDPOINTS) {
        try {
            console.log('[tickets] try fetch', url);
            const resp = await fetch(url, { cache: 'no-store' });
            if (!resp.ok) {
                lastErr = `HTTP ${resp.status} from ${url}`;
                console.warn('[tickets] non-ok response', lastErr);
                continue;
            }
            const data = await resp.json();

            if (Array.isArray(data)) {
                allTracks = data;
            } else if (Array.isArray(data.tracks)) {
                allTracks = data.tracks;
            } else if (Array.isArray(data.data)) {
                allTracks = data.data;
            } else {
                const arr = Object.values(data).find(v => Array.isArray(v));
                if (arr) {
                    allTracks = arr;
                } else {
                    lastErr = `Неизвестный JSON формат от ${url}`;
                    continue;
                }
            }

            console.log('[tickets] loaded tracks count=', allTracks.length, 'from', url);

            // Сбрасываем превью треки при загрузке новых данных
            previewTracks = [];
            updateTicketPreview();
            updatePreviewStats();
            return;
        } catch (err) {
            lastErr = err.message || String(err);
            console.warn('[tickets] fetch error', url, lastErr);
            continue;
        }
    }

    allTracks = [];
    previewTracks = [];
    const msg = `Не удалось получить треки.\nПоследняя ошибка: ${lastErr}\nПроверь /api/tracks на сервере (см. консоль).`;
    console.error('[tickets] all attempts failed', lastErr);
    setPreviewDebug(msg);
    updatePreviewStats();
}

/** Чтение настроек UI */
function readTicketDesignFromUI() {
    return {
        font_family: document.getElementById('t_font')?.value || 'Helvetica',
        title_size: parseInt(document.getElementById('t_title_size')?.value || 14),
        artist_size: parseInt(document.getElementById('t_artist_size')?.value || 11),
        text_color: document.getElementById('t_text_color')?.value || '#E8EEFC',
        accent_color: document.getElementById('t_accent_color')?.value || '#4E7CFF',
        bold: document.getElementById('t_bold')?.checked || false,
        uppercase: document.getElementById('t_upper')?.checked || false,
        title_position: parseInt(document.getElementById('t_title_position')?.value || 30),
        artist_position: parseInt(document.getElementById('t_artist_position')?.value || 70),
        vertical_padding: parseInt(document.getElementById('t_vertical_padding')?.value || 15)
    };
}

/** Обновление увеличенного превью 6x6 */
function updateTicketPreview() {
    const previewCard = document.getElementById('ticketPreviewCard');
    const grid = document.getElementById('ticketPreviewGrid');
    const titleEl = document.getElementById('ticketPreviewTitle');
    if (!previewCard || !grid || !titleEl) return;

    const cfg = readTicketDesignFromUI();

    // обновляем заголовок
    titleEl.style.color = cfg.accent_color;
    titleEl.style.fontFamily = cfg.font_family;
    titleEl.style.textTransform = cfg.uppercase ? 'uppercase' : 'none';
    titleEl.style.fontWeight = cfg.bold ? '700' : '600';

    // обновляем статистику
    updatePreviewStats();

    // если нет треков или меньше 36 — показываем сообщение
    if (!allTracks || allTracks.length < 36) {
        const needed = 36 - (allTracks ? allTracks.length : 0);
        setPreviewDebug(`❗ Для генерации билета требуется минимум 36 треков.\n\n` +
            `Найдено треков: ${allTracks ? allTracks.length : 0}\n` +
            `Необходимо ещё: ${needed} треков\n\n` +
            `Загрузите треки во вкладке "📁 Медиатека"`);
        return;
    }

    // очистка и установка сетки 6x6
    grid.innerHTML = '';
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(6, 1fr)';
    grid.style.gap = '8px';
    grid.style.padding = '15px';

    // используем сохраненный набор треков для превью
    const currentPreviewTracks = generateRandomPreviewTracks();

    // создаем ячейки 6x6
    for (let i = 0; i < 36; i++) {
        const track = currentPreviewTracks[i] || { title: `Трек ${i + 1}`, artist: 'Артист' };
        const title = (cfg.uppercase ? (track.title || '').toUpperCase() : (track.title || `Трек ${i + 1}`));
        const artist = (cfg.uppercase ? (track.artist || '').toUpperCase() : (track.artist || 'Артист'));

        const cell = document.createElement('div');

        // Основные стили ячейки
        cell.style.cssText = [
            'display:flex',
            'flex-direction:column',
            'justify-content:flex-start',
            'align-items:center',
            'border-radius:8px',
            'background:#0b1116',
            'padding:' + cfg.vertical_padding + 'px',
            'border:1px solid rgba(255,255,255,0.08)',
            'min-height:80px',
            'box-sizing:border-box',
            'overflow:hidden',
            'position:relative',
            'transition:all 0.3s ease',
            'cursor:pointer'
        ].join(';');

        // hover эффект
        cell.onmouseover = () => {
            cell.style.background = '#1a2432';
            cell.style.borderColor = cfg.accent_color;
            cell.style.transform = 'translateY(-2px) scale(1.02)';
            cell.style.boxShadow = '0 4px 12px rgba(78, 124, 255, 0.2)';
        };
        cell.onmouseout = () => {
            cell.style.background = '#0b1116';
            cell.style.borderColor = 'rgba(255,255,255,0.08)';
            cell.style.transform = 'translateY(0) scale(1)';
            cell.style.boxShadow = 'none';
        };

        // Контейнер для текста с абсолютным позиционированием
        const textContainer = document.createElement('div');
        textContainer.style.cssText = [
            'position:absolute',
            'top:0',
            'left:0',
            'right:0',
            'bottom:0',
            'display:flex',
            'flex-direction:column',
            'justify-content:space-between',
            'padding:' + cfg.vertical_padding + 'px',
            'box-sizing:border-box'
        ].join(';');

        // Название трека
        const titleNode = document.createElement('div');
        titleNode.textContent = title;
        titleNode.style.fontFamily = cfg.font_family;
        titleNode.style.fontSize = Math.max(12, cfg.title_size) + 'px';
        titleNode.style.fontWeight = cfg.bold ? '700' : '600';
        titleNode.style.color = cfg.accent_color;
        titleNode.style.textAlign = 'center';
        titleNode.style.lineHeight = '1.1';
        titleNode.style.whiteSpace = 'normal';
        titleNode.style.overflow = 'visible';
        titleNode.style.wordWrap = 'break-word';
        titleNode.style.marginTop = cfg.title_position + '%';
        titleNode.title = title;

        // Имя артиста
        const artistNode = document.createElement('div');
        artistNode.textContent = artist;
        artistNode.style.fontFamily = cfg.font_family;
        artistNode.style.fontSize = Math.max(9, cfg.artist_size) + 'px';
        artistNode.style.color = cfg.text_color;
        artistNode.style.opacity = '0.9';
        artistNode.style.textAlign = 'center';
        artistNode.style.lineHeight = '1.1';
        artistNode.style.whiteSpace = 'normal';
        artistNode.style.overflow = 'visible';
        artistNode.style.wordWrap = 'break-word';
        artistNode.style.marginTop = 'auto';
        artistNode.style.marginBottom = (100 - cfg.artist_position) + '%';
        artistNode.title = artist;

        // Добавляем элементы
        textContainer.appendChild(titleNode);
        textContainer.appendChild(artistNode);
        cell.appendChild(textContainer);
        grid.appendChild(cell);
    }
}

/** Показать уведомление */
function showNotification(message, type = 'info') {
    // Создаем элемент уведомления
    const notification = document.createElement('div');
    notification.style.cssText = [
        'position:fixed',
        'top:20px',
        'right:20px',
        'padding:15px 20px',
        'border-radius:8px',
        'color:white',
        'font-weight:bold',
        'z-index:10000',
        'max-width:400px',
        'box-shadow:0 4px 12px rgba(0,0,0,0.3)',
        'transition:all 0.3s ease',
        'transform:translateX(100%)',
        'opacity:0'
    ].join(';');

    // Цвет в зависимости от типа
    if (type === 'success') {
        notification.style.background = 'linear-gradient(135deg, #10b981, #059669)';
    } else if (type === 'error') {
        notification.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
    } else {
        notification.style.background = 'linear-gradient(135deg, #3b82f6, #2563eb)';
    }

    notification.textContent = message;
    document.body.appendChild(notification);

    // Анимация появления
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
        notification.style.opacity = '1';
    }, 100);

    // Автоматическое скрытие
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

/** Генерация билетов (запрос на сервер) */
async function generateTickets() {
    const count = parseInt(document.getElementById('t_count')?.value || '10', 10);
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
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Генерация...';

    try {
        showNotification('🚀 Начинаем генерацию билетов...', 'info');

        console.log('📤 Отправка запроса на:', TICKETS_API);
        console.log('📦 Данные:', { count, design });

        const resp = await fetch(TICKETS_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ count, design })
        });

        console.log('📥 Ответ сервера:', resp.status, resp.statusText);

        if (!resp.ok) {
            let errorMessage = `HTTP ${resp.status}`;
            try {
                const errorData = await resp.json();
                errorMessage = errorData.detail || errorMessage;
                console.log('📋 Детали ошибки:', errorData);
            } catch (e) {
                const text = await resp.text();
                if (text) {
                    errorMessage = text;
                    console.log('📋 Текст ошибки:', text);
                }
            }

            // Проверим доступность endpointа
            try {
                const testResp = await fetch(TICKETS_API, { method: 'OPTIONS' });
                console.log('🔧 OPTIONS запрос:', testResp.status);
            } catch (testErr) {
                console.log('🔧 OPTIONS ошибка:', testErr);
            }

            throw new Error(errorMessage);
        }

        const result = await resp.json();
        console.log('✅ Успешный ответ:', result);

        if (result && result.file) {
            // Автоматическое скачивание файла
            const downloadUrl = result.file.startsWith('http') ? result.file : API_BASE_URL + result.file;

            showNotification(`✅ Сгенерировано ${count} билетов!`, 'success');

            // Небольшая задержка перед открытием файла
            setTimeout(() => {
                window.open(downloadUrl, '_blank');
            }, 1000);

        } else {
            throw new Error('Сервер вернул неожиданный ответ: ' + JSON.stringify(result));
        }
    } catch (err) {
        console.error('[tickets] generate error', err);

        // Более информативные сообщения об ошибках
        let userMessage = err.message;
        if (err.message.includes('404')) {
            userMessage = 'Endpoint не найден. Проверьте подключение роутера билетов.';
        } else if (err.message.includes('Failed to fetch')) {
            userMessage = 'Не удалось подключиться к серверу. Проверьте: ' + API_BASE_URL;
        } else if (err.message.includes('Нет треков')) {
            userMessage = 'В медиатеке нет треков. Сначала загрузите треки.';
        }

        showNotification('❌ Ошибка: ' + userMessage, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
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
        if (!slider) return;

        // Создаем элемент для отображения значения, если его нет
        let displayEl = document.getElementById(displayId);
        if (!displayEl) {
            displayEl = document.createElement('div');
            displayEl.id = displayId;
            displayEl.style.cssText = 'font-size:12px; color:#4E7CFF; font-weight:bold; margin-top:4px;';
            slider.parentNode.appendChild(displayEl);
        }

        // Функция обновления значения
        const updateValue = () => {
            let valueText = slider.value;
            if (id === 't_title_position' || id === 't_artist_position') {
                valueText += '%';
            } else if (id === 't_vertical_padding') {
                valueText += 'px';
            }
            displayEl.textContent = valueText;
        };

        // Инициализация и слушатели
        updateValue();
        slider.addEventListener('input', updateValue);
        slider.addEventListener('change', updateValue);
    });
}

/** Привязка событий */
function attachTicketSettingsEvents() {
    const ids = [
        't_font', 't_title_size', 't_artist_size', 't_text_color', 't_accent_color',
        't_bold', 't_upper', 't_title_position', 't_artist_position', 't_vertical_padding'
    ];

    ids.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;

        // Для слайдеров используем debounce чтобы не перегружать
        if (id.includes('position') || id.includes('padding')) {
            let timeout;
            el.addEventListener('input', () => {
                clearTimeout(timeout);
                timeout = setTimeout(updateTicketPreview, 100);
            });
            el.addEventListener('change', updateTicketPreview);
        } else {
            el.addEventListener('input', updateTicketPreview);
            el.addEventListener('change', updateTicketPreview);
        }
    });

    const genBtn = document.getElementById('generateTicketsBtn');
    if (genBtn) genBtn.addEventListener('click', generateTickets);

    // Обновление при изменении размера окна
    window.addEventListener('resize', updateTicketPreview);

    // Настройка отображения значений слайдеров
    setupSliderValueDisplays();
}

/** Инициализация */
document.addEventListener('DOMContentLoaded', () => {
    console.log('🎫 Инициализация модуля билетов...');

    attachTicketSettingsEvents();
    setupSliderValueDisplays();

    // Пытаемся загрузить треки
    loadTracksForTickets().catch(e => {
        console.warn('[tickets] Ошибка загрузки треков:', e);
    });

    // Начальное обновление превью
    setTimeout(updateTicketPreview, 500);

    console.log('🎫 Модуль билетов инициализирован');
});

// Глобальные функции для отладки
window.ticketsDebug = {
    reloadTracks: () => {
        console.log('🔄 Принудительная перезагрузка треков...');
        loadTracksForTickets().catch(console.error);
    },
    showTrackCount: () => {
        console.log('📊 Треков в системе:', allTracks ? allTracks.length : 0);
        return allTracks ? allTracks.length : 0;
    },
    regeneratePreview: () => {
        console.log('🔄 Перегенерация превью...');
        regeneratePreviewTracks();
    },
    testAPI: async () => {
        console.log('🧪 Тестирование API...');
        try {
            const resp = await fetch(TICKETS_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ count: 1 }) });
            console.log('API Response:', resp.status, resp.statusText);
            return resp.status;
        } catch (err) {
            console.error('API Test Error:', err);
            return err.message;
        }
    }
};