'use strict';

let allPosts = [];
let allNotes = [];
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

async function loadNotes() {
  try {
    const res = await fetch('./notes/index.json');
    if (!res.ok) return;
    const index = await res.json();
    const noteDataArr = await Promise.all(
      index.notes.map(async (n) => {
        const r = await fetch(`./notes/${n.note_id}.json`);
        if (!r.ok) return n;
        const full = await r.json();
        return { ...n, ...full };
      })
    );
    allNotes = noteDataArr.sort((a, b) => b.date.localeCompare(a.date));
  } catch (e) {
    allNotes = [];
  }
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
    await loadNotes();
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
    const hasNonStamp = allPosts.some(p => p.weekId === week && p.platform !== 'LINEスタンプ');
    if (!hasNonStamp) return;
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
    const isStamp = p.platform === 'LINEスタンプ';
    if (activeFilters.platform === 'LINEスタンプ') {
      if (!isStamp) return false;
    } else {
      if (isStamp) return false;
      if (activeFilters.platform !== 'all' && p.platform !== activeFilters.platform) return false;
    }
    if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
    return true;
  });
}

function renderNotes() {
  const container = document.getElementById('postsContainer');
  document.getElementById('statsBar').textContent = `note ${allNotes.length}本`;
  const weekRow = document.getElementById('weekFilterRow');
  if (weekRow) weekRow.style.display = 'none';

  if (allNotes.length === 0) {
    container.innerHTML = '<p class="empty-state">noteデータがありません</p>';
    return;
  }
  container.innerHTML = `<div class="cards-grid" style="padding:16px 16px 0;max-width:680px;margin:0 auto;">${allNotes.map(renderNoteCard).join('')}</div>`;
}

function renderNoteCard(note) {
  const tags = (note.hashtags || []).map(t => `<span class="note-tag">${escapeHtml(t)}</span>`).join('');
  const hooks = note.sns_hooks || {};
  const hooksHtml = Object.entries(hooks).map(([platform, text]) => `
    <div class="note-hook-row">
      <span class="note-hook-platform">${escapeHtml(platform)}</span>
      <span class="note-hook-text">${escapeHtml(text)}</span>
      <button class="copy-btn" data-copy="${escapeHtml(text)}" style="flex-shrink:0">コピー</button>
    </div>`).join('');

  return `
    <article class="card note-card" style="margin-bottom:12px;display:block;text-decoration:none;">
      <div class="note-card-header">
        <div class="card-meta-left">
          <span class="platform-badge platform-note">note</span>
          <span class="card-date" style="font-size:.72rem;color:var(--text-muted)">${escapeHtml(note.date)}</span>
        </div>
        <span class="note-price-badge">¥${escapeHtml(note.price)}</span>
      </div>
      <div class="note-card-body">
        <a href="./notes/${escapeHtml(note.filename)}" class="note-card-title" style="display:block;text-decoration:none;color:var(--text-primary);font-size:.95rem;font-weight:600;line-height:1.55;margin-bottom:10px;">${escapeHtml(note.title)}</a>
        <p class="note-card-desc">${escapeHtml(note.description)}</p>
        <div class="note-card-tags">${tags}</div>
      </div>
      ${hooksHtml ? `<div class="note-hooks"><p class="note-hooks-title">SNS導線文</p>${hooksHtml}</div>` : ''}
      <div class="note-card-footer">
        <span class="note-card-date">参照週: ${escapeHtml(note.source_week || '')}</span>
        <a href="./notes/${escapeHtml(note.filename)}" style="font-size:.72rem;color:#c9a96e;text-decoration:none;">全文を見る →</a>
      </div>
    </article>`;
}

function renderPosts() {
  const container = document.getElementById('postsContainer');
  const noteMode = activeFilters.platform === 'note';
  if (noteMode) { renderNotes(); return; }

  const filtered = getFilteredPosts();
  const stampMode = activeFilters.platform === 'LINEスタンプ';
  const nonStampTotal = allPosts.filter(p => p.platform !== 'LINEスタンプ').length;

  document.getElementById('statsBar').textContent = stampMode
    ? `LINEスタンプ ${filtered.length}個`
    : `${filtered.length}件 / 全${nonStampTotal}件`;

  const weekRow = document.getElementById('weekFilterRow');
  if (weekRow) weekRow.style.display = stampMode ? 'none' : '';

  if (filtered.length === 0) {
    container.innerHTML = '<p class="empty-state">該当する投稿がありません</p>';
    return;
  }

  const byDate = {};
  filtered.forEach(p => {
    if (!byDate[p.date]) byDate[p.date] = [];
    byDate[p.date].push(p);
  });

  const seriesHeader = stampMode ? `
    <div class="stamp-series-header">
      <p class="stamp-series-title">きょうも、そのままで ③</p>
      <p class="stamp-series-desc">日常のあの気持ちを、もっとやさしく届けるために。「ありがとう」「おはよう」「少しずつでいい」——言いたいけどちょっと照れる言葉を、Cocoが代わりに届けます。関係の温度と距離を整える21枚のスタンプ。</p>
    </div>` : '';

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
  const promptEscaped = escapeHtml(post.prompt || '');

  const promptSection = post.prompt ? `
      <div class="stamp-prompt-section">
        <p class="stamp-prompt-label">DALL-E 3 プロンプト</p>
        <pre class="stamp-prompt-code">${promptEscaped}</pre>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(post.prompt)}">プロンプトをコピー</button>
        </div>
      </div>` : '';

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
      </div>${promptSection}
      <div class="card-quote">
        <p class="quote-text">${quoteEscaped}</p>
        <button class="copy-btn" data-copy="${escapeHtml(post.quote)}">コピー</button>
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
      b.classList.remove('active', 'active-x', 'active-threads', 'active-stamp', 'active-note');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else if (platform === 'LINEスタンプ') btn.classList.add('active-stamp');
    else if (platform === 'note') btn.classList.add('active-note');
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
