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
    const bust = `?t=${Date.now()}`;
    const indexRes = await fetch(`./posts/index.json${bust}`);
    if (!indexRes.ok) throw new Error('index not found');
    const index = await indexRes.json();

    const weekDataArr = await Promise.all(
      index.weeks.map(async (filename) => {
        const res = await fetch(`./posts/${filename}${bust}`);
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
    renderLineStampButtons();
    renderStampPromoButtons();
    renderPosts();

    if (index.linestamps && index.linestamps.length > 0) {
      const stampSets = await Promise.all(
        index.linestamps.map(async (filename) => {
          const res = await fetch(`./posts/${filename}${bust}`);
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
    const weekId = set.week || '';
    const setEl = document.createElement('div');
    setEl.className = 'stamp-set';
    setEl.dataset.week = weekId;

    const seriesName = set.series || `LINEスタンプ ${set.week}`;
    const e = escapeHtml;

    let html = `
      <h3 class="stamp-set-heading">
        ${e(seriesName)}
        <span class="pattern-badge">パターン${set.pattern}：${e(set.pattern_description)}</span>
      </h3>`;

    if (set.trend_analysis) {
      html += `
      <details class="stamp-section-detail">
        <summary class="stamp-section-summary">📈 1ヶ月後トレンド分析</summary>
        <div class="stamp-section-body">${e(set.trend_analysis).replace(/\n/g, '<br>')}</div>
      </details>`;
    }

    if (set.title_ja || set.desc_ja || set.title_en || set.desc_en) {
      html += `<div class="stamp-sales-block"><h4 class="stamp-subsection-heading">💬 販売テキスト</h4>`;
      if (set.title_ja) html += `
        <div class="sales-row">
          <span class="sales-label">タイトル（日本語）</span>
          <p class="sales-value">${e(set.title_ja)}</p>
          <button class="copy-btn" data-copy="${e(set.title_ja)}">コピー</button>
        </div>`;
      if (set.desc_ja) html += `
        <div class="sales-row">
          <span class="sales-label">説明文（日本語）</span>
          <p class="sales-value">${e(set.desc_ja)}</p>
          <button class="copy-btn" data-copy="${e(set.desc_ja)}">コピー</button>
        </div>`;
      if (set.title_en) html += `
        <div class="sales-row">
          <span class="sales-label">Title (English)</span>
          <p class="sales-value">${e(set.title_en)}</p>
          <button class="copy-btn" data-copy="${e(set.title_en)}">コピー</button>
        </div>`;
      if (set.desc_en) html += `
        <div class="sales-row">
          <span class="sales-label">Description (English)</span>
          <p class="sales-value">${e(set.desc_en)}</p>
          <button class="copy-btn" data-copy="${e(set.desc_en)}">コピー</button>
        </div>`;
      html += `</div>`;
    }

    html += `<h4 class="stamp-subsection-heading">🖼 スタンプ一覧（全${set.stamps.length}個）</h4>
      <div class="stamp-grid">${set.stamps.map(renderStampCard).join('')}</div>`;

    if (set.threads_promo && set.threads_promo.length > 0) {
      html += `<h4 class="promo-heading">📣 Threads宣伝文（${set.threads_promo.length}パターン）</h4>
        <div class="promo-grid">${set.threads_promo.map(p => `
          <div class="promo-card">
            <span class="promo-date">${e(p.date)} ${e(p.time)}</span>
            <p class="promo-text">${e(p.content)}</p>
            <button class="copy-btn" data-copy="${e(p.content)}">コピー</button>
          </div>`).join('')}
        </div>`;
    }

    setEl.innerHTML = html;
    section.appendChild(setEl);
  });

  const postsContainer = document.getElementById('postsContainer');
  postsContainer.parentNode.insertBefore(section, postsContainer.nextSibling);
}

function renderStampCard(stamp) {
  const charLabel = Array.isArray(stamp.character)
    ? stamp.character.map(c => {
        if (c === 'しらたま') return '🐈‍⬛しらたま';
        if (c === 'しずく') return '🐢しずく';
        if (c === 'ひより') return '🕊ひより';
        if (c === 'Coco') return '💎Coco';
        return c;
      }).join(' + ')
    : (stamp.character || '');

  const typeClass = stamp.with_coco ? 'type-coco' : 'type-char';
  const e = escapeHtml;

  const idLabel = stamp.id != null ? stamp.id : (stamp.purpose || '');
  const typeLabel = stamp.type || (stamp.with_coco ? 'Coco参加' : 'キャラのみ');
  const dialogue = stamp.dialogue || '';
  const scene = stamp.scene || '';
  const imagePrompt = stamp.image_prompt || '';
  const colorScheme = stamp.color_scheme || '';

  return `
    <div class="stamp-card">
      <div class="stamp-card-header">
        <span class="stamp-num">#${e(String(idLabel))}</span>
        <span class="stamp-type-badge ${typeClass}">${e(typeLabel)}</span>
      </div>
      <div class="stamp-characters">${e(charLabel)}</div>
      ${dialogue ? `<div class="stamp-dialogue">${e(dialogue)}</div>` : ''}
      ${scene ? `<div class="stamp-scene">📍 ${e(scene)}</div>` : ''}
      ${stamp.send_timing ? `<div class="stamp-timing">⏰ ${e(stamp.send_timing)}</div>` : ''}
      ${stamp.send_psychology ? `<div class="stamp-psychology">💭 ${e(stamp.send_psychology)}</div>` : ''}
      <details class="stamp-details">
        <summary>コーデ・プロンプトを見る</summary>
        ${stamp.outfit ? `<div class="stamp-outfit">👗 ${e(stamp.outfit)}</div>` : ''}
        ${colorScheme ? `<div class="stamp-color">🎨 ${e(colorScheme)}</div>` : ''}
        ${imagePrompt ? `<div class="stamp-prompt-wrap">
          <pre class="stamp-prompt">${e(imagePrompt)}</pre>
          <button class="copy-btn" data-copy="${e(imagePrompt)}">プロンプトをコピー</button>
        </div>` : ''}
        ${stamp.content ? `<div class="stamp-prompt-wrap">
          <pre class="stamp-prompt">${e(stamp.content)}</pre>
          <button class="copy-btn" data-copy="${e(stamp.content)}">コンテンツをコピー</button>
        </div>` : ''}
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

function renderLineStampButtons() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  const lineStampPosts = allPosts.filter(p => p.platform === 'LINEスタンプ');
  if (lineStampPosts.length === 0) return;

  const dates = [...new Set(lineStampPosts.map(p => p.date))].sort().reverse();
  const staticLineBtn = row.querySelector('[data-platform="LINEスタンプ"]:not([data-week])');

  dates.forEach(date => {
    const startM = parseInt(date.slice(5, 7));
    const startD = date.slice(8);
    const weekId = lineStampPosts.find(p => p.date === date)?.weekId;

    const promoInWeek = allPosts.filter(p => p.platform === 'スタンプ宣伝' && p.weekId === weekId);
    const promoEndDate = promoInWeek.length > 0
      ? promoInWeek.map(p => p.date).sort().pop()
      : date;
    const endD = promoEndDate.slice(8);

    const label = endD !== startD
      ? `LINEスタンプ ${startM}/${startD}〜${endD}`
      : `LINEスタンプ ${startM}/${startD}`;

    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.platform = 'LINEスタンプ';
    if (weekId) btn.dataset.week = weekId;
    btn.textContent = label;

    if (staticLineBtn) {
      row.insertBefore(btn, staticLineBtn);
    } else {
      row.appendChild(btn);
    }
  });
}

function renderStampPromoButtons() {
  const row = document.getElementById('platformFilterRow');
  if (!row) return;

  const promoPosts = allPosts.filter(p => p.platform === 'スタンプ宣伝');
  if (promoPosts.length === 0) return;

  const byWeek = {};
  promoPosts.forEach(p => {
    const w = p.weekId || 'unknown';
    if (!byWeek[w]) byWeek[w] = [];
    byWeek[w].push(p);
  });

  const staticLineBtn = row.querySelector('[data-platform="LINEスタンプ"]:not([data-week])');

  Object.keys(byWeek).sort().reverse().forEach(weekId => {
    const dates = byWeek[weekId].map(p => p.date).sort();
    const fromDate = dates[0];
    const toDate = dates[dates.length - 1];
    const fromM = parseInt(fromDate.slice(5, 7));
    const fromD = fromDate.slice(8);
    const toD = toDate.slice(8);
    const label = `スタンプ宣伝 ${fromM}/${fromD}〜${toD}`;

    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.platform = 'スタンプ宣伝';
    btn.dataset.week = weekId;
    btn.textContent = label;

    if (staticLineBtn) {
      row.insertBefore(btn, staticLineBtn);
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
    if (activeFilters.platform === 'all' && p.platform === 'LINEスタンプ') return false;
    if (activeFilters.platform === 'all' && p.platform === 'スタンプ宣伝') return false;
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
                        post.platform === 'Threads' ? 'platform-threads' :
                        post.platform === 'スタンプ宣伝' ? 'platform-stamp-promo' : 'platform-line';
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
      b.classList.remove('active', 'active-x', 'active-threads', 'active-stamp', 'active-xshindan', 'active-threads-shindan', 'active-stamp-promo', 'active-line');
    });

    const platform = btn.dataset.platform;
    const weekId = btn.dataset.week || null;
    activeFilters.platform = platform;
    activeFilters.week = weekId || 'all';

    const stampSection = document.getElementById('stampSection');
    const postsContainer = document.getElementById('postsContainer');
    const weekFilterRow = document.getElementById('weekFilterRow');
    const statsBar = document.getElementById('statsBar');

    if (platform === 'LINEスタンプ' && !weekId) {
      btn.classList.add('active-stamp');
      if (postsContainer) postsContainer.style.display = 'none';
      if (stampSection) {
        stampSection.querySelectorAll('.stamp-set').forEach(el => { el.style.display = ''; });
        stampSection.style.display = 'block';
      }
      if (weekFilterRow) weekFilterRow.style.display = 'none';
      if (statsBar) statsBar.style.display = 'none';
    } else if (platform === 'LINEスタンプ' && weekId) {
      btn.classList.add('active-line');
      if (postsContainer) postsContainer.style.display = 'none';
      if (stampSection) {
        stampSection.querySelectorAll('.stamp-set').forEach(el => {
          el.style.display = el.dataset.week === weekId ? '' : 'none';
        });
        stampSection.style.display = 'block';
      }
      if (weekFilterRow) weekFilterRow.style.display = 'none';
      if (statsBar) statsBar.style.display = 'none';
    } else if (platform === 'スタンプ宣伝') {
      btn.classList.add('active-stamp-promo');
      if (postsContainer) postsContainer.style.display = '';
      if (stampSection) stampSection.style.display = 'none';
      if (weekFilterRow) weekFilterRow.style.display = 'none';
      if (statsBar) statsBar.style.display = '';
      renderPosts();
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
