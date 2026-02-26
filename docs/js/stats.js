/**
 * stats.js — Public statistics tab.
 * Depends on: config.js (API, fmtM, emoji, animateCount)
 */

function renderStats(data) {
    const panel = document.getElementById('tab-stats');
    const net = data.total_income_uzs - data.total_expense_uzs;
    const maxIE = Math.max(data.total_income_uzs, data.total_expense_uzs) || 1;
    const maxCat = data.top_categories.length ? data.top_categories[0].count : 1;

    panel.innerHTML = `
    <div class="cards">
      <div class="card blue">
        <div class="card-icon">👥</div>
        <div class="card-label">Foydalanuvchilar</div>
        <div class="card-value" id="v-users">0</div>
        <div class="card-sub">Jami ro'yxatdan o'tganlar</div>
      </div>
      <div class="card purple">
        <div class="card-icon">📋</div>
        <div class="card-label">Operatsiyalar</div>
        <div class="card-value" id="v-txns">0</div>
        <div class="card-sub">Jami yozuvlar</div>
      </div>
      <div class="card green">
        <div class="card-icon">💵</div>
        <div class="card-label">Jami Kirim</div>
        <div class="card-value" id="v-income">0</div>
        <div class="card-sub">UZS</div>
      </div>
      <div class="card red">
        <div class="card-icon">💸</div>
        <div class="card-label">Jami Chiqim</div>
        <div class="card-value" id="v-expense">0</div>
        <div class="card-sub">UZS</div>
      </div>
    </div>

    <div class="box">
      <div class="box-title">💹 Kirim vs Chiqim</div>
      <div class="balance-row">
        <span class="balance-label" style="color:var(--income)">Kirim</span>
        <div class="balance-bar"><div class="balance-income" id="bar-inc"></div></div>
        <span class="balance-val" style="color:var(--income)" id="lbl-inc">—</span>
      </div>
      <div class="balance-row">
        <span class="balance-label" style="color:var(--expense)">Chiqim</span>
        <div class="balance-bar"><div class="balance-expense" id="bar-exp"></div></div>
        <span class="balance-val" style="color:var(--expense)" id="lbl-exp">—</span>
      </div>
      <div style="text-align:right;margin-top:14px;font-size:.82rem;color:${net >= 0 ? 'var(--income)' : 'var(--expense)'}">
        Sof: <strong id="v-net">—</strong> UZS
      </div>
    </div>

    ${data.top_categories.length ? `
    <div class="box">
      <div class="box-title">📂 TOP Kategoriyalar</div>
      ${data.top_categories.map((c, i) => `
        <div class="cat-row">
          <div class="cat-header">
            <span class="cat-name">${emoji(c.name)} ${c.name}</span>
            <span class="cat-count">${c.count} ta</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" id="cf-${i}" data-pct="${Math.round(c.count / maxCat * 100)}"></div>
          </div>
        </div>`).join('')}
    </div>` : ''}

    <button class="btn btn-primary" id="refresh-btn" onclick="loadStats()">🔄 Yangilash</button>
    <div id="last-updated">Yangilangan: ${new Date().toLocaleTimeString('uz')}</div>
  `;

    animateCount(document.getElementById('v-users'), data.total_users, 800);
    animateCount(document.getElementById('v-txns'), data.total_transactions, 800);
    animateCount(document.getElementById('v-income'), data.total_income_uzs, 1000, fmtM);
    animateCount(document.getElementById('v-expense'), data.total_expense_uzs, 1000, fmtM);

    setTimeout(() => {
        document.getElementById('bar-inc').style.width = (data.total_income_uzs / maxIE * 100) + '%';
        document.getElementById('bar-exp').style.width = (data.total_expense_uzs / maxIE * 100) + '%';
        document.getElementById('lbl-inc').textContent = fmtM(data.total_income_uzs);
        document.getElementById('lbl-exp').textContent = fmtM(data.total_expense_uzs);
        document.getElementById('v-net').textContent = fmtM(Math.abs(net));
        data.top_categories.forEach((_, i) => {
            const el = document.getElementById('cf-' + i);
            if (el) el.style.width = el.dataset.pct + '%';
        });
    }, 100);
}

async function loadStats() {
    const panel = document.getElementById('tab-stats');
    try {
        const res = await fetch(API + '/stats');
        if (!res.ok) throw new Error(res.statusText);
        const d = await res.json();
        if (d.error) throw new Error(d.error);
        renderStats(d);
    } catch (e) {
        panel.innerHTML = `
      <div class="status-msg">
        ⚠️ Ma'lumot yuklanmadi<br>
        <small>${e.message}</small><br>
        <button class="btn btn-primary btn-small" style="margin-top:14px" onclick="loadStats()">🔄 Qayta urinish</button>
      </div>`;
    }
}
