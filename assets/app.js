'use strict';

let allPosts = [];
let allStamps = null;
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

function escapeAttr(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function loadPosts() {
  const container = document.getElementById('postsContainer');
  container.innerHTML = '<p class="loading">読み込み中…</p>';

  try {
    const indexRes = await fetch('./posts/index.json');
    if (!indexRes.ok) throw new Error('index not found');
    const index = await indexRes.json();

    const [weekDataArr, stampsArr] = await Promise.all([
      Promise.all(
        (index.weeks || []).map(async (filename) => {
          const res = await fetch(`./posts/${filename}`);
          if (!res.ok) throw new Error(`${filename} not found`);
          return res.json();
        })
      ),
      Promise.all(
        (index.stamps || []).map(async (filename) => {
          const res = await fetch(`./posts/${filename}`);
          if (!res.ok) throw new Error(`${filename} not found`);
          return res.json();
        })
      )
    ]);

    allPosts = weekDataArr
      .flatMap(w => w.posts.map(p => ({ ...p, weekId: w.week })))
      .sort((a, b) => {
        const tA = new Date(`${a.date}T${a.time}:00`);
        const tB = new Date(`${b.date}T${b.time}:00`);
        return tA - tB;
      });

    allStamps = stampsArr.length > 0 ? stampsArr : null;

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

function renderPosts() {
  const postsContainer = document.getElementById('postsContainer');
  const stampSection = document.getElementById('stampSection');
  const weekRow = document.getElementById('weekFilterRow');

  if (activeFilters.platform === 'LINEスタンプ') {
    postsContainer.style.display = 'none';
    stampSection.style.display = 'block';
    if (weekRow) weekRow.style.display = 'none';
    renderStamps();
    document.getElementById('statsBar').textContent =
      allStamps ? `LINEスタンプ ${allStamps.length}シリーズ / 計${allStamps.reduce((s, d) => s + d.stamps.length, 0)}枚` : 'スタンプなし';
    return;
  }

  postsContainer.style.display = '';
  stampSection.style.display = 'none';
  if (weekRow) weekRow.style.display = '';

  const filtered = getFilteredPosts();

  document.getElementById('statsBar').textContent =
    `${filtered.length}件 / 全${allPosts.length}件`;

  if (filtered.length === 0) {
    postsContainer.innerHTML = '<p class="empty-state">該当する投稿がありません</p>';
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

  postsContainer.innerHTML = html;
}

function renderCard(post) {
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
          <button class="copy-btn" data-copy="${escapeAttr(post.content)}">コピー</button>
        </div>
      </div>
      <div class="card-quote">
        <p class="quote-text">${quoteEscaped}</p>
        <button class="copy-btn" data-copy="${escapeAttr(post.quote)}">コピー</button>
      </div>
    </article>`;
}

function renderStamps() {
  const inner = document.getElementById('stampSectionInner');
  if (!allStamps || allStamps.length === 0) {
    inner.innerHTML = '<p class="empty-state">スタンプデータがありません</p>';
    return;
  }

  const html = allStamps.map(data => renderStampSet(data)).join('');
  inner.innerHTML = html;
}

function renderStampSet(data) {
  const st = data.sales_text;
  const charMap = { 'Coco': '👩', 'しらたま': '🐈‍⬛', 'しずく': '🐢', 'ひより': '🕊' };

  const salesHtml = `
    <div class="stamp-sales-block">
      <div class="stamp-series-badge">
        LINEスタンプ ${data.created} 作成分 ／ ${data.series} 第${data.installment}弾
      </div>
      <div class="stamp-theme-tag">📌 週テーマ：${data.week_theme}</div>
      <div class="stamp-sales-grid">
        <div class="stamp-sales-item">
          <div class="stamp-sales-label">タイトル（日本語）</div>
          <div class="stamp-sales-value">${escapeHtml(st.title_ja)}</div>
          <button class="copy-btn" data-copy="${escapeAttr(st.title_ja)}">コピー</button>
        </div>
        <div class="stamp-sales-item">
          <div class="stamp-sales-label">説明文（日本語）<span class="char-count">${st.description_ja.length}文字</span></div>
          <div class="stamp-sales-value">${escapeHtml(st.description_ja)}</div>
          <button class="copy-btn" data-copy="${escapeAttr(st.description_ja)}">コピー</button>
        </div>
        <div class="stamp-sales-item">
          <div class="stamp-sales-label">Title (English)</div>
          <div class="stamp-sales-value">${escapeHtml(st.title_en)}</div>
          <button class="copy-btn" data-copy="${escapeAttr(st.title_en)}">コピー</button>
        </div>
        <div class="stamp-sales-item">
          <div class="stamp-sales-label">Description (English)</div>
          <div class="stamp-sales-value">${escapeHtml(st.description_en)}</div>
          <button class="copy-btn" data-copy="${escapeAttr(st.description_en)}">コピー</button>
        </div>
      </div>
    </div>`;

  const stampsHtml = data.stamps.map(s => renderStampCard(s)).join('');

  return `
    <div class="stamp-set">
      ${salesHtml}
      <h2 class="stamp-list-heading">スタンプ一覧（${data.stamps.length}枚 / 需要順）</h2>
      <div class="stamp-cards-grid">
        ${stampsHtml}
      </div>
    </div>`;
}

function renderStampCard(stamp) {
  const isCoco = stamp.characters.includes('Coco');
  const cocoTypeHtml = isCoco
    ? `<span class="coco-type-badge ${stamp.coco_type === 'クールビューティー' ? 'coco-cool' : 'coco-fem'}">${stamp.coco_type}</span>`
    : '';

  const sceneHtml = `
    <div class="stamp-scene">
      <span class="scene-tag">⏱ ${stamp.scene_timing}</span>
      <span class="scene-tag">📍 ${stamp.scene_context}</span>
      <span class="scene-tag">💭 ${stamp.scene_psychology}</span>
    </div>`;

  const outfitHtml = stamp.outfit
    ? `<div class="stamp-outfit"><span class="outfit-label">衣装</span>${escapeHtml(stamp.outfit)}</div>`
    : '';

  const analysisHtml = stamp.analysis
    ? `<div class="stamp-analysis"><span class="analysis-label">分析反映</span>${escapeHtml(stamp.analysis)}</div>`
    : '';

  const promptStyleCopy = escapeAttr(stamp.prompt_style);
  const promptCharCopy = escapeAttr(stamp.prompt_character);
  const promptTextCopy = escapeAttr(stamp.prompt_text_size);

  return `
    <article class="stamp-card">
      <div class="stamp-card-header">
        <div class="stamp-number-badge">${stamp.number}</div>
        <div class="stamp-card-title-area">
          <div class="stamp-text-line">
            <span class="stamp-text-value">${escapeHtml(stamp.text)}</span>
            <button class="copy-btn stamp-text-copy" data-copy="${escapeAttr(stamp.text)}">コピー</button>
          </div>
          <div class="stamp-chars-line">
            <span class="stamp-chars">${escapeHtml(stamp.characters)}</span>
            ${cocoTypeHtml}
          </div>
        </div>
      </div>

      ${sceneHtml}
      ${outfitHtml}
      ${analysisHtml}

      <div class="stamp-prompts">
        <div class="prompt-block">
          <div class="prompt-block-label">① スタイル指定</div>
          <p class="prompt-block-text">${escapeHtml(stamp.prompt_style)}</p>
          <button class="copy-btn" data-copy="${promptStyleCopy}">コピー</button>
        </div>
        <div class="prompt-block">
          <div class="prompt-block-label">② キャラクター・表情指定</div>
          <p class="prompt-block-text">${escapeHtml(stamp.prompt_character)}</p>
          <button class="copy-btn" data-copy="${promptCharCopy}">コピー</button>
        </div>
        <div class="prompt-block">
          <div class="prompt-block-label">③ テキスト・サイズ指定</div>
          <p class="prompt-block-text">${escapeHtml(stamp.prompt_text_size)}</p>
          <button class="copy-btn" data-copy="${promptTextCopy}">コピー</button>
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
      b.classList.remove('active', 'active-x', 'active-threads', 'active-stamp');
    });

    const platform = btn.dataset.platform;
    activeFilters.platform = platform;

    if (platform === 'X') btn.classList.add('active-x');
    else if (platform === 'Threads') btn.classList.add('active-threads');
    else if (platform === 'LINEスタンプ') btn.classList.add('active-stamp');
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
