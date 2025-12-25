// track_view_manager.js - ФИНАЛЬНАЯ ВЕРСИЯ С ПРАВИЛЬНЫМ КЕШИРОВАНИЕМ

// Проверяем, не загружен ли уже этот файл
if (typeof window.trackViewManager !== 'undefined') {
    console.warn('⚠️ Track View Manager уже загружен, пропускаем повторную загрузку');
} else {
    console.log('🎵 Загрузка Track View Manager...');

    // ==================== КОНФИГУРАЦИЯ ====================
    const TRACK_VIEW_CONFIG = {
        // Система хэшей для фото
        PHOTO_HASH_ENABLED: true,
        PHOTO_HASH_KEY: 'track_photo_hash_',
        PHOTO_HASH_TIMESTAMP_KEY: 'track_photo_timestamp_',

        // Настройки отображения
        DEFAULT_VIEW_MODE: 'compact',
        ITEMS_PER_PAGE: 50,

        // Воспроизведение
        DEFAULT_SEGMENT_DURATION: 30,
        PLAYBACK_VOLUME: 0.5,

        // Безопасность
        NO_AUTO_REFRESH: true,
        PRESERVE_EXISTING_DOM: true,

        // API Endpoints
        PHOTO_HASH_ENDPOINT: '/api/tracks/photo-hashes'
    };

    // ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
    let trackViewCurrentViewMode = TRACK_VIEW_CONFIG.DEFAULT_VIEW_MODE;
    let trackViewSearchQuery = '';
    let trackViewSortBy = 'id';
    let trackViewSortDirection = 'asc';
    let trackViewFilterByStatus = 'all';
    let trackViewCurrentPlayingTrackId = null;
    let trackViewIsGlobalPlaying = false;
    let trackViewGlobalAudioPlayer = null;
    let trackViewPhotoHashMap = new Map();
    let isInitialized = false;
    let photoHashVersion = 1; // Версия хэшей для инвалидации кеша

    // Презентации
    let trackViewPresentationTrackList = [];
    let trackViewPresentationFilterByStatus = 'all';

    // ==================== ОПТИМИЗИРОВАННАЯ СИСТЕМА ХЭШЕЙ ДЛЯ ФОТО ====================

    // Инициализация системы хэшей
    async function initPhotoHashSystem() {
        console.log('🔄 Инициализация системы хэшей фото...');

        await loadPhotoHashes();

        console.log('✅ Система хэшей инициализирована');
    }

    // Загрузка хэшей из localStorage
    async function loadPhotoHashes() {
        trackViewPhotoHashMap.clear();

        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith(TRACK_VIEW_CONFIG.PHOTO_HASH_KEY)) {
                const trackId = key.replace(TRACK_VIEW_CONFIG.PHOTO_HASH_KEY, '');
                const hash = localStorage.getItem(key);

                const timestampKey = TRACK_VIEW_CONFIG.PHOTO_HASH_TIMESTAMP_KEY + trackId;
                const timestamp = localStorage.getItem(timestampKey) || Date.now();

                trackViewPhotoHashMap.set(parseInt(trackId), {
                    hash: hash,
                    timestamp: parseInt(timestamp)
                });
            }
        }

        console.log(`📊 Загружено ${trackViewPhotoHashMap.size} хэшей фото из localStorage`);
    }

    // Сохранение хэша для трека
    function savePhotoHash(trackId, hash, isNew = false) {
        const existingData = trackViewPhotoHashMap.get(trackId);

        // Если хэш не изменился, просто обновляем timestamp
        if (!isNew && existingData && existingData.hash === hash) {
            existingData.timestamp = Date.now();
            trackViewPhotoHashMap.set(trackId, existingData);

            const timestampKey = TRACK_VIEW_CONFIG.PHOTO_HASH_TIMESTAMP_KEY + trackId;
            localStorage.setItem(timestampKey, Date.now().toString());

            return false; // Хэш не изменился
        }

        // Хэш изменился или новый - увеличиваем версию
        if (existingData && existingData.hash !== hash) {
            photoHashVersion++;
            console.log(`🔄 Хэш изменился для трека ${trackId}, новая версия: ${photoHashVersion}`);
        }

        const key = TRACK_VIEW_CONFIG.PHOTO_HASH_KEY + trackId;
        localStorage.setItem(key, hash);

        const timestampKey = TRACK_VIEW_CONFIG.PHOTO_HASH_TIMESTAMP_KEY + trackId;
        localStorage.setItem(timestampKey, Date.now().toString());

        trackViewPhotoHashMap.set(trackId, {
            hash: hash,
            timestamp: Date.now()
        });

        return true; // Хэш изменился или новый
    }

    // Получение хэша для трека
    function getPhotoHash(trackId) {
        const hashData = trackViewPhotoHashMap.get(trackId);
        return hashData ? hashData.hash : null;
    }

    // Обновление хэшей для списка треков
    async function updatePhotoHashesForTracks(trackIds) {
        if (!trackIds || trackIds.length === 0) return;

        // Фильтруем треки, у которых еще нет хэша
        const tracksWithoutHash = trackIds.filter(trackId => !getPhotoHash(trackId));

        if (tracksWithoutHash.length === 0) {
            console.log('✅ Все хэши уже загружены');
            return;
        }

        console.log(`🔍 Запрашиваем хэши для ${tracksWithoutHash.length} треков...`);

        try {
            const response = await fetch(TRACK_VIEW_CONFIG.PHOTO_HASH_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({
                    track_ids: tracksWithoutHash
                })
            });

            if (!response.ok) {
                console.warn(`⚠️ Ошибка получения хэшей: ${response.status}`);
                return;
            }

            const data = await response.json();

            if (data.success && data.hashes) {
                let addedCount = 0;

                for (const [trackIdStr, hashInfo] of Object.entries(data.hashes)) {
                    const trackId = parseInt(trackIdStr);
                    const hash = hashInfo.hash;

                    if (hash && hash !== 'no_photo' && hash !== 'missing' && hash !== 'error') {
                        const existingHash = getPhotoHash(trackId);

                        if (!existingHash) {
                            savePhotoHash(trackId, hash, true);
                            addedCount++;

                            // Обновляем изображения на странице
                            updateImageUrls(trackId);
                        }
                    }
                }

                console.log(`📸 Получено ${addedCount} новых хэшей`);

            } else {
                console.warn('⚠️ Некорректный ответ от сервера хэшей');
            }

        } catch (error) {
            console.warn('⚠️ Ошибка при получении хэшей с сервера:', error);
        }
    }

    // Обновление URL изображений для трека
    function updateImageUrls(trackId) {
        const hash = getPhotoHash(trackId);
        if (!hash) return;

        const images = document.querySelectorAll(`img[data-track-id="${trackId}"]`);

        images.forEach(img => {
            const currentSrc = img.src;
            const newUrl = generatePhotoUrl(trackId, hash);

            // Обновляем только если URL изменился
            if (currentSrc !== newUrl) {
                img.src = newUrl;
            }
        });
    }

    // Генерация URL фото (БЕЗ timestamp для кеширования!)
    function generatePhotoUrl(trackId, hash = null) {
        if (!trackId) return null;

        const actualHash = hash || getPhotoHash(trackId);
        const baseUrl = `/api/tracks/${trackId}/artist-photo`;

        if (actualHash) {
            // Используем версию хэшей вместо timestamp
            return `${baseUrl}?h=${actualHash}&v=${photoHashVersion}`;
        } else {
            // Без хэша - используем timestamp чтобы избежать кеширования
            return `${baseUrl}?t=${Date.now()}`;
        }
    }

    // Генерация URL фото с хэшем для рендеринга
    function generatePhotoUrlWithHash(trackId, imagePath) {
        if (!imagePath) return null;
        return generatePhotoUrl(trackId);
    }

    // ==================== ОСНОВНОЙ TRACK VIEW MANAGER ====================

    // Инициализация менеджера представления
    async function initTrackViewManager() {
        if (isInitialized) {
            console.log('⚠️ Track View Manager уже инициализирован');
            return;
        }

        console.log('🎵 Track View Manager инициализируется...');

        // Инициализируем систему хэшей
        await initPhotoHashSystem();

        // Настройка интерфейса
        setupViewToggle();
        updateViewToggleText();
        setupSearchHandlers();
        setupSortHandlers();
        setupFilterHandlers();
        setupPresentationFilterHandlers();
        setupStatsDisplay();
        setupGlobalPlayer();
        setupProcessAllButton();

        isInitialized = true;
        console.log('✅ Track View Manager инициализирован');
    }

    // Настройка переключателя вида
    function setupViewToggle() {
        const toggleBtn = document.getElementById('toggleDetailedView');
        if (!toggleBtn) return;

        toggleBtn.addEventListener('click', function (e) {
            e.preventDefault();
            toggleViewMode();
        });
    }

    // Переключение между компактным и подробным видом
    function toggleViewMode() {
        const tracksList = document.getElementById('tracksList');
        if (!tracksList) return;

        trackViewCurrentViewMode = trackViewCurrentViewMode === 'compact' ? 'detailed' : 'compact';

        if (trackViewCurrentViewMode === 'detailed') {
            tracksList.classList.add('detailed-view');
        } else {
            tracksList.classList.remove('detailed-view');
        }

        renderFilteredTracks();
        updateViewToggleText();
    }

    // Обновление текста кнопки переключения
    function updateViewToggleText() {
        const toggleBtn = document.getElementById('toggleDetailedView');
        const textSpan = document.getElementById('viewToggleText');

        if (!toggleBtn || !textSpan) return;

        if (trackViewCurrentViewMode === 'compact') {
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
                trackViewSearchQuery = this.value.toLowerCase().trim();
                debouncedSearch();
            });

            searchInput.addEventListener('keypress', function (e) {
                if (e.key === 'Enter') {
                    trackViewSearchQuery = this.value.toLowerCase().trim();
                    performSearch();
                }
            });
        }

        if (searchBtn) {
            searchBtn.addEventListener('click', function () {
                if (searchInput) {
                    trackViewSearchQuery = searchInput.value.toLowerCase().trim();
                }
                performSearch();
            });
        }

        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', function () {
                trackViewSearchQuery = '';
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
                trackViewSortBy = this.value;
                performSort();
            });
        }

        const sortDirectionBtn = document.getElementById('sortDirectionBtn');
        if (sortDirectionBtn) {
            sortDirectionBtn.addEventListener('click', function () {
                trackViewSortDirection = trackViewSortDirection === 'asc' ? 'desc' : 'asc';
                this.innerHTML = trackViewSortDirection === 'asc' ? '↑' : '↓';
                this.title = trackViewSortDirection === 'asc' ? 'По возрастанию' : 'По убыванию';
                performSort();
            });
        }
    }

    // Настройка обработчиков фильтрации по статусу
    function setupFilterHandlers() {
        const filterButtons = document.querySelectorAll('.status-filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', function () {
                filterButtons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                trackViewFilterByStatus = this.dataset.filter;
                applyFilters();
            });
        });
    }

    // Настройка обработчиков фильтрации для презентаций
    function setupPresentationFilterHandlers() {
        createPresentationFilterButtons();

        const presFilterButtons = document.querySelectorAll('.pres-status-filter-btn');
        presFilterButtons.forEach(btn => {
            btn.addEventListener('click', function () {
                presFilterButtons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                trackViewPresentationFilterByStatus = this.dataset.filter;
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
                    <button class="btn btn-small pres-status-filter-btn ${trackViewPresentationFilterByStatus === 'all' ? 'active' : ''}" 
                            data-filter="all" title="Все треки">
                        Все
                    </button>
                    <button class="btn btn-small pres-status-filter-btn ${trackViewPresentationFilterByStatus === 'processed' ? 'active' : ''}" 
                            data-filter="processed" title="Только обработанные">
                        ✅ Обработанные
                    </button>
                    <button class="btn btn-small pres-status-filter-btn ${trackViewPresentationFilterByStatus === 'unprocessed' ? 'active' : ''}" 
                            data-filter="unprocessed" title="Только необработанные">
                        ⏳ Необработанные
                    </button>
                </div>
            </div>
        `;
    }

    // Настройка отображения статистики
    function setupStatsDisplay() {
        updateGlobalStats();
    }

    // Настройка глобального плеера
    function setupGlobalPlayer() {
        if (!trackViewGlobalAudioPlayer) {
            trackViewGlobalAudioPlayer = new Audio();
            trackViewGlobalAudioPlayer.preload = 'auto';
            trackViewGlobalAudioPlayer.volume = TRACK_VIEW_CONFIG.PLAYBACK_VOLUME;

            trackViewGlobalAudioPlayer.addEventListener('ended', function () {
                stopGlobalPlayback();
            });

            trackViewGlobalAudioPlayer.addEventListener('error', function (e) {
                if (trackViewGlobalAudioPlayer.error && trackViewGlobalAudioPlayer.error.code !== 0) {
                    console.warn('Ошибка аудио:', trackViewGlobalAudioPlayer.error.message);
                }
                stopGlobalPlayback();
            });

            trackViewGlobalAudioPlayer.addEventListener('timeupdate', function () {
                if (trackViewCurrentPlayingTrackId && trackViewIsGlobalPlaying) {
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

    // ==================== ПОИСК И ФИЛЬТРАЦИЯ ====================

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

    // Применение фильтров
    function applyFilters() {
        renderFilteredTracks();
        updateFilterStats();
    }

    // Получение отфильтрованных треков
    function getFilteredTracks() {
        if (!window.currentTracks) return [];

        let filtered = window.currentTracks.filter(track => {
            if (!track) return false;

            if (trackViewSearchQuery) {
                const artistMatch = track.artist && track.artist.toLowerCase().includes(trackViewSearchQuery);
                const titleMatch = track.title && track.title.toLowerCase().includes(trackViewSearchQuery);
                if (!artistMatch && !titleMatch) return false;
            }

            if (trackViewFilterByStatus === 'processed') {
                return track.processed === true;
            } else if (trackViewFilterByStatus === 'unprocessed') {
                return track.processed !== true;
            }

            return true;
        });

        filtered.sort((a, b) => {
            let aValue, bValue;

            switch (trackViewSortBy) {
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
                    aValue = a.processed === true ? 1 : 0;
                    bValue = b.processed === true ? 1 : 0;
                    break;
                default:
                    aValue = a.id || 0;
                    bValue = b.id || 0;
            }

            if (trackViewSortDirection === 'asc') {
                return aValue > bValue ? 1 : -1;
            } else {
                return aValue < bValue ? 1 : -1;
            }
        });

        return filtered;
    }

    // Применение фильтров для презентации
    function applyPresentationFilters() {
        if (!trackViewPresentationTrackList || trackViewPresentationTrackList.length === 0) {
            renderFilteredPresentationTracks([]);
            return;
        }

        let filteredPresentationTracks = JSON.parse(JSON.stringify(trackViewPresentationTrackList));

        if (trackViewPresentationFilterByStatus === 'processed') {
            filteredPresentationTracks = filteredPresentationTracks.filter(track => track.processed);
        } else if (trackViewPresentationFilterByStatus === 'unprocessed') {
            filteredPresentationTracks = filteredPresentationTracks.filter(track => !track.processed);
        }

        renderFilteredPresentationTracks(filteredPresentationTracks);
        updatePresentationFilterStats();
    }

    // Обновление статистики поиска
    function updateSearchStats() {
        const searchStats = document.getElementById('searchStats');
        if (!searchStats) return;

        const filtered = getFilteredTracks();
        const total = window.currentTracks ? window.currentTracks.length : 0;

        if (trackViewSearchQuery) {
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
        if (trackViewFilterByStatus === 'processed') {
            statusText = 'обработанных';
        } else if (trackViewFilterByStatus === 'unprocessed') {
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

    // Обновление статистики фильтрации презентации
    function updatePresentationFilterStats() {
        const filterStats = document.getElementById('presentationFilterStats');
        if (!filterStats) return;

        const totalInPresentation = trackViewPresentationTrackList ? trackViewPresentationTrackList.length : 0;
        let filteredCount = totalInPresentation;

        if (trackViewPresentationFilterByStatus === 'processed') {
            filteredCount = trackViewPresentationTrackList ?
                trackViewPresentationTrackList.filter(t => t.processed).length : 0;
        } else if (trackViewPresentationFilterByStatus === 'unprocessed') {
            filteredCount = trackViewPresentationTrackList ?
                trackViewPresentationTrackList.filter(t => !t.processed).length : 0;
        }

        filterStats.innerHTML = `
            <span class="filter-stats-text">
                Показано: <strong>${filteredCount}</strong> треков (из ${totalInPresentation} в списке)
            </span>
        `;
        filterStats.style.display = filteredCount === totalInPresentation ? 'none' : 'block';
    }

    // ==================== РЕНДЕРИНГ ТРЕКОВ ====================

    // Рендер отфильтрованных треков
    function renderFilteredTracks() {
        const filteredTracks = getFilteredTracks();

        // Запрашиваем хэши для отображенных треков (один раз)
        const trackIds = filteredTracks.map(track => track.id);
        if (trackIds.length > 0) {
            updatePhotoHashesForTracks(trackIds);
        }

        if (trackViewCurrentViewMode === 'detailed') {
            renderTracksDetailed(filteredTracks);
        } else {
            renderTracksCompact(filteredTracks);
        }

        updateSearchStats();
        updateFilterStats();
        updateGlobalStats();
    }

    // Рендер треков в компактном виде
    function renderTracksCompact(tracks) {
        const container = document.getElementById('tracksList');
        if (!container) return;

        if (tracks.length === 0) {
            const noResultsMessage = trackViewSearchQuery || trackViewFilterByStatus !== 'all'
                ? '<div class="empty-state"><div class="icon">🔍</div><h3>Треки не найдены</h3><p>Попробуйте изменить поисковый запрос или фильтр</p></div>'
                : '<div class="empty-state"><div class="icon">🎵</div><h3>Нет загруженных треков</h3><p>Нажмите "Загрузить треки" чтобы добавить музыку</p></div>';

            container.innerHTML = noResultsMessage;
            return;
        }

        container.innerHTML = tracks.map(track => {
            const isPlaying = trackViewCurrentPlayingTrackId === track.id && trackViewIsGlobalPlaying;
            const photoUrl = generatePhotoUrlWithHash(track.id, track.image_path);

            return `
            <div class="track-item draggable ${track.processed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" draggable="true" data-track-id="${track.id}">
                <div class="col-id">
                    ${track.id}
                    <button class="btn-id-change" onclick="window.openChangeIdModal && window.openChangeIdModal(${track.id})" title="Изменить ID">🔢</button>
                </div>
                <div class="col-artist">
                    ${track.image_path && photoUrl ?
                    `<span onclick="window.openPhotoEditor && window.openPhotoEditor(${track.id})" style="cursor: pointer; display: inline-block;">
                        <img src="${photoUrl}" 
                             data-track-id="${track.id}" 
                             alt="${escapeHtml(track.artist)}" 
                             class="track-cover"
                             onerror="handleImageError(this)"
                             onload="handleImageLoad(this)"
                             style="opacity: 1; transition: opacity 0.3s ease;">
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
    }

    // Рендер треков в подробном виде
    function renderTracksDetailed(tracks) {
        const container = document.getElementById('tracksList');
        if (!container) return;

        if (tracks.length === 0) {
            const noResultsMessage = trackViewSearchQuery || trackViewFilterByStatus !== 'all'
                ? '<div class="empty-state"><div class="icon">🔍</div><h3>Треки не найдены</h3><p>Попробуйте изменить поисковый запрос или фильтр</p></div>'
                : '<div class="empty-state"><div class="icon">🎵</div><h3>Нет загруженных треков</h3><p>Нажмите "Загрузить треки" чтобы добавить музыку</p></div>';

            container.innerHTML = noResultsMessage;
            return;
        }

        container.innerHTML = tracks.map(track => {
            const isPlaying = trackViewCurrentPlayingTrackId === track.id && trackViewIsGlobalPlaying;
            const photoUrl = generatePhotoUrlWithHash(track.id, track.image_path);

            return `
            <div class="track-item detailed draggable ${track.processed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" draggable="true" data-track-id="${track.id}">
                <div class="track-image-container">
                    ${track.image_path && photoUrl ?
                    `<img src="${photoUrl}" 
                         data-track-id="${track.id}" 
                         alt="${escapeHtml(track.artist)}"
                         onclick="window.openPhotoEditor && window.openPhotoEditor(${track.id})"
                         onerror="handleImageError(this)"
                         onload="handleImageLoad(this)"
                         style="opacity: 1; transition: opacity 0.3s ease; display: block;">` :
                    `<div class="track-cover-placeholder" onclick="window.openPhotoEditor && window.openPhotoEditor(${track.id})" title="Добавить фото">🎵</div>`
                }
                </div>
                
                <div class="track-main-content">
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
                    
                    <div class="waveform-btn-container">
                        <button class="waveform-btn" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})" title="Открыть аудио редактор">
                            ${track.duration ? `🎵 ${formatTime(track.segment_start || 0)} - ${formatTime((track.segment_start || 0) + (track.segment_duration || 30))}` : 'Загрузка...'}
                        </button>
                    </div>
                    
                    <div class="track-actions detailed">
                        <button class="btn btn-secondary btn-small play-btn" data-track-id="${track.id}" 
                                onclick="playTrackSegmentFromManager(${track.id})" title="${isPlaying ? 'Остановить воспроизведение' : 'Воспроизвести отрывок'}">
                            ${isPlaying ? '⏹️' : '▶️'}
                        </button>
                        <button class="btn btn-secondary btn-small" onclick="window.openAudioEditor && window.openPhotoEditor(${track.id})" title="Редактировать фото">🖼️</button>
                        <button class="btn btn-secondary btn-small" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})" title="Аудио редактор">🎚️</button>
                        <button class="btn btn-secondary btn-small" onclick="window.editTrack && window.editTrack(${track.id})" title="Редактировать метаданные">✏️</button>
                        <button class="btn btn-success btn-small" onclick="toggleProcessedFromManager(${track.id})" 
                                title="${track.processed ? 'Отметить как необработанный' : 'Отметить как обработанный'}">
                            ${track.processed ? '❌' : '✅'}
                        </button>
                        <button class="btn btn-danger btn-small" onclick="window.deleteTrack && window.deleteTrack(${track.id})" title="Удалить">🗑️</button>
                        <button class="btn btn-small" onclick="window.openChangeIdModal && window.openChangeIdModal(${trackId})" title="Изменить ID">#️⃣</button>
                    </div>
                </div>
            </div>
        `}).join('');
    }

    // Рендер треков презентации
    function renderFilteredPresentationTracks(tracks) {
        const container = document.getElementById('presentationTracksList');
        if (!container) return;

        if (!tracks || tracks.length === 0) {
            const noResultsMessage = trackViewPresentationFilterByStatus !== 'all'
                ? `<div class="empty-state">
                    <div class="icon">🔍</div>
                    <h3>${trackViewPresentationFilterByStatus === 'processed' ? 'Нет обработанных треков' : 'Нет необработанных треков'}</h3>
                    <p>Попробуйте изменить фильтр</p>
                   </div>`
                : '<div class="empty-state"><div class="icon">🎵</div><h3>Нет треков в списке</h3><p>Добавьте треки в список презентации</p></div>';

            container.innerHTML = noResultsMessage;
            return;
        }

        container.innerHTML = tracks.map(track => {
            const isPlaying = trackViewCurrentPlayingTrackId === track.id && trackViewIsGlobalPlaying;
            const photoUrl = generatePhotoUrlWithHash(track.id, track.image_path);

            return `
            <div class="track-item ${track.processed ? 'processed' : ''} ${isPlaying ? 'playing' : ''}" data-track-id="${track.id}">
                <div class="col-id">${track.id}</div>
                <div class="col-artist">
                    ${track.image_path && photoUrl ?
                    `<img src="${photoUrl}" 
                          alt="${escapeHtml(track.artist)}"
                          class="track-cover"
                          onerror="handleImageError(this)"
                          onload="handleImageLoad(this)"
                          style="opacity: 1;">` :
                    `<div class="track-cover empty">🎵</div>`
                }
                    <span>${escapeHtml(track.artist)}</span>
                    ${track.processed ? '<span class="track-processed-badge">✅</span>' : ''}
                </div>
                <div class="col-title">${escapeHtml(track.title)}</div>
                <div class="col-actions">
                    <button class="btn btn-secondary btn-small" onclick="playTrackSegmentFromManager(${track.id})">
                        ${isPlaying ? '⏹️' : '▶️'}
                    </button>
                    <button class="btn btn-secondary btn-small" onclick="window.openAudioEditor && window.openAudioEditor(${track.id})">🎚️</button>
                    <button class="btn btn-secondary btn-small" onclick="window.editTrack && window.editTrack(${track.id})">✏️</button>
                    <button class="btn btn-success btn-small" onclick="toggleProcessedFromManager(${track.id})">
                        ${track.processed ? '❌' : '✅'}
                    </button>
                </div>
            </div>
            `;
        }).join('');
    }

    // Обработчики для изображений
    function handleImageLoad(img) {
        img.style.opacity = '1';
        const placeholder = img.nextElementSibling;
        if (placeholder && placeholder.classList.contains('track-cover-placeholder')) {
            placeholder.style.display = 'none';
        }
    }

    function handleImageError(img) {
        img.style.display = 'none';
        const placeholder = img.nextElementSibling;
        if (placeholder && placeholder.classList.contains('track-cover-placeholder')) {
            placeholder.style.display = 'flex';
        }
    }

    // ==================== ВОСПРОИЗВЕДЕНИЕ АУДИО ====================

    // Воспроизведение отрезка трека
    async function playTrackSegmentFromManager(trackId) {
        try {
            if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
                stopGlobalPlayback();
                return;
            }

            stopGlobalPlayback();

            const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
            if (!track) {
                showNotification('Трек не найден', 'error');
                return;
            }

            trackViewCurrentPlayingTrackId = trackId;
            trackViewIsGlobalPlaying = true;

            updatePlayButtons();

            showNotification(`▶️ Воспроизведение: ${track.artist} - ${track.title}`, 'info');

            const segmentUrl = `/api/tracks/${trackId}/segment-file?start_time=${track.segment_start || 0}&duration=${track.segment_duration || 30}&nocache=${Date.now()}`;

            if (!trackViewGlobalAudioPlayer) {
                setupGlobalPlayer();
            }

            if (trackViewGlobalAudioPlayer) {
                trackViewGlobalAudioPlayer.pause();
                trackViewGlobalAudioPlayer.currentTime = 0;
            }

            trackViewGlobalAudioPlayer.src = segmentUrl;
            trackViewGlobalAudioPlayer.currentTime = 0;

            const playPromise = trackViewGlobalAudioPlayer.play();

            if (playPromise !== undefined) {
                playPromise
                    .then(() => {
                        updateNowPlayingInfo(track);
                    })
                    .catch(error => {
                        console.error('❌ Ошибка воспроизведения:', error);
                        showNotification('Ошибка воспроизведения трека', 'error');
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
        if (trackViewGlobalAudioPlayer) {
            try {
                trackViewGlobalAudioPlayer.pause();
                trackViewGlobalAudioPlayer.currentTime = 0;
                trackViewGlobalAudioPlayer.src = '';
            } catch (error) {
                console.warn('Ошибка при остановке воспроизведения:', error);
            }
        }

        trackViewCurrentPlayingTrackId = null;
        trackViewIsGlobalPlaying = false;

        updatePlayButtons();
        hideNowPlayingInfo();
    }

    // Обновление кнопок воспроизведения
    function updatePlayButtons() {
        document.querySelectorAll('.play-btn').forEach(btn => {
            const trackId = parseInt(btn.dataset.trackId);
            if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
                btn.innerHTML = '⏹️';
                btn.title = 'Остановить воспроизведение';
            } else {
                btn.innerHTML = '▶️';
                btn.title = 'Воспроизвести отрывок';
            }
        });

        document.querySelectorAll('.play-btn-presentation').forEach(btn => {
            const trackId = parseInt(btn.dataset.trackId);
            if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
                btn.innerHTML = '⏹️';
                btn.title = 'Остановить воспроизведение';
            } else {
                btn.innerHTML = '▶️';
                btn.title = 'Воспроизвести отрывок';
            }
        });

        document.querySelectorAll('.track-item').forEach(item => {
            const trackId = parseInt(item.dataset.trackId);
            if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
                item.classList.add('playing');
            } else {
                item.classList.remove('playing');
            }
        });

        const presentationContainer = document.getElementById('presentationTracksList');
        if (presentationContainer) {
            presentationContainer.querySelectorAll('.track-item').forEach(item => {
                const trackId = parseInt(item.dataset.trackId);
                if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
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

    // ==================== ИНЛАЙН-РЕДАКТИРОВАНИЕ ====================

    // Инлайн-редактирование
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
                if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
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

            const response = await fetch(`/api/tracks/${trackId}`, {
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
                if (trackViewCurrentPlayingTrackId === trackId && trackViewIsGlobalPlaying) {
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

    // ==================== УПРАВЛЕНИЕ СТАТУСАМИ ====================

    // Функция для переключения статуса обработки
    async function toggleProcessedStatus(trackId, forceValue = null) {
        const track = window.currentTracks && window.currentTracks.find(t => t.id === trackId);
        if (!track) return;

        const newStatus = forceValue !== null ? forceValue : !track.processed;

        try {
            const response = await fetch(`/api/tracks/${trackId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ processed: newStatus })
            });

            if (!response.ok) {
                throw new Error('Ошибка обновления статуса');
            }

            track.processed = newStatus;

            renderFilteredTracks();
            updateGlobalStats();

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

    // ==================== СТАТИСТИКА ====================

    // Обновление статистики
    function updateGlobalStats() {
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
                    <div class="stat-card">
                        <div class="stat-icon">🖼️</div>
                        <div class="stat-info">
                            <span class="stat-label">С фото</span>
                            <span class="stat-value">${withPhotos}</span>
                        </div>
                    </div>
                </div>
            `;

        } catch (error) {
            console.error('Ошибка обновления статистики:', error);
        }
    }

    // ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

    // Функция для обновления отображения
    function refreshTrackDisplay() {
        renderFilteredTracks();
    }

    // Обновление отображения треков презентации
    function refreshPresentationTrackDisplay() {
        if (trackViewPresentationTrackList) {
            applyPresentationFilters();
        }
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
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

    // ==================== ГЛОБАЛЬНЫЕ ФУНКЦИИ ====================

    // Функция для установки списка презентации
    function setPresentationTrackList(tracks) {
        trackViewPresentationTrackList = Array.isArray(tracks) ? JSON.parse(JSON.stringify(tracks)) : [];
        console.log(`📋 Установлен список презентации: ${trackViewPresentationTrackList.length} треков`);
        applyPresentationFilters();
    }

    // Функция для получения списка презентаций
    function getPresentationList() {
        return trackViewPresentationTrackList;
    }

    // Экспорт функций в глобальную область видимости
    window.trackViewManager = {
        // Основные функции
        toggleViewMode: toggleViewMode,
        startInlineEdit: startInlineEdit,
        refreshTrackDisplay: refreshTrackDisplay,
        updateViewToggleText: updateViewToggleText,
        handleImageLoad: handleImageLoad,
        handleImageError: handleImageError,
        playTrackSegment: playTrackSegmentFromManager,
        stopGlobalPlayback: stopGlobalPlayback,
        getFilteredTracks: getFilteredTracks,
        updateGlobalStats: updateGlobalStats,
        initTrackViewManager: initTrackViewManager,
        renderFilteredTracks: renderFilteredTracks,
        toggleProcessedStatus: toggleProcessedStatus,
        updatePlayButtons: updatePlayButtons,
        escapeHtml: escapeHtml,
        formatTime: formatTime,
        applyPresentationFilters: applyPresentationFilters,
        refreshPresentationTrackDisplay: refreshPresentationTrackDisplay,
        updatePresentationFilterStats: updatePresentationFilterStats,

        // Система хэшей
        initPhotoHashSystem: initPhotoHashSystem,
        getPhotoHash: getPhotoHash,
        savePhotoHash: savePhotoHash,
        updatePhotoHashesForTracks: updatePhotoHashesForTracks,
        generatePhotoUrl: generatePhotoUrl,

        // Функция для презентации
        setPresentationTrackList: setPresentationTrackList,
        getPresentationList: getPresentationList
    };

    // Глобальные функции для совместимости
    window.toggleViewMode = toggleViewMode;
    window.startInlineEdit = startInlineEdit;
    window.playTrackSegment = playTrackSegmentFromManager;
    window.stopGlobalPlayback = stopGlobalPlayback;
    window.updateGlobalStats = updateGlobalStats;
    window.initTrackViewManager = initTrackViewManager;
    window.setPresentationTrackList = setPresentationTrackList;
    window.getPresentationList = getPresentationList;

    // Инициализация при загрузке
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initTrackViewManager();
        });
    } else {
        initTrackViewManager();
    }

    console.log('✅ Track View Manager загружен с правильным кешированием');
}