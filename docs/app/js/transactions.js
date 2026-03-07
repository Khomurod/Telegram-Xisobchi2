/**
 * transactions.js — Transaction list screen.
 *
 * Paginated list with type filter (all / income / expense).
 * Tap-and-hold to delete (with confirmation sheet).
 */

/* global apiGetTransactions, apiDeleteTransaction, fmtAmount, escHtml,
          hapticLight, hapticMedium, hapticError, hapticSuccess, renderTxnRow */

let _txnPage = 1;
let _txnFilter = null;  // null = all, 'income', 'expense'
let _txnData = null;

function renderTransactions(container) {
    _txnPage = 1;
    _txnFilter = null;
    container.innerHTML = `
    <div class="screen" id="txn-screen">
      <div class="section-header" style="margin-bottom:14px">
        <div class="section-title" style="font-size:.92rem">📝 Operatsiyalar</div>
      </div>
      <div class="filter-bar">
        <button class="filter-chip active" data-filter="">Barchasi</button>
        <button class="filter-chip" data-filter="expense">📉 Chiqim</button>
        <button class="filter-chip" data-filter="income">📈 Kirim</button>
      </div>
      <div id="txn-list-wrap">
        <div class="loading-screen" style="min-height:30vh"><div class="loading-spinner"></div></div>
      </div>
    </div>`;

    // Filter click handler
    container.querySelector('.filter-bar').addEventListener('click', e => {
        const chip = e.target.closest('.filter-chip');
        if (!chip) return;
        hapticLight();

        container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');

        _txnFilter = chip.dataset.filter || null;
        _txnPage = 1;
        loadTransactions(container);
    });

    // Long-press to delete
    let longPressTimer = null;
    container.addEventListener('pointerdown', e => {
        const row = e.target.closest('.txn-row[data-id]');
        if (!row) return;
        longPressTimer = setTimeout(() => {
            hapticMedium();
            showDeleteConfirm(parseInt(row.dataset.id), container);
        }, 600);
    });
    container.addEventListener('pointerup', () => clearTimeout(longPressTimer));
    container.addEventListener('pointercancel', () => clearTimeout(longPressTimer));

    loadTransactions(container);
}

async function loadTransactions(container) {
    const wrap = container.querySelector('#txn-list-wrap');
    if (!wrap) return;

    try {
        _txnData = await apiGetTransactions(_txnPage, _txnFilter);
        const txns = _txnData.transactions || [];

        if (txns.length === 0 && _txnPage === 1) {
            wrap.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📭</div>
          <div>Operatsiyalar topilmadi</div>
        </div>`;
            return;
        }

        let html = `<div class="txn-list">`;
        for (const txn of txns) {
            html += renderTxnRow(txn);
        }
        html += `</div>`;

        // Pagination
        if (_txnData.pages > 1) {
            html += `<div class="pagination">`;
            if (_txnPage > 1) {
                html += `<button class="filter-chip" id="txn-prev">← Oldingi</button>`;
            }
            html += `<span>${_txnPage} / ${_txnData.pages}</span>`;
            if (_txnPage < _txnData.pages) {
                html += `<button class="filter-chip" id="txn-next">Keyingi →</button>`;
            }
            html += `</div>`;
        }

        wrap.innerHTML = html;

        // Pagination handlers
        const prevBtn = wrap.querySelector('#txn-prev');
        const nextBtn = wrap.querySelector('#txn-next');
        if (prevBtn) prevBtn.addEventListener('click', () => { _txnPage--; hapticLight(); loadTransactions(container); });
        if (nextBtn) nextBtn.addEventListener('click', () => { _txnPage++; hapticLight(); loadTransactions(container); });

    } catch (err) {
        wrap.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚠️</div>
        <div>Yuklab bo'lmadi</div>
        <div style="font-size:.75rem;margin-top:6px;color:var(--tg-hint)">${escHtml(err.message)}</div>
      </div>`;
    }
}

function showDeleteConfirm(txnId, container) {
    // Remove existing overlay if any
    document.querySelector('.confirm-overlay')?.remove();

    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    overlay.innerHTML = `
    <div class="confirm-sheet">
      <div class="confirm-title">O'chirish</div>
      <div class="confirm-msg">Bu operatsiyani o'chirishni xohlaysizmi?</div>
      <div class="confirm-btns">
        <button class="confirm-btn confirm-cancel" id="del-cancel">Bekor qilish</button>
        <button class="confirm-btn confirm-danger" id="del-confirm">O'chirish</button>
      </div>
    </div>`;

    document.body.appendChild(overlay);

    overlay.querySelector('#del-cancel').addEventListener('click', () => {
        hapticLight();
        overlay.remove();
    });

    overlay.querySelector('#del-confirm').addEventListener('click', async () => {
        try {
            await apiDeleteTransaction(txnId);
            hapticSuccess();
            overlay.remove();
            loadTransactions(container);
        } catch (err) {
            hapticError();
            overlay.remove();
            alert('O\'chirishda xatolik: ' + err.message);
        }
    });

    overlay.addEventListener('click', e => {
        if (e.target === overlay) {
            hapticLight();
            overlay.remove();
        }
    });
}
