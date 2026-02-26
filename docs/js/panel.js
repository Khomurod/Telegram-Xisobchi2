/**
 * panel.js — User detail side panel: profile, transactions, direct message.
 * Depends on: config.js (API, fmtM, emoji)
 * Depends on: admin.js (adminToken) — must be loaded first.
 */

let _currentTelegramId = null;

// ── Open ──────────────────────────────────────────────────────
async function openUser(telegramId) {
    _currentTelegramId = telegramId;
    document.getElementById('panel-overlay').classList.add('open');
    document.getElementById('user-panel').classList.add('open');
    document.getElementById('dm-status').textContent = '';
    document.getElementById('dm-text').value = '';
    document.getElementById('panel-txns').innerHTML = '<div style="color:var(--muted);font-size:.82rem">Yuklanmoqda…</div>';
    document.getElementById('panel-name').textContent = '—';
    document.getElementById('panel-meta').textContent = '—';

    try {
        const res = await fetch(`${API}/admin/users/${telegramId}/transactions`, {
            headers: { 'X-Admin-Token': adminToken },
        });
        if (!res.ok) throw new Error('Server: ' + res.status);
        const { user: u, transactions: txns = [] } = await res.json();

        // Header
        document.getElementById('panel-avatar').textContent = u.first_name ? u.first_name[0].toUpperCase() : '👤';
        document.getElementById('panel-name').textContent = u.first_name || '(ism yo\'q)';
        document.getElementById('panel-meta').textContent =
            (u.username ? '@' + u.username + '  ·  ' : '') +
            'ID: ' + u.telegram_id +
            (u.phone_number && u.phone_number !== 'skipped' ? '  ·  ' + u.phone_number : '');

        // Stats chips
        const income = txns.filter(t => t.type === 'income' && t.currency === 'UZS').reduce((s, t) => s + t.amount, 0);
        const expense = txns.filter(t => t.type === 'expense' && t.currency === 'UZS').reduce((s, t) => s + t.amount, 0);
        document.getElementById('p-txn-count').textContent = txns.length + ' ta';
        document.getElementById('p-joined').textContent = u.created_at ? new Date(u.created_at).toLocaleDateString('uz') : '—';
        document.getElementById('p-income').textContent = fmtM(income) + ' UZS';
        document.getElementById('p-expense').textContent = fmtM(expense) + ' UZS';

        // Transaction list
        if (!txns.length) {
            document.getElementById('panel-txns').innerHTML = '<div style="color:var(--muted);font-size:.82rem">Operatsiyalar yo\'q</div>';
        } else {
            document.getElementById('panel-txns').innerHTML = txns.map(t => {
                const isInc = t.type === 'income';
                const date = t.created_at
                    ? new Date(t.created_at).toLocaleString('uz', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
                    : '';
                return `
          <div class="txn-row">
            <span class="badge ${isInc ? 'badge-income' : 'badge-expense'}">${isInc ? 'Kirim' : 'Chiqim'}</span>
            <span class="txn-cat">${emoji(t.category)} ${t.category}</span>
            <span class="txn-amt" style="color:${isInc ? 'var(--income)' : 'var(--expense)'}">
              ${isInc ? '+' : '-'}${fmtM(t.amount)} ${t.currency}
            </span>
            <span class="txn-date">${date}</span>
          </div>`;
            }).join('');
        }
    } catch (e) {
        document.getElementById('panel-txns').innerHTML =
            `<div style="color:var(--expense);font-size:.82rem">Xatolik: ${e.message}</div>`;
    }
}

// ── Close ─────────────────────────────────────────────────────
function closeUserPanel() {
    document.getElementById('panel-overlay').classList.remove('open');
    document.getElementById('user-panel').classList.remove('open');
    _currentTelegramId = null;
}

// ── Direct message ────────────────────────────────────────────
async function sendDirectMessage() {
    if (!_currentTelegramId) return;
    const text = document.getElementById('dm-text').value.trim();
    const status = document.getElementById('dm-status');
    if (!text) {
        status.style.color = 'var(--expense)';
        status.textContent = 'Xabar bo\'sh!';
        return;
    }
    status.style.color = 'var(--accent)';
    status.textContent = 'Yuborilmoqda…';
    try {
        const res = await fetch(`${API}/admin/users/${_currentTelegramId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken },
            body: JSON.stringify({ text }),
        });
        const d = await res.json();
        if (!res.ok) {
            status.style.color = 'var(--expense)';
            status.textContent = '⚠️ ' + (d.error || res.status);
            return;
        }
        status.style.color = 'var(--income)';
        status.textContent = '✅ Yuborildi';
        document.getElementById('dm-text').value = '';
    } catch (e) {
        status.style.color = 'var(--expense)';
        status.textContent = '⚠️ ' + e.message;
    }
}
