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
let isGeneratingWaveform = false;
let isUploading = false; // Флаг для предотвращения множественной загрузки

// Volume Control
let currentVolume = 50;
let isMuted = false;

// Drag & Drop для отрезка
let isDragging = false;
let dragType = null;
let dragStartX = 0;
let initialSegmentStart = 0;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();
});

function setupEventListeners() {
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
        if (document.getElementById('audioEditorModal').style.display === 'block') {
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
    });
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

// Загрузка файлов - ИСПРАВЛЕННАЯ (без дублирования)
async function handleFileUpload(event) {
    const files = event.target.files;
    if (files.length === 0 || isUploading) return;

    isUploading = true;
    showStatus('mediaStatus', `🔄 Загружаем ${files.length} файл(ов)...`, 'loading');

    const formData = new FormData();
    for (let file of files) {
        if (file.size > 100 * 1024 * 1024) {
            showNotification(`Файл ${file.name} слишком большой (макс. 100MB)`, 'error');
            continue;
        }
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

        if (result.errors && result.errors.length > 0) {
            showStatus('mediaStatus', `⚠️ Загружено с ошибками: ${result.errors.join(', ')}`, 'warning');
        } else {
            showStatus('mediaStatus', `✅ ${result.message}`, 'success');
        }

        // Загружаем обновленный список треков только один раз
        await loadTracks();

    } catch (error) {
        console.error('Ошибка загрузки:', error);
        showStatus('mediaStatus', `❌ Ошибка: ${error.message}`, 'error');
    } finally {
        // Сбрасываем input и снимаем блокировку
        event.target.value = '';
        isUploading = false;
    }
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
        await loadTracks(); // Перезагружаем список

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
        await loadTracks(); // Перезагружаем список

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
        await loadTracks(); // Перезагружаем список

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

// =========================
// AUDIO EDITOR FUNCTIONS
// =========================

// Открытие аудио-редактора
async function openAudioEditor(trackId) {
    console.log('Opening audio editor for track:', trackId);

    if (isGeneratingWaveform) {
        showNotification('Дождитесь завершения генерации waveform', 'warning');
        return;
    }

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
    totalTrackDuration = track.duration || 180;

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

// Закрытие редактора
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

    document.getElementById('totalDurationDisplay').textContent = formatTime(totalTrackDuration);
}

// Загрузка waveform
async function loadWaveform(trackId) {
    if (isGeneratingWaveform) {
        console.log('Waveform generation already in progress');
        return;
    }

    const container = document.getElementById('waveformContainer');
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

// Обработчик ошибки загрузки waveform
function handleWaveformError() {
    const container = document.getElementById('waveformContainer');
    container.innerHTML = '<div class="waveform-loading">Ошибка загрузки изображения waveform</div>';
    isGeneratingWaveform = false;
}

// Инициализация маркера отрезка
function initSegmentMarker() {
    updateSegmentMarker();
    const marker = document.getElementById('segmentMarker');
    if (marker) {
        marker.style.display = 'block';
    }
    isGeneratingWaveform = false;
}

// Обновление позиции маркера отрезка
function updateSegmentMarker() {
    const marker = document.getElementById('segmentMarker');
    const container = document.getElementById('waveformContainer');

    if (!marker || !container) return;

    const startPercent = (segmentStart / totalTrackDuration) * 100;
    const durationPercent = (segmentDuration / totalTrackDuration) * 100;

    marker.style.left = startPercent + '%';
    marker.style.width = durationPercent + '%';
}

// Обновление отображения времени
function updateTimelineDisplay() {
    const startTime = segmentStart;
    const endTime = Math.min(segmentStart + segmentDuration, totalTrackDuration);

    // Обновляем все отображения времени
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

    document.getElementById('segmentDurationDisplay').textContent = `${segmentDuration} сек`;
    document.getElementById('previewInfo').textContent = `Начните с ${formatTime(startTime)}, длительность ${segmentDuration} секунд`;

    // Обновляем слайдер
    const slider = document.getElementById('timeSlider');
    if (slider) {
        const maxValue = Math.max(0, totalTrackDuration - segmentDuration);
        slider.max = maxValue;
        slider.value = segmentStart;

        slider.disabled = maxValue <= 0;
    }

    updateSegmentMarker();
}

// Перемещение отрезка
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

// Показать результаты анализа
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

// Воспроизведение отрезка
async function playSegment() {
    if (!currentEditorTrack || isPlaying) return;

    try {
        const track = await loadTrackInfo(currentEditorTrack);
        if (!track) {
            throw new Error('Track not found');
        }

        const segmentUrl = `${API_BASE}/tracks/${currentEditorTrack}/segment-file?start_time=${segmentStart}&duration=${segmentDuration}`;

        console.log('Playing from URL:', segmentUrl);

        audioElement.src = segmentUrl;
        audioElement.currentTime = 0;

        const playPromise = audioElement.play();

        if (playPromise !== undefined) {
            await playPromise;
        }

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

// Переключение воспроизведения
function togglePlayback() {
    if (isPlaying) {
        stopPlayback();
    } else {
        playSegment();
    }
}

// Обновление кнопки воспроизведения
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

// Таймер воспроизведения
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
            await loadTracks();
        } else {
            throw new Error('Save failed');
        }
    } catch (error) {
        console.error('Error saving segment:', error);
        showNotification('Ошибка сохранения отрезка', 'error');
    }
}

// Drag & Drop для отрезка
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

// Клик по waveform для установки начала
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
    if (volumeValueElement) {
        volumeValueElement.textContent = value + '%';
    }

    if (audioElement) {
        audioElement.volume = currentVolume / 100;
    }

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
    if (!icon) return;

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
});

window.addEventListener('unhandledrejection', function (e) {
    console.error('Unhandled promise rejection:', e.reason);
    e.preventDefault();
});

console.log('🎵 Music Loto Maker frontend загружен!');
// Функция обновления метаданных трека
async function refreshTrackMetadata(trackId) {
    try {
        showNotification('🔄 Обновляем метаданные...', 'info');

        const response = await fetch(`${API_BASE}/tracks/${trackId}/refresh-metadata`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Ошибка обновления метаданных');
        }

        const result = await response.json();
        showNotification('✅ Метаданные обновлены', 'success');
        loadTracks(); // Перезагружаем список

    } catch (error) {
        console.error('Ошибка обновления метаданных:', error);
        showNotification('❌ Ошибка обновления метаданных', 'error');
    }
}

// Массовое обновление метаданных
async function batchRefreshMetadata() {
    if (!confirm('Обновить метаданные для всех треков? Это может занять некоторое время.')) {
        return;
    }

    try {
        showNotification('🔄 Обновляем метаданные всех треков...', 'info');

        const response = await fetch(`${API_BASE}/tracks/batch-refresh-metadata`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Ошибка массового обновления');
        }

        const result = await response.json();

        if (result.errors && result.errors.length > 0) {
            showNotification(`⚠️ Обновлено ${result.updated} треков. Ошибки: ${result.errors.length}`, 'warning');
        } else {
            showNotification(`✅ Успешно обновлено ${result.updated} треков`, 'success');
        }

        loadTracks();

    } catch (error) {
        console.error('Ошибка массового обновления:', error);
        showNotification('❌ Ошибка обновления метаданных', 'error');
    }
}

// Обновляем отображение треков с обложками
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
            <div class="col-artist">
                ${track.cover_data ?
            `<img src="${track.cover_data}" alt="${escapeHtml(track.artist)}" class="track-cover">` :
            '<div class="track-cover-placeholder">🎵</div>'
        }
                <span>${escapeHtml(track.artist)}</span>
            </div>
            <div class="col-title">${escapeHtml(track.title)}</div>
            <div class="col-actions">
                <button class="btn btn-secondary btn-small" onclick="refreshTrackMetadata(${track.id})" title="Обновить метаданные">
                    🔄 Мета
                </button>
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

// Добавляем кнопку массового обновления в toolbar
function updateToolbar() {
    const toolbar = document.querySelector('.toolbar');
    if (toolbar && !document.getElementById('batchRefreshBtn')) {
        const batchButton = document.createElement('button');
        batchButton.id = 'batchRefreshBtn';
        batchButton.className = 'btn btn-warning';
        batchButton.innerHTML = '🔄 Обновить все метаданные';
        batchButton.onclick = batchRefreshMetadata;
        toolbar.appendChild(batchButton);
    }
}

// Обновляем инициализацию
document.addEventListener('DOMContentLoaded', function () {
    console.log('🎵 Music Loto Maker инициализирован');
    initTabs();
    loadTracks();
    updateTracksCount();
    loadSystemStatus();
    setupEventListeners();
    updateToolbar(); // Добавляем кнопку обновления
});