'use strict';

let allPosts = [];
let activeFilters = {
  platform: 'all',
  week: 'all'
};
let weekDataMap = {};

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

    weekDataArr.forEach(w => {
      weekDataMap[w.week] = w;
    });

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
    if (activeFilters.platform !== 'all' && p.platform !== activeFilters.platform) return false;
    if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
    return true;
  });
}

function renderTrendSummary(weekId) {
  const weekData = weekDataMap[weekId];
  if (!weekData || !weekData.trend_summary || weekData.trend_summary.length === 0) return '';

  const items = weekData.trend_summary
    .map(t => `<li class="trend-item">${escapeHtml(t)}</li>`)
    .join('');

  return `
    <details class="trend-box">
      <summary class="trend-summary-toggle">今週のトレンド</summary>
      <ul class="trend-list">${items}</ul>
    </details>`;
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

  const trendSection = activeFilters.week !== 'all'
    ? renderTrendSummary(activeFilters.week)
    : '';

  const html = trendSection + Object.keys(byDate)
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
  const platformClass = post.platform === 'X' ? 'platform-x' : 'platform-threads';
  const quoteLabel = post.platform === 'X' ? '名言' : 'お守り言葉';
  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = escapeHtml(post.quote);

  return `
    <article class="card" data-platform="${post.platform}">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge ${platformClass}">${post.platform}</span>
          <span class="card-time">${post.time}</span>
          <span class="card-character">${escapeHtml(post.character)}</span>
        </div>
        <span class="purpose-badge">${escapeHtml(post.purpose)}</span>
      </div>
      <div class="card-body">
        <p class="card-content">${contentEscaped}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(post.content)}">本文をコピー</button>
        </div>
      </div>
      <div class="card-quote">
        <div class="quote-header-row">
          <span class="quote-label">${quoteLabel}</span>
        </div>
        <p class="quote-text">${quoteEscaped}</p>
        <div class="quote-copy-row">
          <button class="copy-btn" data-copy="${escapeHtml(post.quote)}">コピー</button>
        </div>
      </div>
    </article>`;
}

function setupPlatformFilter() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-platform]');
    if (!btn) return;

    row.querySelectorAll('.filter-btn').forEach(b => {
      b.classList.remove('active', 'active-x', 'active-threads');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else btn.classList.add('active');

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
      flashCopied(btn);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      flashCopied(btn);
    }
  });
}

function flashCopied(btn) {
  const original = btn.textContent;
  btn.textContent = 'コピー完了 ✓';
  btn.classList.add('copied');
  setTimeout(() => {
    btn.textContent = original;
    btn.classList.remove('copied');
  }, 1800);
}

document.addEventListener('DOMContentLoaded', () => {
  setupPlatformFilter();
  setupCopyHandler();
  loadPosts();
});
