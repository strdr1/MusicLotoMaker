/**
 * Простой автообновитель
 */

let currentVersion = 'unknown';
let latestVersion = 'unknown';
let updateAvailable = false;

// Элементы
function getElement(id) {
    return document.getElementById(id);
}

// Загрузить информацию о версии
async function loadVersionInfo() {
    try {
        const response = await fetch('/api/updater/version');
        const data = await response.json();

        currentVersion = data.current_version || 'unknown';
        latestVersion = data.latest_version || currentVersion;
        updateAvailable = data.update_available || false;

        // Обновляем UI
        updateUI(data);

        return data;
    } catch (error) {
        console.error('Ошибка загрузки версии:', error);
        showError('Не удалось загрузить информацию о версии');
        return null;
    }
}

// Обновить UI
function updateUI(data) {
    const currentVersionEl = getElement('currentVersion');
    const versionDetailsEl = getElement('versionDetails');
    const updateBadgeEl = getElement('updateBadge');
    const updateStatusTextEl = getElement('updateStatusText');
    const installUpdateBtn = getElement('installUpdateBtn');

    if (!currentVersionEl) return;

    // Текущая версия
    currentVersionEl.textContent = currentVersion;

    // Бейдж статуса
    if (updateBadgeEl) {
        updateBadgeEl.style.display = 'block';

        if (data.update_available) {
            updateStatusTextEl.textContent = 'Доступно обновление';
            updateStatusTextEl.className = 'badge badge-warning';

            // Информация
            let details = `Доступна новая версия: <strong>${latestVersion}</strong>`;
            if (data.commit_info && data.commit_info.message) {
                details += `<br>${data.commit_info.message}`;
            }

            if (versionDetailsEl) {
                versionDetailsEl.innerHTML = details;
            }

            // Показываем кнопку установки
            if (installUpdateBtn) {
                installUpdateBtn.style.display = 'inline-block';
            }
        } else {
            updateStatusTextEl.textContent = 'Актуальна';
            updateStatusTextEl.className = 'badge badge-success';

            if (versionDetailsEl) {
                versionDetailsEl.innerHTML = 'У вас установлена последняя версия';
            }

            if (installUpdateBtn) {
                installUpdateBtn.style.display = 'none';
            }
        }
    }
}

// Проверить обновления
async function checkForUpdates() {
    try {
        const checkBtn = getElement('checkUpdateBtn');
        if (checkBtn) {
            checkBtn.disabled = true;
            checkBtn.innerHTML = '⏳ Проверка...';
        }

        showNotification('Проверка обновлений...', 'info');

        const response = await fetch('/api/updater/check', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            if (result.update_available) {
                showNotification(`Доступно обновление ${result.latest_version}`, 'success');
                updateUI(result);
            } else {
                showNotification('Установлена последняя версия', 'info');
            }
        } else {
            showNotification(result.error || 'Ошибка проверки', 'error');
        }
    } catch (error) {
        console.error('Ошибка проверки:', error);
        showNotification('Ошибка соединения', 'error');
    } finally {
        const checkBtn = getElement('checkUpdateBtn');
        if (checkBtn) {
            checkBtn.disabled = false;
            checkBtn.innerHTML = '🔄 Проверить обновления';
        }
    }
}

// Установить обновление
async function installUpdate() {
    if (!updateAvailable) {
        showNotification('Обновлений нет', 'warning');
        return;
    }

    if (!confirm(`Установить обновление ${latestVersion}?`)) {
        return;
    }

    try {
        showProgress('Начало установки...', 0);

        const response = await fetch('/api/updater/install', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showProgress('Обновление установлено!', 100);

            setTimeout(() => {
                alert(`✅ Обновление ${result.new_version} установлено!\n\nПриложение будет перезапущено.`);
                setTimeout(() => location.reload(), 2000);
            }, 1000);
        } else {
            showNotification(result.error || 'Ошибка установки', 'error');
        }
    } catch (error) {
        console.error('Ошибка установки:', error);
        showNotification('Ошибка установки', 'error');
    }
}

// Показать прогресс
function showProgress(message, percent) {
    const progressEl = getElement('updateProgress');
    const progressTextEl = getElement('updateProgressText');
    const progressPercentEl = getElement('updateProgressPercent');
    const progressFillEl = getElement('updateProgressFill');

    if (progressEl) progressEl.style.display = 'block';
    if (progressTextEl) progressTextEl.textContent = message;
    if (progressPercentEl) progressPercentEl.textContent = `${percent}%`;
    if (progressFillEl) progressFillEl.style.width = `${percent}%`;
}

// Показать уведомление
function showNotification(message, type = 'info') {
    const colors = {
        info: '#339af0',
        success: '#51cf66',
        warning: '#ff922b',
        error: '#ff6b6b'
    };

    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${colors[type] || colors.info};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;

    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Показать ошибку
function showError(message) {
    showNotification(message, 'error');
}

// Инициализация
document.addEventListener('DOMContentLoaded', function () {
    // Загружаем информацию о версии
    setTimeout(() => {
        loadVersionInfo();

        // Автопроверка через 3 секунды
        setTimeout(checkForUpdates, 3000);
    }, 500);

    // Добавляем стили для анимаций
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            color: white;
        }
        .badge-success { background: #51cf66; }
        .badge-warning { background: #ff922b; }
        .badge-error { background: #ff6b6b; }
    `;
    document.head.appendChild(style);
});