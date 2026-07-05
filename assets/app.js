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

  const knownPlatforms = new Set(['all', 'X', 'Threads']);
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
  const c1 = post.comment_1 || post.comment1;
  if (c1) {
    const c1Escaped = escapeHtml(c1);
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">📝 コメント①</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${c1Escaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${c1Escaped}">コピー</button>
          </div>
        </div>
      </div>`;
  }
  if (post.comment_2) {
    const c2Escaped = escapeHtml(post.comment_2);
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">💬 コメント②</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${c2Escaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${c2Escaped}">コピー</button>
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
  if (post.choices && post.choices.length) {
    const labels = ['A', 'B', 'C', 'D'];
    const choicesHtml = post.choices.map((choice, i) => {
      const escaped = escapeHtml(choice);
      return `<div class="choice-item">
          <span class="choice-label">${labels[i]}</span>
          <span class="choice-text">${escaped}</span>
          <button class="copy-btn" data-copy="${escaped}">コピー</button>
        </div>`;
    }).join('');
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">🔤 4択</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <div class="choices-list">${choicesHtml}</div>
        </div>
      </div>`;
  }
  if (post.image_prompts && post.image_prompts.length) {
    const labels = ['A', 'B', 'C', 'D'];
    const promptsHtml = post.image_prompts.map((prompt, i) => {
      const escaped = escapeHtml(prompt);
      return `<div class="prompt-item">
          <span class="prompt-label">選択肢 ${labels[i]}</span>
          <p>${escaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${escaped}">コピー</button>
          </div>
        </div>`;
    }).join('');
    extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">🖼 画像プロンプト（4択）</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <div class="prompts-list">${promptsHtml}</div>
        </div>
      </div>`;
  } else if (post.image_prompt) {
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

function setupPlatformFilter() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-platform]');
    if (!btn) return;

    row.querySelectorAll('.filter-btn').forEach(b => {
      b.classList.remove('active', 'active-x', 'active-threads', 'active-xdiag');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else if (platform.startsWith('X診断')) btn.classList.add('active-xdiag');
    else if (platform.startsWith('Threads診断')) btn.classList.add('active-threadsdiag');
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
      // fallback for older browsers
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

// ─── Note section ────────────────────────────────────────────────────────────

let allNotes = [];
let activeNoteFilters = { tier: 'all', week: 'all' };
let notesLoaded = false;

async function loadNotes() {
  const container = document.getElementById('notesContainer');
  container.innerHTML = '<p class="loading">読み込み中…</p>';

  try {
    const indexRes = await fetch('./notes/index.json');
    if (!indexRes.ok) throw new Error('notes/index.json not found');
    const index = await indexRes.json();

    allNotes = await Promise.all(
      index.notes.map(async (filename) => {
        const res = await fetch(`./notes/${filename}`);
        if (!res.ok) throw new Error(`${filename} not found`);
        return res.json();
      })
    );

    allNotes.sort((a, b) => new Date(b.date) - new Date(a.date));
    notesLoaded = true;

    renderNoteWeekFilter();
    renderNotes();
  } catch (err) {
    container.innerHTML = `<p class="error-state">データの読み込みに失敗しました<br><small>${err.message}</small></p>`;
  }
}

function renderNoteWeekFilter() {
  const weekRow = document.getElementById('noteWeekFilterRow');
  if (!weekRow) return;

  weekRow.querySelectorAll('.filter-btn').forEach(b => b.remove());

  const allBtn = document.createElement('button');
  allBtn.className = 'filter-btn active';
  allBtn.dataset.noteWeek = 'all';
  allBtn.textContent = '全週';
  weekRow.appendChild(allBtn);

  const weeks = [...new Set(allNotes.map(n => n.source_week))].sort().reverse();
  weeks.forEach(week => {
    const [from, to] = week.split('_');
    const label = `${from.slice(5).replace('-', '/')}〜${to.slice(5).replace('-', '/')}`;
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.noteWeek = week;
    btn.textContent = label;
    weekRow.appendChild(btn);
  });

  weekRow.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-note-week]');
    if (!btn) return;
    weekRow.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeNoteFilters.week = btn.dataset.noteWeek;
    renderNotes();
  });
}

function setupNoteTierFilter() {
  const tierRow = document.getElementById('noteTierFilterRow');
  if (!tierRow) return;
  tierRow.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-tier]');
    if (!btn) return;
    tierRow.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeNoteFilters.tier = btn.dataset.tier;
    renderNotes();
  });
}

function renderNotes() {
  const container = document.getElementById('notesContainer');
  const filtered = allNotes.filter(n => {
    if (activeNoteFilters.tier !== 'all' && n.tier !== activeNoteFilters.tier) return false;
    if (activeNoteFilters.week !== 'all' && n.source_week !== activeNoteFilters.week) return false;
    return true;
  });

  document.getElementById('noteStatsBar').textContent = `${filtered.length}本 / 全${allNotes.length}本`;

  if (filtered.length === 0) {
    container.innerHTML = '<p class="empty-state">該当するnoteがありません</p>';
    return;
  }

  container.innerHTML = filtered.map(renderNoteCard).join('');
}

function renderNoteCard(note) {
  const tierClass = note.tier === 'flagship' ? 'tier-flagship' : 'tier-member';
  const tierLabel = note.tier === 'flagship' ? 'Flagship' : 'メンバー限定';
  const visLabel = note.visibility === 'single_paid' ? `単発 ¥${note.price}`
    : note.visibility === 'members_only' ? 'メンバー限定'
    : '無料';
  const visClass = note.visibility === 'single_paid' ? 'vis-paid'
    : note.visibility === 'members_only' ? 'vis-member'
    : 'vis-free';

  const hashtags = (note.hashtags || [])
    .map(h => `<span class="note-tag">${escapeHtml(h)}</span>`).join('');
  const funnelTargets = (note.funnel_targets || [])
    .map(t => `<span class="funnel-tag">${escapeHtml(t)}</span>`).join('');

  const freeRatioBadge = (note.free_ratio && note.tier === 'flagship')
    ? `<span class="free-ratio-badge">無料${Math.round(parseFloat(note.free_ratio) * 100)}%公開</span>`
    : '';

  const outcomeHtml = note.outcome_promise
    ? `<p class="note-outcome">${escapeHtml(note.outcome_promise)}</p>`
    : '';
  const frameworkHtml = note.framework
    ? `<p class="note-meta-line"><span class="meta-label">構造：</span>${escapeHtml(note.framework)}</p>`
    : '';
  const toolHtml = note.practice_tool
    ? `<p class="note-meta-line"><span class="meta-label">実践ツール：</span>${escapeHtml(note.practice_tool)}</p>`
    : '';

  let sections = '';

  if (note.image_prompt) {
    const promptEsc = escapeHtml(note.image_prompt);
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">🖼 画像プロンプト</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${promptEsc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${promptEsc}">コピー</button>
          </div>
        </div>
      </div>`;
  }

  if (note.content_html) {
    const mdEsc = note.content_markdown ? escapeHtml(note.content_markdown) : '';
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">📄 本文</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <div class="note-content">${note.content_html}</div>
          ${mdEsc ? `<div class="copy-btn-content"><button class="copy-btn" data-copy="${mdEsc}">本文をコピー</button></div>` : ''}
        </div>
      </div>`;
  }

  if (note.before_after && note.before_after.length) {
    const casesHtml = note.before_after
      .map(c => typeof c === 'object'
        ? `<div class="before-after-case"><p><strong>Before：</strong>${escapeHtml(c.before)}</p><p><strong>After：</strong>${escapeHtml(c.after)}</p></div>`
        : `<div class="before-after-case"><p>${escapeHtml(String(c))}</p></div>`)
      .join('');
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">✨ Before / After 事例</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">${casesHtml}</div>
      </div>`;
  }

  if (note.sns_hooks) {
    let hooksHtml = '';
    if (note.sns_hooks.Threads) {
      const esc = escapeHtml(note.sns_hooks.Threads);
      hooksHtml += `
        <div class="hook-item">
          <span class="hook-platform platform-badge platform-threadsdiag">Threads</span>
          <p>${esc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${esc}">コピー</button>
          </div>
        </div>`;
    }
    if (note.sns_hooks.X) {
      const esc = escapeHtml(note.sns_hooks.X);
      hooksHtml += `
        <div class="hook-item">
          <span class="hook-platform platform-badge platform-x">X</span>
          <p>${esc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${esc}">コピー</button>
          </div>
        </div>`;
    }
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">📣 SNS導線文</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">${hooksHtml}</div>
      </div>`;
  }

  if (note.cta_text) {
    const ctaEsc = escapeHtml(note.cta_text);
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">✅ CTA</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${ctaEsc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${ctaEsc}">コピー</button>
          </div>
        </div>
      </div>`;
  }

  if (note.micro_adjustment_points && note.micro_adjustment_points.length) {
    const points = note.micro_adjustment_points
      .map(p => `<li>${escapeHtml(p)}</li>`).join('');
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">✏️ 補強ポイント</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <ul class="adjustment-list">${points}</ul>
        </div>
      </div>`;
  }

  const noteClass = note.tier === 'flagship' ? 'note-card note-flagship' : 'note-card';

  return `
    <article class="${noteClass}">
      <div class="note-card-header">
        <div class="note-meta-left">
          <span class="tier-badge ${tierClass}">${tierLabel}</span>
          <span class="vis-badge ${visClass}">${visLabel}</span>
          ${freeRatioBadge}
          ${funnelTargets}
        </div>
        <span class="note-date">${formatDate(note.date)}</span>
      </div>
      <div class="note-card-body">
        <h2 class="note-title">${escapeHtml(note.title)}</h2>
        <p class="note-description">${escapeHtml(note.description)}</p>
        ${outcomeHtml}
        ${frameworkHtml}
        ${toolHtml}
        ${hashtags ? `<div class="note-tags">${hashtags}</div>` : ''}
      </div>
      ${sections}
    </article>`;
}

// ─── Tab switching ────────────────────────────────────────────────────────────

function setupTabs() {
  const tabNav = document.querySelector('.tab-nav');
  if (!tabNav) return;

  tabNav.addEventListener('click', e => {
    const btn = e.target.closest('.tab-btn[data-tab]');
    if (!btn) return;

    tabNav.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const tab = btn.dataset.tab;
    document.getElementById('postsSection').hidden = tab !== 'posts';
    document.getElementById('notesSection').hidden = tab !== 'notes';

    if (tab === 'notes' && !notesLoaded) {
      loadNotes();
    }
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  setupPlatformFilter();
  setupSectionToggle();
  setupCopyHandler();
  setupTabs();
  setupNoteTierFilter();
  loadPosts();
});
