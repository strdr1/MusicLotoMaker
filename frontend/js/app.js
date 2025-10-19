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
let isUploading = false;

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

    document.getElementById('photoModal').addEventListener('click', function (e) {
        if (e.target === this) {
            closePhotoModal();
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

        // Горячие клавиши для фото модалки
        if (document.getElementById('photoModal').style.display === 'block') {
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
            <div class="col-actions">
                <button class="btn btn-secondary btn-small" onclick="openAudioEditor(${track.id})" title="Аудио редактор">
                    🎚️ Редактор
                </button>
                <button class="btn btn-secondary btn-small" onclick="editTrack(${track.id})" title="Редактировать метаданные">
                    ✏️ Текст
                </button>
                <button class="btn btn-secondary btn-small" onclick="addArtistPhoto(${track.id})" title="Добавить фото артиста">
                    📷 Фото
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

        // Загружаем обновленный список треков
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

// =========================
// ARTIST PHOTO FUNCTIONS
// =========================

// Функция для добавления фото артиста
async function addArtistPhoto(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) {
        showNotification('Трек не найден', 'error');
        return;
    }

    currentPhotoTrackId = trackId;
    currentPhotoUrls = [];
    currentPhotoIndex = 0;

    // Показываем модальное окно
    document.getElementById('photoArtistName').textContent = track.artist;
    document.getElementById('photoPreview').style.display = 'none';
    document.getElementById('photoStatus').style.display = 'none';

    // Очищаем предыдущую навигацию
    const previewContainer = document.getElementById('photoPreview');
    const existingNav = previewContainer.querySelector('.photo-navigation');
    if (existingNav) {
        existingNav.remove();
    }

    document.getElementById('photoModal').style.display = 'block';
}

// Функция для поиска фото в интернете
async function searchArtistPhoto() {
    if (!currentPhotoTrackId || isSearchingPhotos) return;

    const track = currentTracks.find(t => t.id === currentPhotoTrackId);
    if (!track) return;

    isSearchingPhotos = true;
    showPhotoStatus('🔍 Ищем фото артиста...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentPhotoTrackId}/search-artist-photo`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
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

// Показать текущее фото
function showCurrentPhoto() {
    if (currentPhotoUrls.length === 0) return;

    const photoUrl = currentPhotoUrls[currentPhotoIndex];
    const previewImg = document.getElementById('photoPreviewImage');
    const previewContainer = document.getElementById('photoPreview');

    // Показываем загрузку
    previewImg.style.display = 'none';
    previewContainer.style.display = 'block';

    // Загружаем изображение
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

// Обновить навигацию по фото
function updatePhotoNavigation() {
    const previewContainer = document.getElementById('photoPreview');
    const existingNav = previewContainer.querySelector('.photo-navigation');

    if (existingNav) {
        existingNav.remove();
    }

    const navHtml = `
        <div class="photo-navigation" style="margin-top: 15px;">
            <div style="display: flex; gap: 10px; justify-content: center; align-items: center; margin-bottom: 10px;">
                <button class="btn btn-small" onclick="previousPhoto()" ${currentPhotoIndex === 0 ? 'disabled' : ''} style="min-width: 80px;">
                    ⬅️ Назад
                </button>
                <span style="color: var(--text-muted); font-weight: 600; min-width: 60px; text-align: center;">
                    ${currentPhotoIndex + 1} / ${currentPhotoUrls.length}
                </span>
                <button class="btn btn-small" onclick="nextPhoto()" ${currentPhotoIndex === currentPhotoUrls.length - 1 ? 'disabled' : ''} style="min-width: 80px;">
                    Вперед ➡️
                </button>
            </div>
            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                <button class="btn btn-small btn-primary" onclick="saveCurrentPhoto()" style="min-width: 140px;">
                    ✅ Сохранить это фото
                </button>
                <button class="btn btn-small btn-secondary" onclick="searchArtistPhoto()" ${isSearchingPhotos ? 'disabled' : ''} style="min-width: 140px;">
                    ${isSearchingPhotos ? '🔍 Поиск...' : '🔄 Найти другие'}
                </button>
                <button class="btn btn-small btn-warning" onclick="uploadArtistPhoto()" style="min-width: 140px;">
                    📁 Загрузить своё
                </button>
            </div>
        </div>
    `;
    previewContainer.insertAdjacentHTML('beforeend', navHtml);
}

// Навигация по фото
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

// Сохранить текущее фото
async function saveCurrentPhoto() {
    if (!currentPhotoTrackId || currentPhotoUrls.length === 0) return;

    const photoUrl = currentPhotoUrls[currentPhotoIndex];

    showPhotoStatus('💾 Сохраняем фото...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentPhotoTrackId}/save-artist-photo`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
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
                loadTracks(); // Обновляем список треков
            }, 1500);
        } else {
            showPhotoStatus('❌ Ошибка сохранения фото', 'error');
        }

    } catch (error) {
        console.error('Ошибка сохранения фото:', error);
        showPhotoStatus('❌ Ошибка сохранения фото', 'error');
    }
}

// Функция для загрузки своего фото
function uploadArtistPhoto() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';

    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Проверяем тип файла
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
                    loadTracks(); // Обновляем список треков
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

// Вспомогательная функция для показа статуса
function showPhotoStatus(message, type) {
    const statusElement = document.getElementById('photoStatus');
    statusElement.innerHTML = message;
    statusElement.className = `status ${type}`;
    statusElement.style.display = 'block';
}

// Закрытие модального окна
function closePhotoModal() {
    document.getElementById('photoModal').style.display = 'none';
    currentPhotoTrackId = null;
    currentPhotoUrls = [];
    currentPhotoIndex = 0;
    isSearchingPhotos = false;
}

// =========================
// TRACK MANAGEMENT FUNCTIONS
// =========================

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
                <div class="status-item ${status.tracks_with_photos > 0 ? 'success' : 'warning'}">
                    <span class="label">Треков с фото:</span>
                    <span class="value">${status.tracks_with_photos || 0}</span>
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

// Обновление информации о треке в редактора
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
            const result = await response.json();
            showNotification('Отрезок сохранен! Файл создан: ' + (result.clip_path || 'успешно'), 'success');
            closeAudioEditor();
            await loadTracks();

            // Дополнительно создаем файл отрезка для гарантии
            await generateSegmentFile(currentEditorTrack, segmentStart, segmentDuration);
        } else {
            throw new Error('Save failed');
        }
    } catch (error) {
        console.error('Error saving segment:', error);
        showNotification('Ошибка сохранения отрезка', 'error');
    }
}

// Создание файла отрезка
async function generateSegmentFile(trackId, startTime, duration) {
    try {
        const response = await fetch(`${API_BASE}/tracks/${trackId}/generate-segment-file`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                start_time: startTime,
                duration: duration
            })
        });

        if (response.ok) {
            const result = await response.json();
            console.log('✅ Файл отрезка создан:', result.clip_path);
            return result.clip_path;
        } else {
            console.warn('⚠️ Не удалось создать файл отрезка');
            return null;
        }
    } catch (error) {
        console.error('Ошибка создания файла отрезка:', error);
        return null;
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