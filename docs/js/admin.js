/**
 * admin.js - Admin panel: login, user list, delete, broadcast draft workflow.
 * Depends on: config.js (API, fmt)
 * Calls into: panel.js (openUser, closeUserPanel)
 */

let adminToken = sessionStorage.getItem('admin_token') || '';
let currentPage = 1;
let broadcastPreviewSnapshot = '';
let broadcastApproved = false;


function currentBroadcastText() {
    return document.getElementById('bc-text').value.trim();
}


function setBroadcastResult(message, tone = 'info') {
    const result = document.getElementById('bc-result');
    const tones = {
        info: 'display:block;background:rgba(88,166,255,.1);color:var(--accent)',
        success: 'display:block;background:rgba(63,185,80,.15);color:var(--income)',
        warning: 'display:block;background:rgba(210,153,34,.18);color:var(--gold)',
        error: 'display:block;background:rgba(248,81,73,.15);color:var(--expense)',
    };
    result.style.cssText = tones[tone] || tones.info;
    result.textContent = message;
}


function setBroadcastPreview(html = '', empty = false) {
    const preview = document.getElementById('bc-preview');
    preview.classList.toggle('empty', empty);
    preview.innerHTML = empty ? 'Preview shu yerda ko\'rinadi.' : html;
}


function updateBroadcastApproval() {
    const approval = document.getElementById('bc-approval');
    const approveBtn = document.getElementById('bc-approve-btn');
    const sendBtn = document.getElementById('bc-send-btn');
    const previewBtn = document.getElementById('bc-preview-btn');
    const text = currentBroadcastText();
    const previewIsFresh = !!broadcastPreviewSnapshot && broadcastPreviewSnapshot === text;

    previewBtn.disabled = !text;
    approveBtn.disabled = !previewIsFresh;
    sendBtn.disabled = !(previewIsFresh && broadcastApproved);

    approval.classList.remove('pending', 'ready', 'approved');
    if (!text) {
        approval.classList.add('pending');
        approval.textContent = 'Matn kiritilmagan';
        return;
    }
    if (broadcastApproved && previewIsFresh) {
        approval.classList.add('approved');
        approval.textContent = 'Tasdiqlangan';
        return;
    }
    if (previewIsFresh) {
        approval.classList.add('ready');
        approval.textContent = 'Preview tayyor';
        return;
    }
    approval.classList.add('pending');
    approval.textContent = broadcastPreviewSnapshot ? 'Matn o\'zgardi, qayta preview qiling' : 'Tasdiqlanmagan';
}


function resetBroadcastComposer() {
    document.getElementById('bc-text').value = '';
    document.getElementById('bc-result').style.display = 'none';
    document.getElementById('bc-result').textContent = '';
    broadcastPreviewSnapshot = '';
    broadcastApproved = false;
    setBroadcastPreview('', true);
    updateBroadcastApproval();
}


function markBroadcastDirty() {
    const text = currentBroadcastText();
    if (!text) {
        broadcastPreviewSnapshot = '';
        broadcastApproved = false;
        setBroadcastPreview('', true);
    } else if (broadcastApproved || broadcastPreviewSnapshot === text) {
        broadcastApproved = false;
    }
    updateBroadcastApproval();
}


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
            err.textContent = 'Noto\'g\'ri token';
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

        err.style.display = 'none';
        sessionStorage.setItem('admin_token', adminToken);
        document.getElementById('admin-gate').style.display = 'none';
        document.getElementById('admin-dash').style.display = 'block';
        resetBroadcastComposer();
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
    resetBroadcastComposer();
}


async function loadUsers(page = 1) {
    currentPage = page;
    const body = document.getElementById('users-body');
    const pages = document.getElementById('users-pages');
    body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted)">Yuklanmoqda...</td></tr>';

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
        <td>${u.first_name || '-'}</td>
        <td style="color:var(--muted);font-size:.85rem">${u.telegram_first_name || '-'}</td>
        <td>${u.username ? '@' + u.username : '-'}</td>
        <td style="font-family:monospace;font-size:.78rem">${u.telegram_id}</td>
        <td style="color:var(--muted)">${u.created_at ? new Date(u.created_at).toLocaleDateString('uz') : '-'}</td>
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


async function deleteUser(telegramId, displayName) {
    if (!confirm(`"${displayName}" foydalanuvchisini o'chirishni tasdiqlaysizmi?\n\nBarcha ma'lumotlari ham o'chiriladi. Bu amalni qaytarib bo'lmaydi.`)) return;

    try {
        const res = await fetch(`${API}/admin/users/${telegramId}`, {
            method: 'DELETE',
            headers: { 'X-Admin-Token': adminToken },
        });
        const d = await res.json();
        if (!res.ok) {
            alert('Xatolik: ' + (d.error || res.status));
            return;
        }

        document.getElementById('row-' + telegramId)?.remove();
        const countEl = document.getElementById('bc-count');
        const match = countEl.textContent.match(/(\d+)/);
        if (match) countEl.textContent = `Jami ${Math.max(parseInt(match[1], 10) - 1, 0)} ta foydalanuvchi`;
        closeUserPanel();
    } catch (e) {
        alert('Xatolik: ' + e.message);
    }
}


async function generateBroadcastDraft() {
    const btn = document.getElementById('bc-generate-btn');
    btn.disabled = true;
    setBroadcastResult('AI draft tayyorlanmoqda...', 'info');

    try {
        const res = await fetch(`${API}/admin/broadcast/generate`, {
            method: 'POST',
            headers: { 'X-Admin-Token': adminToken },
        });
        const d = await res.json();
        if (!res.ok || d.error) {
            setBroadcastResult('⚠️ ' + (d.error || res.status), 'error');
            return;
        }

        document.getElementById('bc-text').value = d.text || '';
        broadcastPreviewSnapshot = '';
        broadcastApproved = false;
        setBroadcastPreview('', true);
        updateBroadcastApproval();
        setBroadcastResult('Draft tayyor. Endi preview qilib, tasdiqlang.', 'success');
    } catch (e) {
        setBroadcastResult('⚠️ ' + e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}


function previewBroadcast() {
    const text = currentBroadcastText();
    if (!text) {
        setBroadcastResult('⚠️ Avval xabar matnini kiriting.', 'warning');
        return;
    }

    broadcastPreviewSnapshot = text;
    broadcastApproved = false;
    setBroadcastPreview(text);
    updateBroadcastApproval();
    setBroadcastResult('Preview yangilandi. Ko\'rib chiqib, tasdiqlang.', 'info');
}


function approveBroadcast() {
    const text = currentBroadcastText();
    if (!text) {
        setBroadcastResult('⚠️ Avval xabar matnini kiriting.', 'warning');
        return;
    }
    if (!broadcastPreviewSnapshot || broadcastPreviewSnapshot !== text) {
        setBroadcastResult('⚠️ Tasdiqlashdan oldin yangi preview qiling.', 'warning');
        return;
    }

    broadcastApproved = true;
    updateBroadcastApproval();
    setBroadcastResult('✅ Xabar tasdiqlandi. Endi yuborish mumkin.', 'success');
}


async function sendBroadcast() {
    const text = currentBroadcastText();
    if (!text) {
        setBroadcastResult('⚠️ Xabar matnini yozing.', 'warning');
        return;
    }
    if (!broadcastPreviewSnapshot || broadcastPreviewSnapshot !== text) {
        setBroadcastResult('⚠️ Yuborishdan oldin preview yangilanishi kerak.', 'warning');
        return;
    }
    if (!broadcastApproved) {
        setBroadcastResult('⚠️ Avval previewni tasdiqlang.', 'warning');
        return;
    }

    const countText = document.getElementById('bc-count').textContent;
    if (!confirm(`${countText} ga ushbu xabar yuborilsinmi?`)) return;

    const sendBtn = document.getElementById('bc-send-btn');
    sendBtn.disabled = true;
    setBroadcastResult('📤 Yuborilmoqda...', 'info');

    try {
        const res = await fetch(`${API}/admin/broadcast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken },
            body: JSON.stringify({ text }),
        });
        const d = await res.json();
        if (!res.ok || d.error) {
            setBroadcastResult('⚠️ ' + (d.error || res.status), 'error');
            return;
        }

        resetBroadcastComposer();
        setBroadcastResult(`✅ Yuborildi: ${d.sent} ta | ❌ Xato: ${d.failed} ta`, 'success');
    } catch (e) {
        setBroadcastResult('⚠️ ' + e.message, 'error');
    } finally {
        updateBroadcastApproval();
    }
}
