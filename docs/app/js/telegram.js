/**
 * telegram.js — Telegram WebApp SDK bridge.
 *
 * Initialises the Telegram Mini App, injects theme CSS vars,
 * and exposes helpers used by other modules.
 */

/* global Telegram */

const tg = window.Telegram?.WebApp;

// ── Init ────────────────────────────────────────────────────
if (tg) {
    tg.ready();
    tg.expand();
}

/** initData string for API auth (empty outside Telegram) */
const INIT_DATA = tg?.initData || '';

/** Whether running inside a real Telegram client */
const IS_TELEGRAM = !!INIT_DATA;

// ── Theme injection ─────────────────────────────────────────
function applyTelegramTheme() {
    if (!tg?.themeParams) return;
    const tp = tg.themeParams;
    const root = document.documentElement;

    const map = {
        '--tg-bg': tp.bg_color,
        '--tg-text': tp.text_color,
        '--tg-hint': tp.hint_color,
        '--tg-link': tp.link_color,
        '--tg-btn': tp.button_color,
        '--tg-btn-text': tp.button_text_color,
        '--tg-secondary-bg': tp.secondary_bg_color,
        '--tg-header-bg': tp.header_bg_color,
        '--tg-section-bg': tp.section_bg_color,
        '--tg-section-separator': tp.section_separator_color,
        '--tg-subtitle': tp.subtitle_text_color,
    };

    for (const [prop, val] of Object.entries(map)) {
        if (val) root.style.setProperty(prop, val);
    }
}

applyTelegramTheme();

// Re-apply if user changes theme while app is open
if (tg) {
    tg.onEvent('themeChanged', applyTelegramTheme);
}

// ── Haptic helpers ──────────────────────────────────────────
function hapticLight() { tg?.HapticFeedback?.impactOccurred('light'); }
function hapticMedium() { tg?.HapticFeedback?.impactOccurred('medium'); }
function hapticSuccess() { tg?.HapticFeedback?.notificationOccurred('success'); }
function hapticError() { tg?.HapticFeedback?.notificationOccurred('error'); }

// ── Back button ─────────────────────────────────────────────
function showBackButton(callback) {
    if (!tg?.BackButton) return;
    tg.BackButton.show();
    tg.BackButton.onClick(callback);
}

function hideBackButton() {
    if (!tg?.BackButton) return;
    tg.BackButton.hide();
    tg.BackButton.offClick();
}

// ── Main button ─────────────────────────────────────────────
function showMainButton(text, callback) {
    if (!tg?.MainButton) return;
    tg.MainButton.setText(text);
    tg.MainButton.show();
    tg.MainButton.onClick(callback);
}

function hideMainButton() {
    if (!tg?.MainButton) return;
    tg.MainButton.hide();
    tg.MainButton.offClick();
}

function setMainButtonLoading(loading) {
    if (!tg?.MainButton) return;
    if (loading) {
        tg.MainButton.showProgress();
        tg.MainButton.disable();
    } else {
        tg.MainButton.hideProgress();
        tg.MainButton.enable();
    }
}
