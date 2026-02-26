/**
 * admin.js — Admin panel: login, user list, delete, broadcast.
 * Depends on: config.js (API, fmt)
 * Calls into: panel.js (openUser, closeUserPanel) — loaded before this file.
 */

// Persisted admin token (survives tab switches, lost on browser close)
let adminToken = sessionStorage.getItem('admin_token') || '';

// ── Auth ──────────────────────────────────────────────────────
async function adminLogin() {
    const inp = document.getElementById('admin-token');
    const err = document.getElementById('admin-err');
    if (!adminToken) adminToken = inp.value.trim();
    if (!adminToken) {
        err.textContent = 'Token kiritilmagan';
        err.style.display = 'block';
        return;
    }
    try {
        const res = await fetch(API + '/admin/users?limit=1', {
            headers: { 'X-Admin-Token': adminToken },
        });
        if (res.status === 401) {
            err.textContent = "Noto'g'ri token";
            err.style.display = 'block';
            adminToken = '';
            sessionStorage.removeItem('admin_token');
            return;
        }
        if (!res.ok) {
            err.textContent = `Server javob bermadi (${res.status}). Render qayta deploy bo'lyaptimi?`;
            err.style.display = 'block';
            return;
        }
        sessionStorage.setItem('admin_token', adminToken);
        document.getElementById('admin-gate').style.display = 'none';
        document.getElementById('admin-dash').style.display = 'block';
        loadUsers(1);
    } catch (e) {
        err.textContent = 'Server xatoligi: ' + e.message;
        err.style.display = 'block';
    }
}

function adminLogout() {
    adminToken = '';
    sessionStorage.removeItem('admin_token');
    document.getElementById('admin-gate').style.display = 'block';
    document.getElementById('admin-dash').style.display = 'none';
}

// ── User list ─────────────────────────────────────────────────
let currentPage = 1;

async function loadUsers(page = 1) {
    currentPage = page;
    const body = document.getElementById('users-body');
    const pages = document.getElementById('users-pages');
    body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted)">Yuklanmoqda…</td></tr>';

    try {
        const res = await fetch(`${API}/admin/users?page=${page}&limit=15`, {
            headers: { 'X-Admin-Token': adminToken },
        });
        if (!res.ok) throw new Error('Server: ' + res.status);
        const d = await res.json();
        if (!d.users) throw new Error('Kutilmagan javob formati');

        const totalPages = Math.ceil(d.total / d.limit) || 1;

        body.innerHTML = d.users.map((u, i) => `
      <tr id="row-${u.telegram_id}" class="clickable-row" onclick="openUser(${u.telegram_id})">
        <td style="color:var(--muted)">${(page - 1) * d.limit + i + 1}</td>
        <td>${u.first_name || '—'}</td>
        <td style="color:var(--muted);font-size:.85rem">${u.telegram_first_name || '—'}</td>
        <td>${u.username ? '@' + u.username : '—'}</td>
        <td style="font-family:monospace;font-size:.78rem">${u.telegram_id}</td>
        <td style="color:var(--muted)">${u.created_at ? new Date(u.created_at).toLocaleDateString('uz') : '—'}</td>
        <td onclick="event.stopPropagation()" style="white-space:nowrap">
          <button class="btn btn-danger btn-small"
            onclick="deleteUser(${u.telegram_id}, '${(u.first_name || u.telegram_id).replace(/'/g, '')}')"
            title="O'chirish">🗑</button>
        </td>
      </tr>`).join('');

        document.getElementById('bc-count').textContent = `Jami ${d.total} ta foydalanuvchi`;

        let phtml = '';
        if (page > 1) phtml += `<button class="btn btn-primary btn-small" onclick="loadUsers(${page - 1})">← Oldingi</button>`;
        phtml += `<span>${page} / ${totalPages}</span>`;
        if (page < totalPages) phtml += `<button class="btn btn-primary btn-small" onclick="loadUsers(${page + 1})">Keyingi →</button>`;
        pages.innerHTML = phtml;

    } catch (e) {
        body.innerHTML = `<tr><td colspan="7" style="color:var(--expense)">Xatolik: ${e.message}</td></tr>`;
    }
}

// ── Delete user ───────────────────────────────────────────────
async function deleteUser(telegramId, displayName) {
    if (!confirm(`"${displayName}" foydalanuvchisini o'chirishni tasdiqlaysizmi?\n\nBarcha ma'lumotlari (tranzaksiyalar) ham o'chiriladi. Bu amalni qaytarib bo'lmaydi!`)) return;
    try {
        const res = await fetch(`${API}/admin/users/${telegramId}`, {
            method: 'DELETE',
            headers: { 'X-Admin-Token': adminToken },
        });
        const d = await res.json();
        if (!res.ok) { alert('Xatolik: ' + (d.error || res.status)); return; }

        // Remove row without full reload
        document.getElementById('row-' + telegramId)?.remove();
        const countEl = document.getElementById('bc-count');
        if (countEl) {
            const m = countEl.textContent.match(/(\d+)/);
            if (m) countEl.textContent = `Jami ${parseInt(m[1]) - 1} ta foydalanuvchi`;
        }
        closeUserPanel();
    } catch (e) {
        alert('Xatolik: ' + e.message);
    }
}

// ── Broadcast ─────────────────────────────────────────────────
async function sendBroadcast() {
    const text = document.getElementById('bc-text').value.trim();
    const result = document.getElementById('bc-result');
    if (!text) {
        result.style.cssText = 'display:block;background:rgba(248,81,73,.15);color:var(--expense)';
        result.textContent = '⚠️ Xabar matnini yozing!';
        return;
    }
    result.style.cssText = 'display:block;background:rgba(88,166,255,.1);color:var(--accent)';
    result.textContent = '📤 Yuborilmoqda…';
    try {
        const res = await fetch(`${API}/admin/broadcast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken },
            body: JSON.stringify({ text }),
        });
        const d = await res.json();
        if (d.error) {
            result.style.cssText = 'display:block;background:rgba(248,81,73,.15);color:var(--expense)';
            result.textContent = '⚠️ ' + d.error;
            return;
        }
        result.style.cssText = 'display:block;background:rgba(63,185,80,.15);color:var(--income)';
        result.textContent = `✅ Yuborildi: ${d.sent} ta | ❌ Xato: ${d.failed} ta`;
        document.getElementById('bc-text').value = '';
    } catch (e) {
        result.style.cssText = 'display:block;background:rgba(248,81,73,.15);color:var(--expense)';
        result.textContent = '⚠️ ' + e.message;
    }
}
