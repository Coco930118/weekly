'use strict';

let allPosts = [];
let activeFilters = {
  platform: 'all',
  week: 'all'
};

const DAYS_JA = ['日', '月', '火', '水', '木', '金', '土'];
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const month = MONTHS[d.getMonth()];
  const day = d.getDate();
  const dow = DAYS_JA[d.getDay()];
  return `${month}${day}日（${dow}）`;
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function loadPosts() {
  const container = document.getElementById('postsContainer');
  container.innerHTML = '<p class="loading">読み込み中…</p>';

  try {
    const indexRes = await fetch('./posts/index.json');
    if (!indexRes.ok) throw new Error('index not found');
    const index = await indexRes.json();

    const weekDataArr = await Promise.all(
      index.weeks.map(async (filename) => {
        const res = await fetch(`./posts/${filename}`);
        if (!res.ok) throw new Error(`${filename} not found`);
        return res.json();
      })
    );

    allPosts = weekDataArr
      .flatMap(w => w.posts.map(p => ({ ...p, weekId: w.week })))
      .sort((a, b) => {
        const tA = new Date(`${a.date}T${a.time}:00`);
        const tB = new Date(`${b.date}T${b.time}:00`);
        return tA - tB;
      });

    renderWeekFilter(weekDataArr.map(w => w.week));
    renderXDiagnosisButtons();
    renderThreadsDiagnosisButtons();
    renderPosts();

    if (index.linestamps && index.linestamps.length > 0) {
      const stampSets = await Promise.all(
        index.linestamps.map(async (filename) => {
          const res = await fetch(`./posts/${filename}`);
          if (!res.ok) return null;
          return res.json();
        })
      );
      renderLineStampSection(stampSets.filter(Boolean));
    }

  } catch (err) {
    container.innerHTML = `<p class="error-state">データの読み込みに失敗しました<br><small>${err.message}</small></p>`;
  }
}

function renderLineStampSection(stampSets) {
  const existing = document.getElementById('stampSection');
  if (existing) existing.remove();
  if (!stampSets || stampSets.length === 0) return;

  const section = document.createElement('section');
  section.id = 'stampSection';
  section.style.display = 'none';

  stampSets.forEach(set => {
    const setEl = document.createElement('div');
    setEl.className = 'stamp-set';

    const setHeading = document.createElement('h3');
    setHeading.className = 'stamp-set-heading';
    setHeading.innerHTML = `LINEスタンプ ${escapeHtml(set.week)}作成分 <span class="pattern-badge">パターン${set.pattern}：${escapeHtml(set.pattern_description)}</span>`;
    setEl.appendChild(setHeading);

    const grid = document.createElement('div');
    grid.className = 'stamp-grid';
    grid.innerHTML = set.stamps.map(renderStampCard).join('');
    setEl.appendChild(grid);

    const promoHeading = document.createElement('h4');
    promoHeading.className = 'promo-heading';
    promoHeading.textContent = '📣 Threads宣伝文（28パターン）';
    setEl.appendChild(promoHeading);

    const promoGrid = document.createElement('div');
    promoGrid.className = 'promo-grid';
    promoGrid.innerHTML = set.threads_promo.map(p => `
      <div class="promo-card">
        <span class="promo-date">${escapeHtml(p.date)} ${escapeHtml(p.time)}</span>
        <p class="promo-text">${escapeHtml(p.content)}</p>
        <button class="copy-btn" data-copy="${escapeHtml(p.content)}">コピー</button>
      </div>
    `).join('');
    setEl.appendChild(promoGrid);

    section.appendChild(setEl);
  });

  const postsContainer = document.getElementById('postsContainer');
  postsContainer.parentNode.insertBefore(section, postsContainer.nextSibling);
}

function renderStampCard(stamp) {
  const charLabel = stamp.character.map(c => {
    if (c === 'しらたま') return '🐈‍⬛しらたま';
    if (c === 'しずく') return '🐢しずく';
    if (c === 'ひより') return '🕊ひより';
    if (c === 'Coco') return '💎Coco';
    return c;
  }).join(' + ');

  const typeClass = stamp.with_coco ? 'type-coco' : 'type-char';

  return `
    <div class="stamp-card">
      <div class="stamp-card-header">
        <span class="stamp-num">#${stamp.id}</span>
        <span class="stamp-type-badge ${typeClass}">${escapeHtml(stamp.type)}</span>
      </div>
      <div class="stamp-characters">${escapeHtml(charLabel)}</div>
      <div class="stamp-dialogue">${escapeHtml(stamp.dialogue)}</div>
      <div class="stamp-scene">📍 ${escapeHtml(stamp.scene)}</div>
      <details class="stamp-details">
        <summary>コーデ・プロンプトを見る</summary>
        <div class="stamp-outfit">👗 ${escapeHtml(stamp.outfit)}</div>
        <div class="stamp-color">🎨 ${escapeHtml(stamp.color_scheme)}</div>
        <div class="stamp-prompt-wrap">
          <p class="stamp-prompt">${escapeHtml(stamp.image_prompt)}</p>
          <button class="copy-btn" data-copy="${escapeHtml(stamp.image_prompt)}">プロンプトをコピー</button>
        </div>
      </details>
    </div>
  `;
}

function renderWeekFilter(weeks) {
  const row = document.getElementById('weekFilterRow');
  if (!row) return;

  const all = document.createElement('button');
  all.className = 'filter-btn active';
  all.dataset.week = 'all';
  all.textContent = '全週';
  row.appendChild(all);

  weeks.forEach(week => {
    const [from, to] = week.split('_');
    const label = `${from.slice(5).replace('-', '/')}～${to.slice(5).replace('-', '/')}`;
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.week = week;
    btn.textContent = label;
    row.appendChild(btn);
  });

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-week]');
    if (!btn) return;
    row.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFilters.week = btn.dataset.week;
    renderPosts();
  });
}

function renderXDiagnosisButtons() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  const xDiagWeeks = [...new Set(
    allPosts.filter(p => p.platform === 'X診断').map(p => p.weekId)
  )].sort().reverse();

  if (xDiagWeeks.length === 0) return;

  const lineBtn = row.querySelector('[data-platform="LINEスタンプ"]');

  xDiagWeeks.forEach(weekId => {
    const [from, to] = weekId.split('_');
    const fromStr = from.slice(5).replace('-', '/');
    const toDay = to.slice(8);
    const label = `X診断 ${fromStr}～${toDay}`;

    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.platform = 'X診断';
    btn.dataset.week = weekId;
    btn.textContent = label;

    if (lineBtn) {
      row.insertBefore(btn, lineBtn);
    } else {
      row.appendChild(btn);
    }
  });
}

function renderThreadsDiagnosisButtons() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  const staticBtn = row.querySelector('[data-platform="Threads診断"]:not([data-week])');
  if (staticBtn) staticBtn.remove();

  const threadsDiagWeeks = [...new Set(
    allPosts.filter(p => p.platform === 'Threads診断').map(p => p.weekId)
  )].sort().reverse();

  if (threadsDiagWeeks.length === 0) return;

  const lineBtn = row.querySelector('[data-platform="LINEスタンプ"]');

  threadsDiagWeeks.forEach(weekId => {
    const [from, to] = weekId.split('_');
    const fromStr = from.slice(5).replace('-', '/');
    const toDay = to.slice(8);
    const label = `Threads診断 ${fromStr}～${toDay}`;

    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.platform = 'Threads診断';
    btn.dataset.week = weekId;
    btn.textContent = label;

    if (lineBtn) {
      row.insertBefore(btn, lineBtn);
    } else {
      row.appendChild(btn);
    }
  });
}

function renderExpandable(label, text) {
  const escaped = escapeHtml(text);
  return `
    <details class="card-expandable">
      <summary class="expandable-summary">${label}</summary>
      <div class="expandable-body">
        <p class="expandable-text">${escaped}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(text)}">コピー</button>
        </div>
      </div>
    </details>`;
}

function getFilteredPosts() {
  return allPosts.filter(p => {
    if (activeFilters.platform === 'all' && p.platform === 'X診断') return false;
    if (activeFilters.platform === 'all' && p.platform === 'Threads診断') return false;
    if (activeFilters.platform !== 'all' && p.platform !== activeFilters.platform) return false;
    if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
    return true;
  });
}

function renderPosts() {
  const container = document.getElementById('postsContainer');
  const filtered = getFilteredPosts();

  document.getElementById('statsBar').textContent =
    `${filtered.length}件 / 全${allPosts.length}件`;

  if (filtered.length === 0) {
    container.innerHTML = '<p class="empty-state">該当する投稿がありません</p>';
    return;
  }

  const byDate = {};
  filtered.forEach(p => {
    if (!byDate[p.date]) byDate[p.date] = [];
    byDate[p.date].push(p);
  });

  const html = Object.keys(byDate)
    .sort()
    .map(date => {
      const cards = byDate[date].map(renderCard).join('');
      return `
        <section class="date-group">
          <h2 class="date-heading">${formatDate(date)}</h2>
          <div class="cards-grid">${cards}</div>
        </section>`;
    })
    .join('');

  container.innerHTML = html;
}

function renderCard(post) {
  if (post.platform === 'X診断') return renderXDiagCard(post);
  if (post.platform === 'Threads診断') return renderThreadsDiagCard(post);

  const platformClass = post.platform === 'X' ? 'platform-x' :
                        post.platform === 'Threads' ? 'platform-threads' : 'platform-line';
  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = escapeHtml(post.quote || '');

  return `
    <article class="card" data-platform="${post.platform}">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge ${platformClass}">${post.platform}</span>
          <span class="card-time">${post.time}</span>
          <span class="card-character">${post.character}</span>
        </div>
        <span class="purpose-badge">${post.purpose}</span>
      </div>
      <div class="card-body">
        <p class="card-content">${contentEscaped}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(post.content)}">コピー</button>
        </div>
      </div>
      <div class="card-quote">
        <p class="quote-text">${quoteEscaped}</p>
        <button class="copy-btn" data-copy="${escapeHtml(post.quote || '')}">コピー</button>
      </div>
    </article>`;
}

function renderXDiagCard(post) {
  const e = escapeHtml;
  const themeHtml = post.theme ? `<span class="card-theme-label">${e(post.theme)}</span>` : '';
  return `
    <article class="card card-xshindan" data-platform="X診断">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge platform-xshindan">X診断</span>
          <span class="card-time">${post.time || ''}</span>
          <span class="card-character">${post.character || ''}</span>
          ${themeHtml}
        </div>
        <span class="purpose-badge">${post.purpose || ''}</span>
      </div>
      <div class="card-body">
        <p class="card-content">${e(post.content)}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${e(post.content)}">コピー</button>
        </div>
      </div>
      <div class="card-quote">
        <p class="quote-text">${e(post.quote || '')}</p>
        <button class="copy-btn" data-copy="${e(post.quote || '')}">コピー</button>
      </div>
      ${post.image_prompt ? renderExpandable('🎨 画像プロンプト（DALL-E 3）', post.image_prompt) : ''}
      ${post.comment1 ? renderExpandable('💬 コメント① 回答・解説', post.comment1) : ''}
      ${post.comment2 ? renderExpandable('📌 コメント② 深掘り・保存補足', post.comment2) : ''}
    </article>`;
}

function renderThreadsDiagCard(post) {
  const e = escapeHtml;
  const themeHtml = post.theme ? `<span class="card-theme-label card-theme-threads-shindan">${e(post.theme)}</span>` : '';
  return `
    <article class="card card-threads-shindan" data-platform="Threads診断">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge platform-threads-shindan">Threads診断</span>
          <span class="card-time">${post.time || ''}</span>
          <span class="card-character">${post.character || ''}</span>
          ${themeHtml}
        </div>
        <span class="purpose-badge">${post.purpose || ''}</span>
      </div>
      <div class="card-body">
        <p class="card-content">${e(post.content)}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${e(post.content)}">コピー</button>
        </div>
      </div>
      <div class="card-quote">
        <p class="quote-text">${e(post.quote || '')}</p>
        <button class="copy-btn" data-copy="${e(post.quote || '')}">コピー</button>
      </div>
      ${post.dall_e_prompt ? renderExpandable('🎨 DALL-E 3 プロンプト', post.dall_e_prompt) : ''}
      ${post.reply_1 ? renderExpandable('💬 返信欄① 解説', post.reply_1) : ''}
    </article>`;
}

function setupPlatformFilter() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-platform]');
    if (!btn) return;

    row.querySelectorAll('.filter-btn').forEach(b => {
      b.classList.remove('active', 'active-x', 'active-threads', 'active-stamp', 'active-xshindan', 'active-threads-shindan');
    });

    const platform = btn.dataset.platform;
    const weekId = btn.dataset.week || null;
    activeFilters.platform = platform;
    activeFilters.week = weekId || 'all';

    const stampSection = document.getElementById('stampSection');
    const postsContainer = document.getElementById('postsContainer');
    const weekFilterRow = document.getElementById('weekFilterRow');
    const statsBar = document.getElementById('statsBar');

    if (platform === 'LINEスタンプ') {
      btn.classList.add('active-stamp');
      if (postsContainer) postsContainer.style.display = 'none';
      if (stampSection) stampSection.style.display = 'block';
      if (weekFilterRow) weekFilterRow.style.display = 'none';
      if (statsBar) statsBar.style.display = 'none';
    } else if (platform === 'X診断') {
      btn.classList.add('active-xshindan');
      if (postsContainer) postsContainer.style.display = '';
      if (stampSection) stampSection.style.display = 'none';
      if (weekFilterRow) weekFilterRow.style.display = 'none';
      if (statsBar) statsBar.style.display = '';
      renderPosts();
    } else if (platform === 'Threads診断') {
      btn.classList.add('active-threads-shindan');
      if (postsContainer) postsContainer.style.display = '';
      if (stampSection) stampSection.style.display = 'none';
      if (weekFilterRow) weekFilterRow.style.display = 'none';
      if (statsBar) statsBar.style.display = '';
      renderPosts();
    } else {
      if (platform === 'X') btn.classList.add('active-x');
      else if (platform === 'Threads') btn.classList.add('active-threads');
      else btn.classList.add('active');
      if (postsContainer) postsContainer.style.display = '';
      if (stampSection) stampSection.style.display = 'none';
      if (weekFilterRow) weekFilterRow.style.display = '';
      if (statsBar) statsBar.style.display = '';
      renderPosts();
    }
  });
}

function setupCopyHandler() {
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;

    const text = btn.dataset.copy;
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);
      const original = btn.textContent;
      btn.textContent = 'コピー完了';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = original;
        btn.classList.remove('copied');
      }, 1800);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      btn.textContent = 'コピー完了';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'コピー';
        btn.classList.remove('copied');
      }, 1800);
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  setupPlatformFilter();
  setupCopyHandler();
  loadPosts();
});
