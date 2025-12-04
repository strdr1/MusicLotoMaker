// track_view_manager.js
// Управление отображением треков в медиатеке с поиском, сортировкой и статистикой

// Глобальные переменные для управления состоянием
let searchQuery = '';
let sortBy = 'id';
let sortDirection = 'asc';
let filterByStatus = 'all'; // 'all', 'processed', 'unprocessed'
let currentPlayingTrackId = null;
let isGlobalPlaying = false;
let globalAudioPlayer = null;

// Для презентаций
let presentationFilterByStatus = 'all';

// Инициализация менеджера представления
function initTrackViewManager() {
    console.log('🎵 Track View Manager инициализируется...');

    setupViewToggle();
    updateViewToggleText();
    setupSearchHandlers();
    setupSortHandlers();
    setupFilterHandlers();
    setupPresentationFilterHandlers();
    setupStatsDisplay();
    setupGlobalPlayer();
    setupProcessAllButton();

    // Важно: вызываем обновление статистики, но убеждаемся, что это не рекурсивно
    safeUpdateGlobalStats();
    safeUpdatePresentationStats();

    console.log('✅ Track View Manager инициализирован');
}

// Безопасное обновление статистики без рекурсии
function safeUpdateGlobalStats() {
    const statsElement = document.getElementById('mediaStats');
    if (!statsElement) return;

    try {
        const total = window.currentTracks ? window.currentTracks.length : 0;
        const processed = window.currentTracks ? window.currentTracks.filter(t => t.processed).length : 0;
        const unprocessed = total - processed;
        const withPhotos = window.currentTracks ? window.currentTracks.filter(t => t.image_path).length : 0;
        const percentage = total > 0 ? Math.round((processed / total) * 100) : 0;

        statsElement.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">📊</div>
                    <div class="stat-info">
                        <span class="stat-label">Всего треков</span>
                        <span class="stat-value">${total}</span>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">✅</div>
                    <div class="stat-info">
                        <span class="stat-label">Обработано</span>
                        <span class="stat-value">${processed}</span>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">⏳</div>
                    <div class="stat-info">
                        <span class="stat-label">Не обработано</span>
                        <span class="stat-value">${unprocessed}</span>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📈</div>
                    <div class="stat-info">
                        <span class="stat-label">Прогресс</span>
                        <span class="stat-value">${percentage}%</span>
                    </div>
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Ошибка обновления статистики:', error);
    }
}

// Безопасное обновление статистики презентации
function safeUpdatePresentationStats() {
    // Просто вызываем функцию из app.js, если она существует
    if (typeof updatePresentationMiniLibraryStats === 'function') {
        updatePresentationMiniLibraryStats();
    }
}


// Обновление индикаторов готовности к презентации
function updatePresentationReadinessIndicators(inPresentation, total) {
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
        generateBtn.disabled = inPresentation < 40;
        generateBtn.title = inPresentation < 40 ?
            `Добавьте хотя бы 40 треков в список (сейчас: ${inPresentation})` :
            `Сгенерировать презентацию из ${inPresentation} треков`;
    }
}

// Обновление глобальной статистики (адаптированная версия без рекурсии)
function updateGlobalStats() {
    safeUpdateGlobalStats();
}

// Обновление статистики презентации
function updatePresentationStats() {
    safeUpdatePresentationStats();
}

// Настройка переключателя вида
function setupViewToggle() {
    const toggleBtn = document.getElementById('toggleDetailedView');
    if (!toggleBtn) {
        console.error('Кнопка переключения вида не найдена');
        return;
    }

    toggleBtn.addEventListener('click', function (e) {
        e.preventDefault();
        toggleViewMode();
    });

    console.log('Обработчик кнопки вида установлен');
}

// Переключение между компактным и подробным видом
function toggleViewMode() {
    console.log('Переключение вида, текущий режим:', window.currentViewMode);

    const tracksList = document.getElementById('tracksList');
    if (!tracksList) {
        console.error('Контейнер треков не найден');
        return;
    }

    window.currentViewMode = window.currentViewMode === 'compact' ? 'detailed' : 'compact';

    if (window.currentViewMode === 'detailed') {
        tracksList.classList.add('detailed-view');
        console.log('Переключились на подробный вид');
        renderFilteredTracks();
    } else {
        tracksList.classList.remove('detailed-view');
        console.log('Переключились на компактный вид');
        renderFilteredTracks();
    }

    updateViewToggleText();
}

// Обновление текста кнопки переключения
function updateViewToggleText() {
    const toggleBtn = document.getElementById('toggleDetailedView');
    const textSpan = document.getElementById('viewToggleText');

    if (!toggleBtn || !textSpan) {
        console.log('Элементы кнопки не найдены');
        return;
    }

    if (window.currentViewMode === 'compact') {
        textSpan.textContent = 'Подробный вид';
        toggleBtn.title = 'Переключиться на подробный вид с waveform и большими фото';
    } else {
        textSpan.textContent = 'Компактный вид';
        toggleBtn.title = 'Переключиться на компактный вид списка';
    }
}

// Настройка обработчиков поиска
function setupSearchHandlers() {
    const searchInput = document.getElementById('trackSearchInput');
    const searchBtn = document.getElementById('trackSearchBtn');
    const clearSearchBtn = document.getElementById('clearSearchBtn');

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            searchQuery = this.value.toLowerCase().trim();
            debouncedSearch();
        });

        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                searchQuery = this.value.toLowerCase().trim();
                performSearch();
            }
        });
    }

    if (searchBtn) {
        searchBtn.addEventListener('click', function () {
            if (searchInput) {
                searchQuery = searchInput.value.toLowerCase().trim();
            }
            performSearch();
        });
    }

    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', function () {
            searchQuery = '';
            if (searchInput) searchInput.value = '';
            performSearch();
        });
    }
}

// Настройка обработчиков сортировки
function setupSortHandlers() {
    const sortSelect = document.getElementById('trackSortSelect');
    if (sortSelect) {
        sortSelect.addEventListener('change', function () {
            sortBy = this.value;
            performSort();
        });
    }

    const sortDirectionBtn = document.getElementById('sortDirectionBtn');
    if (sortDirectionBtn) {
        sortDirectionBtn.addEventListener('click', function () {
            sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            this.innerHTML = sortDirection === 'asc' ? '↑' : '↓';
            this.title = sortDirection === 'asc' ? 'По возрастанию' : 'По убыванию';
            performSort();
        });
    }
}

// Настройка обработчиков фильтрации по статусу (для основной медиатеки)
function setupFilterHandlers() {
    const filterButtons = document.querySelectorAll('.status-filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            filterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            filterByStatus = this.dataset.filter;
            applyFilters();
        });
    });
}

// Настройка обработчиков фильтрации для презентаций
function setupPresentationFilterHandlers() {
    // Создаем кнопки фильтрации для презентаций, если их нет
    createPresentationFilterButtons();

    // Вешаем обработчики
    const presFilterButtons = document.querySelectorAll('.pres-status-filter-btn');
    presFilterButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            presFilterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            presentationFilterByStatus = this.dataset.filter;
            applyPresentationFilters();
        });
    });
}

// Создание кнопок фильтрации для презентаций
function createPresentationFilterButtons() {
    const filterContainer = document.getElementById('presentationFilterContainer');
    if (!filterContainer || filterContainer.querySelector('.pres-status-filter-btn')) {
        return;
    }

    filterContainer.innerHTML = `
        <div class="filter-group">
            <span class="filter-label">Фильтр по статусу:</span>
            <div class="filter-buttons">
                <button class="btn btn-small pres-status-filter-btn ${presentationFilterByStatus === 'all' ? 'active' : ''}" 
                        data-filter="all" title="Все треки">
                    Все
                </button>
                <button class="btn btn-small pres-status-filter-btn ${presentationFilterByStatus === 'processed' ? 'active' : ''}" 
                        data-filter="processed" title="Только обработанные">
                    ✅ Обработанные
                </button>
                <button class="btn btn-small pres-status-filter-btn ${presentationFilterByStatus === 'unprocessed' ? 'active' : ''}" 
                        data-filter="unprocessed" title="Только необработанные">
                    ⏳ Необработанные
                </button>
            </div>
        </div>
    `;
}

// Применение фильтров для презентаций
function applyPresentationFilters() {
    if (!window.presentationTrackList) return;

    let filteredPresentationTracks = [...window.presentationTrackList];

    if (presentationFilterByStatus === 'processed') {
        filteredPresentationTracks = filteredPresentationTracks.filter(track => track.processed);
    } else if (presentationFilterByStatus === 'unprocessed') {
        filteredPresentationTracks = filteredPresentationTracks.filter(track => !track.processed);
    }

    // Обновляем отображение
    renderFilteredPresentationTracks(filteredPresentationTracks);
    updatePresentationFilterStats();
}

// Обновление статистики фильтрации презентации
function updatePresentationFilterStats() {
    const filterStats = document.getElementById('presentationFilterStats');
    if (!filterStats) return;

    const totalInPresentation = window.presentationTrackList ? window.presentationTrackList.length : 0;
    let filteredCount = totalInPresentation;

    if (presentationFilterByStatus === 'processed') {
        filteredCount = window.presentationTrackList ?
            window.presentationTrackList.filter(t => t.processed).length : 0;
    } else if (presentationFilterByStatus === 'unprocessed') {
        filteredCount = window.presentationTrackList ?
            window.presentationTrackList.filter(t => !t.processed).length : 0;
    }

    filterStats.innerHTML = `
        <span class="filter-stats-text">
            Показано: <strong>${filteredCount}</strong> треков (из ${totalInPresentation} в списке)
        </span>
    `;
    filterStats.style.display = filteredCount === totalInPresentation ? 'none' : 'block';
}

// Рендер отфильтрованных треков презентации
function renderFilteredPresentationTracks(tracks) {
    const container = document.getElementById('presentationTracksList');
    if (!container) return;

    if (tracks.length === 0) {
        const noResultsMessage = presentationFilterByStatus !== 'all'
            ? `<div class="empty-state">
                <div class="icon">🔍</div>
                <h3>${presentationFilterByStatus === 'processed' ? 'Нет обработанных треков' : 'Нет необработанных треков'}</h3>
                <p>Попробуйте изменить фильтр</p>
               </div>`
            : '<div class="empty-state"><div class="icon">🎵</div><h3>Нет треков в списке</h3><p>Добавьте треки в список презентации</p></div>';

        container.innerHTML = noResultsMessage;
        return;
    }

    // Используем функцию из app.js для рендера, если она существует
    if (typeof window.renderPresentationTracksCompact === 'function') {
        window.renderPresentationTracksCompact(tracks);
    } else {
        // Запасной вариант
        container.innerHTML = tracks.map(track => {
            const isPlaying = currentPlayingTrackId === track.id && isGlobalPlaying;
            return `
            <div class="track-item ${track.processed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" data-track-id="${track.id}">
                <div class="col-id">${track.id}</div>
                <div class="col-artist">
                    ${track.image_path ?
                    `<img src="${window.API_BASE}/tracks/${track.id}/artist-photo?t=${Date.now()}" 
                          alt="${escapeHtml(track.artist)}"
                          class="track-cover">` :
                    `<div class="track-cover empty"></div>`
                }
                    <span>${escapeHtml(track.artist)}</span>
                    ${track.processed ? '<span class="track-processed-badge">✅</span>' : ''}
                </div>
                <div class="col-title">${escapeHtml(track.title)}</div>
                <div class="col-actions">
                    <button class="btn btn-secondary btn-small" onclick="window.trackViewManager.playTrackSegment(${track.id})">
                        ${isPlaying ? '⏹️' : '▶️'}
                    </button>
                    <button class="btn btn-secondary btn-small" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})">🎚️</button>
                    <button class="btn btn-secondary btn-small" onclick="window.editTrack && window.editTrack(${track.id})">✏️</button>
                    <button class="btn btn-success btn-small" onclick="window.trackViewManager.toggleProcessedStatus(${track.id})">
                        ${track.processed ? '❌' : '✅'}
                    </button>
                </div>
            </div>
            `;
        }).join('');
    }
}

// Настройка отображения статистики
function setupStatsDisplay() {
    safeUpdateGlobalStats();
    safeUpdatePresentationStats();
}

// Настройка глобального плеера
function setupGlobalPlayer() {
    if (!globalAudioPlayer) {
        globalAudioPlayer = new Audio();
        globalAudioPlayer.preload = 'auto';
        globalAudioPlayer.volume = 0.5;

        globalAudioPlayer.addEventListener('ended', function () {
            stopGlobalPlayback();
        });

        globalAudioPlayer.addEventListener('error', function (e) {
            // Только для реальных ошибок, игнорируем обычные прерывания
            if (globalAudioPlayer.error && globalAudioPlayer.error.code !== 0) {
                console.warn('Ошибка аудио:', globalAudioPlayer.error.message);
            }
            stopGlobalPlayback();
        });

        globalAudioPlayer.addEventListener('timeupdate', function () {
            if (currentPlayingTrackId && isGlobalPlaying) {
                updatePlayButtons();
            }
        });
    }
}


// Настройка кнопки "Обработать все"
function setupProcessAllButton() {
    const processAllBtn = document.getElementById('processAllBtn');
    if (processAllBtn) {
        processAllBtn.addEventListener('click', async function () {
            const filteredTracks = getFilteredTracks();
            const unprocessedTracks = filteredTracks.filter(track => !track.processed);
            if (unprocessedTracks.length === 0) {
                showNotification('Все треки уже обработаны', 'info');
                return;
            }

            if (!confirm(`Пометить как обработанные ${unprocessedTracks.length} треков?`)) {
                return;
            }

            try {
                this.disabled = true;
                this.innerHTML = '⏳ Обработка...';

                let successCount = 0;
                for (const track of unprocessedTracks) {
                    try {
                        await toggleProcessedStatus(track.id, true);
                        successCount++;
                    } catch (error) {
                        console.error(`Ошибка обработки трека ${track.id}:`, error);
                    }
                }

                showNotification(`Обработано ${successCount} из ${unprocessedTracks.length} треков`, 'success');
                if (window.loadTracks) {
                    window.loadTracks();
                }

            } catch (error) {
                console.error('Ошибка массовой обработки:', error);
                showNotification('Ошибка при обработке треков', 'error');
            } finally {
                this.disabled = false;
                this.innerHTML = '✅ Обработать все';
            }
        });
    }
}

// Дебаунс для поиска
const debouncedSearch = debounce(performSearch, 300);

// Выполнение поиска
function performSearch() {
    renderFilteredTracks();
    updateSearchStats();
}

// Выполнение сортировки
function performSort() {
    renderFilteredTracks();
}

// Применение фильтров (основная медиатека)
function applyFilters() {
    renderFilteredTracks();
    updateFilterStats();
}

// Получение отфильтрованных и отсортированных треков
function getFilteredTracks() {
    const currentTracks = window.currentTracks || [];

    let filtered = currentTracks.filter(track => {
        if (searchQuery && track) {
            const artistMatch = track.artist && track.artist.toLowerCase().includes(searchQuery);
            const titleMatch = track.title && track.title.toLowerCase().includes(searchQuery);
            if (!artistMatch && !titleMatch) return false;
        }

        if (filterByStatus === 'processed') {
            return track.processed === true;
        } else if (filterByStatus === 'unprocessed') {
            return track.processed === false;
        }

        return true;
    });

    filtered.sort((a, b) => {
        let aValue, bValue;

        switch (sortBy) {
            case 'artist':
                aValue = a.artist ? a.artist.toLowerCase() : '';
                bValue = b.artist ? b.artist.toLowerCase() : '';
                break;
            case 'title':
                aValue = a.title ? a.title.toLowerCase() : '';
                bValue = b.title ? b.title.toLowerCase() : '';
                break;
            case 'id':
                aValue = a.id || 0;
                bValue = b.id || 0;
                break;
            case 'processed':
                aValue = a.processed ? 1 : 0;
                bValue = b.processed ? 1 : 0;
                break;
            default:
                aValue = a.id || 0;
                bValue = b.id || 0;
        }

        if (sortDirection === 'asc') {
            return aValue > bValue ? 1 : -1;
        } else {
            return aValue < bValue ? 1 : -1;
        }
    });

    return filtered;
}

// Обновление статистики поиска
function updateSearchStats() {
    const searchStats = document.getElementById('searchStats');
    if (!searchStats) return;

    const filtered = getFilteredTracks();
    const total = window.currentTracks ? window.currentTracks.length : 0;

    if (searchQuery) {
        searchStats.innerHTML = `
            <span class="search-stats-text">
                Найдено: <strong>${filtered.length}</strong> из ${total} треков
            </span>
        `;
        searchStats.style.display = 'block';
    } else {
        searchStats.style.display = 'none';
    }
}

// Обновление статистики фильтров
function updateFilterStats() {
    const filterStats = document.getElementById('filterStats');
    if (!filterStats) return;

    const filtered = getFilteredTracks();
    const total = window.currentTracks ? window.currentTracks.length : 0;

    let statusText = '';
    if (filterByStatus === 'processed') {
        statusText = 'обработанных';
    } else if (filterByStatus === 'unprocessed') {
        statusText = 'необработанных';
    } else {
        statusText = 'всех';
    }

    filterStats.innerHTML = `
        <span class="filter-stats-text">
            Показано: <strong>${filtered.length}</strong> ${statusText} треков
        </span>
    `;
}

// Рендер отфильтрованных треков
function renderFilteredTracks() {
    const filteredTracks = getFilteredTracks();

    if (window.currentViewMode === 'detailed') {
        renderTracksDetailed(filteredTracks);
    } else {
        renderTracksCompact(filteredTracks);
    }

    updateSearchStats();
    updateFilterStats();
    safeUpdateGlobalStats();
}

// Рендер треков в компактном виде с кнопкой воспроизведения
function renderTracksCompact(tracks) {
    const container = document.getElementById('tracksList');
    if (!container) return;

    if (tracks.length === 0) {
        const noResultsMessage = searchQuery || filterByStatus !== 'all'
            ? '<div class="empty-state"><div class="icon">🔍</div><h3>Треки не найдены</h3><p>Попробуйте изменить поисковый запрос или фильтр</p></div>'
            : '<div class="empty-state"><div class="icon">🎵</div><h3>Нет загруженных треков</h3><p>Нажмите "Загрузить треки" чтобы добавить музыку</p></div>';

        container.innerHTML = noResultsMessage;
        return;
    }

    container.innerHTML = tracks.map(track => {
        const isPlaying = currentPlayingTrackId === track.id && isGlobalPlaying;

        return `
        <div class="track-item draggable ${track.processed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" draggable="true" data-track-id="${track.id}">
            <div class="col-id">
                ${track.id}
                <button class="btn-id-change" onclick="window.openChangeIdModal && window.openChangeIdModal(${track.id})" title="Изменить ID">🔢</button>
            </div>
            <div class="col-artist">
                ${track.image_path ?
                `<span onclick="window.openPhotoEditor && window.openPhotoEditor(${track.id})" style="cursor: pointer; display: inline-block;">
                        <img src="${window.API_BASE}/tracks/${track.id}/artist-photo?t=${Date.now()}" 
                             alt="${escapeHtml(track.artist)}" 
                             class="track-cover"
                             onerror="handleImageError(this)"
                             onload="handleImageLoad(this)">
                    </span>` :
                ''
            }
                <div class="track-cover-placeholder" style="${track.image_path ? 'display: none;' : ''}">🎵</div>
                <span>${escapeHtml(track.artist)}</span>
                ${track.processed ? '<span class="track-processed-badge">✅</span>' : ''}
                ${isPlaying ? '<span class="playing-indicator-small">🔊</span>' : ''}
            </div>
            <div class="col-title">${escapeHtml(track.title)}</div>
            <div class="col-segment">
                <span class="segment-time">${formatTime(track.segment_start || 0)}</span>
                <span class="segment-duration">${track.segment_duration || 30}с</span>
            </div>
            <div class="col-actions">
                <button class="btn btn-secondary btn-small play-btn" data-track-id="${track.id}" 
                        onclick="playTrackSegmentFromManager(${track.id})" title="${isPlaying ? 'Остановить воспроизведение' : 'Воспроизвести отрывок'}">
                    ${isPlaying ? '⏹️' : '▶️'}
                </button>
                <button class="btn btn-secondary btn-small" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})" title="Аудио редактор">🎚️</button>
                <button class="btn btn-secondary btn-small" onclick="window.editTrack && window.editTrack(${track.id})" title="Редактировать метаданные">✏️</button>
                <button class="btn btn-success btn-small" onclick="toggleProcessedFromManager(${track.id})" 
                        title="${track.processed ? 'Отметить как необработанный' : 'Отметить как обработанный'}">
                    ${track.processed ? '❌' : '✅'}
                </button>
                <button class="btn btn-danger btn-small" onclick="window.deleteTrack && window.deleteTrack(${track.id})" title="Удалить">🗑️</button>
            </div>
        </div>
    `}).join('');

    setupDragHandlers();
    enhanceTrackListWithIdEdit();
}

// Рендер треков в подробном виде с кнопкой воспроизведения
function renderTracksDetailed(tracks) {
    const container = document.getElementById('tracksList');
    if (!container) return;

    if (tracks.length === 0) {
        const noResultsMessage = searchQuery || filterByStatus !== 'all'
            ? '<div class="empty-state"><div class="icon">🔍</div><h3>Треки не найдены</h3><p>Попробуйте изменить поисковый запрос или фильтр</p></div>'
            : '<div class="empty-state"><div class="icon">🎵</div><h3>Нет загруженных треков</h3><p>Нажмите "Загрузить треки" чтобы добавить музыку</p></div>';

        container.innerHTML = noResultsMessage;
        return;
    }

    container.innerHTML = tracks.map(track => {
        const isPlaying = currentPlayingTrackId === track.id && isGlobalPlaying;

        return `
        <div class="track-item detailed draggable ${track.processed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" draggable="true" data-track-id="${track.id}">
            <!-- ОГРОМНОЕ ФОТО СЛЕВА 284x284 -->
            <div class="track-image-container">
                ${track.image_path ?
                `<img src="${window.API_BASE}/tracks/${track.id}/artist-photo?t=${Date.now()}" 
                         alt="${escapeHtml(track.artist)}"
                         onclick="window.openPhotoEditor && window.openPhotoEditor(${track.id})"
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgdmlld0JveD0iMCAwIDEwMCAxMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiNmMWYxZjEiLz48dGV4dCB4PSI1MCIgeT0iNTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxMiIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPs6PzqPOlc6dzp/Oo86ZPC90ZXh0Pjwvc3ZnPg==';"
                         onload="this.style.display='block';">` :
                `<div class="track-cover-placeholder" onclick="window.openPhotoEditor && window.openPhotoEditor(${track.id})" title="Добавить фото">🎵</div>`
            }
            </div>
            
            <!-- ПРАВАЯ ЧАСТЬ -->
            <div class="track-main-content">
                <!-- НАЗВАНИЯ СВЕРХУ -->
                <div class="track-info-header">
                    <div class="track-artist" 
                         onclick="startInlineEdit(this, 'artist', ${track.id})"
                         title="Кликните для редактирования">
                        ${escapeHtml(track.artist)}
                        ${track.processed ? '<span class="track-processed-badge">✅</span>' : ''}
                        ${isPlaying ? '<span class="playing-indicator">🔊</span>' : ''}
                    </div>
                    <div class="track-title" 
                         onclick="startInlineEdit(this, 'title', ${track.id})"
                         title="Кликните для редактирования">
                        ${escapeHtml(track.title)}
                    </div>
                </div>
                
                <!-- БОЛЬШАЯ WAVEFORM КНОПКА ПО ЦЕНТРУ -->
                <div class="waveform-btn-container">
                    <button class="waveform-btn" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})" title="Открыть аудио редактор">
                        ${track.duration ? `🎵 ${formatTime(track.segment_start || 0)} - ${formatTime((track.segment_start || 0) + (track.segment_duration || 30))}` : 'Загрузка...'}
                    </button>
                </div>
                
                <!-- КНОПКИ ДЕЙСТВИЙ СНИЗУ В РЯД -->
                <div class="track-actions detailed">
                    <button class="btn btn-secondary btn-small play-btn" data-track-id="${track.id}" 
                            onclick="playTrackSegmentFromManager(${track.id})" title="${isPlaying ? 'Остановить воспроизведение' : 'Воспроизвести отрывок'}">
                        ${isPlaying ? '⏹️' : '▶️'}
                    </button>
                    <button class="btn btn-secondary btn-small" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})" title="Аудио редактор">🎚️</button>
                    <button class="btn btn-secondary btn-small" onclick="window.editTrack && window.editTrack(${track.id})" title="Редактировать метаданные">✏️</button>
                    <button class="btn btn-success btn-small" onclick="toggleProcessedFromManager(${track.id})" 
                            title="${track.processed ? 'Отметить как необработанный' : 'Отметить как обработанный'}">
                        ${track.processed ? '❌' : '✅'}
                    </button>
                    <button class="btn btn-danger btn-small" onclick="window.deleteTrack && window.deleteTrack(${track.id})" title="Удалить">🗑️</button>
                    <button class="btn btn-small" onclick="window.openChangeIdModal && window.openChangeIdModal(${track.id})" title="Изменить ID">#️⃣</button>
                </div>
            </div>
        </div>
    `}).join('');

    setupDragHandlers();
}

// Обработчики для изображений
function handleImageLoad(img) {
    const placeholder = img.nextElementSibling;
    if (placeholder && placeholder.classList.contains('track-cover-placeholder')) {
        placeholder.style.display = 'none';
    }
    img.style.display = 'block';
}

function handleImageError(img) {
    img.style.display = 'none';
    const placeholder = img.nextElementSibling;
    if (placeholder && placeholder.classList.contains('track-cover-placeholder')) {
        placeholder.style.display = 'flex';
    }
}

// Инлайн-редактирование исполнителя и названия
function startInlineEdit(element, field, trackId) {
    let currentText = element.textContent;
    currentText = currentText.replace(/[✅🔊]/g, '').trim();

    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentText;
    input.className = field === 'artist' ? 'track-artist-input' : 'track-title-input';

    element.innerHTML = '';
    element.appendChild(input);
    element.classList.add('editable');

    input.focus();
    input.select();

    function saveEdit() {
        const newValue = input.value.trim();
        if (newValue && newValue !== currentText) {
            updateTrackField(trackId, field, newValue, element);
        } else {
            cancelEdit();
        }
    }

    function cancelEdit() {
        const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
        if (track) {
            let text = escapeHtml(track[field]);
            if (field === 'artist' && track.processed) {
                text += '<span class="track-processed-badge">✅</span>';
            }
            if (currentPlayingTrackId === trackId && isGlobalPlaying) {
                text += '<span class="playing-indicator">🔊</span>';
            }
            element.innerHTML = text;
        } else {
            element.textContent = currentText;
        }
        element.classList.remove('editable');
    }

    input.addEventListener('blur', saveEdit);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            saveEdit();
        } else if (e.key === 'Escape') {
            cancelEdit();
        }
    });
}

// Обновление поля трека
async function updateTrackField(trackId, field, newValue, element) {
    try {
        const updateData = {};
        updateData[field] = newValue;

        const response = await fetch(`${window.API_BASE}/tracks/${trackId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });

        if (!response.ok) {
            throw new Error('Ошибка обновления');
        }

        const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
        if (track) {
            track[field] = newValue;
            let text = escapeHtml(newValue);
            if (field === 'artist' && track.processed) {
                text += '<span class="track-processed-badge">✅</span>';
            }
            if (currentPlayingTrackId === trackId && isGlobalPlaying) {
                text += '<span class="playing-indicator">🔊</span>';
            }
            element.innerHTML = text;
        }

        element.classList.remove('editable');

        showNotification('✅ Изменения сохранены', 'success');
    } catch (error) {
        console.error('Ошибка сохранения:', error);
        showNotification('❌ Ошибка сохранения', 'error');
        const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
        if (track) {
            element.textContent = track[field];
        }
        element.classList.remove('editable');
    }
}

// Воспроизведение отрезка трека (исправленная версия)
async function playTrackSegmentFromManager(trackId) {
    try {
        if (currentPlayingTrackId === trackId && isGlobalPlaying) {
            stopGlobalPlayback();
            return;
        }

        stopGlobalPlayback();

        const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
        if (!track) {
            showNotification('Трек не найден', 'error');
            return;
        }

        currentPlayingTrackId = trackId;
        isGlobalPlaying = true;

        updatePlayButtons();

        showNotification(`▶️ Воспроизведение: ${track.artist} - ${track.title}`, 'info');

        const segmentUrl = `${window.API_BASE}/tracks/${trackId}/segment-file?start_time=${track.segment_start || 0}&duration=${track.segment_duration || 30}&nocache=${Date.now()}`;

        if (!globalAudioPlayer) {
            setupGlobalPlayer();
        }

        if (globalAudioPlayer) {
            globalAudioPlayer.pause();
            globalAudioPlayer.currentTime = 0;
        }

        globalAudioPlayer.src = segmentUrl;
        globalAudioPlayer.currentTime = 0;

        const playPromise = globalAudioPlayer.play();

        if (playPromise !== undefined) {
            playPromise
                .then(() => {
                    console.log('✅ Воспроизведение начато успешно');
                    updateNowPlayingInfo(track);
                })
                .catch(error => {
                    console.error('❌ Ошибка воспроизведения:', error);

                    if (error.name === 'NotSupportedError') {
                        showNotification('Формат аудио не поддерживается браузером', 'error');
                    } else if (error.name === 'NotAllowedError') {
                        showNotification('Автовоспроизведение заблокировано. Нажмите на кнопку воспроизведения еще раз.', 'warning');
                    } else {
                        showNotification('Ошибка воспроизведения трека: ' + error.message, 'error');
                    }

                    stopGlobalPlayback();
                });
        }

    } catch (error) {
        console.error('❌ Общая ошибка воспроизведения:', error);
        showNotification('Ошибка воспроизведения трека', 'error');
        stopGlobalPlayback();
    }
}

// Остановка глобального воспроизведения
function stopGlobalPlayback() {
    if (globalAudioPlayer) {
        try {
            globalAudioPlayer.pause();
            globalAudioPlayer.currentTime = 0;
            globalAudioPlayer.src = '';
        } catch (error) {
            console.warn('Ошибка при остановке воспроизведения:', error);
        }
    }

    currentPlayingTrackId = null;
    isGlobalPlaying = false;

    updatePlayButtons();
    hideNowPlayingInfo();
}

// Обновление кнопок воспроизведения
function updatePlayButtons() {
    document.querySelectorAll('.play-btn').forEach(btn => {
        const trackId = parseInt(btn.dataset.trackId);
        if (currentPlayingTrackId === trackId && isGlobalPlaying) {
            btn.innerHTML = '⏹️';
            btn.title = 'Остановить воспроизведение';
        } else {
            btn.innerHTML = '▶️';
            btn.title = 'Воспроизвести отрывок';
        }
    });

    document.querySelectorAll('.play-btn-presentation').forEach(btn => {
        const trackId = parseInt(btn.dataset.trackId);
        if (currentPlayingTrackId === trackId && isGlobalPlaying) {
            btn.innerHTML = '⏹️';
            btn.title = 'Остановить воспроизведение';
        } else {
            btn.innerHTML = '▶️';
            btn.title = 'Воспроизвести отрывок';
        }
    });

    document.querySelectorAll('.track-item').forEach(item => {
        const trackId = parseInt(item.dataset.trackId);
        if (currentPlayingTrackId === trackId && isGlobalPlaying) {
            item.classList.add('playing');
        } else {
            item.classList.remove('playing');
        }
    });

    const presentationContainer = document.getElementById('presentationTracksList');
    if (presentationContainer) {
        presentationContainer.querySelectorAll('.track-item').forEach(item => {
            const trackId = parseInt(item.dataset.trackId);
            if (currentPlayingTrackId === trackId && isGlobalPlaying) {
                item.classList.add('playing');
            } else {
                item.classList.remove('playing');
            }
        });
    }
}

// Обновление информации о текущем треке
function updateNowPlayingInfo(track) {
    const nowPlayingInfo = document.getElementById('nowPlayingInfo');
    if (!nowPlayingInfo) return;

    nowPlayingInfo.innerHTML = `
        <div class="now-playing">
            <span class="now-playing-icon">🔊</span>
            <span class="now-playing-text">
                Сейчас играет: <strong>${escapeHtml(track.artist)} - ${escapeHtml(track.title)}</strong>
            </span>
            <button class="btn btn-small btn-secondary" onclick="stopGlobalPlayback()">⏹️ Остановить</button>
        </div>
    `;
    nowPlayingInfo.style.display = 'block';
}

// Скрытие информации о текущем треке
function hideNowPlayingInfo() {
    const nowPlayingInfo = document.getElementById('nowPlayingInfo');
    if (nowPlayingInfo) {
        nowPlayingInfo.style.display = 'none';
    }
}

// Функция для переключения статуса обработки
async function toggleProcessedStatus(trackId, forceValue = null) {
    const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
    if (!track) return;

    const newStatus = forceValue !== null ? forceValue : !track.processed;

    try {
        const response = await fetch(`${window.API_BASE}/tracks/${trackId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ processed: newStatus })
        });

        if (!response.ok) {
            throw new Error('Ошибка обновления статуса');
        }

        track.processed = newStatus;

        renderFilteredTracks();
        if (window.presentationTrackList) {
            applyPresentationFilters();
        }

        safeUpdateGlobalStats();
        safeUpdatePresentationStats();

        if (typeof window.refreshPresentationData === 'function') {
            window.refreshPresentationData();
        }

        return true;
    } catch (error) {
        console.error('Ошибка обновления статуса:', error);
        throw error;
    }
}

// Локальная функция для переключения статуса
async function toggleProcessedFromManager(trackId) {
    try {
        await toggleProcessedStatus(trackId);
        const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
        if (track) {
            showNotification(`Трек помечен как ${track.processed ? 'обработанный' : 'необработанный'}`, 'info');
        }
    } catch (error) {
        showNotification('Ошибка обновления статуса', 'error');
    }
}

// Функция для обновления отображения при изменении данных
function refreshTrackDisplay() {
    renderFilteredTracks();
}

// Переопределяем глобальную функцию renderTracks
if (!window.renderTracksOriginal) {
    window.renderTracksOriginal = window.renderTracks;
}

window.renderTracks = function (tracks) {
    window.currentTracks = tracks;
    renderFilteredTracks();

    // Обновляем статистику презентации
    safeUpdatePresentationStats();

    if (typeof window.updateTracksCount === 'function') {
        window.updateTracksCount();
    }
};

// Обновление отображения треков презентации
function refreshPresentationTrackDisplay() {
    if (window.presentationTrackList) {
        applyPresentationFilters();
    }
    safeUpdatePresentationStats();
}

// Вспомогательные функции
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "<")
        .replace(/>/g, ">")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function showNotification(message, type = 'info') {
    if (typeof window.showNotification === 'function') {
        window.showNotification(message, type);
    } else {
        console.log(`${type}: ${message}`);
    }
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

// Дополнительные функции для совместимости
function setupDragHandlers() {
    console.log('Drag handlers setup placeholder');
}

function enhanceTrackListWithIdEdit() {
    console.log('Track list ID edit enhancement placeholder');
}

// Экспорт функций в глобальную область видимости
window.trackViewManager = {
    toggleViewMode: toggleViewMode,
    startInlineEdit: startInlineEdit,
    refreshTrackDisplay: refreshTrackDisplay,
    renderTracksCompact: renderTracksCompact,
    renderTracksDetailed: renderTracksDetailed,
    updateViewToggleText: updateViewToggleText,
    handleImageLoad: handleImageLoad,
    handleImageError: handleImageError,
    playTrackSegment: playTrackSegmentFromManager,
    stopGlobalPlayback: stopGlobalPlayback,
    getFilteredTracks: getFilteredTracks,
    updateGlobalStats: safeUpdateGlobalStats,
    updatePresentationStats: safeUpdatePresentationStats,
    initTrackViewManager: initTrackViewManager,
    renderFilteredTracks: renderFilteredTracks,
    toggleProcessedStatus: toggleProcessedStatus,
    updatePlayButtons: updatePlayButtons,
    escapeHtml: escapeHtml,
    formatTime: formatTime,
    applyPresentationFilters: applyPresentationFilters,
    refreshPresentationTrackDisplay: refreshPresentationTrackDisplay
};

// Глобальные функции для совместимости
window.toggleViewMode = toggleViewMode;
window.startInlineEdit = startInlineEdit;
window.playTrackSegment = playTrackSegmentFromManager;
window.stopGlobalPlayback = stopGlobalPlayback;
window.updateGlobalStats = safeUpdateGlobalStats;
window.updatePresentationStats = safeUpdatePresentationStats;

// Инициализация при загрузке
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
        if (!window.currentViewMode) window.currentViewMode = 'compact';
        if (!window.currentTracks) window.currentTracks = [];
        if (!window.presentationTrackList) window.presentationTrackList = [];
        if (!window.API_BASE) window.API_BASE = '/api';

        setTimeout(initTrackViewManager, 500);
    });
} else {
    if (!window.currentViewMode) window.currentViewMode = 'compact';
    if (!window.currentTracks) window.currentTracks = [];
    if (!window.presentationTrackList) window.presentationTrackList = [];
    if (!window.API_BASE) window.API_BASE = '/api';

    setTimeout(initTrackViewManager, 500);
}

console.log('🎵 Track View Manager загружен');