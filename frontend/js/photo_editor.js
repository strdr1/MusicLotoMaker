// photo_editor.js — ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ
// === Глобальные переменные ===
let currentPhotoEditorTrackId = null;
let currentTool = 'select';
let isSelecting = false;
let isErasing = false;
let selectPoints = [];
let currentEraserOperation = null;
let eraserOperations = [];
let cropRect = { x: 100, y: 100, width: 200, height: 150 };
let isDraggingCrop = false;
let isResizingCrop = false;
let dragStart = { x: 0, y: 0 };
let originalImageSize = { width: 0, height: 0 };
let zoomLevel = 1;
let imagePosition = { x: 0, y: 0 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let resizeEdge = null;
let eraserSize = 20;
let currentImageData = null;
let isInitialized = false;
let toolLock = false;

// История изменений
let editHistory = [];
let currentHistoryIndex = -1;
let MAX_HISTORY = 20;
let originalImageState = null;
let lastUploadedPhoto = null; // Сохраняем последнее загруженное фото
let previousPhotoBeforeUpload = null; // Сохраняем фото до загрузки нового

// === Основные функции редактора ===
function openPhotoEditor(trackId) {
    const track = currentTracks.find(t => t.id === trackId);
    if (!track) return;

    currentPhotoEditorTrackId = trackId;
    document.getElementById('photoEditorArtistName').textContent = track.artist || 'Неизвестный';

    const imgUrl = track.image_path
        ? `${API_BASE}/tracks/${trackId}/artist-photo?t=${Date.now()}`
        : 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgdmlld0JveD0iMCAwIDEwMCAxMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiMyZDM3NDgiLz48dGV4dCB4PSI1MCIgeT0iNTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxMiIgZmlsbD0iI2NiZDVlMCIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPs6PzqPOlc6dzp/Oo86ZPC90ZXh0Pjwvc3ZnPg==';

    const imgElement = document.getElementById('photoEditorImage');
    imgElement.src = imgUrl;

    resetEditorState();
    updateImageTransform();

    imgElement.onload = function () {
        const imgWidth = imgElement.naturalWidth;
        const imgHeight = imgElement.naturalHeight;
        originalImageSize.width = imgWidth;
        originalImageSize.height = imgHeight;

        const container = document.getElementById('photoEditorImageContainer');
        const maxWidth = container.clientWidth - 40;
        const maxHeight = container.clientHeight - 40;

        const scaleX = maxWidth / imgWidth;
        const scaleY = maxHeight / imgHeight;
        zoomLevel = Math.min(scaleX, scaleY, 1);
        updateImageTransform();
    };

    document.getElementById('photoEditorModal').style.display = 'flex';
}

function resetEditorState() {
    zoomLevel = 1;
    imagePosition = { x: 0, y: 0 };
    selectPoints = [];
    eraserOperations = [];
    currentEraserOperation = null;
    isSelecting = false;
    isErasing = false;
    cropRect = { x: 100, y: 100, width: 200, height: 150 };
    currentImageData = null;
    isInitialized = false;
    toolLock = false;
    editHistory = [];
    currentHistoryIndex = -1;
    originalImageState = null;
}

function closePhotoEditor() {
    document.getElementById('photoEditorModal').style.display = 'none';
    currentPhotoEditorTrackId = null;
    resetEditorState();
}

// === Функции для загрузки фото ===
function uploadCustomPhotoForEditor() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            // Сохраняем текущее фото перед загрузкой нового
            const imgElement = document.getElementById('photoEditorImage');
            previousPhotoBeforeUpload = imgElement ? imgElement.src : null;

            const formData = new FormData();
            formData.append('photo', file);

            const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/upload-artist-photo`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                showPhotoNotification('✅ Фото успешно загружено', 'success');

                // Получаем обновленное изображение с сервера
                const imgElement = document.getElementById('photoEditorImage');
                const removerImgElement = document.getElementById('backgroundRemoverImage');

                if (imgElement) {
                    // Обновляем изображение, добавляя timestamp для предотвращения кэширования
                    const newUrl = `${API_BASE}/tracks/${currentPhotoEditorTrackId}/artist-photo?t=${Date.now()}`;
                    imgElement.src = newUrl;
                    currentImageData = newUrl;
                    originalImageState = newUrl;
                    lastUploadedPhoto = newUrl; // Сохраняем последнее загруженное фото
                }
                if (removerImgElement) {
                    const newUrl = `${API_BASE}/tracks/${currentPhotoEditorTrackId}/artist-photo?t=${Date.now()}`;
                    removerImgElement.src = newUrl;
                }

                // Сбрасываем состояние редактора
                resetEditorState();
                updateImageTransform();

            } else {
                showPhotoNotification('❌ Ошибка загрузки: ' + result.error, 'error');
            }
        } catch (error) {
            console.error('❌ Ошибка загрузки фото:', error);
            showPhotoNotification('❌ Ошибка загрузки фото', 'error');
        }
    };
    input.click();
}

// ФУНКЦИЯ ДЛЯ ОТМЕНЫ ЗАГРУЗКИ ФОТО
function cancelPhotoUpload() {
    if (!previousPhotoBeforeUpload) {
        showPhotoNotification('❌ Нет загруженного фото для отмены', 'error');
        return;
    }

    if (!confirm('Отменить загрузку нового фото и вернуть предыдущее?')) {
        return;
    }

    try {
        const imgElement = document.getElementById('photoEditorImage');
        const removerImgElement = document.getElementById('backgroundRemoverImage');

        if (imgElement) {
            imgElement.src = previousPhotoBeforeUpload;
            currentImageData = previousPhotoBeforeUpload;
            originalImageState = previousPhotoBeforeUpload;
        }
        if (removerImgElement) {
            removerImgElement.src = previousPhotoBeforeUpload;
        }

        // Сбрасываем сохраненные данные о загрузке
        lastUploadedPhoto = null;
        previousPhotoBeforeUpload = null;

        showPhotoNotification('✅ Загрузка фото отменена', 'success');
    } catch (error) {
        console.error('❌ Ошибка отмены загрузки:', error);
        showPhotoNotification('❌ Ошибка отмены загрузки', 'error');
    }
}

function uploadPhotoDirectToEditor() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            // Сохраняем текущее фото перед загрузкой нового
            const imgElement = document.getElementById('photoEditorImage');
            previousPhotoBeforeUpload = imgElement ? imgElement.src : null;

            // Показываем превью сразу
            const url = URL.createObjectURL(file);
            const removerImgElement = document.getElementById('backgroundRemoverImage');

            if (imgElement) {
                imgElement.src = url;
            }
            if (removerImgElement) {
                removerImgElement.src = url;
            }

            // Сохраняем на сервер
            const formData = new FormData();
            formData.append('photo', file);

            const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/upload-artist-photo`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                showPhotoNotification('✅ Фото успешно загружено', 'success');

                // Получаем обновленное изображение с сервера
                const newUrl = `${API_BASE}/tracks/${currentPhotoEditorTrackId}/artist-photo?t=${Date.now()}`;

                if (imgElement) {
                    imgElement.src = newUrl;
                    currentImageData = newUrl;
                    originalImageState = newUrl;
                    lastUploadedPhoto = newUrl; // Сохраняем последнее загруженное фото
                }
                if (removerImgElement) {
                    removerImgElement.src = newUrl;
                }

            } else {
                showPhotoNotification('❌ Ошибка загрузки: ' + result.error, 'error');
                // Откатываем к предыдущему изображению при ошибке
                if (previousPhotoBeforeUpload) {
                    imgElement.src = previousPhotoBeforeUpload;
                    if (removerImgElement) {
                        removerImgElement.src = previousPhotoBeforeUpload;
                    }
                }
            }

            // Освобождаем временный URL
            setTimeout(() => {
                URL.revokeObjectURL(url);
            }, 1000);

        } catch (error) {
            console.error('❌ Ошибка загрузки фото:', error);
            showPhotoNotification('❌ Ошибка загрузки фото', 'error');
        }
    };
    input.click();
}

async function saveEditorPhoto() {
    if (!currentPhotoEditorTrackId) {
        alert('Сначала выберите трек');
        return;
    }

    try {
        // Если есть изменения в background remover, применяем их
        if (editHistory.length > 1) {
            await applyAllChanges();
        } else {
            showPhotoNotification('ℹ️ Нет изменений для сохранения', 'info');
        }

        closePhotoEditor();
        await loadTracks();
        showPhotoNotification('✅ Фото сохранено', 'success');
    } catch (e) {
        showPhotoNotification('❌ Ошибка сохранения', 'error');
    }
}

// === Функции для вырезания фона ===
function openBackgroundRemover() {
    if (!currentPhotoEditorTrackId) {
        alert('❌ Сначала выберите трек');
        return;
    }

    const modal = document.getElementById('photoEditorModal');
    if (!modal || modal.style.display === 'none') {
        alert('❌ Модальное окно с фото не открыто');
        return;
    }

    modal.style.display = 'none';
    let removerModal = document.getElementById('backgroundRemoverModal');

    if (!removerModal) {
        createBackgroundRemoverModal();
        removerModal = document.getElementById('backgroundRemoverModal');
    }

    const imgElement = document.getElementById('photoEditorImage');
    const imageElement = document.getElementById('backgroundRemoverImage');

    if (!imageElement) {
        console.error('❌ Элемент #backgroundRemoverImage не найден');
        modal.style.display = 'flex';
        return;
    }

    imageElement.src = imgElement.src;
    originalImageState = imgElement.src;
    resetEditorState();

    imageElement.onload = function () {
        initializeBackgroundRemover();
    };

    removerModal.style.display = 'flex';
}

function createBackgroundRemoverModal() {
    const modal = document.createElement('div');
    modal.id = 'backgroundRemoverModal';
    modal.className = 'modal';
    modal.style.display = 'none';

    modal.innerHTML = `
        <div class="modal-content" style="max-width: 95vw; max-height: 95vh; width: 95vw; height: 95vh;">
            <div class="modal-header">
                <h3>✂️ Профессиональный редактор фото</h3>
                <button class="photo-editor-close" onclick="closeBackgroundRemover()">&times;</button>
            </div>
            <div class="modal-body" style="display: flex; height: calc(100% - 100px);">
                <div class="tool-panel" style="width: 200px; padding: 15px; border-right: 1px solid #3d3d3d;">
                    <button class="photo-editor-btn-tool active" onclick="setTool('select')" id="tool-select" title="Выделить область">✏️ Выделение</button>
                    <button class="photo-editor-btn-tool" onclick="setTool('crop')" id="tool-crop" title="Обрезать кадр">🔲 Обрезка</button>
                    <button class="photo-editor-btn-tool" onclick="setTool('eraser')" id="tool-eraser" title="Ластик">🧽 Ластик</button>
                    <button class="photo-editor-btn-tool" onclick="setTool('hand')" id="tool-hand" title="Перемещение">👋 Рука</button>
                    
                    <div style="margin: 20px 0; width: 100%; display: flex; flex-direction: column; align-items: center; gap: 8px;">
                        <div style="color: #cccccc; font-size: 12px;">Размер ластика: <span id="eraserSizeValue">20</span>px</div>
                        <input type="range" id="eraserSize" min="1" max="100" value="20" style="width: 90%;">
                    </div>
                    
                    <div style="margin: 15px 0; width: 100%; display: flex; gap: 8px; justify-content: center;">
                        <button class="photo-editor-btn-tool" onclick="undoEdit()" title="Отменить" id="undo-btn" style="font-size: 14px; padding: 8px 12px;">↶ Отменить</button>
                        <button class="photo-editor-btn-tool" onclick="redoEdit()" title="Повторить" id="redo-btn" style="font-size: 14px; padding: 8px 12px;">↷ Повторить</button>
                    </div>
                    
                    <div style="color: #888; font-size: 12px; text-align: center; margin-top: 10px;">
                        Операций: <span id="operations-count">0</span>
                    </div>
                    
                    <div style="margin-top: 10px; padding: 8px; background: rgba(255,255,255,0.1); border-radius: 4px;">
                        <div style="color: #ccc; font-size: 10px; text-align: center;">
                            Область обрезки:<br/>
                            <span id="cropSizeInfo">200 x 150</span>
                        </div>
                    </div>
                    
                    <div style="margin-top: 20px; display: flex; flex-direction: column; gap: 8px;">
                        <button class="photo-editor-btn success" onclick="applySelectionCut()" style="font-size: 12px; padding: 8px;">✂️ Вырезать выделенное</button>
                        <button class="photo-editor-btn secondary" onclick="applyCrop()" style="font-size: 12px; padding: 8px;">🔲 Применить обрезку</button>
                        <button class="photo-editor-btn warning" onclick="resetAllChanges()" style="font-size: 12px; padding: 8px;">🔄 Сбросить всё</button>
                        <button class="photo-editor-btn danger" onclick="revertToOriginal()" style="font-size: 12px; padding: 8px; background: #c6262e;">⏮️ Вернуть оригинал</button>
                        <button class="photo-editor-btn secondary" onclick="uploadPhotoDirectToEditor()" style="font-size: 12px; padding: 8px;">📁 Загрузить своё фото</button>
                        <button class="photo-editor-btn warning" onclick="cancelPhotoUpload()" id="cancel-upload-btn" style="font-size: 12px; padding: 8px; display: none;">❌ Отменить загрузку</button>
                    </div>
                </div>
                
                <div id="backgroundRemoverContainer" style="flex: 1; position: relative; overflow: hidden; background: #2d3748;">
                    <img id="backgroundRemoverImage" src="" style="position: absolute; transform-origin: 0 0; transition: transform 0.1s;" />
                    
                    <div id="cropRect" style="display: none; position: absolute; border: 2px dashed #1a5fb4; background: rgba(26, 95, 180, 0.1); box-sizing: border-box;">
                        <div class="crop-handle top" style="position: absolute; top: -4px; left: 50%; transform: translateX(-50%); width: 8px; height: 8px; background: #1a5fb4; cursor: n-resize;"></div>
                        <div class="crop-handle bottom" style="position: absolute; bottom: -4px; left: 50%; transform: translateX(-50%); width: 8px; height: 8px; background: #1a5fb4; cursor: s-resize;"></div>
                        <div class="crop-handle left" style="position: absolute; left: -4px; top: 50%; transform: translateY(-50%); width: 8px; height: 8px; background: #1a5fb4; cursor: w-resize;"></div>
                        <div class="crop-handle right" style="position: absolute; right: -4px; top: 50%; transform: translateY(-50%); width: 8px; height: 8px; background: #1a5fb4; cursor: e-resize;"></div>
                        <div class="crop-handle top-left" style="position: absolute; top: -4px; left: -4px; width: 8px; height: 8px; background: #1a5fb4; cursor: nw-resize;"></div>
                        <div class="crop-handle top-right" style="position: absolute; top: -4px; right: -4px; width: 8px; height: 8px; background: #1a5fb4; cursor: ne-resize;"></div>
                        <div class="crop-handle bottom-left" style="position: absolute; bottom: -4px; left: -4px; width: 8px; height: 8px; background: #1a5fb4; cursor: sw-resize;"></div>
                        <div class="crop-handle bottom-right" style="position: absolute; bottom: -4px; right: -4px; width: 8px; height: 8px; background: #1a5fb4; cursor: se-resize;"></div>
                    </div>
                    
                    <canvas id="selectionCanvas" style="position: absolute; top: 0; left: 0; pointer-events: none;"></canvas>
                    <canvas id="eraserCanvas" style="position: absolute; top: 0; left: 0; pointer-events: none;"></canvas>
                    
                    <div class="tool-info" id="toolInfo" style="position: absolute; bottom: 10px; left: 10px; color: #ccc; font-size: 12px; background: rgba(0,0,0,0.7); padding: 5px 10px; border-radius: 3px;">Инструмент: Выделение</div>
                    <div class="zoom-info" id="zoomInfo" style="position: absolute; top: 10px; right: 10px; color: #ccc; font-size: 12px; background: rgba(0,0,0,0.7); padding: 5px 10px; border-radius: 3px;">100%</div>
                </div>
            </div>
            
            <div class="modal-actions" style="padding: 15px; border-top: 1px solid #3d3d3d; display: flex; gap: 10px; justify-content: center;">
                <button class="photo-editor-btn success" onclick="applyAllChanges()">✅ Применить все изменения</button>
                <button class="photo-editor-btn secondary" onclick="closeBackgroundRemover()">💾 Сохранить и выйти</button>
                <button class="photo-editor-btn warning" onclick="cancelEditing()">❌ Отмена</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    setTimeout(() => {
        initializeEventHandlers();
    }, 100);
}

function initializeEventHandlers() {
    if (isInitialized) return;

    const container = document.getElementById('backgroundRemoverContainer');
    const eraserSizeInput = document.getElementById('eraserSize');

    if (container) {
        // Удаляем старые обработчики
        container.removeEventListener('mousedown', handleContainerMouseDown);
        container.removeEventListener('mousemove', handleContainerMouseMove);
        container.removeEventListener('mouseup', handleContainerMouseUp);
        container.removeEventListener('wheel', handleContainerWheel);

        // Добавляем новые
        container.addEventListener('mousedown', handleContainerMouseDown);
        container.addEventListener('mousemove', handleContainerMouseMove);
        container.addEventListener('mouseup', handleContainerMouseUp);
        container.addEventListener('wheel', handleContainerWheel);

        // Обработчики для ручек обрезки
        const handles = container.querySelectorAll('.crop-handle');
        handles.forEach(handle => {
            handle.removeEventListener('mousedown', handleCropHandleMouseDown);
            handle.addEventListener('mousedown', handleCropHandleMouseDown);
        });

        // Обработчик для перемещения области обрезки
        const cropRectElement = document.getElementById('cropRect');
        if (cropRectElement) {
            cropRectElement.removeEventListener('mousedown', handleCropRectMouseDown);
            cropRectElement.addEventListener('mousedown', handleCropRectMouseDown);
        }

        if (eraserSizeInput) {
            eraserSizeInput.addEventListener('input', handleEraserSizeChange);
        }
    }

    isInitialized = true;
}

// === История изменений ===
function saveToHistory() {
    const imageElement = document.getElementById('backgroundRemoverImage');
    if (!imageElement) return;

    const state = {
        imageSrc: imageElement.src,
        eraserOperations: JSON.parse(JSON.stringify(eraserOperations)),
        selectPoints: JSON.parse(JSON.stringify(selectPoints)),
        timestamp: Date.now()
    };

    if (currentHistoryIndex < editHistory.length - 1) {
        editHistory = editHistory.slice(0, currentHistoryIndex + 1);
    }

    editHistory.push(state);
    currentHistoryIndex = editHistory.length - 1;

    if (editHistory.length > MAX_HISTORY) {
        editHistory.shift();
        currentHistoryIndex--;
    }

    updateOperationsCount();
    updateUndoRedoButtons();
}

function undoEdit() {
    if (currentHistoryIndex > 0) {
        currentHistoryIndex--;
        restoreFromHistory();
        showPhotoNotification('↶ Отменена последняя операция', 'info');
    } else {
        showPhotoNotification('❌ Нечего отменять', 'warning');
    }
}

function redoEdit() {
    if (currentHistoryIndex < editHistory.length - 1) {
        currentHistoryIndex++;
        restoreFromHistory();
        showPhotoNotification('↷ Повторена последняя операция', 'info');
    } else {
        showPhotoNotification('❌ Нечего повторять', 'warning');
    }
}

function restoreFromHistory() {
    const state = editHistory[currentHistoryIndex];
    const imageElement = document.getElementById('backgroundRemoverImage');

    if (imageElement) {
        imageElement.src = state.imageSrc;
        currentImageData = state.imageSrc;
        eraserOperations = JSON.parse(JSON.stringify(state.eraserOperations));
        selectPoints = JSON.parse(JSON.stringify(state.selectPoints || []));
    }

    updateOperationsCount();
    updateUndoRedoButtons();
    updateSelectionCanvas();
}

function updateOperationsCount() {
    const countElement = document.getElementById('operations-count');
    if (countElement) {
        countElement.textContent = eraserOperations.length;
    }
}

function updateUndoRedoButtons() {
    const undoBtn = document.getElementById('undo-btn');
    const redoBtn = document.getElementById('redo-btn');

    if (undoBtn) {
        undoBtn.disabled = currentHistoryIndex <= 0;
        undoBtn.style.opacity = currentHistoryIndex <= 0 ? '0.5' : '1';
    }

    if (redoBtn) {
        redoBtn.disabled = currentHistoryIndex >= editHistory.length - 1;
        redoBtn.style.opacity = currentHistoryIndex >= editHistory.length - 1 ? '0.5' : '1';
    }

    // Обновляем видимость кнопки отмены загрузки
    const cancelUploadBtn = document.getElementById('cancel-upload-btn');
    if (cancelUploadBtn) {
        if (lastUploadedPhoto) {
            cancelUploadBtn.style.display = 'block';
        } else {
            cancelUploadBtn.style.display = 'none';
        }
    }
}

// === Основные функции ===
function initializeBackgroundRemover() {
    const imageElement = document.getElementById('backgroundRemoverImage');
    const container = document.getElementById('backgroundRemoverContainer');

    if (!imageElement || !container) return;

    const imgWidth = imageElement.naturalWidth;
    const imgHeight = imageElement.naturalHeight;
    originalImageSize.width = imgWidth;
    originalImageSize.height = imgHeight;

    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;

    const scaleX = containerWidth / imgWidth;
    const scaleY = containerHeight / imgHeight;
    zoomLevel = Math.min(scaleX, scaleY, 1);

    imagePosition.x = (containerWidth - imgWidth * zoomLevel) / 2;
    imagePosition.y = (containerHeight - imgHeight * zoomLevel) / 2;

    updateImageTransform();

    const canvas = document.getElementById('selectionCanvas');
    const eraserCanvas = document.getElementById('eraserCanvas');

    if (canvas && eraserCanvas) {
        canvas.width = containerWidth;
        canvas.height = containerHeight;
        eraserCanvas.width = containerWidth;
        eraserCanvas.height = containerHeight;
    }

    // Инициализация области обрезки
    cropRect.width = Math.min(containerWidth * 0.6, 300);
    cropRect.height = Math.min(containerHeight * 0.6, 200);
    cropRect.x = (containerWidth - cropRect.width) / 2;
    cropRect.y = (containerHeight - cropRect.height) / 2;

    updateCropRect();
    updateCropSizeInfo();

    toolLock = true;
    setTool('select');
    toolLock = false;

    updateZoomInfo();
    saveCurrentImageState();
    saveToHistory();

    // Обновляем кнопки
    updateUndoRedoButtons();
}

function setTool(tool) {
    if (toolLock && currentTool !== tool) return;
    if (currentTool === tool) return;

    currentTool = tool;

    const tools = ['select', 'crop', 'eraser', 'hand'];
    tools.forEach(t => {
        const btn = document.getElementById(`tool-${t}`);
        if (btn) btn.classList.toggle('active', t === tool);
    });

    const toolInfo = document.getElementById('toolInfo');
    if (toolInfo) {
        const toolNames = {
            'select': 'Выделение',
            'crop': 'Обрезка',
            'eraser': 'Ластик',
            'hand': 'Перемещение'
        };
        toolInfo.textContent = `Инструмент: ${toolNames[tool]}`;
    }

    const container = document.getElementById('backgroundRemoverContainer');
    if (container) {
        container.style.cursor = '';
        if (tool === 'select') container.style.cursor = 'crosshair';
        if (tool === 'crop') container.style.cursor = 'default';
        if (tool === 'eraser') container.style.cursor = 'crosshair';
        if (tool === 'hand') container.style.cursor = 'grab';
    }

    const cropRectElement = document.getElementById('cropRect');
    if (cropRectElement) {
        cropRectElement.style.display = tool === 'crop' ? 'block' : 'none';
    }

    if (tool !== 'select') {
        isSelecting = false;
        updateSelectionCanvas();
    }

    if (tool !== 'eraser') {
        isErasing = false;
        currentEraserOperation = null;
        updateEraserCanvas();
    }
}

// === Обработчики событий ===
function handleContainerMouseDown(e) {
    e.preventDefault();
    e.stopPropagation();

    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (currentTool === 'select') {
        startSelection(x, y);
    } else if (currentTool === 'hand') {
        startPanning(x, y);
    } else if (currentTool === 'eraser') {
        startErasing(x, y);
    } else if (currentTool === 'crop') {
        // Обработка клика на области обрезки
        const cropRectElement = document.getElementById('cropRect');
        if (cropRectElement && e.target === cropRectElement) {
            handleCropRectMouseDown(e);
        }
    }
}

function handleContainerMouseMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (currentTool === 'select' && isSelecting) {
        continueSelection(x, y);
    } else if (currentTool === 'hand' && isPanning) {
        continuePanning(x, y);
    } else if (currentTool === 'eraser' && isErasing) {
        continueErasing(x, y);
    } else if (currentTool === 'crop') {
        if (isResizingCrop) {
            handleCropResize(x, y);
        } else if (isDraggingCrop) {
            handleCropDrag(x, y);
        }
    }
}

function handleContainerMouseUp(e) {
    if (currentTool === 'select' && isSelecting) {
        endSelection();
    } else if (currentTool === 'hand' && isPanning) {
        endPanning();
    } else if (currentTool === 'eraser' && isErasing) {
        endErasing();
    } else if (currentTool === 'crop') {
        isDraggingCrop = false;
        isResizingCrop = false;
        resizeEdge = null;
        updateCropSizeInfo();
    }
}

function handleContainerWheel(e) {
    e.preventDefault();

    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const worldX = (mouseX - imagePosition.x) / zoomLevel;
    const worldY = (mouseY - imagePosition.y) / zoomLevel;

    const oldZoom = zoomLevel;
    zoomLevel *= zoomFactor;
    zoomLevel = Math.max(0.1, Math.min(5, zoomLevel));

    imagePosition.x = mouseX - worldX * zoomLevel;
    imagePosition.y = mouseY - worldY * zoomLevel;

    updateImageTransform();
    updateZoomInfo();
}

// === Профессиональный ластик ===
function startErasing(x, y) {
    isErasing = true;
    if (!currentImageData) {
        saveCurrentImageState();
    }

    currentEraserOperation = {
        points: [{ x, y, size: eraserSize }],
        size: eraserSize,
        timestamp: Date.now()
    };

    updateEraserPreview();
}

function continueErasing(x, y) {
    if (!isErasing || !currentEraserOperation) return;

    currentEraserOperation.points.push({ x, y, size: eraserSize });
    updateEraserPreview();
    updateEraserCanvas();
}

async function endErasing() {
    if (!isErasing || !currentEraserOperation) return;

    isErasing = false;

    if (currentEraserOperation.points.length > 0) {
        eraserOperations.push(currentEraserOperation);
        await applyEraserOperation(currentEraserOperation);
        saveToHistory();
        showPhotoNotification(`✅ Ластик применен (${currentEraserOperation.points.length} точек)`, 'success');
    }

    currentEraserOperation = null;
    updateEraserCanvas();
}

async function applyEraserOperation(operation) {
    if (!currentPhotoEditorTrackId) return false;

    try {
        const container = document.getElementById('backgroundRemoverContainer');
        const imageTransform = {
            x: imagePosition.x,
            y: imagePosition.y,
            scale: zoomLevel
        };

        const containerSize = {
            width: container.clientWidth,
            height: container.clientHeight
        };

        const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/process-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                operations: [
                    {
                        type: 'erase',
                        data: {
                            operations: [operation]
                        }
                    }
                ],
                container_size: containerSize,
                image_transform: imageTransform
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                const imageElement = document.getElementById('backgroundRemoverImage');
                imageElement.src = result.image;
                currentImageData = result.image;
                return true;
            }
        }
    } catch (error) {
        console.error('Ошибка применения ластика:', error);
        showPhotoNotification('❌ Ошибка применения ластика', 'error');
    }

    return false;
}

async function updateEraserPreview() {
    if (!currentPhotoEditorTrackId || !currentEraserOperation) return;

    try {
        const container = document.getElementById('backgroundRemoverContainer');
        const imageTransform = {
            x: imagePosition.x,
            y: imagePosition.y,
            scale: zoomLevel
        };

        const containerSize = {
            width: container.clientWidth,
            height: container.clientHeight
        };

        const allOperations = [...eraserOperations, currentEraserOperation];

        const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/preview-eraser`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image: currentImageData,
                operations: allOperations,
                container_size: containerSize,
                image_transform: imageTransform
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                const imageElement = document.getElementById('backgroundRemoverImage');
                imageElement.src = result.image;
            }
        }
    } catch (error) {
        console.error('Ошибка предпросмотра ластика:', error);
    }
}

// === Функции выделения ===
function startSelection(x, y) {
    isSelecting = true;
    selectPoints = [{ x, y }];
    updateSelectionCanvas();
}

function continueSelection(x, y) {
    if (!isSelecting) return;

    if (selectPoints.length === 0 ||
        Math.abs(x - selectPoints[selectPoints.length - 1].x) > 2 ||
        Math.abs(y - selectPoints[selectPoints.length - 1].y) > 2) {
        selectPoints.push({ x, y });
        updateSelectionCanvas();
    }
}

function endSelection() {
    if (!isSelecting) return;

    isSelecting = false;

    if (selectPoints.length > 2) {
        const closedPoints = [...selectPoints, selectPoints[0]];
        selectPoints = closedPoints;
        updateSelectionCanvas();
        showPhotoNotification('✅ Область выделена', 'info');
    } else {
        showPhotoNotification('❌ Выделите большую область', 'warning');
        selectPoints = [];
        updateSelectionCanvas();
    }
}

async function applySelectionCut() {
    if (selectPoints.length < 3) {
        showPhotoNotification('❌ Сначала выделите область', 'warning');
        return;
    }

    try {
        const container = document.getElementById('backgroundRemoverContainer');
        const imageTransform = {
            x: imagePosition.x,
            y: imagePosition.y,
            scale: zoomLevel
        };

        const containerSize = {
            width: container.clientWidth,
            height: container.clientHeight
        };

        // Преобразуем точки для сервера
        const transformedPoints = selectPoints.map(point => ({
            x: point.x,
            y: point.y
        }));

        console.log('✂️ Отправка выделения:', {
            points: transformedPoints,
            count: transformedPoints.length
        });

        const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/process-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                operations: [
                    {
                        type: 'selection',
                        data: {
                            points: transformedPoints
                        }
                    }
                ],
                container_size: containerSize,
                image_transform: imageTransform
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                const imageElement = document.getElementById('backgroundRemoverImage');
                imageElement.src = result.image;
                currentImageData = result.image;
                selectPoints = [];
                updateSelectionCanvas();
                saveToHistory();
                showPhotoNotification('✅ Выделенная область вырезана', 'success');
                return true;
            } else {
                showPhotoNotification(`❌ Ошибка сервера: ${result.error}`, 'error');
            }
        } else {
            showPhotoNotification('❌ Ошибка сети при вырезке', 'error');
        }
    } catch (error) {
        console.error('Ошибка вырезки по выделению:', error);
        showPhotoNotification('❌ Ошибка вырезки', 'error');
    }

    return false;
}

// === ИСПРАВЛЕННЫЕ ФУНКЦИИ ОБРЕЗКИ ===
function handleCropDrag(x, y) {
    if (!isDraggingCrop) return;

    const dx = x - dragStart.x;
    const dy = y - dragStart.y;

    cropRect.x = dragStart.cropX + dx;
    cropRect.y = dragStart.cropY + dy;

    const container = document.getElementById('backgroundRemoverContainer');
    cropRect.x = Math.max(0, Math.min(cropRect.x, container.clientWidth - cropRect.width));
    cropRect.y = Math.max(0, Math.min(cropRect.y, container.clientHeight - cropRect.height));

    updateCropRect();
}

function handleCropResize(x, y) {
    if (!isResizingCrop) return;

    const dx = x - dragStart.x;
    const dy = y - dragStart.y;

    const newCrop = {
        x: dragStart.cropX,
        y: dragStart.cropY,
        width: dragStart.cropWidth,
        height: dragStart.cropHeight
    };

    switch (resizeEdge) {
        case 'top':
            newCrop.height = Math.max(10, dragStart.cropHeight - dy);
            newCrop.y = dragStart.cropY + dy;
            break;
        case 'bottom':
            newCrop.height = Math.max(10, dragStart.cropHeight + dy);
            break;
        case 'left':
            newCrop.width = Math.max(10, dragStart.cropWidth - dx);
            newCrop.x = dragStart.cropX + dx;
            break;
        case 'right':
            newCrop.width = Math.max(10, dragStart.cropWidth + dx);
            break;
        case 'top-left':
            newCrop.width = Math.max(10, dragStart.cropWidth - dx);
            newCrop.height = Math.max(10, dragStart.cropHeight - dy);
            newCrop.x = dragStart.cropX + dx;
            newCrop.y = dragStart.cropY + dy;
            break;
        case 'top-right':
            newCrop.width = Math.max(10, dragStart.cropWidth + dx);
            newCrop.height = Math.max(10, dragStart.cropHeight - dy);
            newCrop.y = dragStart.cropY + dy;
            break;
        case 'bottom-left':
            newCrop.width = Math.max(10, dragStart.cropWidth - dx);
            newCrop.height = Math.max(10, dragStart.cropHeight + dy);
            newCrop.x = dragStart.cropX + dx;
            break;
        case 'bottom-right':
            newCrop.width = Math.max(10, dragStart.cropWidth + dx);
            newCrop.height = Math.max(10, dragStart.cropHeight + dy);
            break;
    }

    const container = document.getElementById('backgroundRemoverContainer');
    newCrop.x = Math.max(0, Math.min(newCrop.x, container.clientWidth - newCrop.width));
    newCrop.y = Math.max(0, Math.min(newCrop.y, container.clientHeight - newCrop.height));
    newCrop.width = Math.min(newCrop.width, container.clientWidth - newCrop.x);
    newCrop.height = Math.min(newCrop.height, container.clientHeight - newCrop.y);

    cropRect = newCrop;
    updateCropRect();
}

async function applyCrop() {
    try {
        const container = document.getElementById('backgroundRemoverContainer');
        const imageTransform = {
            x: imagePosition.x,
            y: imagePosition.y,
            scale: zoomLevel
        };

        const containerSize = {
            width: container.clientWidth,
            height: container.clientHeight
        };

        console.log('🔲 Отправка обрезки:', {
            width: cropRect.width,
            height: cropRect.height,
            position: { x: cropRect.x, y: cropRect.y }
        });

        const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/process-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                operations: [
                    {
                        type: 'crop',
                        data: {
                            rect: cropRect
                        }
                    }
                ],
                container_size: containerSize,
                image_transform: imageTransform
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                const imageElement = document.getElementById('backgroundRemoverImage');
                imageElement.src = result.image;
                currentImageData = result.image;

                // Сбрасываем zoom и позицию после обрезки
                zoomLevel = 1;
                imagePosition = { x: 0, y: 0 };
                updateImageTransform();
                updateZoomInfo();

                // Обновляем область обрезки
                setTimeout(() => {
                    const container = document.getElementById('backgroundRemoverContainer');
                    cropRect.width = Math.min(container.clientWidth * 0.6, 300);
                    cropRect.height = Math.min(container.clientHeight * 0.6, 200);
                    cropRect.x = (container.clientWidth - cropRect.width) / 2;
                    cropRect.y = (container.clientHeight - cropRect.height) / 2;
                    updateCropRect();
                    updateCropSizeInfo();
                }, 100);

                saveToHistory();
                showPhotoNotification(`✅ Изображение обрезано до ${Math.round(cropRect.width)}x${Math.round(cropRect.height)}`, 'success');
            } else {
                showPhotoNotification(`❌ Ошибка обрезки: ${result.error}`, 'error');
            }
        } else {
            showPhotoNotification('❌ Ошибка сервера при обрезке', 'error');
        }
    } catch (error) {
        console.error('Ошибка обрезки:', error);
        showPhotoNotification('❌ Ошибка обрезки', 'error');
    }
}

// ИСПРАВЛЕННАЯ ФУНКЦИЯ - обработка перемещения области обрезки
function handleCropRectMouseDown(e) {
    if (currentTool === 'crop') {
        isDraggingCrop = true;
        const container = document.getElementById('backgroundRemoverContainer');
        const rect = container.getBoundingClientRect();

        dragStart = {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            cropX: cropRect.x,
            cropY: cropRect.y
        };

        e.preventDefault();
        e.stopPropagation();
    }
}

function handleCropHandleMouseDown(e) {
    if (currentTool !== 'crop') return;

    e.stopPropagation();
    e.preventDefault();

    const handle = e.target;
    const edge = Array.from(handle.classList).find(cls => cls !== 'crop-handle');

    isResizingCrop = true;
    resizeEdge = edge;

    const container = document.getElementById('backgroundRemoverContainer');
    const rect = container.getBoundingClientRect();

    dragStart = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        cropX: cropRect.x,
        cropY: cropRect.y,
        cropWidth: cropRect.width,
        cropHeight: cropRect.height
    };
}

// === Функции перемещения ===
function startPanning(x, y) {
    isPanning = true;
    panStart = { x, y };

    const container = document.getElementById('backgroundRemoverContainer');
    if (container) {
        container.style.cursor = 'grabbing';
    }
}

function continuePanning(x, y) {
    if (!isPanning) return;

    const dx = x - panStart.x;
    const dy = y - panStart.y;

    imagePosition.x += dx;
    imagePosition.y += dy;
    panStart = { x, y };

    updateImageTransform();
}

function endPanning() {
    isPanning = false;
    const container = document.getElementById('backgroundRemoverContainer');
    if (container && currentTool === 'hand') {
        container.style.cursor = 'grab';
    }
}

// === Вспомогательные функции ===
function updateImageTransform() {
    const imageElement = document.getElementById('backgroundRemoverImage');
    if (imageElement) {
        imageElement.style.transform = `translate(${imagePosition.x}px, ${imagePosition.y}px) scale(${zoomLevel})`;
    }
}

function updateZoomInfo() {
    const zoomInfo = document.getElementById('zoomInfo');
    if (zoomInfo) {
        zoomInfo.textContent = `${Math.round(zoomLevel * 100)}%`;
    }
}

function updateCropRect() {
    const cropRectElement = document.getElementById('cropRect');
    if (!cropRectElement) return;

    cropRectElement.style.left = `${cropRect.x}px`;
    cropRectElement.style.top = `${cropRect.y}px`;
    cropRectElement.style.width = `${cropRect.width}px`;
    cropRectElement.style.height = `${cropRect.height}px`;
}

function updateCropSizeInfo() {
    const infoElement = document.getElementById('cropSizeInfo');
    if (infoElement) {
        infoElement.textContent = `${Math.round(cropRect.width)} x ${Math.round(cropRect.height)}`;
    }
}

function updateSelectionCanvas() {
    const canvas = document.getElementById('selectionCanvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (selectPoints.length > 1) {
        ctx.beginPath();
        ctx.moveTo(selectPoints[0].x, selectPoints[0].y);

        for (let i = 1; i < selectPoints.length; i++) {
            ctx.lineTo(selectPoints[i].x, selectPoints[i].y);
        }

        if (!isSelecting && selectPoints.length > 2) {
            ctx.closePath();
        }

        ctx.strokeStyle = '#1a5fb4';
        ctx.lineWidth = 2;
        ctx.stroke();

        if (!isSelecting && selectPoints.length > 2) {
            ctx.fillStyle = 'rgba(26, 95, 180, 0.3)';
            ctx.fill();
        }

        if (!isSelecting && selectPoints.length > 2) {
            ctx.setLineDash([5, 5]);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }
}

function updateEraserCanvas() {
    const canvas = document.getElementById('eraserCanvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (currentEraserOperation) {
        for (const point of currentEraserOperation.points) {
            ctx.beginPath();
            ctx.arc(point.x, point.y, point.size / 2, 0, 2 * Math.PI);
            ctx.fillStyle = 'rgba(255, 0, 0, 0.3)';
            ctx.fill();
            ctx.strokeStyle = '#ff0000';
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }
}

function saveCurrentImageState() {
    const imageElement = document.getElementById('backgroundRemoverImage');
    if (imageElement) {
        currentImageData = imageElement.src;
    }
    return Promise.resolve();
}

// === Функции отмены и сброса ===
async function revertToOriginal() {
    if (!originalImageState) {
        showPhotoNotification('❌ Оригинальное изображение не найдено', 'error');
        return;
    }

    if (!confirm('Вернуть оригинальное изображение? Все изменения будут потеряны.')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/original-image?t=${Date.now()}`);
        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                const imageElement = document.getElementById('backgroundRemoverImage');
                imageElement.src = result.image;
                currentImageData = result.image;
                eraserOperations = [];
                selectPoints = [];
                editHistory = [];
                currentHistoryIndex = -1;

                setTimeout(() => {
                    initializeBackgroundRemover();
                }, 100);

                showPhotoNotification('✅ Возвращено оригинальное изображение', 'success');
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки оригинала:', error);
        // Fallback на локальное состояние
        const imageElement = document.getElementById('backgroundRemoverImage');
        imageElement.src = originalImageState;
        currentImageData = originalImageState;
        eraserOperations = [];
        selectPoints = [];
        editHistory = [];
        currentHistoryIndex = -1;

        setTimeout(() => {
            initializeBackgroundRemover();
        }, 100);

        showPhotoNotification('✅ Возвращено оригинальное изображение', 'success');
    }
}

function resetAllChanges() {
    if (confirm('Вы уверены? Все несохраненные изменения будут потеряны.')) {
        const imageElement = document.getElementById('backgroundRemoverImage');
        if (imageElement && editHistory.length > 0) {
            const initialState = editHistory[0];
            imageElement.src = initialState.imageSrc;
            currentImageData = initialState.imageSrc;
            eraserOperations = JSON.parse(JSON.stringify(initialState.eraserOperations));
            selectPoints = JSON.parse(JSON.stringify(initialState.selectPoints || []));
            editHistory = [initialState];
            currentHistoryIndex = 0;

            updateOperationsCount();
            updateUndoRedoButtons();
            updateSelectionCanvas();
            updateEraserCanvas();
        }

        showPhotoNotification('🔄 Все изменения сброшены', 'info');
    }
}

async function applyAllChanges() {
    if (eraserOperations.length === 0 && selectPoints.length < 3) {
        showPhotoNotification('ℹ️ Нет изменений для применения', 'info');
        return;
    }

    try {
        const container = document.getElementById('backgroundRemoverContainer');
        const imageTransform = {
            x: imagePosition.x,
            y: imagePosition.y,
            scale: zoomLevel
        };

        const containerSize = {
            width: container.clientWidth,
            height: container.clientHeight
        };

        const operations = [];

        if (eraserOperations.length > 0) {
            operations.push({
                type: 'erase',
                data: {
                    operations: eraserOperations
                }
            });
        }

        if (selectPoints.length > 2) {
            operations.push({
                type: 'selection',
                data: {
                    points: selectPoints
                }
            });
        }

        const response = await fetch(`${API_BASE}/tracks/${currentPhotoEditorTrackId}/process-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                operations: operations,
                container_size: containerSize,
                image_transform: imageTransform
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                showPhotoNotification(`✅ Все изменения применены (${operations.length} операций)`, 'success');
                closeBackgroundRemover();
            }
        }
    } catch (error) {
        console.error('Ошибка применения изменений:', error);
        showPhotoNotification('❌ Ошибка применения изменений', 'error');
    }
}

function cancelEditing() {
    if (editHistory.length > 1 && !confirm('У вас есть несохраненные изменения. Выйти без сохранения?')) {
        return;
    }
    closeBackgroundRemover();
}

function closeBackgroundRemover() {
    const removerModal = document.getElementById('backgroundRemoverModal');
    if (removerModal) {
        removerModal.style.display = 'none';
    }

    const mainModal = document.getElementById('photoEditorModal');
    if (mainModal) {
        mainModal.style.display = 'flex';
    }
}

// Обработчики для элементов управления
function handleEraserSizeChange(e) {
    eraserSize = parseInt(e.target.value);
    const eraserSizeValue = document.getElementById('eraserSizeValue');
    if (eraserSizeValue) {
        eraserSizeValue.textContent = eraserSize;
    }
}

function showPhotoNotification(message, type = 'info') {
    console.log('Photo Editor Notification:', message, type);

    if (typeof window.showNotification === 'function' && window.showNotification !== showPhotoNotification) {
        window.showNotification(message, type);
        return;
    }

    try {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            border-radius: 5px;
            color: white;
            font-family: Arial, sans-serif;
            font-size: 14px;
            z-index: 10000;
            max-width: 300px;
            word-wrap: break-word;
            background: ${type === 'error' ? '#c6262e' :
                type === 'success' ? '#26a269' :
                    type === 'warning' ? '#f37329' : '#1a5fb4'};
        `;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    } catch (e) {
        console.log('Notification:', message, type);
    }
}