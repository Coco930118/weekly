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

  const EXCLUDED = ['LINEスタンプ', 'Threads宣伝'];
  weeks.forEach(week => {
    const hasRegular = allPosts.some(p => p.weekId === week && !EXCLUDED.includes(p.platform));
    if (!hasRegular) return;
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
  const mode = activeFilters.platform;
  const EXCLUDED = ['LINEスタンプ', 'Threads宣伝'];

  return allPosts.filter(p => {
    const isStamp = p.platform === 'LINEスタンプ';

    if (mode === 'LINEスタンプ') return isStamp;
    if (mode === 'LINEスタンププロンプト') return isStamp;

    // Regular modes: exclude stamps and promo posts
    if (EXCLUDED.includes(p.platform)) return false;
    if (mode !== 'all' && p.platform !== mode) return false;
    if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
    return true;
  });
}

function renderPosts() {
  const container = document.getElementById('postsContainer');
  const filtered = getFilteredPosts();
  const mode = activeFilters.platform;
  const stampMode = mode === 'LINEスタンプ';
  const promptMode = mode === 'LINEスタンププロンプト';
  const EXCLUDED = ['LINEスタンプ', 'Threads宣伝'];
  const regularTotal = allPosts.filter(p => !EXCLUDED.includes(p.platform)).length;

  document.getElementById('statsBar').textContent = promptMode
    ? `DALL-E 3 プロンプト ${filtered.length}個`
    : stampMode
    ? `LINEスタンプ ${filtered.length}個`
    : `${filtered.length}件 / 全${regularTotal}件`;

  const weekRow = document.getElementById('weekFilterRow');
  if (weekRow) weekRow.style.display = (stampMode || promptMode) ? 'none' : '';

  if (filtered.length === 0) {
    container.innerHTML = '<p class="empty-state">該当する投稿がありません</p>';
    return;
  }

  const seriesHeader = (stampMode || promptMode) ? `
    <div class="stamp-series-header">
      <p class="stamp-series-title">きょうも、そのままで ③</p>
      <p class="stamp-series-desc">日常のあの気持ちを、もっとやさしく届けるために。「ありがとう」「おはよう」「少しずつでいい」——言いたいけどちょっと照れる言葉を、Cocoが代わりに届けます。関係の温度と距離を整える21枚のスタンプ。</p>
    </div>` : '';

  if (promptMode) {
    const cards = filtered.map(renderCard).join('');
    container.innerHTML = seriesHeader + `<div class="cards-grid prompt-grid">${cards}</div>`;
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

  container.innerHTML = seriesHeader + html;
}

function renderCard(post) {
  if (activeFilters.platform === 'LINEスタンププロンプト') return renderPromptCard(post);
  if (post.platform === 'LINEスタンプ') return renderStampCard(post);

  const platformClass = post.platform === 'X' ? 'platform-x' : 'platform-threads';
  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = escapeHtml(post.quote);

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
        <button class="copy-btn" data-copy="${escapeHtml(post.quote)}">コピー</button>
      </div>
    </article>`;
}

function renderStampCard(post) {
  const stampEscaped = escapeHtml(post.stamp || '');
  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = escapeHtml(post.quote);

  return `
    <article class="card stamp-card" data-platform="LINEスタンプ">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge platform-stamp">LINEスタンプ</span>
          <span class="card-character">${post.character}</span>
        </div>
        <span class="purpose-badge">${post.purpose}</span>
      </div>
      <div class="stamp-phrase-row">
        <span class="stamp-phrase-text">${stampEscaped}</span>
        <button class="copy-btn" data-copy="${escapeHtml(post.stamp || '')}">コピー</button>
      </div>
      <div class="card-body">
        <p class="card-content">${contentEscaped}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(post.content)}">本文コピー</button>
        </div>
      </div>
      <div class="card-quote">
        <p class="quote-text">${quoteEscaped}</p>
        <button class="copy-btn" data-copy="${escapeHtml(post.quote)}">コピー</button>
      </div>
    </article>`;
}

function renderPromptCard(post) {
  const stampEscaped = escapeHtml(post.stamp || '');
  const promptEscaped = escapeHtml(post.prompt || '');

  return `
    <article class="card prompt-card">
      <div class="prompt-card-header">
        <span class="platform-badge platform-prompt">DALL-E 3</span>
        <span class="prompt-stamp-phrase">${stampEscaped}</span>
      </div>
      <div class="prompt-card-body">
        <pre class="prompt-code">${promptEscaped}</pre>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(post.prompt || '')}">プロンプトをコピー</button>
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
      b.classList.remove('active', 'active-x', 'active-threads', 'active-stamp', 'active-prompt');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else if (platform === 'LINEスタンプ') btn.classList.add('active-stamp');
    else if (platform === 'LINEスタンププロンプト') btn.classList.add('active-prompt');
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
