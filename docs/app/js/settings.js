/**
 * settings.js — Settings screen.
 *
 * Shows: user info, app version, default currency toggle,
 * clear local cache button, and links.
 */

/* global tg, IS_TELEGRAM, hapticLight, hapticSuccess, escHtml */

const SETTINGS_KEY = 'xisobchi_settings';

/** Load saved settings from localStorage */
function getSettings() {
    try {
        return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    } catch { return {}; }
}

/** Save settings to localStorage */
function saveSettings(obj) {
    try {
        const current = getSettings();
        localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...current, ...obj }));
    } catch { /* quota exceeded – silently ignore */ }
}

function renderSettings(container) {
    const settings = getSettings();
    const defaultCurrency = settings.defaultCurrency || 'UZS';

    // User info from Telegram
    const user = tg?.initDataUnsafe?.user;
    const firstName = user?.first_name || 'Foydalanuvchi';
    const username = user?.username ? `@${user.username}` : '';
    const userId = user?.id || '—';

    container.innerHTML = `
    <div class="screen" id="settings-screen">
      <div class="section-header" style="margin-bottom:14px">
        <div class="section-title" style="font-size:.92rem">⚙️ Sozlamalar</div>
      </div>

      <!-- User info card -->
      <div class="settings-card">
        <div class="settings-card-header">
          <div class="settings-avatar">${escHtml(firstName.charAt(0).toUpperCase())}</div>
          <div class="settings-user-info">
            <div class="settings-user-name">${escHtml(firstName)}</div>
            ${username ? `<div class="settings-user-handle">${escHtml(username)}</div>` : ''}
          </div>
        </div>
        <div class="settings-row dim">
          <span>Telegram ID</span>
          <span>${userId}</span>
        </div>
      </div>

      <!-- Default currency -->
      <div class="settings-card">
        <div class="settings-row">
          <span>💱 Standart valyuta</span>
          <div class="currency-switch" id="currency-switch">
            <button class="cs-btn ${defaultCurrency === 'UZS' ? 'active' : ''}" data-cur="UZS">🇺🇿 UZS</button>
            <button class="cs-btn ${defaultCurrency === 'USD' ? 'active' : ''}" data-cur="USD">🇺🇸 USD</button>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="settings-card">
        <button class="settings-action" id="btn-clear-cache">
          <span>🗑 Keshni tozalash</span>
          <span class="settings-action-hint">Saqlangan ma'lumotlarni o'chirish</span>
        </button>
      </div>

      <!-- App info -->
      <div class="settings-footer">
        <div class="settings-footer-icon">📊</div>
        <div class="settings-footer-name">Xisobchi Mini App</div>
        <div class="settings-footer-ver">v1.0.0 • Faza 3</div>
        <div class="settings-footer-link">
          <a href="https://t.me/XisobchiBot" target="_blank">@XisobchiBot</a>
        </div>
      </div>
    </div>`;

    // Currency switch
    container.querySelector('#currency-switch')?.addEventListener('click', e => {
        const btn = e.target.closest('.cs-btn');
        if (!btn) return;
        hapticLight();
        container.querySelectorAll('.cs-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        saveSettings({ defaultCurrency: btn.dataset.cur });
    });

    // Clear cache
    container.querySelector('#btn-clear-cache')?.addEventListener('click', () => {
        hapticLight();
        try {
            // Clear only our app keys, not Telegram's
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                if (k && k.startsWith('xisobchi_')) keysToRemove.push(k);
            }
            keysToRemove.forEach(k => localStorage.removeItem(k));
        } catch { /* ignore */ }

        hapticSuccess();

        // Show confirmation
        const btn = container.querySelector('#btn-clear-cache');
        if (btn) {
            const orig = btn.innerHTML;
            btn.innerHTML = '<span>✅ Tozalandi!</span><span class="settings-action-hint">Cache o\'chirildi</span>';
            btn.disabled = true;
            setTimeout(() => {
                btn.innerHTML = orig;
                btn.disabled = false;
            }, 1500);
        }
    });
}
