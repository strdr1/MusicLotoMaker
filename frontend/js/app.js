// frontend/js/app.js
const API_BASE = 'http://127.0.0.1:8000/api';

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

// Volume Control
let currentVolume = 50;
let isMuted = false;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();

    // Обработчик загрузки файлов
    document.getElementById('fileInput').addEventListener('change', handleFileUpload);

    // Обработчик закрытия модальных окон
    document.getElementById('editModal').addEventListener('click', function (e) {
        if (e.target === this) {
            closeEditModal();
        }
    });

    document.getElementById('audioEditorModal').addEventListener('click', function (e) {
        if (e.target === this) {
            closeAudioEditor();
        }
    });
});

// Управление вкладками
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            // Сбрасываем активные элементы
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            // Активируем выбранную вкладку
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');

            // Обновляем данные если нужно
            if (btn.dataset.tab === 'status') {
                loadSystemStatus();
            } else if (btn.dataset.tab === 'presentation') {
                updateTracksCount();
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
            <div class="col-artist">${escapeHtml(track.artist)}</div>
            <div class="col-title">${escapeHtml(track.title)}</div>
            <div class="col-actions">
                <button class="btn btn-secondary btn-small" onclick="openAudioEditor(${track.id})" title="Аудио редактор">
                    🎚️ Редактор
                </button>
                <button class="btn btn-secondary btn-small" onclick="editTrack(${track.id})" title="Редактировать метаданные">
                    ✏️ Текст
                </button>
                <button class="btn btn-danger btn-small" onclick="deleteTrack(${track.id})" title="Удалить">
                    🗑️ Удалить
                </button>
            </div>
        </div>
    `).join('');
}

// Загрузка файлов
async function handleFileUpload(event) {
    const files = event.target.files;
    if (files.length === 0) return;

    showStatus('mediaStatus', `🔄 Загружаем ${files.length} файл(ов)...`, 'loading');

    const formData = new FormData();
    for (let file of files) {
        formData.append('files', file);
    }

    try {
        const response = await fetch(`${API_BASE}/tracks/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        showStatus('mediaStatus', `✅ ${result.message}`, 'success');
        loadTracks(); // Перезагружаем список

    } catch (error) {
        console.error('Ошибка загрузки:', error);
        showStatus('mediaStatus', `❌ Ошибка: ${error.message}`, 'error');
    }

    // Сбрасываем input
    event.target.value = '';
}

// Редактирование трека
async function editTrack(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) {
        showNotification('Трек не найден', 'error');
        return;
    }

    currentEditingTrack = track;

    // Заполняем форму
    document.getElementById('editTrackId').value = track.id;
    document.getElementById('editArtist').value = track.artist;
    document.getElementById('editTitle').value = track.title;

    // Показываем модальное окно
    document.getElementById('editModal').style.display = 'block';
}

// Закрытие модального окна редактирования
function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
    currentEditingTrack = null;
    document.getElementById('editForm').reset();
}

// Сохранение трека
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
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                artist: artist,
                title: title
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Ошибка обновления');
        }

        showNotification('Трек успешно обновлен', 'success');
        closeEditModal();
        loadTracks(); // Перезагружаем список

    } catch (error) {
        console.error('Ошибка сохранения:', error);
        showNotification(`Ошибка: ${error.message}`, 'error');
    }
}

// Удаление трека
async function deleteTrack(trackId) {
    if (!confirm('Вы уверены, что хотите удалить этот трек?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/tracks/${trackId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Ошибка удаления');
        }

        showNotification('Трек успешно удален', 'success');
        loadTracks(); // Перезагружаем список

    } catch (error) {
        console.error('Ошибка удаления:', error);
        showNotification(`Ошибка: ${error.message}`, 'error');
    }
}

// Очистка всех треков
async function clearTracks() {
    if (!confirm('Вы уверены, что хотите очистить всю медиатеку? Это действие нельзя отменить.')) {
        return;
    }

    showStatus('mediaStatus', '🔄 Очищаем медиатеку...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Ошибка очистки');
        }

        showStatus('mediaStatus', '✅ Медиатека очищена', 'success');
        loadTracks(); // Перезагружаем список

    } catch (error) {
        console.error('Ошибка очистки:', error);
        showStatus('mediaStatus', `❌ Ошибка: ${error.message}`, 'error');
    }
}

// Генерация презентации
async function generatePresentation() {
    const statusElement = document.getElementById('presentationStatus');
    showStatus('presentationStatus', '🔄 Генерируем презентацию...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/generate/presentation`, {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Ошибка генерации');
        }

        const result = await response.json();

        showStatus('presentationStatus',
            `✅ ${result.message} 
             <br><a href="${API_BASE}/download/${result.file_name}" class="download-link" download>
                 📥 Скачать презентацию
             </a>`,
            'success'
        );

        showNotification('Презентация успешно создана!', 'success');

    } catch (error) {
        console.error('Ошибка генерации презентации:', error);
        showStatus('presentationStatus', `❌ Ошибка: ${error.message}`, 'error');
        showNotification('Ошибка создания презентации', 'error');
    }
}

// Генерация билетов
async function generateTickets() {
    const count = parseInt(document.getElementById('ticketsCount').value) || 24;

    if (count < 1 || count > 100) {
        showNotification('Количество билетов должно быть от 1 до 100', 'warning');
        return;
    }

    const statusElement = document.getElementById('ticketsStatus');
    showStatus('ticketsStatus', '🔄 Генерируем билеты...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/generate/tickets?count=${count}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Ошибка генерации');
        }

        const result = await response.json();

        showStatus('ticketsStatus',
            `✅ ${result.message} 
             <br><a href="${API_BASE}/download/${result.file_name}" class="download-link" download>
                 📥 Скачать билеты (PDF)
             </a>`,
            'success'
        );

        showNotification(`Создано ${count} билетов!`, 'success');

    } catch (error) {
        console.error('Ошибка генерации билетов:', error);
        showStatus('ticketsStatus', `❌ Ошибка: ${error.message}`, 'error');
        showNotification('Ошибка создания билетов', 'error');
    }
}

// Загрузка статуса системы
async function loadSystemStatus() {
    const container = document.getElementById('systemStatus');
    container.innerHTML = '<p>🔄 Загружаем информацию о системе...</p>';

    try {
        const response = await fetch(`${API_BASE}/status`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

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

// Обновление счетчика треков
function updateTracksCount() {
    document.getElementById('tracksCount').textContent = currentTracks.length;
}

// Показать статус
function showStatus(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
    element.innerHTML = message;
    element.className = `status ${type}`;
}

// Audio Editor Functions

// Открытие аудио-редактора
async function openAudioEditor(trackId) {
    console.log('Opening audio editor for track:', trackId);

    currentEditorTrack = trackId;

    // Загружаем информацию о треке
    const track = await loadTrackInfo(trackId);
    if (!track) {
        showNotification('Ошибка загрузки трека', 'error');
        return;
    }

    // Устанавливаем начальные значения
    segmentStart = track.segment_start || 0;
    segmentDuration = track.segment_duration || 30;
    totalTrackDuration = track.duration || 0;

    // Показываем модальное окно
    document.getElementById('audioEditorModal').style.display = 'block';

    // Обновляем информацию о треке
    updateTrackInfo(track);

    // Загружаем и отображаем waveform
    await loadWaveform(trackId);

    // Обновляем таймлайн
    updateTimelineDisplay();

    // Скрываем результаты анализа
    document.getElementById('analysisInfo').style.display = 'none';

    // Создаем аудио элемент для воспроизведения
    initAudioPlayer();
}

// Инициализация аудио плеера
function initAudioPlayer() {
    if (audioElement) {
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
}

// Закрытие редактора
function closeAudioEditor() {
    stopPlayback();
    document.getElementById('audioEditorModal').style.display = 'none';
    currentEditorTrack = null;

    if (audioElement) {
        audioElement.remove();
        audioElement = null;
    }
}

// Загрузка информации о треке для редактора
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

// Обновление информации о треке в редакторе
function updateTrackInfo(track) {
    const infoElement = document.getElementById('editorTrackInfo');
    infoElement.innerHTML = `
        <h4>${escapeHtml(track.artist)} - ${escapeHtml(track.title)}</h4>
        <p>Файл: ${track.original_filename}</p>
    `;

    // Обновляем общую длительность
    document.getElementById('totalDuration').textContent = formatTime(totalTrackDuration);
}

// Загрузка waveform
async function loadWaveform(trackId) {
    const container = document.getElementById('waveformContainer');
    container.innerHTML = '<div class="waveform-loading">Генерация waveform...</div>';

    try {
        const response = await fetch(`${API_BASE}/tracks/${trackId}/waveform`);
        if (!response.ok) throw new Error('Failed to load waveform');

        const data = await response.json();

        if (data.waveform_data) {
            container.innerHTML = `
                <img src="${data.waveform_data}" alt="Waveform" class="waveform-image" 
                     onclick="handleWaveformClick(event)" 
                     onload="initSegmentMarker()">
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
    }
}

// Инициализация маркера отрезка
function initSegmentMarker() {
    updateSegmentMarker();
    document.getElementById('segmentMarker').style.display = 'block';
}

// Обновление позиции маркера отрезка
function updateSegmentMarker() {
    const marker = document.getElementById('segmentMarker');
    const container = document.getElementById('waveformContainer');

    if (!marker || !container) return;

    const containerWidth = container.offsetWidth;
    const startPercent = (segmentStart / totalTrackDuration) * 100;
    const durationPercent = (segmentDuration / totalTrackDuration) * 100;

    marker.style.left = startPercent + '%';
    marker.style.width = durationPercent + '%';
}

// Обновление отображения времени
function updateTimelineDisplay() {
    const startTime = segmentStart;
    const endTime = segmentStart + segmentDuration;

    document.getElementById('timeDisplay').textContent =
        `${formatTime(startTime)} - ${formatTime(endTime)}`;

    document.getElementById('segmentStartTime').textContent = formatTime(startTime);
    document.getElementById('segmentEndTime').textContent = formatTime(endTime);
    document.getElementById('segmentDuration').textContent = `${segmentDuration} сек`;

    document.getElementById('previewInfo').textContent =
        `Начните с ${formatTime(startTime)}, длительность ${segmentDuration} секунд`;

    updateSegmentMarker();
}

// Перемещение отрезка
function moveSegment(seconds) {
    const newStart = segmentStart + seconds;

    // Проверяем границы
    if (newStart < 0) {
        segmentStart = 0;
    } else if (newStart + segmentDuration > totalTrackDuration) {
        segmentStart = totalTrackDuration - segmentDuration;
    } else {
        segmentStart = newStart;
    }

    updateTimelineDisplay();
}

// Установка отрезка в начало
function setSegmentToStart() {
    segmentStart = 0;
    updateTimelineDisplay();
}

// Установка отрезка в середину
function setSegmentToMiddle() {
    segmentStart = Math.max(0, (totalTrackDuration - segmentDuration) / 2);
    updateTimelineDisplay();
}

// Установка отрезка в конец
function setSegmentToEnd() {
    segmentStart = Math.max(0, totalTrackDuration - segmentDuration);
    updateTimelineDisplay();
}

// Умный анализ отрезка
async function suggestBestSegment() {
    if (!currentEditorTrack) return;

    try {
        showNotification('🔍 Анализируем аудио...', 'info');

        const response = await fetch(`${API_BASE}/tracks/${currentEditorTrack}/suggest-segment`);
        if (!response.ok) throw new Error('Failed to get suggestion');

        const data = await response.json();
        segmentStart = data.suggested_start;

        // Показываем детали анализа если есть
        if (data.analysis_details) {
            showAnalysisResults(data.analysis_details);
        }

        updateTimelineDisplay();
        showNotification(`🎵 Найден отличный отрезок! Начало: ${formatTime(segmentStart)}`, 'success');

    } catch (error) {
        console.error('Error getting segment suggestion:', error);
        showNotification('Ошибка анализа аудио', 'error');
    }
}

// Показать результаты анализа
function showAnalysisResults(analysis) {
    const analysisInfo = document.getElementById('analysisInfo');
    const analysisResult = document.getElementById('analysisResult');

    analysisInfo.style.display = 'block';

    let html = `
        <div style="margin-bottom: 10px;">
            <strong>Метод:</strong> ${analysis.method}<br>
            <strong>Оценка:</strong> ${(analysis.score * 100).toFixed(1)}%
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

// Воспроизведение отрезка
async function playSegment() {
    if (!currentEditorTrack || isPlaying) return;

    try {
        // Получаем информацию о треке
        const track = await loadTrackInfo(currentEditorTrack);
        if (!track) {
            throw new Error('Track not found');
        }

        // Создаем URL для отрезка через API
        const segmentUrl = `${API_BASE}/tracks/${currentEditorTrack}/segment-file`;

        // Устанавливаем источник для аудио элемента
        audioElement.src = segmentUrl;
        audioElement.currentTime = 0;

        // Пытаемся воспроизвести
        await audioElement.play();

        isPlaying = true;
        updatePlayButton();
        startPlaybackTimer();
        showNotification('Воспроизведение началось', 'success');

    } catch (error) {
        console.error('Error playing segment:', error);
        showNotification('Ошибка воспроизведения. Проверьте аудио файл.', 'error');
    }
}

// Остановка воспроизведения
function stopPlayback() {
    if (audioElement) {
        audioElement.pause();
        audioElement.currentTime = 0;
    }

    isPlaying = false;
    clearInterval(playbackInterval);
    updatePlayButton();
    document.getElementById('playbackTime').textContent = '--:--';
}

// Обновление кнопки воспроизведения
function updatePlayButton() {
    const playBtn = document.getElementById('playBtn');
    const stopBtn = document.getElementById('stopBtn');

    if (isPlaying) {
        playBtn.style.display = 'none';
        stopBtn.style.display = 'block';
    } else {
        playBtn.style.display = 'block';
        stopBtn.style.display = 'none';
    }
}

// Таймер воспроизведения
function startPlaybackTimer() {
    let elapsed = 0;
    document.getElementById('playbackTime').textContent = formatTime(elapsed);

    playbackInterval = setInterval(() => {
        elapsed++;
        document.getElementById('playbackTime').textContent = formatTime(elapsed);

        if (elapsed >= segmentDuration) {
            stopPlayback();
        }
    }, 1000);
}

// Сохранение отрезка
async function saveSegment() {
    if (!currentEditorTrack) return;

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentEditorTrack}/segment`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                start_time: segmentStart,
                duration: segmentDuration
            })
        });

        if (response.ok) {
            showNotification('Отрезок сохранен!', 'success');
            closeAudioEditor();
            loadTracks(); // Обновляем список треков
        } else {
            throw new Error('Save failed');
        }
    } catch (error) {
        console.error('Error saving segment:', error);
        showNotification('Ошибка сохранения отрезка', 'error');
    }
}

// Drag & Drop для отрезка
let isDragging = false;
let dragType = null;
let dragStartX = 0;
let initialSegmentStart = 0;

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

// Клик по waveform для установки начала
function handleWaveformClick(event) {
    if (isDragging) return;

    const container = document.getElementById('waveformContainer');
    const clickX = event.offsetX;
    const clickPercent = (clickX / container.offsetWidth);
    const clickTime = clickPercent * totalTrackDuration;

    // Устанавливаем начало отрезка в место клика
    segmentStart = Math.max(0, Math.min(clickTime, totalTrackDuration - segmentDuration));
    updateTimelineDisplay();
}

// Volume Control Functions
function changeVolume(value) {
    currentVolume = parseInt(value);
    document.getElementById('volumeValue').textContent = value + '%';

    if (audioElement) {
        audioElement.volume = currentVolume / 100;
    }

    // Обновляем иконку
    updateVolumeIcon();
}

function toggleMute() {
    isMuted = !isMuted;

    if (audioElement) {
        audioElement.muted = isMuted;
    }

    updateVolumeIcon();
}

function updateVolumeIcon() {
    const icon = document.getElementById('volumeIcon');
    if (isMuted) {
        icon.textContent = '🔇';
    } else if (currentVolume === 0) {
        icon.textContent = '🔇';
    } else if (currentVolume < 30) {
        icon.textContent = '🔈';
    } else if (currentVolume < 70) {
        icon.textContent = '🔉';
    } else {
        icon.textContent = '🔊';
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
    // Создаем элемент уведомления
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

    // Временные стили для уведомления
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

    // Автоматическое удаление через 5 секунд
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

function getNotificationIcon(type) {
    const icons = {
        'success': '✅',
        'error': '❌',
        'warning': '⚠️',
        'info': 'ℹ️'
    };
    return icons[type] || 'ℹ️';
}

function getNotificationColor(type) {
    const colors = {
        'success': '#16a34a',
        'error': '#dc2626',
        'warning': '#d97706',
        'info': '#2563eb'
    };
    return colors[type] || '#2563eb';
}

// Обработчик ошибок
window.addEventListener('error', function (e) {
    console.error('Global error:', e.error);
    showNotification('Произошла непредвиденная ошибка', 'error');
});

// Обработчик обещаний без catch
window.addEventListener('unhandledrejection', function (e) {
    console.error('Unhandled promise rejection:', e.reason);
    showNotification('Ошибка в асинхронной операции', 'error');
    e.preventDefault();
});

console.log('🎵 Music Loto Maker frontend загружен!');