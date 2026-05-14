'use strict';

let allPosts = [];
let activeFilters = {
  platform: 'all',
  week: 'all'
};

const DAYS_JA = ['日', '月', '火', '水', '木', '金', '土'];
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

// 長い/具体的な型を先に並べること（"X診断" を "X" より前に）
const PLATFORM_TYPES = ['X診断', 'Threads診断', 'Lineスタンプ', 'スタンプ宣伝', 'note', 'Threads', 'X'];

const PLATFORM_STYLE = {
  'X':           { cls: 'platform-x',         active: 'active-x' },
  'Threads':     { cls: 'platform-threads',    active: 'active-threads' },
  'X診断':       { cls: 'platform-xdiag',      active: 'active-xdiag' },
  'Threads診断': { cls: 'platform-tdiag',      active: 'active-tdiag' },
  'Lineスタンプ': { cls: 'platform-linestamp',  active: 'active-linestamp' },
  'スタンプ宣伝': { cls: 'platform-stamppr',    active: 'active-stamppr' },
  'note':        { cls: 'platform-note',       active: 'active-note' },
};

/**
 * "X診断 5/12〜5/18" → "X診断" のように、
 * JSONのplatformフィールドからベース媒体名を抽出する
 */
function getPlatformType(platform) {
  for (const type of PLATFORM_TYPES) {
    if (platform.startsWith(type)) return type;
  }
  return platform;
}

function platformCls(type) {
  return PLATFORM_STYLE[type]?.cls || 'platform-other';
}

function platformActiveClass(type) {
  return PLATFORM_STYLE[type]?.active || 'active';
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const month = MONTHS[d.getMonth()];
  const day = d.getDate();
  const dow = DAYS_JA[d.getDay()];
  return `${month}${day}日（${dow}）`;
}

function escapeHtml(str) {
  return (str || '')
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
    renderPosts();

  } catch (err) {
    container.innerHTML = `<p class="error-state">データの読み込みに失敗しました<br><small>${err.message}</small></p>`;
  }
}

function renderWeekFilter(weeks) {
  const row = document.getElementById('weekFilterRow');
  if (!row) return;
  // ラベル以外のボタンをリセット
  row.querySelectorAll('button').forEach(b => b.remove());

  const all = document.createElement('button');
  all.className = 'filter-btn active';
  all.dataset.week = 'all';
  all.textContent = '全週';
  row.appendChild(all);

  weeks.forEach(week => {
    const [from, to] = week.split('_');
    const label = `${from.slice(5).replace('-', '/')}〜${to.slice(5).replace('-', '/')}`;
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

function getFilteredPosts() {
  return allPosts.filter(p => {
    if (activeFilters.platform !== 'all' && getPlatformType(p.platform) !== activeFilters.platform) return false;
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
  const type = getPlatformType(post.platform);
  const badgeCls = platformCls(type);
  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = escapeHtml(post.quote || '');

  let extraSections = '';
  if (post.comment) {
    const commentEscaped = escapeHtml(post.comment);
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">📝 解説コメント</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${commentEscaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${commentEscaped}">コピー</button>
          </div>
        </div>
      </div>`;
  }
  if (post.image_prompt) {
    const promptEscaped = escapeHtml(post.image_prompt);
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">🖼 画像プロンプト</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${promptEscaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${promptEscaped}">コピー</button>
          </div>
        </div>
      </div>`;
  }

  const quoteSection = quoteEscaped ? `
    <div class="card-quote">
      <p class="quote-text">${quoteEscaped}</p>
      <button class="copy-btn" data-copy="${quoteEscaped}">コピー</button>
    </div>` : '';

  return `
    <article class="card" data-platform="${escapeHtml(type)}">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge ${badgeCls}">${escapeHtml(type)}</span>
          <span class="card-time">${post.time}</span>
          <span class="card-character">${escapeHtml(post.character || '')}</span>
        </div>
        <span class="purpose-badge">${escapeHtml(post.purpose)}</span>
      </div>
      <div class="card-body">
        <p class="card-content">${contentEscaped}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(post.content)}">コピー</button>
        </div>
      </div>
      ${extraSections}
      ${quoteSection}
    </article>`;
}

function setupPlatformFilter() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-platform]');
    if (!btn) return;

    // すべてのボタンをリセット
    row.querySelectorAll('.filter-btn').forEach(b => {
      b.className = 'filter-btn';
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'all') {
      btn.classList.add('active');
    } else {
      btn.classList.add(platformActiveClass(platform));
    }

    renderPosts();
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
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    const original = btn.textContent;
    btn.textContent = 'コピー完了';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = original;
      btn.classList.remove('copied');
    }, 1800);
  });
}

function setupSectionToggle() {
  document.addEventListener('click', e => {
    const header = e.target.closest('.card-section-header');
    if (!header) return;
    const body = header.nextElementSibling;
    if (!body || !body.classList.contains('card-section-body')) return;
    body.classList.toggle('open');
    const toggle = header.querySelector('.card-section-toggle');
    if (toggle) toggle.textContent = body.classList.contains('open') ? '▲' : '▼';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  setupPlatformFilter();
  setupSectionToggle();
  setupCopyHandler();
  loadPosts();
});
