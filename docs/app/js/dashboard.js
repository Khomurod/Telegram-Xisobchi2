/**
 * dashboard.js — Dashboard screen.
 *
 * Shows: greeting, balance cards (UZS + USD),
 * today's transactions, monthly category breakdown.
 */

/* global apiGetDashboard, fmtAmount, fmtNum, hapticLight */

function renderDashboard(container) {
    container.innerHTML = `
    <div class="screen" id="dashboard-screen">
      <div class="loading-screen"><div class="loading-spinner"></div><p>Yuklanmoqda…</p></div>
    </div>`;

    loadDashboardData(container);
}

async function loadDashboardData(container) {
    try {
        const data = await apiGetDashboard();
        const screen = container.querySelector('#dashboard-screen') || container;

        const firstName = data.user?.first_name || 'Foydalanuvchi';
        const uzs = data.balance?.uzs || { income: 0, expense: 0, balance: 0 };
        const usd = data.balance?.usd || { income: 0, expense: 0, balance: 0 };
        const recent = data.recent || [];
        const categories = data.categories || [];

        const hasUzs = uzs.income > 0 || uzs.expense > 0;
        const hasUsd = usd.income > 0 || usd.expense > 0;

        let html = `<div class="screen">`;

        // Greeting
        html += `
      <div class="greeting">
        <div class="greeting-hello">Assalomu alaykum 👋</div>
        <div class="greeting-name">${escHtml(firstName)}</div>
      </div>`;

        // Balance cards
        html += `<div class="balance-cards">`;

        html += `
      <div class="balance-card uzs">
        <div class="balance-card-flag">🇺🇿</div>
        <div class="balance-card-label">Balans (so'm)</div>
        <div class="balance-card-amount ${uzs.balance >= 0 ? 'positive' : 'negative'}">
          ${fmtAmount(uzs.balance, 'UZS')}
        </div>
        <div class="balance-card-row">
          <span class="income">↑ ${fmtNum(uzs.income)}</span>
          <span class="expense">↓ ${fmtNum(uzs.expense)}</span>
        </div>
      </div>`;

        if (hasUsd) {
            html += `
        <div class="balance-card usd">
          <div class="balance-card-flag">🇺🇸</div>
          <div class="balance-card-label">Balans (USD)</div>
          <div class="balance-card-amount ${usd.balance >= 0 ? 'positive' : 'negative'}">
            ${fmtAmount(usd.balance, 'USD')}
          </div>
          <div class="balance-card-row">
            <span class="income">↑ $${fmtNum(usd.income)}</span>
            <span class="expense">↓ $${fmtNum(usd.expense)}</span>
          </div>
        </div>`;
        }

        html += `</div>`;

        // Today's transactions
        html += `
      <div class="section">
        <div class="section-header">
          <div class="section-title">📊 Bugungi operatsiyalar</div>
          <a class="section-link" onclick="location.hash='#/transactions'">Barchasi →</a>
        </div>`;

        if (recent.length === 0) {
            html += `
        <div class="empty-state">
          <div class="empty-state-icon">📭</div>
          <div>Bugun hali operatsiya yo'q</div>
        </div>`;
        } else {
            html += `<div class="txn-list">`;
            for (const txn of recent) {
                html += renderTxnRow(txn);
            }
            html += `</div>`;
        }

        html += `</div>`;

        // Monthly categories (expenses only)
        const expenseCats = categories.filter(c => c.type === 'expense' && c.currency === 'UZS');
        if (expenseCats.length > 0) {
            const maxTotal = Math.max(...expenseCats.map(c => c.total));

            html += `
        <div class="section">
          <div class="section-header">
            <div class="section-title">📅 Oylik chiqimlar</div>
          </div>
          <div class="cat-list">`;

            for (const cat of expenseCats) {
                const pct = maxTotal > 0 ? (cat.total / maxTotal * 100) : 0;
                html += `
          <div class="cat-row">
            <div class="cat-header">
              <span class="cat-name">${cat.category_emoji} ${escHtml(cat.category_name)}</span>
              <span class="cat-amount">${fmtAmount(cat.total, cat.currency)}</span>
            </div>
            <div class="cat-track">
              <div class="cat-fill expense-fill" style="width:${pct}%"></div>
            </div>
          </div>`;
            }

            html += `</div></div>`;
        }

        html += `</div>`;
        screen.outerHTML = html;

        // Animate category bars after DOM paint
        requestAnimationFrame(() => {
            document.querySelectorAll('.cat-fill').forEach(bar => {
                const w = bar.style.width;
                bar.style.width = '0%';
                requestAnimationFrame(() => { bar.style.width = w; });
            });
        });

    } catch (err) {
        const screen = container.querySelector('#dashboard-screen') || container;
        screen.innerHTML = `
      <div class="screen">
        <div class="empty-state">
          <div class="empty-state-icon">⚠️</div>
          <div>Ma'lumotlar yuklanmadi</div>
          <div style="font-size:.75rem;margin-top:6px;color:var(--tg-hint)">${escHtml(err.message)}</div>
        </div>
      </div>`;
    }
}

/** Render a single transaction row */
function renderTxnRow(txn) {
    const sign = txn.type === 'income' ? '+' : '−';
    const cls = txn.type;
    const desc = txn.description || txn.category_name || txn.category;
    const time = txn.created_at_display || txn.created_at || '';

    return `
    <div class="txn-row" data-id="${txn.id}">
      <div class="txn-emoji">${txn.category_emoji || '📦'}</div>
      <div class="txn-info">
        <div class="txn-cat">${escHtml(txn.category_name || txn.category)}</div>
        ${txn.description ? `<div class="txn-desc">${escHtml(txn.description)}</div>` : ''}
      </div>
      <div class="txn-right">
        <div class="txn-amount ${cls}">${sign}${fmtAmount(txn.amount, txn.currency)}</div>
        <div class="txn-time">${time}</div>
      </div>
    </div>`;
}

/** Escape HTML */
function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
}
