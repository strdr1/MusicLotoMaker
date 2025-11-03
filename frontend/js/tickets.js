// static/js/tickets.js
// Исправленная версия с автоматическим обновлением треков

const API_BASE_URL = '/api';
const TRACKS_ENDPOINTS = ['/api/tracks'];

const TICKETS_API = `/api/tickets/generate`;
let allTracks = [];
let previewTracks = [];
let autoRefreshInterval = null;
let lastTrackCount = 0;

/** Установка значений по умолчанию */
function setDefaultTicketSettings() {
    console.log('🎨 Установка настроек билетов по умолчанию...');

    // Устанавливаем значения по умолчанию
    const elements = {
        't_text_color': '#666666',
        't_accent_color': '#000000',
        't_title_position': 0,
        't_artist_position': 90,
        't_vertical_padding': 5,
        't_bold': true, // чекбокс включен по умолчанию
        't_upper': false // чекбокс выключен по умолчанию
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

/** Генерация случайного набора треков для превью */
function generateRandomPreviewTracks() {
    if (!allTracks || allTracks.length < 36) {
        return [];
    }

    // Всегда генерируем новый случайный набор при обновлении
    const shuffled = [...allTracks].sort(() => Math.random() - 0.5);
    previewTracks = shuffled.slice(0, 36);
    console.log('🎲 Сгенерирован новый набор превью треков');

    return previewTracks;
}

/** Перегенерировать превью треки */
function regeneratePreviewTracks() {
    if (allTracks && allTracks.length >= 36) {
        const shuffled = [...allTracks].sort(() => Math.random() - 0.5);
        previewTracks = shuffled.slice(0, 36);
        console.log('🔄 Превью треки перегенерированы');
        updateTicketPreview();
    }
}

/** Загрузка треков для билетов с принудительным обновлением */
async function loadTracksForTickets(forceRefresh = false) {
    let lastErr = null;

    // Сбрасываем preview если принудительное обновление
    if (forceRefresh) {
        previewTracks = [];
        console.log('🔄 Принудительное обновление треков...');
    }

    for (const url of TRACKS_ENDPOINTS) {
        try {
            console.log('[tickets] попытка fetch', url);

            // Добавляем timestamp для избежания кеширования
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

            // Универсальное извлечение массива треков
            const arr = (() => {
                if (Array.isArray(data)) return data;
                if (Array.isArray(data.tracks)) return data.tracks;
                if (Array.isArray(data.data)) return data.data;
                // ищем первый массив в объекте
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

            // Проверяем, изменилось ли количество треков
            const newTrackCount = arr.length;
            const tracksChanged = newTrackCount !== lastTrackCount;

            allTracks = arr;
            lastTrackCount = newTrackCount;

            console.log(`[tickets] загружено треков: ${allTracks.length} из ${url}, изменилось: ${tracksChanged}`);

            // Всегда сбрасываем preview при обновлении треков
            previewTracks = [];

            updatePreviewStats();
            updateTicketPreview();

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
}

/** Автоматическое обновление треков каждые 10 секунд */
function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }

    autoRefreshInterval = setInterval(() => {
        // Обновляем только если вкладка активна
        if (!document.hidden) {
            console.log('🔄 Авто-обновление треков...');
            loadTracksForTickets(true).catch(console.error);
        }
    }, 10000); // 10 секунд

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
            // При возвращении на вкладку сразу обновляем треки
            console.log('📱 Возврат на вкладку - обновляем треки');
            loadTracksForTickets(true).catch(console.error);
        }
    });
}

/** Чтение настроек UI с новыми названиями */
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

/** Обновление увеличенного превью 6x6 с белым фоном */
function updateTicketPreview() {
    console.log('🔄 Обновление превью билета...');

    const cfg = readTicketDesignFromUI();
    const previewCard = document.getElementById('ticketPreviewCard');
    const grid = document.getElementById('ticketPreviewGrid');
    const titleEl = document.getElementById('ticketPreviewTitle');

    if (!previewCard || !grid || !titleEl) {
        console.error('❌ Элементы превью не найдены');
        return;
    }

    // Заголовок (Билет №)
    titleEl.style.color = '#000000';
    titleEl.style.fontFamily = cfg.font_family;
    titleEl.style.textTransform = cfg.uppercase ? 'uppercase' : 'none';
    titleEl.style.fontWeight = cfg.bold ? '700' : '600';

    updatePreviewStats();

    if (!allTracks || allTracks.length < 36) {
        const needed = 36 - (allTracks ? allTracks.length : 0);
        setPreviewDebug(`❗ Для генерации билета требуется минимум 36 треков.\n\n` +
            `Найдено треков: ${allTracks ? allTracks.length : 0}\n` +
            `Необходимо ещё: ${needed} треков\n\n` +
            `Загрузите треки во вкладке "📁 Медиатека"`);
        return;
    }

    grid.innerHTML = '';
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(6, 1fr)';
    grid.style.gap = '8px';
    grid.style.padding = '15px';
    grid.style.background = '#ffffff';

    // Всегда генерируем новый случайный набор
    const currentPreviewTracks = generateRandomPreviewTracks();

    for (let i = 0; i < 36; i++) {
        const track = currentPreviewTracks[i] || { title: `Трек ${i + 1}`, artist: 'Артист' };
        const titleText = cfg.uppercase ? (track.title || `Трек ${i + 1}`).toUpperCase() : (track.title || `Трек ${i + 1}`);
        const artistText = cfg.uppercase ? (track.artist || 'Артист').toUpperCase() : (track.artist || 'Артист');

        const cell = document.createElement('div');
        cell.style.cssText = [
            'display:flex', 'flex-direction:column', 'justify-content:flex-start',
            'align-items:center', 'border-radius:8px', 'background:#ffffff',
            'padding:' + cfg.vertical_padding + 'px', 'border:2px solid #e0e0e0',
            'min-height:80px', 'box-sizing:border-box', 'overflow:hidden',
            'position:relative', 'transition:all 0.3s ease', 'cursor:pointer'
        ].join(';');

        cell.onmouseover = () => {
            cell.style.background = '#f8f9fa';
            cell.style.borderColor = cfg.accent_color;
            cell.style.transform = 'translateY(-2px) scale(1.02)';
            cell.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.1)';
        };
        cell.onmouseout = () => {
            cell.style.background = '#ffffff';
            cell.style.borderColor = '#e0e0e0';
            cell.style.transform = 'translateY(0) scale(1)';
            cell.style.boxShadow = 'none';
        };

        const textContainer = document.createElement('div');
        textContainer.style.cssText = [
            'position:absolute', 'top:0', 'left:0', 'right:0', 'bottom:0',
            'display:flex', 'flex-direction:column', 'justify-content:space-between',
            'padding:' + cfg.vertical_padding + 'px', 'box-sizing:border-box'
        ].join(';');

        const titleNode = document.createElement('div');
        titleNode.textContent = titleText;
        titleNode.style.fontFamily = cfg.font_family;
        titleNode.style.fontSize = Math.max(6, cfg.title_size) + 'px';
        titleNode.style.fontWeight = cfg.bold ? '700' : '400';
        titleNode.style.color = cfg.accent_color;
        titleNode.style.textAlign = 'center';
        titleNode.style.textTransform = cfg.uppercase ? 'uppercase' : 'none';
        titleNode.style.lineHeight = '1.1';
        titleNode.style.whiteSpace = 'normal';
        titleNode.style.wordWrap = 'break-word';
        titleNode.style.marginTop = cfg.title_position + '%';

        const artistNode = document.createElement('div');
        artistNode.textContent = artistText;
        artistNode.style.fontFamily = cfg.font_family;
        artistNode.style.fontSize = Math.max(6, cfg.artist_size) + 'px';
        artistNode.style.color = cfg.text_color;
        artistNode.style.opacity = '0.9';
        artistNode.style.textAlign = 'center';
        artistNode.style.textTransform = cfg.uppercase ? 'uppercase' : 'none';
        artistNode.style.lineHeight = '1.1';
        artistNode.style.whiteSpace = 'normal';
        artistNode.style.wordWrap = 'break-word';
        artistNode.style.marginTop = 'auto';
        artistNode.style.marginBottom = (100 - cfg.artist_position) + '%';

        textContainer.appendChild(titleNode);
        textContainer.appendChild(artistNode);
        cell.appendChild(textContainer);
        grid.appendChild(cell);
    }

    console.log('✅ Превью билета обновлено');
}

/** Показать уведомление */
function showNotification(message, type = 'info') {
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

    if (type === 'success') {
        notification.style.background = 'linear-gradient(135deg, #10b981, #059669)';
    } else if (type === 'error') {
        notification.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
    } else {
        notification.style.background = 'linear-gradient(135deg, #3b82f6, #2563eb)';
    }

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

            // --- НОВАЯ ЛОГИКА: Автоматическое скачивание ---
            const fullUrl = result.download_url.startsWith('/')
                ? `${window.location.origin}${result.download_url}`
                : result.download_url;

            // Создаем временную ссылку для скачивания
            const link = document.createElement('a');
            link.href = fullUrl;
            link.download = result.zip_file; // Указываем имя файла

            // Добавляем в DOM, кликаем и удаляем
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            console.log('✅ Автоматическое скачивание запущено:', result.zip_file);

            // --- НОВАЯ ЛОГИКА: Показать блок загрузки с информацией ---
            const downloadSection = document.getElementById('downloadSection');
            if (downloadSection) {
                // Заполняем информацию о скачивании
                document.getElementById('downloadFileName').textContent = result.zip_file || '-';
                // API не возвращает tickets_count и tracks_used, используем переданные значения
                document.getElementById('downloadTicketsCount').textContent = result.tickets_count || count;
                document.getElementById('downloadTracksUsed').textContent = result.tracks_used || '36'; // Или длина allTracks

                // Показываем блок
                downloadSection.style.display = 'block';

                // Привязываем событие к кнопке скачивания на случай, если пользователь захочет снова скачать
                const downloadBtn = document.getElementById('downloadTicketsBtn');
                if (downloadBtn) {
                    downloadBtn.onclick = function () {
                        console.log('🎫 Повторное нажатие кнопки скачивания');
                        // Повторяем логику скачивания
                        const link = document.createElement('a');
                        link.href = fullUrl;
                        link.download = result.zip_file;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    };
                }
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


/** Простая функция скачивания (теперь используется только для повторного скачивания) */
function downloadFile(downloadUrl, filename) {
    console.log('🎫 downloadFile вызвана:', downloadUrl, filename);

    try {
        // Проверяем входные параметры
        if (!downloadUrl || !filename) {
            throw new Error('Не указан URL или имя файла для скачивания');
        }

        const fullUrl = downloadUrl.startsWith('/')
            ? `${window.location.origin}${downloadUrl}`
            : downloadUrl;
        console.log('🎫 Полный URL для скачивания:', fullUrl);

        // Создаем временную ссылку для скачивания
        const link = document.createElement('a');
        link.href = fullUrl;
        link.download = filename;

        // Добавляем в DOM, кликаем и удаляем
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showNotification(`📦 Файл "${filename}" начал скачивание...`, 'success');

        // Логируем успешное скачивание
        console.log('🎫 ✅ Скачивание запущено:', {
            url: fullUrl,
            filename: filename,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        console.error('❌ Ошибка скачивания:', error);
        showNotification(`❌ Ошибка при скачивании файла: ${error.message}`, 'error');

        // Fallback: открываем в новом окне
        try {
            const fullUrl = `${API_BASE_URL}${downloadUrl}`;
            window.open(fullUrl, '_blank');
            showNotification('📦 Файл открывается в новом окне...', 'info');
        } catch (fallbackError) {
            console.error('❌ Fallback также не сработал:', fallbackError);
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
        if (!el) {
            console.warn(`❌ Элемент не найден: ${id}`);
            return;
        }

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

    // Кнопка обновления треков
    const refreshBtn = document.getElementById('refreshTracksBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadTracksForTickets(true).catch(console.error);
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

    // Устанавливаем настройки по умолчанию
    setDefaultTicketSettings();

    attachTicketSettingsEvents();
    setupSliderValueDisplays();

    // Пытаемся загрузить треки
    loadTracksForTickets().catch(e => {
        console.warn('[tickets] Ошибка загрузки треков:', e);
    });

    // Запускаем авто-обновление
    startAutoRefresh();

    // Настраиваем обработчик видимости вкладки
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
    regeneratePreview: () => {
        console.log('🔄 Перегенерация превью...');
        regeneratePreviewTracks();
    },
    startAutoRefresh: () => {
        startAutoRefresh();
    },
    stopAutoRefresh: () => {
        stopAutoRefresh();
    }
};