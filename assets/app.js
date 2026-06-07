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

// ─── Posts ───────────────────────────────────────────────

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

    renderDynamicPlatformFilter();
    renderWeekFilter(weekDataArr.map(w => w.week));
    renderPosts();

  } catch (err) {
    container.innerHTML = `<p class="error-state">データの読み込みに失敗しました<br><small>${err.message}</small></p>`;
  }
}

function renderDynamicPlatformFilter() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  row.querySelectorAll('[data-dynamic]').forEach(b => b.remove());

  const knownPlatforms = new Set(['all', 'X', 'Threads', 'note']);
  const extraPlatforms = [...new Set(allPosts.map(p => p.platform))]
    .filter(p => !knownPlatforms.has(p))
    .sort();

  extraPlatforms.forEach(platform => {
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.platform = platform;
    btn.dataset.dynamic = '1';
    btn.textContent = platform;
    row.appendChild(btn);
  });
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

function renderPosts() {
  // noteモードのときはnote一覧を表示
  if (activeFilters.platform === 'note') {
    renderNotes();
    return;
  }

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
  const platformClass = post.platform === 'X' ? 'platform-x'
    : post.platform === 'Threads' ? 'platform-threads'
    : post.platform.startsWith('X診断') ? 'platform-xdiag'
    : post.platform.startsWith('Threads診断') ? 'platform-threadsdiag'
    : 'platform-other';

  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = post.quote ? escapeHtml(post.quote) : '';

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
  if (post.reply_1) {
    const r1Escaped = escapeHtml(post.reply_1);
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">📝 返信コメント</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${r1Escaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${r1Escaped}">コピー</button>
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

  return `
    <article class="card" data-platform="${escapeHtml(post.platform)}">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge ${platformClass}">${escapeHtml(post.platform)}</span>
          <span class="card-time">${post.time}</span>
          <span class="card-character">${escapeHtml(post.character)}</span>
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
      ${post.quote ? `<div class="card-quote">
        <p class="quote-text">${quoteEscaped}</p>
        <button class="copy-btn" data-copy="${escapeHtml(post.quote)}">コピー</button>
      </div>` : ''}
    </article>`;
}

// ─── Notes ───────────────────────────────────────────────

async function loadNotes() {
  try {
    const indexRes = await fetch('./notes/index.json');
    if (!indexRes.ok) return;
    const index = await indexRes.json();

    const results = await Promise.all(
      index.notes.map(async (filename) => {
        const res = await fetch(`./notes/${filename}`);
        if (!res.ok) return null;
        return res.json();
      })
    );

    allNotes = results.filter(Boolean).sort((a, b) => b.date.localeCompare(a.date));
  } catch (err) {
    console.warn('Notes load failed:', err.message);
  }
}

function visibilityLabel(v) {
  if (v === 'single_paid') return '有料';
  if (v === 'members_only') return '会員限定';
  return '無料';
}

function renderNotes() {
  const container = document.getElementById('postsContainer');

  // 週フィルターはnoteモードでは非表示
  const weekRow = document.getElementById('weekFilterRow');
  if (weekRow) weekRow.style.display = 'none';

  document.getElementById('statsBar').textContent = `${allNotes.length}件のnote`;

  if (allNotes.length === 0) {
    container.innerHTML = '<p class="empty-state">noteがありません</p>';
    return;
  }

  container.innerHTML = allNotes.map(renderNoteCard).join('');
}

function renderNoteCard(note) {
  const visLabel = visibilityLabel(note.visibility);
  const visCls = note.visibility === 'single_paid' ? 'vis-paid'
    : note.visibility === 'members_only' ? 'vis-members'
    : 'vis-free';

  const priceStr = note.price && note.price !== '0' ? ` ¥${note.price}` : '';

  // SNSフックセクション
  let snsSection = '';
  if (note.sns_hooks) {
    const xHook = note.sns_hooks.x || '';
    const thHook = note.sns_hooks.threads || '';
    const xEsc = escapeHtml(xHook);
    const thEsc = escapeHtml(thHook);
    snsSection = `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">🔗 SNS誘導文</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          ${xHook ? `<p class="sns-hook-label">X用</p><p>${xEsc}</p><div class="copy-btn-content"><button class="copy-btn" data-copy="${xEsc}">コピー</button></div>` : ''}
          ${thHook ? `<p class="sns-hook-label">Threads用</p><p>${thEsc}</p><div class="copy-btn-content"><button class="copy-btn" data-copy="${thEsc}">コピー</button></div>` : ''}
        </div>
      </div>`;
  }

  // 調整ポイントセクション
  let microSection = '';
  if (note.micro_adjustment_points && note.micro_adjustment_points.length > 0) {
    const items = note.micro_adjustment_points
      .map(p => `<li>${escapeHtml(p)}</li>`).join('');
    microSection = `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">✏️ 調整ポイント</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <ul class="micro-list">${items}</ul>
        </div>
      </div>`;
  }

  // 本文セクション（全文表示 + 全文コピー）
  const contentSection = `
    <div class="card-section">
      <div class="card-section-header">
        <span class="card-section-title">📄 本文（全文）</span>
        <span class="card-section-toggle">▼</span>
      </div>
      <div class="card-section-body">
        <pre class="note-full-text">${escapeHtml(note.content_markdown || '')}</pre>
        <div class="copy-btn-content">
          <button class="copy-btn copy-btn-full" data-note-id="${escapeHtml(note.note_id)}">全文コピー</button>
        </div>
      </div>
    </div>`;

  return `
    <article class="card note-card">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge platform-note">note</span>
          <span class="note-vis-badge ${visCls}">${visLabel}${priceStr}</span>
          <span class="card-time">${note.date}</span>
        </div>
      </div>
      <div class="card-body">
        <p class="note-title">${escapeHtml(note.title)}</p>
        <p class="note-description">${escapeHtml(note.description || '')}</p>
        ${note.linked_principle ? `<p class="note-principle">${escapeHtml(note.linked_principle)}</p>` : ''}
        <div class="copy-btn-content">
          <button class="copy-btn copy-btn-full" data-note-id="${escapeHtml(note.note_id)}">全文コピー</button>
        </div>
      </div>
      ${contentSection}
      ${snsSection}
      ${microSection}
    </article>`;
}

// ─── Platform filter ──────────────────────────────────────

function setupPlatformFilter() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-platform]');
    if (!btn) return;

    row.querySelectorAll('.filter-btn').forEach(b => {
      b.classList.remove('active', 'active-x', 'active-threads', 'active-xdiag', 'active-note');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else if (platform.startsWith('X診断')) btn.classList.add('active-xdiag');
    else if (platform.startsWith('Threads診断')) btn.classList.add('active-threadsdiag');
    else if (platform === 'note') btn.classList.add('active-note');
    else btn.classList.add('active');

    // noteモード以外では週フィルターを再表示
    const weekRow = document.getElementById('weekFilterRow');
    if (weekRow) weekRow.style.display = platform === 'note' ? 'none' : '';

    renderPosts();
  });
}

// ─── Copy handler ─────────────────────────────────────────

async function copyText(text, btn) {
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
  btn.textContent = 'コピー完了 ✓';
  btn.classList.add('copied');
  setTimeout(() => {
    btn.textContent = original;
    btn.classList.remove('copied');
  }, 1800);
}

function setupCopyHandler() {
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;

    // note全文コピー（data-note-id経由でallNotesから取得）
    const noteId = btn.dataset.noteId;
    if (noteId) {
      const note = allNotes.find(n => n.note_id === noteId);
      if (note) await copyText(note.content_markdown || '', btn);
      return;
    }

    // 通常コピー
    const text = btn.dataset.copy;
    if (!text) return;
    await copyText(text, btn);
  });
}

// ─── Section toggle ───────────────────────────────────────

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

// ─── Init ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  setupPlatformFilter();
  setupSectionToggle();
  setupCopyHandler();
  await Promise.all([loadPosts(), loadNotes()]);
});
