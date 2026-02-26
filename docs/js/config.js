/**
 * config.js — Shared constants and utility helpers.
 * Add new API base URLs or helper functions here.
 */

// ── API ──────────────────────────────────────────────────────
const API = 'https://telegram-xisobchi2.onrender.com';

// ── Number formatters ────────────────────────────────────────
const fmt = n => new Intl.NumberFormat('uz').format(Math.round(n));
const fmtM = n => {
    if (n >= 1e9) return (n / 1e9).toFixed(1) + ' mlrd';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + ' mln';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + ' ming';
    return fmt(n);
};

// ── Category emoji map ───────────────────────────────────────
const CAT_EMOJI = {
    'oziq-ovqat': '🛒', 'transport': '🚗', 'uy-joy': '🏠',
    "sog'liq": '💊', 'kiyim': '👗', 'aloqa': '📱',
    "ta'lim": '📚', "ko'ngil ochar": '🎬', "o'tkazma": '💸',
    'maosh': '💰', 'boshqa': '📌',
};
const emoji = c => CAT_EMOJI[c] || '💳';

// ── Animated counter ─────────────────────────────────────────
function animateCount(el, target, duration = 900, formatter = fmt) {
    const start = performance.now();
    const step = ts => {
        const p = Math.min((ts - start) / duration, 1);
        const ease = 1 - Math.pow(1 - p, 3);
        el.textContent = formatter(target * ease);
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = formatter(target);
    };
    requestAnimationFrame(step);
}
