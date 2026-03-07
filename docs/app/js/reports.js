/**
 * reports.js — Reports screen.
 *
 * Period tabs: Hafta (week) / Oy (month).
 * Charts:
 *   – SVG donut chart: income vs expense ratio
 *   – Daily bar chart for 7-day spending (pure HTML/CSS, no library)
 *   – Category bars (same as dashboard but expanded)
 */

/* global apiGetReports, fmtAmount, fmtNum, escHtml, hapticLight */

let _reportsData = null;

function renderReports(container) {
    container.innerHTML = `
      <div class="screen" id="reports-screen">
        <div class="section-header" style="margin-bottom:14px">
          <div class="section-title" style="font-size:.92rem">📈 Hisobotlar</div>
        </div>
        <div class="filter-bar">
          <button class="filter-chip active" data-period="week">📅 Hafta</button>
          <button class="filter-chip" data-period="month">🗓 Oy</button>
        </div>
        <div id="reports-content">
          <div class="loading-screen" style="min-height:30vh"><div class="loading-spinner"></div></div>
        </div>
      </div>`;

    // Period tab switching
    container.querySelector('.filter-bar').addEventListener('click', e => {
        const chip = e.target.closest('.filter-chip');
        if (!chip) return;
        hapticLight();
        container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        if (_reportsData) renderReportContent(container, chip.dataset.period);
    });

    loadReportsData(container);
}

async function loadReportsData(container) {
    try {
        _reportsData = await apiGetReports();
        renderReportContent(container, 'week');
    } catch (err) {
        const content = container.querySelector('#reports-content');
        if (content) content.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div>Yuklab bo'lmadi</div>
            <div style="font-size:.75rem;margin-top:6px;color:var(--tg-hint)">${escHtml(err.message)}</div>
          </div>`;
    }
}

function renderReportContent(container, period) {
    const content = container.querySelector('#reports-content');
    if (!content || !_reportsData) return;

    if (period === 'week') {
        content.innerHTML = renderWeekReport(_reportsData);
    } else {
        content.innerHTML = renderMonthReport(_reportsData);
    }

    // Animate bars after paint
    requestAnimationFrame(() => {
        document.querySelectorAll('.bar-fill, .cat-fill').forEach(bar => {
            const w = bar.style.width;
            const h = bar.style.height;
            if (w) { bar.style.width = '0%'; requestAnimationFrame(() => { bar.style.width = w; }); }
            if (h) { bar.style.height = '0%'; requestAnimationFrame(() => { bar.style.height = h; }); }
        });
        // Animate donut
        const donut = document.querySelector('.donut-ring');
        if (donut) {
            const target = donut.dataset.offset;
            donut.style.strokeDashoffset = '339.3';
            requestAnimationFrame(() => {
                donut.style.transition = 'stroke-dashoffset 1s cubic-bezier(.4,0,.2,1)';
                donut.style.strokeDashoffset = target;
            });
        }
    });
}

// ── Week report ──────────────────────────────────────────────
function renderWeekReport(data) {
    const w = data.week || {};
    const daily = data.daily || [];

    const incUzs = w.income_uzs || 0;
    const expUzs = w.expense_uzs || 0;
    const total = incUzs + expUzs;
    const incPct = total > 0 ? (incUzs / total) : 0.5;

    // SVG donut: circumference = 2π×54 ≈ 339.3
    const C = 339.3;
    const incOffset = C - incPct * C;
    const hasData = total > 0;

    // Daily bars
    const maxDay = Math.max(...daily.map(d => Math.max(d.income_uzs, d.expense_uzs)), 1);

    let dailyBarsHtml = '';
    for (const d of daily) {
        const incH = Math.round((d.income_uzs / maxDay) * 100);
        const expH = Math.round((d.expense_uzs / maxDay) * 100);
        dailyBarsHtml += `
          <div class="day-col">
            <div class="day-bars">
              <div class="bar-wrap">
                <div class="bar-fill income-bar" style="height:${incH}%" title="${fmtNum(d.income_uzs)}"></div>
              </div>
              <div class="bar-wrap">
                <div class="bar-fill expense-bar" style="height:${expH}%" title="${fmtNum(d.expense_uzs)}"></div>
              </div>
            </div>
            <div class="day-label">${d.weekday}</div>
            <div class="day-date">${d.date}</div>
          </div>`;
    }

    return `
      <!-- Donut chart -->
      <div class="section">
        <div class="section-title" style="margin-bottom:12px">📊 Kirim/chiqim nisbati (7 kun)</div>
        <div class="donut-wrap">
          <svg class="donut-svg" viewBox="0 0 120 120">
            <circle class="donut-track" cx="60" cy="60" r="54" fill="none" stroke-width="12"/>
            <circle class="donut-ring income-ring" cx="60" cy="60" r="54" fill="none" stroke-width="12"
              stroke-dasharray="${C}" stroke-dashoffset="${hasData ? incOffset : C / 2}"
              data-offset="${hasData ? incOffset : C / 2}"
              transform="rotate(-90 60 60)"/>
            <circle class="donut-ring expense-ring" cx="60" cy="60" r="54" fill="none" stroke-width="12"
              stroke-dasharray="${C}" stroke-dashoffset="${hasData ? C - incPct * C - C : C / 2}"
              transform="rotate(${-90 + incPct * 360} 60 60)"/>
          </svg>
          <div class="donut-center">
            <div class="donut-pct">${hasData ? Math.round(incPct * 100) : 50}%</div>
            <div class="donut-sub">kirim</div>
          </div>
        </div>
        <div class="donut-legend">
          <div class="legend-item"><span class="legend-dot income-dot"></span>Kirim: ${fmtAmount(incUzs, 'UZS')}</div>
          <div class="legend-item"><span class="legend-dot expense-dot"></span>Chiqim: ${fmtAmount(expUzs, 'UZS')}</div>
        </div>
      </div>

      <!-- 7-day daily bar chart -->
      <div class="section">
        <div class="section-title" style="margin-bottom:12px">📉 Kunlik tahlil (7 kun, so'm)</div>
        <div class="chart-card">
          <div class="day-chart">${dailyBarsHtml || '<div class="empty-state" style="padding:20px">Ma\'lumot yo\'q</div>'}</div>
          <div class="chart-legend">
            <span><span class="legend-dot income-dot"></span>Kirim</span>
            <span><span class="legend-dot expense-dot"></span>Chiqim</span>
          </div>
        </div>
      </div>

      <!-- Week summary -->
      <div class="section">
        <div class="section-title" style="margin-bottom:10px">📋 Hafta xulosasi</div>
        <div class="summary-card">
          <div class="summary-row">
            <span class="summary-label">📈 Jami kirim</span>
            <span class="summary-value income">${fmtAmount(incUzs, 'UZS')}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">📉 Jami chiqim</span>
            <span class="summary-value expense">${fmtAmount(expUzs, 'UZS')}</span>
          </div>
          <div class="summary-row summary-net">
            <span class="summary-label">${incUzs - expUzs >= 0 ? '✅' : '🔴'} Net</span>
            <span class="summary-value ${incUzs - expUzs >= 0 ? 'income' : 'expense'}">${fmtAmount(Math.abs(incUzs - expUzs), 'UZS')}</span>
          </div>
          ${w.income_usd || w.expense_usd ? `
          <div class="summary-row" style="border-top:1px solid var(--tg-section-separator);margin-top:8px;padding-top:8px">
            <span class="summary-label">💵 Dollar kirim</span>
            <span class="summary-value income">${fmtAmount(w.income_usd || 0, 'USD')}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">💵 Dollar chiqim</span>
            <span class="summary-value expense">${fmtAmount(w.expense_usd || 0, 'USD')}</span>
          </div>` : ''}
        </div>
      </div>`;
}

// ── Month report ─────────────────────────────────────────────
function renderMonthReport(data) {
    const m = data.month || {};
    const incUzs = m.income_uzs || 0;
    const expUzs = m.expense_uzs || 0;
    const count = m.count || 0;
    const categories = m.categories || [];

    const expCats = categories.filter(c => c.type === 'expense' && c.currency === 'UZS');
    const incCats = categories.filter(c => c.type === 'income' && c.currency === 'UZS');
    const maxExp = Math.max(...expCats.map(c => c.total), 1);
    const maxInc = Math.max(...incCats.map(c => c.total), 1);

    let expHtml = '', incHtml = '';

    for (const cat of expCats) {
        const pct = (cat.total / maxExp * 100).toFixed(1);
        expHtml += `
          <div class="cat-row">
            <div class="cat-header">
              <span class="cat-name">${cat.category_emoji} ${escHtml(cat.category_name)}</span>
              <span class="cat-amount">${fmtAmount(cat.total, 'UZS')}</span>
            </div>
            <div class="cat-track"><div class="cat-fill expense-fill" style="width:${pct}%"></div></div>
          </div>`;
    }

    for (const cat of incCats) {
        const pct = (cat.total / maxInc * 100).toFixed(1);
        incHtml += `
          <div class="cat-row">
            <div class="cat-header">
              <span class="cat-name">${cat.category_emoji} ${escHtml(cat.category_name)}</span>
              <span class="cat-amount">${fmtAmount(cat.total, 'UZS')}</span>
            </div>
            <div class="cat-track"><div class="cat-fill income-fill" style="width:${pct}%"></div></div>
          </div>`;
    }

    return `
      <!-- Month summary -->
      <div class="section">
        <div class="section-title" style="margin-bottom:10px">📋 Oylik xulosa</div>
        <div class="summary-card">
          <div class="summary-row">
            <span class="summary-label">🔢 Operatsiyalar</span>
            <span class="summary-value">${count} ta</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">📈 Jami kirim</span>
            <span class="summary-value income">${fmtAmount(incUzs, 'UZS')}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">📉 Jami chiqim</span>
            <span class="summary-value expense">${fmtAmount(expUzs, 'UZS')}</span>
          </div>
          <div class="summary-row summary-net">
            <span class="summary-label">${incUzs - expUzs >= 0 ? '✅' : '🔴'} Net</span>
            <span class="summary-value ${incUzs - expUzs >= 0 ? 'income' : 'expense'}">${fmtAmount(Math.abs(incUzs - expUzs), 'UZS')}</span>
          </div>
          ${m.income_usd || m.expense_usd ? `
          <div class="summary-row" style="border-top:1px solid var(--tg-section-separator);margin-top:8px;padding-top:8px">
            <span class="summary-label">💵 Dollar net</span>
            <span class="summary-value ${(m.income_usd - m.expense_usd) >= 0 ? 'income' : 'expense'}">${fmtAmount(Math.abs((m.income_usd || 0) - (m.expense_usd || 0)), 'USD')}</span>
          </div>` : ''}
        </div>
      </div>

      <!-- Expense categories -->
      ${expCats.length ? `
      <div class="section">
        <div class="section-title" style="margin-bottom:10px">📉 Chiqimlar kategoriyasi</div>
        <div class="cat-list">${expHtml}</div>
      </div>` : ''}

      <!-- Income categories -->
      ${incCats.length ? `
      <div class="section">
        <div class="section-title" style="margin-bottom:10px">📈 Kirimlar kategoriyasi</div>
        <div class="cat-list">${incHtml}</div>
      </div>` : ''}

      ${!expCats.length && !incCats.length ? `
      <div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div>Bu oyda hali operatsiya yo'q</div>
      </div>` : ''}`;
}
