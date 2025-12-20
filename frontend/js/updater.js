/**
 * GitHub Auto-Updater для фронтенда
 */

class GitHubUpdaterUI {
    constructor() {
        this.currentVersion = 'unknown';
        this.latestVersion = 'unknown';
        this.updateAvailable = false;
        this.updateInProgress = false;

        // Элементы UI
        this.elements = {
            currentVersion: document.getElementById('currentVersion'),
            versionDetails: document.getElementById('versionDetails'),
            updateBadge: document.getElementById('updateBadge'),
            updateStatusText: document.getElementById('updateStatusText'),
            checkUpdateBtn: document.getElementById('checkUpdateBtn'),
            installUpdateBtn: document.getElementById('installUpdateBtn'),
            updateInfo: document.getElementById('updateInfo'),
            updateProgress: document.getElementById('updateProgress'),
            updateProgressText: document.getElementById('updateProgressText'),
            updateProgressPercent: document.getElementById('updateProgressPercent'),
            updateProgressFill: document.getElementById('updateProgressFill'),
            updateDetails: document.getElementById('updateDetails'),
            repoInfo: document.getElementById('repoInfo'),
            branchInfo: document.getElementById('branchInfo')
        };

        this.initialize();
    }

    async initialize() {
        try {
            await this.loadVersionInfo();
            await this.loadRepoInfo();

            // Автопроверка через 3 секунды
            setTimeout(() => this.checkForUpdates(false), 3000);

        } catch (error) {
            console.error('Ошибка инициализации:', error);
            this.showError('Ошибка инициализации автообновителя');
        }
    }

    async loadVersionInfo() {
        try {
            const response = await fetch('/api/updater/version');
            const data = await response.json();

            this.currentVersion = data.current_version;
            this.latestVersion = data.latest_version || this.currentVersion;
            this.updateAvailable = data.update_available || false;

            this.updateVersionDisplay(data);

            return data;

        } catch (error) {
            console.error('Ошибка загрузки версии:', error);
            this.elements.currentVersion.textContent = 'Ошибка загрузки';
            this.showError('Не удалось загрузить информацию о версии');
            return null;
        }
    }

    async loadRepoInfo() {
        try {
            const response = await fetch('/api/updater/version');
            const data = await response.json();

            if (data.repo) {
                this.elements.repoInfo.textContent = data.repo;
                this.elements.branchInfo.textContent = 'master';
            }

            return data;

        } catch (error) {
            console.error('Ошибка загрузки репозитория:', error);
            return null;
        }
    }

    updateVersionDisplay(data) {
        // Отображаем текущую версию
        this.elements.currentVersion.textContent = this.currentVersion;

        // Обновляем бейдж
        if (data.update_available) {
            this.elements.updateBadge.style.display = 'block';
            this.elements.updateStatusText.textContent = 'Доступно обновление';
            this.elements.updateStatusText.className = 'badge badge-warning';

            // Информация об обновлении
            let details = `Доступна новая версия: <strong>${this.latestVersion}</strong><br>`;
            if (data.commit_info && data.commit_info.message) {
                details += `Коммит: ${data.commit_info.message}<br>`;
            }
            if (data.commit_info && data.commit_info.date) {
                const date = new Date(data.commit_info.date);
                details += `Дата: ${date.toLocaleDateString()}`;
            }

            this.elements.versionDetails.innerHTML = details;

            // Показываем кнопку установки
            this.elements.installUpdateBtn.style.display = 'inline-block';
            this.elements.updateInfo.innerHTML = `<span style="color: #ff922b;">Доступно обновление ${this.latestVersion}</span>`;

        } else {
            this.elements.updateBadge.style.display = 'block';
            this.elements.updateStatusText.textContent = 'Актуальна';
            this.elements.updateStatusText.className = 'badge badge-success';

            let details = 'У вас установлена последняя версия<br>';
            if (data.commit_info && data.commit_info.date) {
                const date = new Date(data.commit_info.date);
                details += `Последнее обновление: ${date.toLocaleDateString()}`;
            }

            this.elements.versionDetails.innerHTML = details;
            this.elements.installUpdateBtn.style.display = 'none';
            this.elements.updateInfo.innerHTML = '';
        }
    }

    async checkForUpdates(showNotification = true) {
        try {
            if (this.updateInProgress) {
                this.showWarning('Обновление уже выполняется');
                return;
            }

            if (showNotification) {
                this.showInfo('Проверка обновлений...');
            }

            this.elements.checkUpdateBtn.disabled = true;
            this.elements.checkUpdateBtn.innerHTML = '<span class="icon">⏳</span> Проверка...';

            const response = await fetch('/api/updater/check', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            this.updateAvailable = result.update_available || false;

            if (result.success) {
                if (result.update_available) {
                    this.latestVersion = result.latest_version;
                    this.updateVersionDisplay(result);

                    if (showNotification) {
                        this.showSuccess(`Доступно обновление ${result.latest_version}`);
                    }
                } else {
                    if (showNotification) {
                        this.showSuccess('У вас установлена последняя версия');
                    }
                }
            } else {
                this.showError(result.error || 'Ошибка проверки обновлений');
            }

        } catch (error) {
            console.error('Ошибка проверки обновлений:', error);
            this.showError('Ошибка соединения с сервером');
        } finally {
            this.elements.checkUpdateBtn.disabled = false;
            this.elements.checkUpdateBtn.innerHTML = '<span class="icon">🔄</span> Проверить обновления';
        }
    }

    async installUpdate() {
        try {
            if (this.updateInProgress) {
                this.showWarning('Обновление уже выполняется');
                return;
            }

            if (!this.updateAvailable) {
                this.showWarning('Обновлений нет');
                return;
            }

            if (!confirm(`Установить обновление ${this.latestVersion}?\n\nПриложение будет перезапущено после установки.`)) {
                return;
            }

            this.updateInProgress = true;

            this.showProgress('Начало установки обновления...', 0);

            const response = await fetch('/api/updater/install', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (result.success) {
                this.showProgress('Обновление успешно установлено!', 100);

                setTimeout(() => {
                    let message = `🎉 Обновление успешно установлено!\n\n`;
                    message += `Новая версия: ${result.new_version}\n`;
                    message += `Обновлено файлов: ${result.updated_items?.length || 0}\n\n`;
                    message += 'Приложение будет перезапущено через 5 секунд.';

                    alert(message);

                    setTimeout(() => {
                        location.reload();
                    }, 5000);
                }, 1000);

            } else {
                this.showError(result.error || 'Ошибка установки обновления');
                this.updateInProgress = false;
            }

        } catch (error) {
            console.error('Ошибка установки обновления:', error);
            this.showError('Ошибка установки обновления');
            this.updateInProgress = false;
        }
    }

    showProgress(message, percent) {
        this.elements.updateProgress.style.display = 'block';
        this.elements.updateProgressText.textContent = message;
        this.elements.updateProgressPercent.textContent = `${percent}%`;
        this.elements.updateProgressFill.style.width = `${percent}%`;

        if (percent < 100) {
            this.elements.updateDetails.innerHTML = `
                <div>⏳ Выполняется обновление...</div>
                <div style="font-size: 11px; margin-top: 5px;">Не закрывайте вкладку</div>
            `;
        } else {
            this.elements.updateDetails.innerHTML = `
                <div>✅ Обновление завершено!</div>
                <div style="font-size: 11px; margin-top: 5px;">Приложение скоро перезагрузится</div>
            `;
        }
    }

    showInfo(message) {
        this.showNotification(message, '#339af0');
    }

    showSuccess(message) {
        this.showNotification(message, '#51cf66');
    }

    showWarning(message) {
        this.showNotification(message, '#ff922b');
    }

    showError(message) {
        this.showNotification(message, '#ff6b6b');
    }

    showNotification(message, color) {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${color};
            color: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 9999;
            max-width: 400px;
            animation: slideIn 0.3s ease;
        `;

        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    const localTab = document.getElementById('local');
    if (localTab && localTab.classList.contains('active')) {
        window.updaterUI = new GitHubUpdaterUI();
    }

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (tab === 'local') {
                setTimeout(() => {
                    if (!window.updaterUI) {
                        window.updaterUI = new GitHubUpdaterUI();
                    }
                }, 100);
            }
        });
    });
});

// Глобальные функции
async function checkForUpdates() {
    if (window.updaterUI) {
        await window.updaterUI.checkForUpdates(true);
    } else {
        window.updaterUI = new GitHubUpdaterUI();
        setTimeout(() => checkForUpdates(), 500);
    }
}

async function installUpdate() {
    if (window.updaterUI) {
        await window.updaterUI.installUpdate();
    } else {
        window.updaterUI = new GitHubUpdaterUI();
        setTimeout(() => installUpdate(), 500);
    }
}

// Стили
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
    }
    
    .badge-success {
        background: #51cf66;
        color: white;
    }
    
    .badge-warning {
        background: #ff922b;
        color: white;
    }
    
    .progress-bar {
        height: 8px;
        background: #1e1e1e;
        border-radius: 4px;
        overflow: hidden;
        margin-top: 8px;
    }
    
    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #339af0, #51cf66);
        width: 0%;
        transition: width 0.3s ease;
    }
    
    .progress-info {
        display: flex;
        justify-content: space-between;
        margin-bottom: 5px;
        font-size: 14px;
    }
    
    .progress-details {
        font-size: 12px;
        color: #666;
        margin-top: 5px;
    }
`;
document.head.appendChild(style);