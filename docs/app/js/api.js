/**
 * api.js — Fetch wrapper for the Mini App API.
 *
 * Sends Authorization: tg <initData> on every request.
 * Falls back to no-auth in browser dev mode.
 */

const API_BASE = 'https://telegram-xisobchi2.onrender.com';

/** Number formatter (Uzbek) */
const fmtNum = n => new Intl.NumberFormat('uz').format(Math.round(n));

/** Format amount with currency symbol */
function fmtAmount(amount, currency) {
    const n = fmtNum(Math.abs(amount));
    if (currency === 'USD') return `$${n}`;
    return `${n} so'm`;
}

/** Core fetch with auth header */
async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };

    // Add Telegram auth if available
    if (INIT_DATA) {
        headers['Authorization'] = `tg ${INIT_DATA}`;
    }

    const resp = await fetch(url, { ...options, headers });

    if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${resp.status}`);
    }

    return resp.json();
}

// ── API methods ─────────────────────────────────────────────

async function apiGetDashboard() {
    return apiFetch('/api/mini/dashboard');
}

async function apiGetTransactions(page = 1, type = null) {
    let url = `/api/mini/transactions?page=${page}`;
    if (type) url += `&type=${type}`;
    return apiFetch(url);
}

async function apiAddTransaction(data) {
    return apiFetch('/api/mini/transactions', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

async function apiDeleteTransaction(id) {
    return apiFetch(`/api/mini/transactions/${id}`, {
        method: 'DELETE',
    });
}
