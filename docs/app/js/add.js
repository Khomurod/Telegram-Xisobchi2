/**
 * add.js — Add transaction form screen.
 *
 * Type toggle (income/expense), amount input, currency picker,
 * category grid, optional description.  Uses Telegram MainButton.
 */

/* global apiAddTransaction, fmtAmount, escHtml,
          hapticLight, hapticSuccess, hapticError,
          showMainButton, hideMainButton, setMainButtonLoading,
          CATEGORY_MAP */

// Category data (synced with backend constants.py)
const CATEGORIES = [
    { key: 'oziq-ovqat', emoji: '🍽', name: "Oziq-ovqat" },
    { key: 'transport', emoji: '🚕', name: "Transport" },
    { key: 'uy-joy', emoji: '🏠', name: "Uy-joy" },
    { key: "sog'liq", emoji: '💊', name: "Sog'liq" },
    { key: 'kiyim', emoji: '👔', name: "Kiyim" },
    { key: 'aloqa', emoji: '📱', name: "Aloqa" },
    { key: "ta'lim", emoji: '📚', name: "Ta'lim" },
    { key: "ko'ngil ochar", emoji: '🎬', name: "Ko'ngil ochar" },
    { key: "o'tkazma", emoji: '💸', name: "O'tkazma" },
    { key: 'maosh', emoji: '💰', name: "Maosh" },
    { key: 'boshqa', emoji: '📦', name: "Boshqa" },
];

let _addState = {
    type: 'expense',
    currency: 'UZS',
    category: 'boshqa',
};

function renderAddForm(container) {
    _addState = { type: 'expense', currency: 'UZS', category: 'boshqa' };

    let catGridHtml = '';
    for (const cat of CATEGORIES) {
        const active = cat.key === _addState.category ? ' active' : '';
        catGridHtml += `
      <button class="cat-btn${active}" data-cat="${cat.key}">
        <span class="cat-btn-emoji">${cat.emoji}</span>
        <span class="cat-btn-label">${cat.name}</span>
      </button>`;
    }

    container.innerHTML = `
    <div class="screen" id="add-screen">

      <!-- Type toggle -->
      <div class="form-section">
        <div class="form-label">Turi</div>
        <div class="type-toggle">
          <button class="type-btn active-expense" data-type="expense">📉 Chiqim</button>
          <button class="type-btn" data-type="income">📈 Kirim</button>
        </div>
      </div>

      <!-- Amount + Currency -->
      <div class="form-section">
        <div class="form-label">Summa</div>
        <div class="amount-row">
          <div class="amount-input-wrap">
            <input type="number" class="amount-input" id="add-amount"
                   placeholder="0" inputmode="decimal" min="0" step="any" />
          </div>
          <div class="currency-toggle">
            <button class="currency-btn active" data-cur="UZS">UZS</button>
            <button class="currency-btn" data-cur="USD">USD</button>
          </div>
        </div>
      </div>

      <!-- Category -->
      <div class="form-section">
        <div class="form-label">Kategoriya</div>
        <div class="category-grid">${catGridHtml}</div>
      </div>

      <!-- Description -->
      <div class="form-section">
        <div class="form-label">Izoh (ixtiyoriy)</div>
        <input type="text" class="desc-input" id="add-desc" placeholder="Masalan: Oilaviy tushlik" maxlength="500" />
      </div>

      <!-- Fallback submit button (for non-Telegram browsers) -->
      <div id="fallback-submit" style="display:none;margin-top:12px">
        <button class="filter-chip active" style="width:100%;padding:14px;font-size:.92rem"
                id="add-submit-btn">✅ Saqlash</button>
      </div>

    </div>`;

    const screen = container.querySelector('#add-screen');

    // Type toggle
    screen.querySelector('.type-toggle').addEventListener('click', e => {
        const btn = e.target.closest('.type-btn');
        if (!btn) return;
        hapticLight();
        _addState.type = btn.dataset.type;
        screen.querySelectorAll('.type-btn').forEach(b => {
            b.classList.remove('active-income', 'active-expense');
        });
        btn.classList.add(btn.dataset.type === 'income' ? 'active-income' : 'active-expense');
    });

    // Currency toggle
    screen.querySelector('.currency-toggle').addEventListener('click', e => {
        const btn = e.target.closest('.currency-btn');
        if (!btn) return;
        hapticLight();
        _addState.currency = btn.dataset.cur;
        screen.querySelectorAll('.currency-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });

    // Category grid
    screen.querySelector('.category-grid').addEventListener('click', e => {
        const btn = e.target.closest('.cat-btn');
        if (!btn) return;
        hapticLight();
        _addState.category = btn.dataset.cat;
        screen.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });

    // Telegram MainButton for submit
    if (typeof showMainButton === 'function') {
        showMainButton('✅ Saqlash', () => handleAddSubmit(container));
    }

    // Fallback button for browser testing
    if (!window.Telegram?.WebApp?.MainButton) {
        const fallback = screen.querySelector('#fallback-submit');
        if (fallback) fallback.style.display = 'block';
        screen.querySelector('#add-submit-btn')?.addEventListener('click', () => handleAddSubmit(container));
    }

    // Auto-focus amount
    setTimeout(() => screen.querySelector('#add-amount')?.focus(), 300);
}

async function handleAddSubmit(container) {
    const amountInput = document.querySelector('#add-amount');
    const descInput = document.querySelector('#add-desc');
    const amount = parseFloat(amountInput?.value);
    const description = (descInput?.value || '').trim();

    if (!amount || amount <= 0) {
        hapticError();
        amountInput?.focus();
        amountInput?.classList.add('shake');
        setTimeout(() => amountInput?.classList.remove('shake'), 400);
        return;
    }

    setMainButtonLoading(true);

    try {
        const result = await apiAddTransaction({
            type: _addState.type,
            amount: amount,
            currency: _addState.currency,
            category: _addState.category,
            description: description || undefined,
        });

        hapticSuccess();
        hideMainButton();

        // Show success animation
        const cat = CATEGORIES.find(c => c.key === _addState.category) || CATEGORIES[CATEGORIES.length - 1];
        showSuccessOverlay(
            _addState.type === 'income' ? '📈' : '📉',
            _addState.type === 'income' ? 'Kirim saqlandi!' : 'Chiqim saqlandi!',
            `${fmtAmount(amount, _addState.currency)} • ${cat.emoji} ${cat.name}`
        );

        // Navigate to dashboard after delay
        setTimeout(() => {
            document.querySelector('.success-overlay')?.remove();
            location.hash = '#/';
        }, 1500);

    } catch (err) {
        hapticError();
        setMainButtonLoading(false);
        alert('Xatolik: ' + err.message);
    }
}

function showSuccessOverlay(icon, text, subtext) {
    document.querySelector('.success-overlay')?.remove();

    const overlay = document.createElement('div');
    overlay.className = 'success-overlay';
    overlay.innerHTML = `
    <div class="success-card">
      <div class="success-icon">${icon}</div>
      <div class="success-text">${escHtml(text)}</div>
      <div class="success-amount">${escHtml(subtext)}</div>
    </div>`;
    document.body.appendChild(overlay);
}

function cleanupAddForm() {
    hideMainButton();
}
