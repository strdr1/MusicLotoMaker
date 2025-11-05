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
let isUploading = false;
// === Upload queue & progress (многопоточная загрузка) ===
const MAX_FILES_TOTAL = 120;           // верхний предел выбранных файлов
const MAX_CONCURRENT_UPLOADS = 6;      // параллельно грузим до 6

let uploadQueue = [];                  // очередь File объектов
let activeUploads = 0;                 // сколько сейчас в полёте
let currentUploads = new Map();        // id -> { xhr, file, rowEl }
let uploadCounter = 0;                 // для уникальных id строк

// элементы панели прогресса
const uploadPanel = () => document.getElementById('uploadProgressPanel');
const uploadRows = () => document.getElementById('uploadRows');
const uploadSummary = () => document.getElementById('uploadSummary');
const cancelAllBtn = () => document.getElementById('cancelAllUploadsBtn');
// Volume Control
let currentVolume = 50;
let isMuted = false;

// Drag & Drop для отрезка
let isDragging = false;
let dragType = null;
let dragStartX = 0;
let initialSegmentStart = 0;

// Photo Management
let currentPhotoTrackId = null;
let currentPhotoUrls = [];
let currentPhotoIndex = 0;
let isSearchingPhotos = false;

// Track Download
let isDownloading = false;

// ===== helpers (селекторы и генератор кнопки) =====
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
 
    refreshArtistPhotos();
    refreshBasePptx();

    // авто-обновление счётчика каждые 10 сек
    setInterval(updateTracksCount, 10000);

    // обновляем при возвращении на вкладку браузера
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) updateTracksCount();
    });

    // если сразу открыта вкладка презентации — инициализируем превью
    const activeTab = document.querySelector('.tab-btn.active')?.dataset?.tab;
    if (activeTab === 'presentation') {
        initPresentationDesigner();
    }
});

function setupEventListeners() {
    // Отмена всех загрузок
    const cancelAll = document.getElementById('cancelAllUploadsBtn');
    if (cancelAll) {
        cancelAll.addEventListener('click', cancelAllUploads);
    }

    // предупреждать, если есть активные загрузки
    window.addEventListener('beforeunload', (e) => {
        if (activeUploads > 0 || uploadQueue.length > 0) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
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
// DEBUG FUNCTIONS
// =========================

function addDebugButton() {
    const toolbar = document.querySelector('.toolbar');
    if (toolbar && !document.getElementById('debugBtn')) {
        const debugBtn = document.createElement('button');
        debugBtn.id = 'debugBtn';
        debugBtn.className = 'btn btn-warning';
        debugBtn.innerHTML = '🐛 Debug';
        debugBtn.onclick = debugCurrentButton;
        debugBtn.title = 'Отладочная информация о текущей кнопке';
        toolbar.appendChild(debugBtn);
    }
}

async function debugCurrentButton() {
    try {
        showNotification('🔍 Проверяем текущую кнопку...', 'info');

        // Проверяем конфигурацию
        const configResponse = await fetch(`${API_BASE}/debug/current-config`);
        const configData = await configResponse.json();

        console.log('🔧 DEBUG CONFIG:', configData);

        let debugInfo = `📋 Конфигурация:\n`;
        debugInfo += `- Файл конфига: ${configData.config_exists ? '✅ существует' : '❌ не существует'}\n`;
        debugInfo += `- Путь к кнопке: ${configData.custom_button_path || '❌ не установлен'}\n`;
        debugInfo += `- Background: ${JSON.stringify(configData.background_config || {})}\n`;

        // Если есть путь к кнопке, проверяем файл
        if (configData.custom_button_path) {
            const filename = configData.custom_button_path.split('/').pop();
            const fileResponse = await fetch(`${API_BASE}/debug/check-file/${filename}`);
            const fileData = await fileResponse.json();

            console.log('📁 DEBUG FILE:', fileData);

            debugInfo += `\n📁 Проверка файла "${filename}":\n`;
            fileData.results.forEach(result => {
                debugInfo += `- ${result.path}: ${result.exists ? `✅ существует (${result.size} байт)` : '❌ не существует'}\n`;
            });

            if (fileData.dir_contents && fileData.dir_contents.length > 0) {
                debugInfo += `\n📂 Содержимое custom_buttons:\n`;
                fileData.dir_contents.forEach(file => {
                    debugInfo += `- ${file}\n`;
                });
            }
        }

        // Проверяем фоновые изображения
        if (configData.background_config && configData.background_config.imageURL) {
            const bgFilename = configData.background_config.imageURL.split('/').pop();
            const bgResponse = await fetch(`${API_BASE}/debug/check-file/${bgFilename}`);
            const bgData = await bgResponse.json();

            debugInfo += `\n🎨 Проверка фона "${bgFilename}":\n`;
            bgData.results.forEach(result => {
                debugInfo += `- ${result.path}: ${result.exists ? `✅ существует (${result.size} байт)` : '❌ не существует'}\n`;
            });

            if (bgData.bg_contents && bgData.bg_contents.length > 0) {
                debugInfo += `\n📂 Содержимое backgrounds:\n`;
                bgData.bg_contents.forEach(file => {
                    debugInfo += `- ${file}\n`;
                });
            }
        }

        // Показываем информацию в alert и в консоли
        alert(debugInfo);
        console.log(debugInfo);

    } catch (error) {
        console.error('❌ Ошибка отладки:', error);
        showNotification('❌ Ошибка отладки', 'error');
    }
}

async function debugCheckButtonFile(filename) {
    try {
        const response = await fetch(`${API_BASE}/debug/check-file/${filename}`);
        const data = await response.json();
        console.log('🔍 DEBUG FILE CHECK:', data);
        return data;
    } catch (error) {
        console.error('❌ Ошибка проверки файла:', error);
        return null;
    }
}

// =========================
// INTERNET TRACK DOWNLOAD FUNCTIONS
// =========================

async function downloadTrackList() {
    if (isDownloading) {
        showNotification('Загрузка уже выполняется', 'warning');
        return;
    }

    const trackListText = document.getElementById('trackList').value.trim();
    if (!trackListText) {
        showNotification('Введите список треков для скачивания', 'warning');
        return;
    }

    isDownloading = true;
    showNotification('🔄 Начинаем скачивание треков...', 'info');

    // Показываем прогресс
    updateDownloadProgress(0, 1, 'Подготовка...');

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

        if (!response.ok) {
            throw new Error('Ошибка скачивания треков');
        }

        const result = await response.json();

        if (result.success) {
            const successCount = result.downloaded || 0;
            const totalCount = result.results.length;

            showNotification(`✅ Скачано ${successCount} из ${totalCount} треков`, 'success');

            // Показываем детали результатов
            showDownloadResults(result.results);

            // Обновляем список треков
            await loadTracks();

            // Обновляем счетчик треков
            updateTracksCount();
        } else {
            throw new Error(result.message || 'Ошибка скачивания');
        }

    } catch (error) {
        console.error('❌ Ошибка скачивания треков:', error);
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    } finally {
        isDownloading = false;
        updateDownloadProgress(0, 0, 'Завершено');
    }
}

function showDownloadResults(results) {
    const progressDetails = document.getElementById('progressDetails');
    if (!progressDetails) return;

    let html = '<div style="max-height: 200px; overflow-y: auto;">';

    results.forEach((result, index) => {
        const statusClass = result.success ? 'status-found' : 'status-error';
        const statusIcon = result.success ? '✅' : '❌';
        const sourceInfo = result.source ? ` (${result.source})` : '';

        html += `
            <div class="track-status ${statusClass}" style="margin: 4px 0; padding: 6px; border-radius: 4px;">
                <span style="font-weight: 600;">${index + 1}.</span>
                ${statusIcon} ${escapeHtml(result.original_line)}${sourceInfo}
                ${!result.success ? `<br><small style="color: var(--text-muted);">Ошибка: ${result.error}</small>` : ''}
            </div>
        `;
    });

    html += '</div>';
    progressDetails.innerHTML = html;

    // Показываем статистику
    const successCount = results.filter(r => r.success).length;
    const totalCount = results.length;

    const statsHtml = `
        <div style="margin-top: 10px; padding: 8px; background: var(--bg-dark); border-radius: 4px;">
            <strong>Статистика:</strong> ${successCount}/${totalCount} успешно
            (${Math.round((successCount / totalCount) * 100)}%)
            <br><small style="color: var(--text-muted);">
                Источник: YouTube Music
            </small>
        </div>
    `;

    progressDetails.insertAdjacentHTML('beforeend', statsHtml);
}

async function testParseTrackList() {
    const trackListText = document.getElementById('trackList').value.trim();
    if (!trackListText) {
        showNotification('Введите список треков для проверки', 'warning');
        return;
    }

    try {
        const tracks = parseTrackListClient(trackListText);

        showNotification(`🔍 Распознано ${tracks.length} треков`, 'info');

        // Показываем детали в блоке прогресса
        const progressDetails = document.getElementById('progressDetails');
        if (progressDetails) {
            let html = '<div style="max-height: 200px; overflow-y: auto;">';

            tracks.forEach((track, i) => {
                const artistDisplay = track.artist || '<span style="color: var(--warning)">Не указан</span>';
                html += `
                    <div style="margin: 4px 0; padding: 6px; background: var(--bg-dark); border-radius: 4px;">
                        <strong>${i + 1}.</strong> 
                        <span style="color: var(--primary)">${escapeHtml(artistDisplay)}</span> - 
                        <strong>${escapeHtml(track.title)}</strong>
                    </div>
                `;
            });

            html += '</div>';
            progressDetails.innerHTML = html;
        }

    } catch (error) {
        console.error('❌ Ошибка парсинга списка:', error);
        showNotification('Ошибка анализа списка треков', 'error');
    }
}

function parseTrackListClient(text) {
    const tracks = [];
    const lines = text.split('\n');

    lines.forEach(line => {
        line = line.trim();
        if (!line) return;

        let artist = '', title = '';

        // Пробуем разные форматы
        const separators = [' - ', ' – ', ' — ', ' | '];
        let found = false;

        for (const sep of separators) {
            if (line.includes(sep)) {
                const parts = line.split(sep);
                if (parts.length >= 2) {
                    artist = parts[0].trim();
                    title = parts.slice(1).join(sep).trim();
                    found = true;
                    break;
                }
            }
        }

        // Формат "Название (Исполнитель)"
        if (!found) {
            const match = line.match(/(.+?)\s+\((.+?)\)$/);
            if (match) {
                title = match[1].trim();
                artist = match[2].trim();
                found = true;
            }
        }

        // Если формат не распознан, считаем всю строку названием
        if (!found) {
            title = line;
            artist = '';
        }

        tracks.push({ artist, title, original_line: line });
    });

    return tracks;
}

function clearTrackList() {
    document.getElementById('trackList').value = '';
    const progressDetails = document.getElementById('progressDetails');
    if (progressDetails) progressDetails.innerHTML = '';
}

function updateDownloadProgress(current, total, status) {
    const progressFill = document.getElementById('progressFill');
    const progressStatus = document.getElementById('progressStatus');
    const progressCount = document.getElementById('progressCount');
    const progressPanel = document.getElementById('listSearchProgress');

    if (progressFill && progressStatus && progressCount && progressPanel) {
        const percent = total > 0 ? (current / total) * 100 : 0;
        progressFill.style.width = `${percent}%`;
        progressStatus.textContent = status;
        progressCount.textContent = total > 0 ? `${current}/${total}` : '';
        progressPanel.style.display = 'block';
    }
}

// =========================
// DESIGN MANAGEMENT FUNCTIONS
// =========================

async function saveDesignAsDefault() {
    const saveBtn = document.getElementById('d_save_btn');
    const statusEl = document.getElementById('d_save_status');

    if (!saveBtn || !statusEl) return;

    try {
        saveBtn.disabled = true;
        statusEl.style.display = 'block';
        statusEl.textContent = '💾 Сохраняем дизайн...';
        statusEl.className = 'status loading';

        const designConfig = readDesignFromUI();

        console.log('🎨 DESIGN CONFIG TO SAVE:', designConfig);

        const response = await fetch(`${API_BASE}/config/presentation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(designConfig)
        });

        if (!response.ok) {
            throw new Error('Ошибка сохранения');
        }

        const result = await response.json();
        console.log('💾 DESIGN SAVE RESPONSE:', result);

        statusEl.textContent = '✅ Дизайн сохранен как стандартный!';
        statusEl.className = 'status success';

        showNotification('Дизайн успешно сохранен как стандартный', 'success');

    } catch (error) {
        console.error('❌ Ошибка сохранения дизайна:', error);
        statusEl.textContent = '❌ Ошибка сохранения дизайна';
        statusEl.className = 'status error';
        showNotification('Ошибка сохранения дизайна', 'error');
    } finally {
        setTimeout(() => {
            statusEl.style.display = 'none';
            saveBtn.disabled = false;
        }, 3000);
    }
}

async function loadSavedDesign() {
    try {
        console.log('🔄 Загружаем сохраненный дизайн...');
        const response = await fetch(`${API_BASE}/config/presentation`);
        if (!response.ok) {
            console.log('❌ Не удалось загрузить дизайн, статус:', response.status);
            return;
        }

        const config = await response.json();
        console.log('📥 LOADED DESIGN CONFIG:', config);
        applyDesignConfig(config);

    } catch (error) {
        console.error('❌ Ошибка загрузки дизайна:', error);
    }
}

function applyDesignConfig(config) {
    if (!config) {
        console.log('⚠️ Конфигурация дизайна пустая');
        return;
    }

    console.log('🎯 APPLYING DESIGN CONFIG:', config);

    setValue('d_font_family', config.fontFamily || config.font_family);
    setValue('d_title_size', config.titleSize || config.title_size);
    setValue('d_text_size', config.textSize || config.text_size);
    setChecked('d_bold_titles', config.boldTitles !== false);
    setChecked('d_upper_titles', config.upperTitles || false);
    setValue('d_text_color', config.textColor || config.text_color);
    setValue('d_accent_color', config.accentColor || config.accent_color);

    setValue('d_layout', config.layout);
    setValue('d_photo_radius', config.photoRadius || config.photo_radius);

    setChecked('d_show_numbers', config.showNumbers !== false);

    const background = config.background || {};
    const bgMode = background.mode || 'solid';
    console.log('🎨 Background mode:', bgMode);

    setRadioValue('bgMode', bgMode);
    setValue('d_bg_color', background.color || '#121B2F');
    setValue('d_grad_from', background.gradFrom || '#1A2340');
    setValue('d_grad_to', background.gradTo || '#0F1623');

    // Восстанавливаем фоновое изображение если есть
    if (bgMode === 'image' && background.imageURL) {
        const filename = background.imageURL.split('/').pop();
        const downloadUrl = `${API_BASE}/download/${filename}`;
        const bgPreview = document.getElementById('d_bg_preview');
        if (bgPreview) {
            bgPreview.src = downloadUrl;
            bgPreview.style.display = 'block';
        }
        console.log('🎯 Восстановлен фон:', downloadUrl);
    } else {
        const bgPreview = document.getElementById('d_bg_preview');
        if (bgPreview) {
            bgPreview.style.display = 'none';
            bgPreview.src = '';
        }
    }

    // Восстанавливаем кастомную кнопку если есть
    if (config.custom_button_path) {
        const filename = config.custom_button_path.split('/').pop();
        const downloadUrl = `${API_BASE}/download/${filename}`;
        updateMiniConstructor(downloadUrl);
        console.log('🎯 Восстановлена кастомная кнопка:', downloadUrl);
    } else {
        updateMiniConstructor(null);
    }

    toggleBgRows();
    drawDesignPreview();

    console.log('✅ Дизайн применен к UI');
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element && value !== undefined) element.value = value;
}

function setChecked(id, checked) {
    const element = document.getElementById(id);
    if (element) element.checked = !!checked;
}

function setRadioValue(name, value) {
    const radio = document.querySelector(`input[name="${name}"][value="${value}"]`);
    if (radio) radio.checked = true;
}

// =========================
// TIMING MANAGEMENT FUNCTIONS
// =========================

async function saveAllTimings() {
    try {
        showNotification('💾 Сохраняем все тайминги в основной файл...', 'info');

        const response = await fetch(`${API_BASE}/tracks/save-all-timings`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Ошибка сохранения таймингов');
        }

        const result = await response.json();

        if (result.success) {
            showNotification(`✅ ${result.message}`, 'success');
        } else {
            throw new Error(result.message || 'Неизвестная ошибка');
        }

    } catch (error) {
        console.error('Ошибка сохранения таймингов:', error);
        showNotification(`❌ Ошибка: ${error.message}`, 'error');
    }
}

function addTimingsButton() {
    const toolbar = document.querySelector('.toolbar');
    if (toolbar && !document.getElementById('saveTimingsBtn')) {
        const timingsBtn = document.createElement('button');
        timingsBtn.id = 'saveTimingsBtn';
        timingsBtn.className = 'btn btn-warning';
        timingsBtn.innerHTML = '💾 Тайминги';
        timingsBtn.onclick = saveAllTimings;
        timingsBtn.title = 'Сохранить все тайминги отрезков в основной JSON файл';
        toolbar.appendChild(timingsBtn);
    }
}

// =========================
// PRESENTATION GENERATION FUNCTIONS
// =========================

async function generatePresentation() {
    const status = document.getElementById("presentationStatus") || document.getElementById("presentation-status");
    const titleInput = document.getElementById("presentation-title");
    const title = titleInput ? titleInput.value.trim() : "";

    // читаем чекбокс (id = "make-bw")
    const makeBWCheckbox = document.getElementById("make-bw");
    const makeBW = !!(makeBWCheckbox && makeBWCheckbox.checked);

    if (!title) {
        if (status) {
            status.textContent = "⚠️ Пожалуйста, введите название презентации.";
            status.style.color = "#f87171";
        }
        return;
    }

    if (status) {
        status.textContent = "⏳ Генерация презентации...";
        status.style.color = "#9ca3af";
    }

    try {
        const payload = {
            title,
            design: { make_bw: makeBW }
        };

        // ИСПРАВЛЕНИЕ: используем правильную константу API_BASE вместо API_BASE_URL
        const response = await fetch(`${API_BASE}/generate/presentation`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (status) {
                status.textContent = "✅ Презентация успешно создана!";
                status.style.color = "#34d399";

                // Если есть ссылка для скачивания, показываем её
                if (data.download_url) {
                    status.innerHTML += `<br><a href="${data.download_url}" class="download-link" download>📥 Скачать презентацию</a>`;
                }
            }
        } else {
            if (status) {
                status.textContent = "❌ Ошибка: " + (data.message || data.detail || "Не удалось создать презентацию.");
                status.style.color = "#f87171";
            }
        }
    } catch (error) {
        console.error("Ошибка при генерации презентации:", error);
        if (status) {
            status.textContent = "❌ Ошибка соединения с сервером.";
            status.style.color = "#f87171";
        }
    }
}



// Вспомогательная функция для получения количества треков
async function getTracksCount() {
    try {
        const response = await fetch(`${API_BASE}/tracks/count`);
        if (response.ok) {
            const data = await response.json();
            return data.count || 0;
        }
    } catch (error) {
        console.error("Ошибка получения количества треков:", error);
    }
    return 0;
}

async function generateTickets() {
    const count = parseInt(document.getElementById('ticketsCount').value) || 24;

    if (count < 1 || count > 100) {
        showNotification('Количество билетов должно быть от 1 до 100', 'warning');
        return;
    }

    showStatus('ticketsStatus', '🔄 Генерируем билеты...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tickets/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                count: count,
                template_id: 'tickets_default'
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Ошибка генерации');
        }

        const result = await response.json();

        if (result.success) {
            const downloadHref = `${API_BASE}/download/${result.file}`;
            showStatus('ticketsStatus',
                `✅ ${result.message}<br>
                 <a href="${downloadHref}" class="download-link" download>
                    📥 Скачать билеты (PDF)
                 </a>`,
                'success'
            );

            showNotification(`Создано ${count} билетов!`, 'success');
        } else {
            throw new Error(result.message || 'Ошибка генерации');
        }

    } catch (error) {
        console.error('Ошибка генерации билетов:', error);
        showStatus('ticketsStatus', `❌ Ошибка: ${error.message}`, 'error');
        showNotification('Ошибка создания билетов', 'error');
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
                initPresentationDesigner();
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

    isUploading = false;

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
            throw new Error('Ошибка сохранения фото');
        }

        const result = await response.json();

        if (result.success) {
            showPhotoStatus('✅ Фото артиста сохранено!', 'success');
            setTimeout(() => {
                closePhotoModal();
                loadTracks();
            }, 1500);
        } else {
            showPhotoStatus('❌ Ошибка сохранения фото', 'error');
        }

    } catch (error) {
        console.error('Ошибка сохранения фото:', error);
        showPhotoStatus('❌ Ошибка сохранения фото', 'error');
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
                throw new Error('Ошибка загрузки фото');
            }

            const result = await response.json();

            if (result.success) {
                showPhotoStatus('✅ Фото артиста загружено!', 'success');
                setTimeout(() => {
                    closePhotoModal();
                    loadTracks();
                }, 1500);
            } else {
                showPhotoStatus('❌ Ошибка загрузки фото', 'error');
            }

        } catch (error) {
            console.error('Ошибка загрузки фото:', error);
            showPhotoStatus('❌ Ошибка загрузки фото', 'error');
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

// Обработчик ошибок
window.addEventListener('error', function (e) {
    console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', function (e) {
    console.error('Unhandled promise rejection:', e.reason);
    e.preventDefault();
});

console.log('🎵 Music Loto Maker frontend загружен!');

/* =======================
   MINI-DESIGNER (preview)
   ======================= */

const Designer = {
    loaded: false,
    customButtonObjectURL: null,
    bgObjectURL: null,
};

(function ensureRoundRectPolyfill() {
    const p = window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
    if (p && typeof p.roundRect !== 'function') {
        p.roundRect = function (x, y, w, h, r = 0) {
            r = Math.max(0, Math.min(r, Math.min(w, h) / 2));
            this.beginPath();
            this.moveTo(x + r, y);
            this.lineTo(x + w - r, y);
            this.arcTo(x + w, y, x + w, y + r, r);
            this.lineTo(x + w, y + h - r);
            this.arcTo(x + w, y + h, x + w - r, y + h, r);
            this.lineTo(x + r, y + h);
            this.arcTo(x, y + h, x, y + h - r, r);
            this.lineTo(x, y + r);
            this.arcTo(x, y, x + r, y, r);
            return this;
        };
    }
})();

let _designResizeObs = null;
function ensureDesignCanvasSize() {
    const canvas = document.getElementById('designPreview');
    const holder = canvas?.parentElement;
    if (!canvas || !holder) return false;

    const cssW = Math.max(320, holder.clientWidth);
    const cssH = Math.max(220, Math.floor(holder.clientWidth * 9 / 16));
    const needResize = canvas.width !== cssW || canvas.height !== cssH;
    if (needResize) {
        canvas.width = cssW;
        canvas.height = cssH;
    }

    if (!_designResizeObs) {
        _designResizeObs = new ResizeObserver(() => {
            const beforeW = canvas.width, beforeH = canvas.height;
            const ok = ensureDesignCanvasSize();
            if (ok && (canvas.width !== beforeW || canvas.height !== beforeH)) {
                drawDesignPreview();
            }
        });
        _designResizeObs.observe(holder);
    }
    return true;
}

function readDesignFromUI() {
    const design = {
        fontFamily: document.getElementById("d_font_family").value,
        titleSize: parseInt(document.getElementById("d_title_size").value),
        textSize: parseInt(document.getElementById("d_text_size").value),
        boldTitles: document.getElementById("d_bold_titles").checked,
        upperTitles: document.getElementById("d_upper_titles").checked,
        textColor: document.getElementById("d_text_color").value,
        accentColor: document.getElementById("d_accent_color").value,
        layout: document.getElementById("d_layout").value,
        photoRadius: parseInt(document.getElementById("d_photo_radius").value),
        showNumbers: document.getElementById("d_show_numbers").checked,
        custom_button_path: null, // Будет установлено ниже
        background: getBackgroundConfig()
    };

    // Получаем актуальный путь к кнопке из конфигурации
    const btnPrev = document.getElementById('d_btn_preview');
    if (btnPrev && btnPrev.src && btnPrev.style.display !== 'none') {
        const src = btnPrev.src;
        if (src.includes('/api/download/')) {
            const filename = src.split('/api/download/')[1].split('?')[0];
            design.custom_button_path = `assets/custom_buttons/${filename}`;
            console.log('🎯 Установлен custom_button_path:', design.custom_button_path);
        }
    }

    console.log("🎨 DESIGN OBJ TO SEND:", design);
    return design;
}

function drawDesignPreview() {
    const canvas = document.getElementById('designPreview');
    if (!canvas) return;
    ensureDesignCanvasSize();
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width, H = canvas.height;
    const cfg = readDesignFromUI();

    if (cfg.background.mode === 'solid') {
        ctx.fillStyle = cfg.background.color;
        ctx.fillRect(0, 0, W, H);
        drawContent();
    } else if (cfg.background.mode === 'gradient') {
        const g = ctx.createLinearGradient(0, 0, W, H);
        g.addColorStop(0, cfg.background.gradFrom);
        g.addColorStop(1, cfg.background.gradTo);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
        drawContent();
    } else {
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, W, H);
        const url = cfg.background.imageURL;
        if (url) {
            const img = new Image();
            img.onload = () => {
                const r1 = W / H, r2 = img.width / img.height;
                let w, h, x, y;
                if (r2 > r1) { h = H; w = r2 * H; x = (W - w) / 2; y = 0; }
                else { w = W; h = W / r2; x = 0; y = (H - h) / 2; }
                ctx.drawImage(img, x, y, w, h);
                drawContent();
            };
            img.onerror = drawContent;
            img.src = url;
        } else {
            drawContent();
        }
    }

    function drawContent() {
        const pad = 32;
        const photoSize = Math.min(W, H) * 0.35;
        let photoX = pad, photoY = pad;
        let textX = photoX + photoSize + pad, textW = W - textX - pad;

        if (cfg.layout === 'photo_right') {
            photoX = W - pad - photoSize;
            textX = pad; textW = W - photoSize - pad * 3;
        } else if (cfg.layout === 'photo_top') {
            photoX = (W - photoSize) / 2;
            textX = pad; textW = W - pad * 2;
            photoY = pad;
        } else if (cfg.layout === 'photo_only') {
            photoX = (W - photoSize) / 2;
            photoY = (H - photoSize) / 2 - 40;
            textX = pad; textW = W - pad * 2;
        }

        ctx.fillStyle = 'rgba(255,255,255,0.10)';
        ctx.strokeStyle = 'rgba(255,255,255,0.28)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.roundRect(photoX, photoY, photoSize, photoSize, cfg.photoRadius);
        ctx.fill();
        ctx.stroke();

        const title = (cfg.upperTitles ? 'БОЛЬШОЕ МУЗЛОТО' : 'Большое МузЛото');
        ctx.fillStyle = cfg.textColor;
        ctx.textBaseline = 'top';
        ctx.font = `${cfg.boldTitles ? '700 ' : ''}${cfg.titleSize}px ${cfg.fontFamily}`;
        ctx.fillText(title, textX, photoY);

        ctx.font = `400 ${cfg.textSize}px ${cfg.fontFamily}`;
        ctx.fillStyle = cfg.textColor + 'cc';
        const sub = 'Юрий Шатунов — Седая ночь';
        wrapText(ctx, sub, textX, photoY + cfg.titleSize + 8, textW, cfg.textSize + 6);

        const btnW = 160, btnH = 100, bx = W - btnW - pad, by = H - btnH - pad;

        // Используем кастомную кнопку если есть
        if (cfg.custom_button_path) {
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, bx, by, btnW, btnH);
                if (cfg.showNumbers) drawNumber();
            };
            img.onerror = () => drawFallbackButton();
            const filename = cfg.custom_button_path.split('/').pop();
            img.src = `${API_BASE}/download/${filename}?t=${Date.now()}`;
        } else {
            drawFallbackButton();
        }

        function drawFallbackButton() {
            ctx.fillStyle = 'rgba(255,255,255,0.12)';
            ctx.strokeStyle = cfg.accentColor;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.roundRect(bx, by, btnW, btnH, 12);
            ctx.fill();
            ctx.stroke();
            if (cfg.showNumbers) drawNumber();
        }

        function drawNumber() {
            ctx.fillStyle = '#fff';
            ctx.font = `700 ${Math.floor(btnH * 0.45)}px ${cfg.fontFamily}`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('12', bx + btnW / 2, by + btnH / 2 + 2);
            ctx.textAlign = 'start';
            ctx.textBaseline = 'alphabetic';
        }
    }

    function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
        const words = text.split(' ');
        let line = '';
        for (let i = 0; i < words.length; i++) {
            const test = line + words[i] + ' ';
            const w = ctx.measureText(test).width;
            if (w > maxWidth && i > 0) {
                ctx.fillText(line, x, y);
                line = words[i] + ' ';
                y += lineHeight;
            } else {
                line = test;
            }
        }
        ctx.fillText(line, x, y);
    }
}

function bindDesignerEvents() {
    const root = document.querySelector('#presentation .settings-card');
    if (!root) return;

    const rerender = () => drawDesignPreview();

    root.querySelectorAll('input, select').forEach(el => {
        el.addEventListener('input', rerender);
        el.addEventListener('change', rerender);
    });

    const radios = root.querySelectorAll('input[name="bgMode"]');
    const rowSolid = document.getElementById('bgSolidRow');
    const rowGrad = document.getElementById('bgGradientRow');
    const rowImg = document.getElementById('bgImageRow');
    function toggleBgRows() {
        const mode = root.querySelector('input[name="bgMode"]:checked')?.value || 'solid';
        rowSolid.style.display = mode === 'solid' ? 'flex' : 'none';
        rowGrad.style.display = mode === 'gradient' ? 'flex' : 'none';
        rowImg.style.display = mode === 'image' ? 'flex' : 'none';
    }
    radios.forEach(r => r.addEventListener('change', () => { toggleBgRows(); rerender(); }));
    toggleBgRows();

    // Обработчик загрузки кастомной кнопки
    const btnUpload = document.getElementById('d_btn_upload');
    const btnReset = document.getElementById('d_btn_reset');

    if (btnUpload) {
        btnUpload.addEventListener('change', async () => {
            const file = btnUpload.files?.[0];
            if (!file) return;

            showNotification('🔼 Загружаем кнопку...', 'info');

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch(`${API_BASE}/assets/custom-button`, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error('Ошибка загрузки');
                }

                const result = await response.json();

                if (result.success) {
                    // Обновляем превью
                    const downloadUrl = `${API_BASE}/download/${result.filename}?t=${Date.now()}`;
                    updateMiniConstructor(downloadUrl);

                    showNotification('✅ Кнопка загружена!', 'success');
                    console.log('🎯 Кнопка загружена:', result);

                    // Проверяем файл
                    await debugCheckButtonFile(result.filename);
                } else {
                    throw new Error(result.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                console.error('❌ Ошибка загрузки кнопки:', error);
                showNotification('❌ Ошибка загрузки кнопки', 'error');
            }
        });
    }

    if (btnReset) {
        btnReset.addEventListener('click', async () => {
            try {
                showNotification('🔄 Сбрасываем кнопку...', 'info');

                // Обновляем конфигурацию
                const configResponse = await fetch(`${API_BASE}/config/presentation`);
                if (configResponse.ok) {
                    const config = await configResponse.json();
                    config.custom_button_path = null;

                    await fetch(`${API_BASE}/config/presentation`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(config)
                    });
                }

                // Обновляем UI
                updateMiniConstructor(null);
                showNotification('✅ Кнопка сброшена', 'success');

            } catch (error) {
                console.error('❌ Ошибка сброса кнопки:', error);
                showNotification('❌ Ошибка сброса кнопки', 'error');
            }
        });
    }

    const bgUpload = document.getElementById('d_bg_upload');
    const bgReset = document.getElementById('d_bg_reset');
    const bgPrev = document.getElementById('d_bg_preview');

    if (bgUpload) {
        bgUpload.addEventListener('change', async () => {
            const file = bgUpload.files?.[0];
            if (!file) return;

            showNotification('🔼 Загружаем фон...', 'info');

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch(`${API_BASE}/assets/background`, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error('Ошибка загрузки');
                }

                const result = await response.json();

                if (result.success) {
                    // Обновляем превью
                    const downloadUrl = `${API_BASE}/download/${result.filename}?t=${Date.now()}`;
                    bgPrev.src = downloadUrl;
                    bgPrev.style.display = 'inline-block';

                    // Устанавливаем режим "image"
                    const radio = document.querySelector('input[name="bgMode"][value="image"]');
                    if (radio) radio.checked = true;

                    // Обновляем строки отображения
                    document.getElementById('bgSolidRow').style.display = 'none';
                    document.getElementById('bgGradientRow').style.display = 'none';
                    document.getElementById('bgImageRow').style.display = 'flex';

                    showNotification('✅ Фон загружен!', 'success');
                    drawDesignPreview();

                } else {
                    throw new Error(result.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                console.error('❌ Ошибка загрузки фона:', error);
                showNotification('❌ Ошибка загрузки фона', 'error');
            }
        });
    }

    if (bgReset) {
        bgReset.addEventListener('click', () => {
            // Сбрасываем на сплошной цвет
            const radio = document.querySelector('input[name="bgMode"][value="solid"]');
            if (radio) radio.checked = true;

            document.getElementById('bgSolidRow').style.display = 'flex';
            document.getElementById('bgGradientRow').style.display = 'none';
            document.getElementById('bgImageRow').style.display = 'none';

            if (bgPrev) {
                bgPrev.style.display = 'none';
                bgPrev.src = '';
            }
            if (bgUpload) bgUpload.value = '';

            drawDesignPreview();
            showNotification('Фон сброшен', 'info');
        });
    }

    const saveBtn = document.getElementById('d_save_btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveDesignAsDefault);
    }
}

// Глобальная функция обновления мини-конструктора
window.updateMiniConstructor = function (customButtonPath) {
    const preview = document.getElementById("d_btn_preview");
    if (preview) {
        if (customButtonPath) {
            preview.src = customButtonPath;
            preview.style.display = "block";
            console.log('🎯 Превью кнопки обновлено:', customButtonPath);
        } else {
            preview.style.display = "none";
            preview.src = "";
            console.log('🎯 Превью кнопки скрыто');
        }
    }
    if (typeof drawDesignPreview === "function") {
        drawDesignPreview();
    }
};

async function initPresentationDesigner() {
    if (Designer.loaded) {
        drawDesignPreview();
        return;
    }

    bindDesignerEvents();
    ensureDesignCanvasSize();

    await loadSavedDesign();

    drawDesignPreview();

    Designer.loaded = true;
}
// =========================
// DROPBOX DOWNLOAD FUNCTIONS (только скачивание)
// =========================

async function downloadBasePptxFromDropbox() {
    try {
        showNotification('📥 Скачиваем base.pptx из облака...', 'info');

        const response = await fetch('/api/dropbox/download-base-pptx', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showNotification('✅ base.pptx успешно скачан!', 'success');
            refreshBasePptx();
        } else {
            showNotification(`❌ Ошибка: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Ошибка скачивания base.pptx:', error);
        showNotification('❌ Ошибка скачивания из облака', 'error');
    }
}

async function downloadArtistPhotosFromDropbox() {
    try {
        showNotification('📥 Скачиваем фото артистов из облака...', 'info');

        const response = await fetch('/api/dropbox/download-artist-photos', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showNotification(`✅ Скачано ${data.photos?.length || 0} фото артистов!`, 'success');
            refreshArtistPhotos();
        } else {
            showNotification(`❌ Ошибка: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Ошибка скачивания фото:', error);
        showNotification('❌ Ошибка скачивания фото из облака', 'error');
    }
}

async function checkDropboxPhotos() {
    try {
        const response = await fetch('/api/dropbox/available-photos');
        const data = await response.json();

        if (data.photos && data.photos.length > 0) {
            return data.photos;
        }
        return [];
    } catch (error) {
        console.error('Ошибка проверки Dropbox:', error);
        return [];
    }
}

// =========================
// LOCAL FILES MANAGEMENT
// =========================

async function uploadArtistPhotos() {
    const input = document.getElementById('uploadArtistPhotos');
    if (!input || !input.files || input.files.length === 0) {
        showNotification('❌ Выберите фото для загрузки', 'error');
        return;
    }

    const files = Array.from(input.files);
    console.log('📤 Загрузка фото:', files.map(f => f.name));

    showNotification(`📤 Загружаем ${files.length} фото...`, 'info');

    const formData = new FormData();
    files.forEach(file => {
        formData.append('files', file);
    });

    try {
        const res = await fetch('/api/local/upload-artist-photos', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        console.log('📥 Ответ сервера:', data);

        if (data.success) {
            showNotification(`✅ ${data.message}`, 'success');
            // Очищаем input
            input.value = '';
            // Обновляем список фото
            refreshArtistPhotos();
        } else {
            showNotification(`❌ Ошибка: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('❌ Ошибка загрузки фото:', error);
        showNotification('❌ Ошибка соединения с сервером', 'error');
    }
}

async function refreshArtistPhotos() {
    try {
        console.log('🔄 Обновление списка фото...');
        const res = await fetch('/api/local/artist-photos');
        const data = await res.json();
        const container = document.getElementById('artistPhotosList');
        const countElement = document.getElementById('photosCount');

        console.log('📊 Данные фото:', data);

        // Обновляем счетчик
        if (countElement) {
            const count = data.photos ? data.photos.length : 0;
            countElement.textContent = `${count} ${getPhotoWord(count)}`;
        }

        if (!data.photos || data.photos.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
                    <div class="icon" style="font-size: 64px; margin-bottom: 16px;">🖼️</div>
                    <h3 style="margin: 0 0 8px 0; color: var(--text-light);">Нет загруженных фото</h3>
                    <p style="margin: 0; color: var(--text-muted);">Загрузите фото артистов для использования в презентациях</p>
                </div>
            `;
            return;
        }

        container.innerHTML = data.photos.map(photo => `
            <div class="artist-photo-card">
                <img src="${photo.url}?t=${Date.now()}" 
                     alt="${photo.artist_name}"
                     onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjE0MCIgdmlld0JveD0iMCAwIDIwMCAxNDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjIwMCIgaGVpZ2h0PSIxNDAiIGZpbGw9IiMxRjJGMzgiIHJ4PSI4Ii8+PHRleHQgeD0iMTAwIiB5PSI3MCIgZm9udC1mYW1pbHk9IkFyaWFsLCBzYW5zLXNlcmlmIiBmb250LXNpemU9IjE0IiBmaWxsPSIjNkM3MjdCIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSI+${photo.artist_name}</dGV4dD48L3N2Zz4='">
                <div class="filename">${escapeHtml(photo.artist_name)}</div>
                <div style="font-size: 12px; color: var(--text-muted); text-align: center; margin-bottom: 12px;">
                    ${photo.size_mb || ''}
                </div>
                <div class="photo-actions">
                    <a href="${photo.url}" target="_blank" class="download-link" title="Просмотр">
                        <span class="icon">👁️</span>
                        Просмотр
                    </a>
                    <button class="btn btn-danger btn-small" onclick="deleteArtistPhoto('${photo.filename}')" title="Удалить">
                        <span class="icon">🗑️</span>
                        Удалить
                    </button>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('❌ Ошибка обновления списка фото:', error);
        const container = document.getElementById('artistPhotosList');
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
                <div class="icon" style="font-size: 64px; margin-bottom: 16px;">❌</div>
                <h3 style="margin: 0 0 8px 0; color: var(--error);">Ошибка загрузки</h3>
                <p style="margin: 0; color: var(--text-muted);">Не удалось загрузить список фото</p>
            </div>
        `;
    }
}

// Вспомогательная функция для правильного склонения
function getPhotoWord(count) {
    if (count % 10 === 1 && count % 100 !== 11) return 'фото';
    if (count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 10 || count % 100 >= 20)) return 'фото';
    return 'фото';
}

async function deleteArtistPhoto(filename) {
    if (!confirm(`Удалить фото ${filename}?`)) return;

    try {
        const res = await fetch(`/api/local/artist-photo/${filename}`, {
            method: 'DELETE'
        });

        const data = await res.json();
        if (data.success) {
            showNotification('✅ Фото удалено', 'success');
            refreshArtistPhotos();
        } else {
            showNotification(`❌ Ошибка удаления: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Ошибка удаления фото:', error);
        showNotification('❌ Ошибка удаления фото', 'error');
    }
}

async function uploadBasePptx() {
    const input = document.getElementById('uploadBasePptx');
    if (!input || !input.files || input.files.length === 0) {
        showNotification('❌ Выберите файл base.pptx', 'error');
        return;
    }

    const file = input.files[0];
    console.log('📤 Загрузка base.pptx:', file.name, file.size, file.type);

    showNotification(`📤 Загружаем ${file.name}...`, 'info');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/local/upload-base-pptx', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        console.log('📥 Ответ сервера:', data);

        if (data.success) {
            showNotification(`✅ ${data.message} (${(data.size / 1024 / 1024).toFixed(2)} MB)`, 'success');
            // Очищаем input
            input.value = '';
            // Обновляем информацию
            refreshBasePptx();
        } else {
            showNotification(`❌ Ошибка: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('❌ Ошибка загрузки base.pptx:', error);
        showNotification('❌ Ошибка соединения с сервером', 'error');
    }
}

async function refreshBasePptx() {
    try {
        console.log('🔄 Обновление информации о base.pptx...');
        const res = await fetch('/api/local/base-pptx');
        const data = await res.json();
        const block = document.getElementById('basePptxBlock');

        console.log('📊 Данные base.pptx:', data);

        if (data.exists) {
            const sizeMB = (data.size / 1024 / 1024).toFixed(2);
            const statusClass = data.size > 0 ? 'success' : 'warning';

            block.innerHTML = `
                <div class="base-pptx-info">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                        <div>
                            <h4 style="margin: 0 0 8px 0; color: var(--text-light);">📄 base.pptx</h4>
                            <p style="margin: 0; color: var(--text-muted);">${data.message || 'Шаблон презентации готов к использованию'}</p>
                        </div>
                        <span class="status-indicator ${statusClass}">
                            ${data.size > 0 ? '✅ Готов' : '⚠️ Ошибка'}
                        </span>
                    </div>
                    
                    <div class="file-info">
                        <div><strong>Размер:</strong> ${sizeMB} MB</div>
                        <div><strong>Статус:</strong> Файл найден</div>
                        <div><strong>Путь:</strong> /base.pptx</div>
                    </div>
                    
                    <div class="pptx-actions">
                        <a href="${data.download_url}" class="btn btn-primary" download>
                            <span class="icon">📥</span>
                            Скачать шаблон
                        </a>
                        <button class="btn btn-secondary" onclick="document.getElementById('uploadBasePptx').click()">
                            <span class="icon">🔄</span>
                            Заменить файл
                        </button>
                        <button class="btn btn-warning" onclick="downloadBasePptxFromDropbox()">
                            <span class="icon">📥</span>
                            Скачать из облака
                        </button>
                    </div>
                </div>
            `;
        } else {
            block.innerHTML = `
                <div class="base-pptx-info">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                        <div>
                            <h4 style="margin: 0 0 8px 0; color: var(--text-light);">📄 base.pptx</h4>
                            <p style="margin: 0; color: var(--text-muted);">${data.message || 'Шаблон презентации не найден'}</p>
                        </div>
                        <span class="status-indicator error">❌ Отсутствует</span>
                    </div>
                    
                    <div class="file-info">
                        <div><strong>Статус:</strong> Файл не найден</div>
                        <div><strong>Решение:</strong> Загрузите или скачайте шаблон</div>
                    </div>
                    
                    <div class="pptx-actions">
                        <button class="btn btn-primary" onclick="document.getElementById('uploadBasePptx').click()">
                            <span class="icon">📤</span>
                            Загрузить файл
                        </button>
                        <button class="btn btn-primary" onclick="downloadBasePptxFromDropbox()">
                            <span class="icon">📥</span>
                            Скачать из облака
                        </button>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('❌ Ошибка обновления информации о base.pptx:', error);
        const block = document.getElementById('basePptxBlock');
        block.innerHTML = `
            <div class="base-pptx-info">
                <div style="text-align: center; color: var(--error);">
                    <h4>❌ Ошибка загрузки</h4>
                    <p>Не удалось получить информацию о base.pptx</p>
                </div>
            </div>
        `;
    }
}

// Инициализация файловой системы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Инициализация файловой системы...');

    // Обработчики загрузки файлов
    const baseInput = document.getElementById('uploadBasePptx');
    if (baseInput) {
        baseInput.addEventListener('change', function (e) {
            console.log('📄 Base PPTX выбран:', e.target.files[0]);
            if (e.target.files.length > 0) {
                uploadBasePptx();
            }
        });
    }

    const photosInput = document.getElementById('uploadArtistPhotos');
    if (photosInput) {
        photosInput.addEventListener('change', function (e) {
            console.log('🖼️ Фото выбраны:', e.target.files);
            if (e.target.files.length > 0) {
                uploadArtistPhotos();
            }
        });
    }

    // Инициализация данных
    refreshArtistPhotos();
    refreshBasePptx();

    console.log('✅ Файловая система готова');
});



// 🔧 Защита от отсутствия функции getBackgroundConfig
if (typeof getBackgroundConfig === "undefined") {
    function getBackgroundConfig() {
        const mode = document.querySelector('input[name="bgMode"]:checked')?.value || "solid";
        const color = document.getElementById("d_bg_color")?.value || "#121B2F";
        const gradFrom = document.getElementById("d_grad_from")?.value || "#1A2340";
        const gradTo = document.getElementById("d_grad_to")?.value || "#0F1623";

        // Получаем URL фонового изображения из превью
        let imageURL = null;
        const bgPreview = document.getElementById('d_bg_preview');
        if (mode === 'image' && bgPreview && bgPreview.style.display !== 'none' && bgPreview.src) {
            imageURL = bgPreview.src;
        }

        return { mode, color, gradFrom, gradTo, imageURL };
    }
    console.warn("⚠️ getBackgroundConfig was missing — added fallback implementation.");
}

// ============================================================
// --- FIX --- КОНЕЦ блока исправлений
// ============================================================