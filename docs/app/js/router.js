/**
 * router.js — Minimal hash-based SPA router + app boot.
 *
 * Routes:
 *   #/               → Dashboard
 *   #/transactions   → Transaction list
 *   #/add            → Add transaction form
 *
 * Boots the app after loading.
 */

/* global renderDashboard, renderTransactions, renderAddForm, renderReports, renderSettings, cleanupAddForm,
          showBackButton, hideBackButton, hideMainButton, hapticLight, tg */

const ROUTES = {
    '#/': { render: renderDashboard, name: 'dashboard' },
    '#/transactions': { render: renderTransactions, name: 'transactions' },
    '#/add': { render: renderAddForm, name: 'add' },
    '#/reports': { render: renderReports, name: 'reports' },
    '#/settings': { render: renderSettings, name: 'settings' },
};

let _currentRoute = null;
let _previousCleanup = null;

function navigate() {
    const hash = location.hash || '#/';
    const route = ROUTES[hash] || ROUTES['#/'];

    if (_currentRoute === hash) return;

    // Cleanup previous screen
    if (_previousCleanup) {
        _previousCleanup();
        _previousCleanup = null;
    }

    // Hide main button between routes
    if (typeof hideMainButton === 'function') hideMainButton();

    _currentRoute = hash;

    const appContainer = document.getElementById('app');
    if (!appContainer) return;

    // Clear container
    appContainer.innerHTML = '';

    // Render screen
    route.render(appContainer);

    // Track cleanup function for add form
    if (route.name === 'add') {
        _previousCleanup = typeof cleanupAddForm === 'function' ? cleanupAddForm : null;
    }

    // Update bottom nav active state
    updateNavActive(hash);

    // Telegram back button
    if (route.name === 'dashboard') {
        if (typeof hideBackButton === 'function') hideBackButton();
    } else {
        if (typeof showBackButton === 'function') {
            showBackButton(() => {
                hapticLight();
                location.hash = '#/';
            });
        }
    }
}

function updateNavActive(hash) {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        const route = btn.dataset.route;
        if (route === hash) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

// ── Event listeners ─────────────────────────────────────────

window.addEventListener('hashchange', navigate);

// Bottom nav clicks
document.getElementById('bottom-nav')?.addEventListener('click', e => {
    const btn = e.target.closest('.nav-btn[data-route]');
    if (!btn) return;
    hapticLight();
    location.hash = btn.dataset.route;
});

// ── Boot ────────────────────────────────────────────────────

(function boot() {
    // Set default route
    if (!location.hash || location.hash === '#') {
        location.hash = '#/';
    }

    // Initial navigation
    navigate();
})();
