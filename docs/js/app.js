/**
 * app.js — Entry point. Wires up tabs and bootstraps the app.
 * Must be loaded LAST (after all other JS modules).
 *
 * To add a new tab:
 *   1. Add <button class="tab" data-tab="mytab"> in index.html
 *   2. Add <div class="tab-panel" id="tab-mytab"> in index.html
 *   3. Create docs/js/mytab.js with your logic
 *   4. Add <script src="js/mytab.js"> in index.html before app.js
 */

// ── Tab switching ─────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(t => {
    t.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
        t.classList.add('active');
        document.getElementById('tab-' + t.dataset.tab).classList.add('active');
        // Auto-load admin panel if already authenticated
        if (t.dataset.tab === 'admin' && adminToken) adminLogin();
    });
});

// ── Bootstrap ─────────────────────────────────────────────────
loadStats();
setInterval(loadStats, 60_000);   // Refresh public stats every minute

// Auto-login if a token was saved in a previous session
if (adminToken) {
    document.querySelector('[data-tab="admin"]').click();
}
