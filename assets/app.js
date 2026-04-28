'use strict';

let allPosts = [];
let allNotes = [];
let allNoteFunnelPosts = [];
let activeFilters = {
  platform: 'all',
  week: 'all',
  series: 'all'
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
        const tA = new Date(`${a.date}T${a.time || '00:00'}:00`);
        const tB = new Date(`${b.date}T${b.time || '00:00'}:00`);
        return tA - tB;
      });

    renderWeekFilter(weekDataArr.map(w => w.week));

    try {
      const notesIndexRes = await fetch('./notes/index.json');
      if (notesIndexRes.ok) {
        const notesIndex = await notesIndexRes.json();
        if (notesIndex.notes) {
          const noteDataArr = await Promise.all(notesIndex.notes.map(async (n) => {
            const r = await fetch(`./notes/${n.note_id}.json`);
            if (!r.ok) return n;
            const full = await r.json();
            return { ...n, ...full };
          }));
          allNotes = noteDataArr.sort((a, b) => b.date.localeCompare(a.date));
        }
        if (notesIndex.funnels) {
          const funnelDataArr = await Promise.all(notesIndex.funnels.map(async (fname) => {
            const r = await fetch(`./notes/${fname}`);
            if (!r.ok) return [];
            const data = await r.json();
            return data.posts || [];
          }));
          allNoteFunnelPosts = funnelDataArr.flat();
        }
      }
    } catch (_) {}

    renderSeriesButtons();
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
  const seen = new Set();
  weeks.forEach(week => {
    if (seen.has(week)) return;
    seen.add(week);
    const hasRegular = allPosts.some(p => p.weekId === week && !EXCLUDED.includes(p.platform) && !p.reply1);
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

function renderSeriesButtons() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  const stampPosts = allPosts.filter(p => p.platform === 'LINEスタンプ' && p.series);
  const uniqueSeries = [...new Set(stampPosts.map(p => p.series))].sort();

  uniqueSeries.forEach(series => {
    const stampBtn = document.createElement('button');
    stampBtn.className = 'filter-btn';
    stampBtn.dataset.platform = 'LINEスタンプ';
    stampBtn.dataset.series = series;
    stampBtn.textContent = series;
    row.appendChild(stampBtn);

    const promptBtn = document.createElement('button');
    promptBtn.className = 'filter-btn';
    promptBtn.dataset.platform = 'LINEスタンププロンプト';
    promptBtn.dataset.series = series;
    promptBtn.textContent = `${series}（プロンプト）`;
    row.appendChild(promptBtn);
  });
}

function getFilteredPosts() {
  const mode = activeFilters.platform;
  const EXCLUDED = ['LINEスタンプ', 'Threads宣伝', 'X診断'];

  if (mode === 'note') return [];

  return allPosts.filter(p => {
    const isStamp = p.platform === 'LINEスタンプ';

    if (mode === 'LINEスタンプ') return isStamp && (activeFilters.series === 'all' || p.series === activeFilters.series);
    if (mode === 'LINEスタンププロンプト') return isStamp && (activeFilters.series === 'all' || p.series === activeFilters.series);
    if (mode === 'Threads診断') {
      if (!(p.platform === 'Threads' && p.reply1)) return false;
      if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
      return true;
    }
    if (mode === 'X診断') {
      if (p.platform !== 'X診断') return false;
      if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
      return true;
    }

    if (EXCLUDED.includes(p.platform)) return false;
    if (p.reply1) return false;
    if (mode !== 'all' && p.platform !== mode) return false;
    if (activeFilters.week !== 'all' && p.weekId !== activeFilters.week) return false;
    return true;
  });
}

function renderPosts() {
  const container = document.getElementById('postsContainer');
  const mode = activeFilters.platform;

  if (mode === 'note') {
    renderNotes();
    return;
  }

  const filtered = getFilteredPosts();
  const stampMode = mode === 'LINEスタンプ';
  const promptMode = mode === 'LINEスタンププロンプト';
  const shindanMode = mode === 'Threads診断';
  const xshindanMode = mode === 'X診断';
  const EXCLUDED = ['LINEスタンプ', 'Threads宣伝', 'X診断'];
  const regularTotal = allPosts.filter(p => !EXCLUDED.includes(p.platform) && !p.reply1).length;

  document.getElementById('statsBar').textContent = promptMode
    ? `DALL-E 3 プロンプト ${filtered.length}個`
    : stampMode
    ? `LINEスタンプ ${filtered.length}個`
    : shindanMode
    ? `Threads診断 ${filtered.length}投稿`
    : xshindanMode
    ? `X診断 ${filtered.length}投稿`
    : `${filtered.length}件 / 全${regularTotal}件`;

  const weekRow = document.getElementById('weekFilterRow');
  if (weekRow) weekRow.style.display = (stampMode || promptMode) ? 'none' : '';

  if (filtered.length === 0) {
    container.innerHTML = '<p class="empty-state">該当する投稿がありません</p>';
    return;
  }

  let seriesHeader = '';
  if (stampMode || promptMode) {
    const titleText = activeFilters.series !== 'all' ? activeFilters.series : 'きょうも、そのままで';
    seriesHeader = `<div class="stamp-series-header">
      <p class="stamp-series-title">${escapeHtml(titleText)}</p>
      <p class="stamp-series-desc">日常のあの気持ちを、もっとやさしく届けるために。言いたいけどちょっと照れる言葉を、Cocoが代わりに届けます。関係の温度と距離を整えるスタンプシリーズ。</p>
    </div>`;
  }

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

function renderNotes() {
  const container = document.getElementById('postsContainer');
  const weekRow = document.getElementById('weekFilterRow');
  if (weekRow) weekRow.style.display = 'none';

  const totalNotes = allNotes.length;
  document.getElementById('statsBar').textContent = `note記事 ${totalNotes}件`;

  if (totalNotes === 0) {
    container.innerHTML = '<p class="empty-state">note記事がありません</p>';
    return;
  }

  const cards = allNotes.map(renderNoteCard).join('');
  container.innerHTML = `<div class="notes-grid">${cards}</div>`;
}

function renderNoteCard(note) {
  const title = escapeHtml(note.title || '');
  const desc = escapeHtml(note.description || '');
  const date = note.date || '';
  const price = note.price ? `¥${note.price}` : '無料';
  const tags = (note.hashtags || []).map(t => `<span class="note-tag">${escapeHtml(t)}</span>`).join('');
  const url = `./notes/${note.filename || note.note_id + '.html'}`;

  return `
    <article class="note-card">
      <div class="note-card-header">
        <span class="platform-badge platform-note">note</span>
        <span class="note-price-badge">${price}</span>
      </div>
      <div class="note-card-body">
        <a href="${url}" class="note-card-title" target="_blank">${title}</a>
        <p class="note-card-desc">${desc}</p>
      </div>
      <div class="note-card-tags">${tags}</div>
      <div class="note-card-footer">
        <span class="note-card-date">${date}</span>
        <a href="${url}" class="note-card-link" target="_blank">詳細を見る →</a>
      </div>
    </article>`;
}

function renderExpandable(label, text, copyLabel, isOpen) {
  const escaped = escapeHtml(text);
  const openAttr = isOpen ? ' open' : '';
  return `
    <details class="card-expandable"${openAttr}>
      <summary class="expandable-summary">${label}</summary>
      <div class="expandable-body">
        <p class="expandable-text">${escaped}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${escapeHtml(text)}">${copyLabel}</button>
        </div>
      </div>
    </details>`;
}

function renderCard(post) {
  if (activeFilters.platform === 'LINEスタンププロンプト') return renderPromptCard(post);
  if (post.platform === 'LINEスタンプ') return renderStampCard(post);
  if (post.platform === 'X診断') return renderXshindanCard(post);

  const isShindan = activeFilters.platform === 'Threads診断';
  const platformClass = post.platform === 'X' ? 'platform-x' : 'platform-threads';
  const contentEscaped = escapeHtml(post.content);
  const quoteEscaped = escapeHtml(post.quote);
  const cardClass = isShindan ? 'card card-shindan' : 'card';

  const themeHtml = post.theme
    ? `<span class="theme-badge">${escapeHtml(post.theme)}</span>`
    : '';

  const extrasHtml = isShindan ? [
    post.reply1 ? renderExpandable('返信① 回答・解説', post.reply1, 'コピー', true) : '',
    post.reply2 ? renderExpandable('返信② note動線', post.reply2, 'コピー', true) : '',
    post.image_prompt ? renderExpandable('🎨 画像プロンプト（DALL-E 3）', post.image_prompt, 'コピー', true) : '',
  ].join('') : '';

  return `
    <article class="${cardClass}" data-platform="${post.platform}">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge ${platformClass}">${post.platform}</span>
          <span class="card-time">${post.time || ''}</span>
          <span class="card-character">${post.character}</span>
          ${themeHtml}
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
      ${extrasHtml}
    </article>`;
}

function renderXshindanCard(post) {
  const e = escapeHtml;
  return `
    <article class="card card-shindan" data-platform="X診断">
      <div class="card-header">
        <div class="card-meta-left">
          <span class="platform-badge platform-xshindan">X診断</span>
          <span class="card-time">${post.time || ''}</span>
          <span class="card-character">${post.character}</span>
          ${post.theme ? `<span class="card-theme-label">${e(post.theme)}</span>` : ''}
        </div>
        <span class="purpose-badge">${post.purpose}</span>
      </div>
      <div class="card-body">
        <p class="card-content">${e(post.content)}</p>
        <div class="copy-btn-content">
          <button class="copy-btn" data-copy="${e(post.content)}">コピー</button>
        </div>
      </div>
      <div class="card-quote">
        <p class="quote-text">${e(post.quote)}</p>
        <button class="copy-btn" data-copy="${e(post.quote)}">コピー</button>
      </div>
      ${post.image_prompt ? renderExpandable('🎨 画像プロンプト（DALL-E 3）', post.image_prompt, 'コピー', false) : ''}
      ${post.comment1 ? renderExpandable('💬 コメント① 回答・解説', post.comment1, 'コピー', false) : ''}
      ${post.comment2 ? renderExpandable('📌 コメント② 深掘り・保存補足', post.comment2, 'コピー', false) : ''}
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
      b.classList.remove('active', 'active-x', 'active-threads', 'active-stamp', 'active-prompt', 'active-shindan', 'active-note');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;
    activeFilters.series = btn.dataset.series || 'all';

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else if (platform === 'Threads診断') btn.classList.add('active-shindan');
    else if (platform === 'X診断') btn.classList.add('active-xshindan');
    else if (platform === 'LINEスタンプ') btn.classList.add('active-stamp');
    else if (platform === 'LINEスタンププロンプト') btn.classList.add('active-prompt');
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
