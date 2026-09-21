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

// 「本文をコピー」が渡す範囲（2026-09-21 Coco指示）。note.com にそのまま貼れる形にする。
// 並びは description → outcome_promise → 区切り線 → 本文 → hashtags で固定。
// **文はJSONから引くだけで、ここで作らない**（`CLAUDE.md`「正典はひとつ」）。
// 区切り線は `---`＝content_markdown が既に使っている形に合わせている。
// outcome_promise が無い古いnote（2026-06 の3本）は、その行を飛ばす。
function noteCopyText(note) {
  const head = [note.description, note.outcome_promise].filter(Boolean);
  const tags = Array.isArray(note.hashtags) ? note.hashtags.filter(Boolean) : [];
  const blocks = [];
  if (head.length) blocks.push(head.join('\n\n'), '---');
  blocks.push(note.content_markdown);
  if (tags.length) blocks.push(tags.join('\n'));
  return blocks.join('\n\n');
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// 週データは index.json と同じく毎回サーバに聞き直す（下の fetch の cache: 'no-cache'）。
// 2026-09-02：ここには手で上げる札（POST_V）を置いていたが、**上げ忘れが2回続いた**
// （8/31 と 9/1〜9/2）。9/1〜9/2 だけで9/1週の本文を4回差し替えていて、そのたびに
// 「反映された？」の確認が要る状態になっていた。**守られない運用は、運用ではなく設計の問題。**
// 札そのものを外して、思い出さなくても新しい本文が出るようにした。
// no-cache は「毎回取り直す」ではなく「毎回聞き直す」（変わっていなければ 304 で返る）。
// note側（NOTE_V）も 2026-09-03 に同じ形へ寄せた（loadNotes を見て）。
// 札はもう投稿側にもnote側にも無い。新しく足さない。

// X短文（観察とコメント）は、本文とは別の投稿として1枚のカードにする。
// 媒体は X のまま（新しいカテゴリを作らない）。時刻はここが持つが、
// **正典は rules/ops.md「週次スケジュール」**（X短文 06:00／22:00・X本文 08:00／23:00）。
// 食い違ったら正典を採る。JSONの `x_short` が無い回は、本文カードだけが出る。
const X_SHORT_SLOT = { morning: '06:00', evening: '22:00' };

function expandXShort(post) {
  if (post.platform !== 'X' || !post.x_short) return [post];
  const isMorning = Number(post.time.slice(0, 2)) < 12;
  const short = {
    ...post,
    id: `${post.id}_short`,
    time: isMorning ? X_SHORT_SLOT.morning : X_SHORT_SLOT.evening,
    purpose: 'X短文（観察とコメント）',
    content: post.x_short,
    // 短文は二文で終わる枠。ひとこと・返信・画像・note導線は持たない
    // （適用外の正典は rules/posts.md「X短文（観察とコメント）」）
    quote: '',
    self_replies: [],
    image_prompt: '',
    note_funnel: false
  };
  delete short.x_short;
  return [short, post];
}

async function loadPosts() {
  const container = document.getElementById('postsContainer');
  container.innerHTML = '<p class="loading">読み込み中…</p>';

  try {
    // 一覧は必ずサーバに聞き直す（notes/index.json と同じ理由）。
    // ここをキャッシュさせると、新しく足した週が「ファイルはあるのに週フィルタに
    // 出ない」状態になる（2026-08-31：?v= を 20260731c で固定したままだった）
    const indexRes = await fetch('./posts/index.json', { cache: 'no-cache' });
    if (!indexRes.ok) throw new Error('index not found');
    const index = await indexRes.json();

    const weekDataArr = await Promise.all(
      index.weeks.map(async (filename) => {
        const res = await fetch(`./posts/${filename}`, { cache: 'no-cache' });
        if (!res.ok) throw new Error(`${filename} not found`);
        const data = await res.json();
        return { ...data, _sourceFile: filename };
      })
    );

    allPosts = weekDataArr
      .flatMap(w => w.posts.map(p => ({ ...p, weekId: w.week, _sourceFile: w._sourceFile })))
      .flatMap(expandXShort)
      .sort((a, b) => {
        const tA = new Date(`${a.date}T${a.time}:00`);
        const tB = new Date(`${b.date}T${b.time}:00`);
        return tA - tB;
      });

    renderDynamicPlatformFilter();
    renderWeekFilter(weekDataArr.map(w => w.week));
    renderWeekCopyBar();
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

  const feCounts = finalEditorStatusCounts(filtered);
  document.getElementById('statsBar').textContent =
    `${filtered.length}件 / 全${allPosts.length}件 ｜ Final：公開OK ${feCounts.public_ok}・軽微 ${feCounts.minor_fix}・要再編集 ${feCounts.reedit}・編集中 ${feCounts.pending}・再check ${feCounts.pending_check}・未判定 ${feCounts.none}`;

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

  const frameText = post.frame || post.content;
  const contentEscaped = escapeHtml(frameText);
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
  // 35投稿（X14・Threads21）の返信。診断は reply_1、35投稿は self_replies（配列）で持つ。
  // 2026-09-03 まで描画していなかったため、全35本の返信が公開サイトから見えていなかった。
  if (Array.isArray(post.self_replies) && post.self_replies.length) {
    const marks = ['①', '②', '③'];
    post.self_replies.forEach((reply, i) => {
      if (!reply) return;
      const rEscaped = escapeHtml(reply);
      // funnel回のX2本目は note案内（定番プロミス。正典は CLAUDE.md「定番プロミス」）
      const isCta = reply.indexOf('メンバーシップは、毎週深堀りが増えて') !== -1;
      extraSections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">${isCta ? '💍' : '📝'} 返信${marks[i] || (i + 1)}${isCta ? '（note案内）' : ''}</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <p>${rEscaped}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${rEscaped}">コピー</button>
          </div>
        </div>
      </div>`;
    });
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
        <div class="card-meta-right">
          ${finalEditorStatusBadge(post)}
          <span class="purpose-badge">${escapeHtml(post.purpose)}</span>
        </div>
      </div>
      <div class="card-body">
        <p class="card-content">${contentEscaped}</p>
        <div class="copy-btn-content card-actions">
          <button class="copy-btn" data-copy="${escapeHtml(frameText)}">コピー</button>
          <button
            class="final-editor-btn"
            data-final-editor-id="${escapeHtml(post.id || '')}"
            data-final-editor-week="${escapeHtml(post.weekId || '')}"
            data-final-editor-date="${escapeHtml(post.date || '')}"
            data-final-editor-time="${escapeHtml(post.time || '')}"
          >Final Editorで編集</button>
          ${finalEditorStatusSelect(post)}
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

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      // fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      return true;
    } catch {
      return false;
    }
  }
}

function flashCopyState(btn, ok) {
  const original = btn.textContent;
  btn.textContent = ok ? 'コピー完了' : 'コピー失敗';
  btn.classList.toggle('copied', ok);
  setTimeout(() => {
    btn.textContent = original;
    btn.classList.remove('copied');
  }, 1800);
}

function setupCopyHandler() {
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;

    const text = btn.dataset.copy;
    if (!text) return;

    const ok = await copyToClipboard(text);
    flashCopyState(btn, ok);
  });
}

// ─── Coco Final Editor ────────────────────────────────────────────────────────
// 保存先はブラウザの localStorage。GitHub Pages からリポジトリへ直接書き込まない。
// 端末ごとの保存だが、公開サイトに認証トークンを置かずに安全に状態を保持できる。
const FINAL_EDITOR_STORAGE_KEY = 'coco-final-editor-status-v1';
const FINAL_EDITOR_STATUSES = {
  pending: { label: '編集中', cls: 'fe-status-pending' },
  pending_check: { label: '再full_check中', cls: 'fe-status-pending' },
  public_ok: { label: '公開OK', cls: 'fe-status-ok' },
  minor_fix: { label: '軽微修正', cls: 'fe-status-minor' },
  reedit: { label: '要再編集', cls: 'fe-status-reedit' }
};

function finalEditorPostKey(post) {
  return [post.weekId || '', post.id || '', post.date || '', post.time || ''].join('::');
}

function loadFinalEditorStatuses() {
  try {
    const raw = localStorage.getItem(FINAL_EDITOR_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveFinalEditorStatuses(map) {
  try {
    localStorage.setItem(FINAL_EDITOR_STORAGE_KEY, JSON.stringify(map));
    return true;
  } catch {
    return false;
  }
}

function getFinalEditorStatus(post) {
  if (post.final_editor_status) return post.final_editor_status;
  const map = loadFinalEditorStatuses();
  return map[finalEditorPostKey(post)] || '';
}

function setFinalEditorStatus(post, status) {
  const map = loadFinalEditorStatuses();
  const key = finalEditorPostKey(post);
  if (!status) delete map[key];
  else map[key] = status;
  return saveFinalEditorStatuses(map);
}

function finalEditorStatusBadge(post) {
  const status = getFinalEditorStatus(post);
  const meta = FINAL_EDITOR_STATUSES[status];
  if (!meta) return '<span class="final-editor-status fe-status-none">未判定</span>';
  return `<span class="final-editor-status ${meta.cls}">${meta.label}</span>`;
}

function finalEditorStatusSelect(post) {
  const current = getFinalEditorStatus(post);
  const options = [
    ['', '未判定'],
    ['public_ok', '公開OK'],
    ['minor_fix', '軽微修正'],
    ['reedit', '要再編集']
  ].map(([value, label]) =>
    `<option value="${value}"${current === value ? ' selected' : ''}>${label}</option>`
  ).join('');

  return `<label class="final-editor-status-control">
    <span>結果</span>
    <select
      class="final-editor-status-select"
      data-final-editor-status-id="${escapeHtml(post.id || '')}"
      data-final-editor-status-week="${escapeHtml(post.weekId || '')}"
      data-final-editor-status-date="${escapeHtml(post.date || '')}"
      data-final-editor-status-time="${escapeHtml(post.time || '')}"
      aria-label="Final Editorの結果"
    >${options}</select>
  </label>`;
}

function finalEditorStatusCounts(posts) {
  const counts = { public_ok: 0, minor_fix: 0, reedit: 0, pending: 0, pending_check: 0, none: 0 };
  posts.forEach(post => {
    const s = getFinalEditorStatus(post);
    if (Object.prototype.hasOwnProperty.call(counts, s)) counts[s] += 1;
    else counts.none += 1;
  });
  return counts;
}

//
// ここは「ルールを増やす場所」ではなく、生成 + full_check を通った投稿の最終編集層。
// GitHub Pages から外部AI APIを直接呼ばない（APIキーをブラウザに置かない）。
// 投稿ごとに専用プロンプトを作り、ChatGPTへ渡すところまでをサイト側が担当する。

function buildFinalEditorPrompt(post) {
  const body = post.frame || post.content || '';
  const replies = Array.isArray(post.self_replies)
    ? post.self_replies.filter(Boolean)
    : [];
  const extras = [];

  if (post.quote) extras.push(`〈ひとこと〉${post.quote}`);
  replies.forEach((r, i) => extras.push(`【返信${['①', '②', '③'][i] || (i + 1)}】\n${r}`));

  return `あなたは「Coco Final Editor」です。
この投稿は、生成後に full_check を通過したものとして扱ってください。
役割は「新しいルールを作ること」ではなく、この1本を公開できる完成度まで整えることです。

【運用の固定】
- 順番は「生成 → full_check → Final Editor → 再 full_check」。
- 新しい要求はルール化しない。まずこの投稿だけの個別修正として扱う。
- 同じ問題が3回目に再発した場合だけ「恒久ルール候補」とする。1回目は「今回だけ」、2回目は「再発2回目」。
- 既存ルール同士の明確な矛盾は「既存矛盾修正候補」として別枠で指摘してよい。
- 過去投稿への遡及修正は提案しない。
- 編集方針を更新するときは、同じ主題の旧指示を残して新旧併記にしない。新しい方針へ置換し、必要な履歴は旧条文を復唱しない墓標だけにする。
- 実体験・素材にない出来事や結果は作らない。

【Cocoの最終編集基準】
1. 一読で、何を言いたい投稿か分かるか。
2. Coco自身の選択が、読者への「正解の押しつけ」になっていないか。
3. 感情・存在は肯定しつつ、行動や距離の選択権が本人に返っているか。
4. 「相手をどう動かすか」という操作技法ではなく、「自分は何を選ぶか」になっているか。
5. 「うまい」より「ある」。実際に起きたことの手触りがあるか。
6. 冷たさ、説教臭さ、強がり、説明しすぎが出ていないか。
7. 選択肢が2つある投稿は、素材に両側の先があるなら両方を見せる。素材に無ければ捏造しない。
8. ウィット一滴は、意味が成立したあとに置き、説明しない。新しい論点にしない。
9. 最後に残る言葉が、Coco Methodologyの「存在は肯定する。選択は未来から決める。」と矛盾していないか。
10. Xなら折り畳み前に必要な判断・先が届く設計を壊さない。Threadsは余白と自然な温度を優先する。
11. A/Bの作り分けは下の「最終編集の出し方」を正典とし、ここに短文化条件を複製しない。

【最終編集の出し方｜この節がA/Bの唯一の正典】
最終回答では、判定が「公開OK」「軽微修正」「要再編集」のどれでも、AとBの完成全文を必ず両方出す。判定や修正説明だけで終了してはいけない。Coco本人が2案を見て選べる状態まで作ることがFinal Editorの仕事。

A｜いつもの構成
- 元投稿の強い実体験・Coco本人の言葉・温度を核として残し、通常投稿として整える。
- 説明の重複は削るが、実体験の入口と判断軸は安易に抽象語へ置き換えない。
- 原文が事実として成立し、既存ルールにも違反していない表現は、「別表現のほうが思想を説明しやすい」という理由だけで修正しない。代案があることと欠陥があることを分ける。

B｜澄んだ短文
- Aと同じ素材・同じ本質から、格言寄りに尖らせる。「薄くする」のではなく「澄ませる」。
- 実体験の入口が短文の強さになるなら残す。一般化したほうが澄む場合だけ外す。
- 判断軸・選択権・余韻を残し、補足説明、重複、なくても成立する問いかけCTA、ブランド説明は削る。
- 素材にない意味や断定を足さない。

A/B共通
- AとBに優劣・おすすめ・正解をつけない。それぞれ「何が残る案か」だけ一言で示し、最後は「Cocoが選ぶ」で止める。
- 2案が近くても必ず両方表示する。差を作るためだけの言い換えはしない。
- 原文が公開可能で、A/B作成のための整理しかしていない場合、判定は「公開OK」。別案が作れること自体を「軽微修正」の理由にしない。

【本文確定後の連動編集と反映｜この節が唯一の正典】
Cocoが「Aで反映して」「Bで反映して」など本文を選んだら、確認質問を挟まず、その応答内で反映処理まで進める。
- 選択本文を確定版にし、同じ投稿に既存の〈ひとこと〉・返信①以降・CTA・note導線があれば、その本文の判断軸・温度・語彙に合わせて連動編集する。
- 本文ですでに言い切った内容を返信で復唱しない。元から存在しない返信やCTAは新設しない。
- Bを選んだのに返信だけ説明過多な旧構成へ戻さない。素材にない事実・結果は足さない。
- GitHub接続が使える場合は、下記【反映先】の投稿JSONを実際に更新する。本文・既存付随文を反映し、その投稿に final_editor_status: pending_check を保存する。
- pending_check の保存後はGitHub Actionsが既存の full_check を実行し、成功時だけ public_ok に更新する。Final Editor自身がチェック未実行のまま public_ok を書いてはいけない。
- GitHub更新を実行できなかった場合は「反映済み」「公開OK」と言わず、反映できなかったことだけを明示する。

【出力形式】
判定：公開OK／軽微修正／要再編集

一言診断：
（1〜2文）

修正箇所：
（必要な場合だけ。最大2箇所）
- before：
- after：
- 理由：

A｜いつもの構成：
（完成全文）

Aの残るもの：
（一言）

B｜澄んだ短文：
（完成全文）

Bの残るもの：
（一言）

選択：
Cocoが選ぶ

本文確定後：
CocoがA/Bを選んだ次の応答で、確定本文に合わせた〈ひとこと〉・返信・CTA・note導線等の完成版を自動提示する。該当要素が無いものは新設しない。

ルール化判定：
今回だけ／再発2回目／恒久ルール候補／既存矛盾修正候補
※同じ問題が3回目か確認できない場合は「今回だけ」にする。

再チェック：
選択後は投稿JSONへ pending_check として反映する。再 full_check と public_ok への更新はGitHub Actionsに任せる。Actionsが失敗した場合は公開OKにしない。

【対象】
媒体：${post.platform || ''}
投稿ID：${post.id || ''}
週：${post.weekId || ''}
日時：${post.date || ''} ${post.time || ''}

【反映先】
GitHub repository：Coco930118/weekly
branch：main
投稿JSON：posts/${post._sourceFile || ''}
対象投稿ID：${post.id || ''}
※CocoがA/Bを選ぶまではGitHubを書き換えない。選択後だけ上記ファイルの対象投稿を更新する。

【本文】
${body}${extras.length ? `\n\n${extras.join('\n\n')}` : ''}`;
}

function ensureFinalEditorModal() {
  let modal = document.getElementById('finalEditorModal');
  if (modal) return modal;

  modal = document.createElement('div');
  modal.id = 'finalEditorModal';
  modal.className = 'final-editor-modal';
  modal.hidden = true;
  modal.innerHTML = `
    <div class="final-editor-backdrop" data-final-editor-close="1"></div>
    <section class="final-editor-panel" role="dialog" aria-modal="true" aria-labelledby="finalEditorTitle">
      <div class="final-editor-head">
        <div>
          <p class="final-editor-kicker">公開前の最終編集</p>
          <h2 id="finalEditorTitle">Coco Final Editor</h2>
        </div>
        <button class="final-editor-close" type="button" data-final-editor-close="1" aria-label="閉じる">×</button>
      </div>
      <p class="final-editor-flow">生成 → full_check → <strong>Final Editor</strong> → 再 full_check</p>
      <p class="final-editor-note">ルールは増やしません。まず1本だけを整え、3回目の再発だけを恒久ルール候補にします。</p>
      <div class="final-editor-target" id="finalEditorTarget"></div>
      <textarea id="finalEditorPrompt" class="final-editor-prompt" readonly></textarea>
      <div class="final-editor-actions">
        <button type="button" class="final-editor-copy" data-final-editor-copy="1">プロンプトをコピー</button>
        <button type="button" class="final-editor-open" data-final-editor-open="1">コピーしてChatGPTを開く</button>
      </div>
      <p class="final-editor-foot">ChatGPTで完成版が出たら、JSONへ反映する前に full_check をもう一度通します。</p>
    </section>`;
  document.body.appendChild(modal);
  return modal;
}

function findFinalEditorPost(btn) {
  return allPosts.find(p =>
    String(p.id || '') === String(btn.dataset.finalEditorId || '') &&
    String(p.weekId || '') === String(btn.dataset.finalEditorWeek || '') &&
    String(p.date || '') === String(btn.dataset.finalEditorDate || '') &&
    String(p.time || '') === String(btn.dataset.finalEditorTime || '')
  );
}

function openFinalEditor(post) {
  const modal = ensureFinalEditorModal();
  const prompt = buildFinalEditorPrompt(post);
  const target = document.getElementById('finalEditorTarget');
  const textarea = document.getElementById('finalEditorPrompt');

  target.textContent = `${post.platform || ''}｜${post.id || ''}｜${post.date || ''} ${post.time || ''}`;
  textarea.value = prompt;
  modal.hidden = false;
  document.body.classList.add('modal-open');
  setTimeout(() => textarea.focus(), 0);
}

function closeFinalEditor() {
  const modal = document.getElementById('finalEditorModal');
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove('modal-open');
}

async function refreshFinalEditorStatusesFromRepo() {
  try {
    const indexRes = await fetch('./posts/index.json', { cache: 'no-cache' });
    if (!indexRes.ok) return;
    const index = await indexRes.json();
    const weeks = await Promise.all(index.weeks.map(async filename => {
      const res = await fetch('./posts/' + filename, { cache: 'no-cache' });
      if (!res.ok) return null;
      return res.json();
    }));
    const repoStatuses = new Map();
    weeks.filter(Boolean).forEach(w => {
      (w.posts || []).forEach(p => {
        const key = [w.week || '', p.id || '', p.date || '', p.time || ''].join('::');
        repoStatuses.set(key, p.final_editor_status || '');
      });
    });
    let changed = false;
    allPosts.forEach(post => {
      const repoStatus = repoStatuses.get(finalEditorPostKey(post)) || '';
      const launchStatus = post._finalEditorRepoStatusAtLaunch;
      if (launchStatus !== undefined && repoStatus === launchStatus) return;
      if (repoStatus && post.final_editor_status !== repoStatus) {
        post.final_editor_status = repoStatus;
        delete post._finalEditorRepoStatusAtLaunch;
        setFinalEditorStatus(post, '');
        changed = true;
      }
    });
    if (changed) renderPosts();
  } catch {}
}

window.addEventListener('focus', () => {
  refreshFinalEditorStatusesFromRepo();
  setTimeout(refreshFinalEditorStatusesFromRepo, 4000);
});

function setupFinalEditor() {
  document.addEventListener('click', async e => {
    const launchBtn = e.target.closest('.final-editor-btn');
    if (launchBtn) {
      const post = findFinalEditorPost(launchBtn);
      if (!post) return;

      const prompt = buildFinalEditorPrompt(post);
      post._finalEditorRepoStatusAtLaunch = post.final_editor_status || '';
      post.final_editor_status = 'pending';
      setFinalEditorStatus(post, 'pending');
      renderPosts();

      // ChatGPT の新規チャットへ対象投稿と編集指示を渡す。
      // ?q= は新規チャットの入力欄へプロンプトを渡す用途で利用する。
      // クライアント側の挙動で自動送信されない場合でも、内容は入力済みの状態になる。
      const targetUrl = 'https://chatgpt.com/?q=' + encodeURIComponent(prompt);
      const chatWindow = window.open(targetUrl, '_blank', 'noopener');
      if (!chatWindow) {
        const ok = await copyToClipboard(prompt);
        if (ok) alert('ChatGPTを開けなかったため、Final Editorの指示をコピーしました。');
        else alert('ChatGPTを開けませんでした。ポップアップ許可を確認してください。');
      }
      return;
    }

    if (e.target.closest('[data-final-editor-close]')) {
      closeFinalEditor();
      return;
    }

    const copyBtn = e.target.closest('[data-final-editor-copy]');
    if (copyBtn) {
      const text = document.getElementById('finalEditorPrompt')?.value || '';
      const ok = await copyToClipboard(text);
      flashCopyState(copyBtn, ok);
      return;
    }

    const openBtn = e.target.closest('[data-final-editor-open]');
    if (openBtn) {
      const text = document.getElementById('finalEditorPrompt')?.value || '';
      const chatWindow = window.open('https://chatgpt.com/', '_blank', 'noopener');
      const ok = await copyToClipboard(text);
      flashCopyState(openBtn, ok);
      if (!chatWindow) {
        alert('ChatGPTを開けませんでした。ポップアップ許可を確認してください。プロンプトはコピー済みです。');
      }
    }
  });

  document.addEventListener('change', e => {
    const select = e.target.closest('.final-editor-status-select');
    if (!select) return;

    const post = allPosts.find(p =>
      String(p.id || '') === String(select.dataset.finalEditorStatusId || '') &&
      String(p.weekId || '') === String(select.dataset.finalEditorStatusWeek || '') &&
      String(p.date || '') === String(select.dataset.finalEditorStatusDate || '') &&
      String(p.time || '') === String(select.dataset.finalEditorStatusTime || '')
    );
    if (!post) return;

    setFinalEditorStatus(post, select.value);
    renderPosts();
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeFinalEditor();
  });
}

// ─── Week bulk copy (X / Threads / X診断 / Threads診断) ────────────────────────

const WEEK_COPY_CATEGORIES = [
  { platform: 'X', cls: 'wcb-x' },
  { platform: 'Threads', cls: 'wcb-threads' },
  { platform: 'X診断', cls: 'wcb-xshindan' },
  { platform: 'Threads診断', cls: 'wcb-threadsshindan' }
];

// カテゴリ（媒体）ごとに、その媒体の投稿が存在する最新週IDを返す。
// X/Threads と X診断/Threads診断 は別ファイル・別週で管理されるため、
// 単一の「最新週」ではなく媒体ごとに最新週を求める。
function getLatestWeekIdForPlatform(platform) {
  const ids = allPosts.filter(p => p.platform === platform).map(p => p.weekId);
  if (!ids.length) return null;
  return ids.reduce((max, id) => (id > max ? id : max), ids[0]);
}

function formatWeekRangeLabel(weekId) {
  const [from, to] = weekId.split('_');
  return `${from.slice(5).replace('-', '/')}〜${to.slice(5).replace('-', '/')}`;
}

function buildCategoryCopyText(weekId, platform) {
  const posts = allPosts
    .filter(p => p.weekId === weekId && p.platform === platform)
    .sort((a, b) => new Date(`${a.date}T${a.time}:00`) - new Date(`${b.date}T${b.time}:00`));

  const blocks = posts.map(p => {
    const head = `◆ ${formatDate(p.date)} ${p.time}`;

    if (p.frame) {
      const choicesText = (p.choices || [])
        .map((c, i) => `${['A', 'B', 'C', 'D'][i]}. ${c}`)
        .join('\n');
      const reply = p.comment_1 || p.reply_1 || '';
      const parts = [head, '【フック】', p.frame, '', '【選択肢】', choicesText, '', '【コメント①】', reply];
      if (p.comment_2) parts.push('', '【コメント②】', p.comment_2);
      return parts.join('\n');
    }

    const parts = [head, p.content || ''];
    if (p.quote) parts.push('', `〈ひとこと〉${p.quote}`);
    // 返信も週コピーに入れる（2026-09-03。入っていなかったので、貼るときに毎回落ちていた）
    if (Array.isArray(p.self_replies)) {
      p.self_replies.forEach((r, i) => {
        if (r) parts.push('', `【返信${['①', '②', '③'][i] || (i + 1)}】`, r);
      });
    }
    return parts.join('\n');
  });

  return blocks.join('\n\n──────────\n\n');
}

function renderWeekCopyBar() {
  const bar = document.getElementById('weekCopyBar');
  if (!bar) return;

  const cats = WEEK_COPY_CATEGORIES
    .map(c => ({ ...c, weekId: getLatestWeekIdForPlatform(c.platform) }))
    .filter(c => c.weekId);

  if (!cats.length) {
    bar.innerHTML = '';
    return;
  }

  const buttons = cats
    .map(c => `<button class="week-copy-btn ${c.cls}" data-week-copy="${escapeHtml(c.platform)}">${escapeHtml(c.platform)}を一括コピー（${formatWeekRangeLabel(c.weekId)}）</button>`)
    .join('');

  bar.innerHTML = `
    <span class="week-copy-label">最新回をまとめてコピー</span>
    <div class="week-copy-buttons">${buttons}</div>
  `;
}

function setupWeekCopyHandler() {
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.week-copy-btn');
    if (!btn) return;

    const platform = btn.dataset.weekCopy;
    const weekId = getLatestWeekIdForPlatform(platform);
    if (!weekId) return;

    const text = buildCategoryCopyText(weekId, platform);
    const ok = await copyToClipboard(text);
    flashCopyState(btn, ok);
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
let activeNoteFilters = { tier: 'all', week: 'all', fixOnly: false };
let notesLoaded = false;

// noteの本文も index.json と同じく毎回サーバに聞き直す（下の fetch の cache: 'no-cache'）。
// 2026-09-03：ここには手で上げる札（NOTE_V）を置いていたが、9/1〜9/3 の3日で4回上げていて、
// 一度でも忘れると「直したのに変わっていない」になる。35投稿側（POST_V）は 2026-09-02 に
// 同じ理由で札を外している。**守られない運用は、運用ではなく設計の問題。**
// no-cache は「毎回ダウンロード」ではなく「毎回聞き直す」（変わっていなければ 304 で返る）。

async function loadNotes() {
  const container = document.getElementById('notesContainer');
  container.innerHTML = '<p class="loading">読み込み中…</p>';

  try {
    // 一覧は必ずサーバに聞き直す。ここをキャッシュさせると、
    // 新しく足したnoteが「ファイルはあるのに週フィルタに出ない」状態になる
    // （2026-08-31：?v= を固定したまま週を足していたため、9/1週と8/18週が出なかった）
    const indexRes = await fetch('./notes/index.json', { cache: 'no-cache' });
    if (!indexRes.ok) throw new Error('notes/index.json not found');
    const index = await indexRes.json();

    allNotes = await Promise.all(
      index.notes.map(async (filename) => {
        const res = await fetch(`./notes/${filename}`, { cache: 'no-cache' });
        if (!res.ok) throw new Error(`${filename} not found`);
        const data = await res.json();
        return { ...data, _sourceFile: filename };
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

// noteの週グループ。week_group があればそれ、なければ source_week
function noteWeekGroup(note) {
  return note.week_group || note.source_week;
}

function noteWeekLabel(week) {
  if (week === '過去分') return '過去分';
  if (week === 'standing_guide') return '常設案内';
  const [from, to] = String(week).split('_');
  if (!from || !to || !/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return week;
  return `${from.slice(5).replace('-', '/')}〜${to.slice(5).replace('-', '/')}`;
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

  // 週フィルタの並び：日付の週（新しい順）→ 過去分 → 常設案内
  const specialOrder = { '過去分': 1, 'standing_guide': 2 };
  const weeks = [...new Set(allNotes.map(noteWeekGroup))].sort((a, b) => {
    const sa = specialOrder[a] || 0;
    const sb = specialOrder[b] || 0;
    if (sa !== sb) return sa - sb;
    if (sa) return 0;
    return a < b ? 1 : a > b ? -1 : 0;
  });
  weeks.forEach(week => {
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.noteWeek = week;
    btn.textContent = noteWeekLabel(week);
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
    const btn = e.target.closest('.filter-btn[data-tier], .filter-btn[data-fix]');
    if (!btn) return;
    tierRow.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeNoteFilters.fixOnly = btn.dataset.fix === '1';
    activeNoteFilters.tier = activeNoteFilters.fixOnly ? 'all' : btn.dataset.tier;
    renderNotes();
  });
}

function renderNotes() {
  const container = document.getElementById('notesContainer');
  const filtered = allNotes.filter(n => {
    if (activeNoteFilters.tier !== 'all' && n.tier !== activeNoteFilters.tier) return false;
    if (activeNoteFilters.week !== 'all' && noteWeekGroup(n) !== activeNoteFilters.week) return false;
    if (activeNoteFilters.fixOnly && n.fix_required !== true && !(n.fix_patch || []).length && !(n.fix_full_rewrite || []).length) return false;
    return true;
  });

  document.getElementById('noteStatsBar').textContent = `${filtered.length}本 / 全${allNotes.length}本`;

  if (filtered.length === 0) {
    container.innerHTML = '<p class="empty-state">該当するnoteがありません</p>';
    return;
  }

  container.innerHTML = filtered.map(renderNoteCard).join('');
}


// ─── 修正必須：一文差し替えのパッチ ───────────────────────────────────────────
function patchPlainText(note) {
  const lines = [`【${note.title}】note.com側の修正`];
  (note.fix_patch || []).forEach((p, i) => {
    lines.push('', `${i + 1}. ${p.kind}`, `（前）${p.before}`, `（後）${p.after}`);
  });
  if ((note.fix_full_rewrite || []).length) {
    lines.push('', `※ 部分修正では直せないもの：${note.fix_full_rewrite.join('／')}`,
               '　 その語が見出し・タイトル・説明文に入っていて、記事の主題語になっています。');
  }
  return lines.join('\n');
}

function renderFixPatch(note) {
  const ps = note.fix_patch || [];
  const fr = note.fix_full_rewrite || [];
  if (!ps.length && !fr.length) return '';
  const rows = ps.map((p, i) => `
      <li class="patch-item">
        <div class="patch-kind">${i + 1}. ${escapeHtml(p.kind)}</div>
        <div class="patch-before">${escapeHtml(p.before)}</div>
        <div class="patch-after">${escapeHtml(p.after)}</div>
      </li>`).join('');
  return `
    <div class="patch-block">
      <div class="patch-head">
        <span>部分修正${ps.length ? `（${ps.length}件・この一文だけ差し替え）` : ''}</span>
        ${ps.length ? `<button class="patch-copy" data-note-id="${escapeHtml(note.note_id || note.title)}">まとめてコピー</button>` : ''}
      </div>
      ${ps.length ? `<ol class="patch-list">${rows}</ol>` : ''}
      ${fr.length ? `<p class="patch-rewrite">部分修正では直せないもの：<strong>${escapeHtml(fr.join('／'))}</strong>　その語が見出し・タイトル・説明文に入っていて、記事の主題語になっています。直すなら全文の作り直しです。</p>` : ''}
    </div>`;
}

document.addEventListener('click', e => {
  const btn = e.target.closest('.patch-copy');
  if (!btn) return;
  const id = btn.dataset.noteId;
  const note = allNotes.find(n => (n.note_id || n.title) === id);
  if (!note) return;
  const text = patchPlainText(note);
  navigator.clipboard.writeText(text).then(() => {
    const o = btn.textContent; btn.textContent = 'コピーしました'; btn.classList.add('copied');
    setTimeout(() => { btn.textContent = o; btn.classList.remove('copied'); }, 1600);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
    const o = btn.textContent; btn.textContent = 'コピーしました';
    setTimeout(() => { btn.textContent = o; }, 1600);
  });
});

function buildNoteSalesFinalEditorPrompt(note) {
  const body = note.content_markdown || '';
  return `あなたはCoco Methodologyのnote専用Final Editorです。
Claudeが既存の型・ルールに沿って完成させた原稿を、内容を別物にせず「売れるnote」へ最終調整してください。

【役割分担】
Claude＝Coco Methodologyの型に沿って記事を作る。
Final Editor＝完成稿の価値が、クリック・読了・保存・回遊・メンバーシップ継続につながるよう販売面を整える。
既存ルールをもう一度増やしたり、文章をうまく見せるためだけに全面改稿したりしない。

【最優先】
- 原稿にある事実・実体験・数字・結果・会話だけを使う。
- 素材にないエピソード、成果、心理、読者の声、具体例、権威づけを創作しない。
- 売るために事実を強く見せたり、保証・断定を足したりしない。
- 売上に影響する修正だけ行う。「別案がある」は修正理由にしない。
- 必要な素材が足りず、補わないと販売上の重要箇所を直せない場合は、推測せずCocoへ質問する。質問は必要最小限、最大3問。その回答が来るまで該当箇所を創作して埋めない。
- 素材不足でない箇所は質問せず、その場で完成させる。
- Cocoらしい静かな熱、押しつけない判断軸、実体験の言葉を守る。

【販売編集で見る順番】
1. タイトル：検索性だけでなく、今開く理由があるか。
2. 冒頭：早い段階で「自分のこと」と感じ、続きを読みたくなるか。
3. 読了：重複・説明過多・同じ結論の言い換えで離脱させていないか。
4. 価値の山場：ここだけでも読んでよかった、と思える判断軸・整理・実践があるか。
5. 保存価値：次に同じことが起きたとき使える問い・判断軸・手順があるか。
6. 有料価値：有料/メンバー記事なら、価格や継続に見合う再現性が伝わるか。無料記事なら自然な次の一歩があるか。
7. 回遊・CTA：売り込み臭くせず、関連記事・メンバーシップ・次の記事へ進む理由が自然か。
8. タイトル・description・outcome_promise・CTA・SNS導線と本文の約束が一致しているか。
9. スマホ可読性：改行・段落・一文の長さ・見出し・余白を整え、スクロール中でも意味の塊が一目で入るか。
10. 改行は装飾ではなく販売導線として扱う。重要文の前後に余白を作り、長い段落を必要に応じて分け、逆に細切れすぎてテンポを壊す改行はまとめる。
11. 強調したい一文を一行で立たせる場合も、原稿にない意味を強調によって作らない。煽るための過剰な一行改行・記号・太字の連発はしない。

【触らないもの】
- Claudeの型を、Final Editor独自の新しい型へ置換しない。
- Cocoの実体験の強い言葉を、一般論やブランド説明に薄めない。
- SEOキーワードを不自然に詰め込まない。
- 情報量を増やすためだけの加筆をしない。
- 有料価値を作るために素材を捏造しない。

【判定】
公開OK：販売上の重大な詰まりがなく、そのまま出せる。
販売調整：内容は完成している。売上に影響するタイトル・冒頭・順序・重複・価値提示・CTA等だけ直す。
再編集：読者が価値を受け取れない構造的問題があり、部分調整では直らない。
素材確認：必要な事実が不足し、創作せずCocoへの確認が必要。

【出力】
判定：
売上を止めている箇所：最大3点。なければ「なし」。
素材確認：必要な場合だけ最大3問。不要なら「なし」。
完成版：
- 修正が必要なら、タイトル・description・outcome_promise・本文・CTA・SNS導線のうち「実際に変更するものだけ」を完成形で出す。
- 本文を変更する場合は、文章だけでなくnoteへそのまま貼れる改行・段落・見出し・余白まで含めた完成稿として出す。
- 修正不要な項目を別案目的で書き換えない。
変更理由：各変更がクリック／読了／保存／回遊／継続のどれに効くかを一言で。
ルール化判定：原則「不要」。同じ独立事例が3回確認された場合のみ候補。
再チェック：Cocoが「反映して」と言ったら下記反映先へ実データを更新し、note_checkを再実行する。通過した場合だけ note_final_editor_status を public_ok にする。失敗・未実行なら公開OKにしない。

【反映先】
GitHub repository：Coco930118/weekly
branch：main
note JSON：notes/${note._sourceFile || ''}
note_id：${note.note_id || ''}
※Cocoが「反映して」と言うまではGitHubを書き換えない。

【対象note】
タイトル：${note.title || ''}
公開区分：${note.visibility || ''}
価格：${note.price || ''}
tier：${note.tier || ''}
description：${note.description || ''}
outcome_promise：${note.outcome_promise || ''}
CTA：${note.cta_text || ''}
SNS導線：${JSON.stringify(note.sns_hooks || {}, null, 2)}

【本文】
${body}`;
}

function noteFinalEditorStatusBadge(note) {
  const s = note.note_final_editor_status || '';
  const labels = { pending: '編集中', public_ok: '公開OK', sales_adjust: '販売調整', reedit: '再編集', source_check: '素材確認' };
  if (!s) return '<span class="final-editor-status fe-status-none">未判定</span>';
  return `<span class="final-editor-status ${s === 'public_ok' ? 'fe-status-ok' : 'fe-status-pending'}">${labels[s] || s}</span>`;
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

  // 本文に有料境界マーカーがあるものだけバッジを出す（free_ratio の宣言だけでは出さない）
  const hasPaywall = /ここから有料/.test(note.content_markdown || '');
  const freeRatioBadge = (note.free_ratio && parseFloat(note.free_ratio) > 0 && hasPaywall)
    ? `<span class="free-ratio-badge">無料${Math.round(parseFloat(note.free_ratio) * 100)}%公開</span>`
    : '';

  // description と outcome_promise は「📄 本文」の先頭に置く（2026-09-21 Coco指示）。
  // 読む位置とコピーされる位置を揃えるため（noteCopyText と同じ並び）。
  // content_html を持たないnote（2026-04・06 の funnel 2本）だけは、行き先が無いので
  // 従来どおりタイトル下に出す。
  const descHtml = note.description
    ? `<p class="note-description">${escapeHtml(note.description)}</p>`
    : '';
  const outcomeHtml = note.outcome_promise
    ? `<p class="note-outcome">${escapeHtml(note.outcome_promise)}</p>`
    : '';
  const headHtml = note.content_html ? descHtml + outcomeHtml : '';
  const frameworkHtml = note.framework
    ? `<p class="note-meta-line"><span class="meta-label">構造：</span>${escapeHtml(note.framework)}</p>`
    : '';
  const toolHtml = note.practice_tool
    ? `<p class="note-meta-line"><span class="meta-label">実践ツール：</span>${escapeHtml(note.practice_tool)}</p>`
    : '';

  let sections = '';

  if (note.image_prompt || note.image_prompt_short) {
    let promptBody = '';
    if (note.image_prompt_short) {
      const shortEsc = escapeHtml(note.image_prompt_short);
      promptBody += `
          <p class="note-meta-line"><span class="meta-label">Canva用（短縮版）：</span></p>
          <p>${shortEsc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${shortEsc}">短縮版をコピー</button>
          </div>`;
    }
    if (note.image_prompt) {
      const promptEsc = escapeHtml(note.image_prompt);
      promptBody += `
          <p class="note-meta-line"><span class="meta-label">詳細版：</span></p>
          <p>${promptEsc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${promptEsc}">詳細版をコピー</button>
          </div>`;
    }
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">🖼 画像プロンプト</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">${promptBody}
        </div>
      </div>`;
  }

  if (note.content_html) {
    const mdEsc = note.content_markdown ? escapeHtml(noteCopyText(note)) : '';
    sections += `
      <div class="card-section">
        <div class="card-section-header">
          <span class="card-section-title">📄 本文</span>
          <span class="card-section-toggle">▼</span>
        </div>
        <div class="card-section-body">
          <div class="note-content">${headHtml}${note.content_html}</div>
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
    // キーの大文字・小文字はデータ側で揺れている（threads/Threads・x/X）。
    // 92本中78本が小文字なので、読む側でどちらも拾う。
    const hookThreads = note.sns_hooks.Threads || note.sns_hooks.threads;
    const hookX = note.sns_hooks.X || note.sns_hooks.x;
    let hooksHtml = '';
    if (hookThreads) {
      const esc = escapeHtml(hookThreads);
      hooksHtml += `
        <div class="hook-item">
          <span class="hook-platform platform-badge platform-threadsdiag">Threads</span>
          <p>${esc}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-copy="${esc}">コピー</button>
          </div>
        </div>`;
    }
    if (hookX) {
      const esc = escapeHtml(hookX);
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
          ${note.fix_required === true ? '<span class="fix-badge">修正必須</span>' : ''}
          ${(note.fix_patch || []).length ? `<span class="patch-badge">部分修正 ${note.fix_patch.length}件</span>` : ''}
          ${(note.fix_full_rewrite || []).length ? '<span class="rewrite-badge">全文の作り直し</span>' : ''}
          <span class="tier-badge ${tierClass}">${tierLabel}</span>
          <span class="vis-badge ${visClass}">${visLabel}</span>
          ${freeRatioBadge}
          ${funnelTargets}
        </div>
        <span class="note-date">${note.published_confirmed === false
          ? (note.scheduled_upload_date
              ? `未アップ（${formatDate(note.scheduled_upload_date)}予定）`
              : '未アップ')
          : formatDate(note.date)}</span>
      </div>
      <div class="note-card-body">
        <h2 class="note-title">${escapeHtml(note.title)}</h2>
        <div class="copy-btn-content card-actions">
          <button class="final-editor-btn note-sales-final-editor-btn" data-note-sales-id="${escapeHtml(note.note_id || note.title)}">note Final Editor</button>
          ${noteFinalEditorStatusBadge(note)}
        </div>
        ${note.fix_required === true && (note.fix_reasons || []).length
          ? `<ul class="fix-reasons">${note.fix_reasons.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>`
          : ''}
        ${renderFixPatch(note)}
        ${note.content_html ? '' : descHtml + outcomeHtml}
        ${frameworkHtml}
        ${toolHtml}
        ${hashtags ? `<div class="note-tags">${hashtags}</div>` : ''}
      </div>
      ${sections}
    </article>`;
}

document.addEventListener('click', async e => {
  const btn = e.target.closest('.note-sales-final-editor-btn');
  if (!btn) return;
  const note = allNotes.find(n => String(n.note_id || n.title) === String(btn.dataset.noteSalesId || ''));
  if (!note) return;

  const prompt = buildNoteSalesFinalEditorPrompt(note);
  note.note_final_editor_status = 'pending';
  renderNotes();

  const targetUrl = 'https://chatgpt.com/?q=' + encodeURIComponent(prompt);
  const chatWindow = window.open(targetUrl, '_blank', 'noopener');
  if (!chatWindow) {
    const ok = await copyToClipboard(prompt);
    if (ok) alert('ChatGPTを開けなかったため、note Final Editorの指示をコピーしました。');
    else alert('ChatGPTを開けませんでした。ポップアップ許可を確認してください。');
  }
});

// ─── Docs section（申し送り・やること・指示文）────────────────────────────────
//
// 次のセッションに渡すために、まるごとコピーできる状態で置く。
// 出す並びは `reference/index.json`（ファイルを足したらそこに1行足す。**この配列を
// コードに持たない**——持つと、申し送りを書くたびにここも直すことになる）。
// 本文はコピー用にそのまま出す（markdownを整形しない。貼る先で崩れるのを避ける）。

let allDocs = [];
let docsLoaded = false;
let activeDocGroup = 'all';

async function loadDocs() {
  const container = document.getElementById('docsContainer');
  container.innerHTML = '<p class="loading">読み込み中…</p>';

  try {
    // 一覧も本文も毎回サーバに聞き直す（投稿・noteと同じ理由。札は置かない）
    const indexRes = await fetch('./reference/index.json', { cache: 'no-cache' });
    if (!indexRes.ok) throw new Error('reference/index.json not found');
    const index = await indexRes.json();

    allDocs = await Promise.all(
      index.docs.map(async (d) => {
        const res = await fetch(`./reference/${d.file}`, { cache: 'no-cache' });
        const text = res.ok ? await res.text() : '';
        return { ...d, text, title: docTitle(text, d.file) };
      })
    );

    docsLoaded = true;
    renderDocGroupFilter();
    renderDocs();
  } catch (err) {
    container.innerHTML = `<p class="error-state">データの読み込みに失敗しました<br><small>${err.message}</small></p>`;
  }
}

// 見出し（# の1行目）をタイトルにする。無ければファイル名
function docTitle(text, file) {
  const m = text.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : file;
}

function renderDocGroupFilter() {
  const row = document.getElementById('docGroupFilterRow');
  if (!row || row.querySelector('.filter-btn')) return;

  const groups = ['all', ...new Set(allDocs.map(d => d.group))];
  row.insertAdjacentHTML('beforeend', groups.map(g =>
    `<button class="filter-btn${g === 'all' ? ' active' : ''}" data-doc-group="${escapeHtml(g)}">${g === 'all' ? '全て' : escapeHtml(g)}</button>`
  ).join(''));

  row.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn[data-doc-group]');
    if (!btn) return;
    row.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeDocGroup = btn.dataset.docGroup;
    renderDocs();
  });
}

function renderDocs() {
  const container = document.getElementById('docsContainer');
  const stats = document.getElementById('docStatsBar');
  const docs = allDocs.filter(d => activeDocGroup === 'all' || d.group === activeDocGroup);

  if (stats) stats.textContent = `${docs.length}件（本文まるごとコピーできます）`;

  if (!docs.length) {
    container.innerHTML = '<p class="empty-state">該当なし</p>';
    return;
  }

  container.innerHTML = docs.map((d, i) => {
    const chars = d.text.length.toLocaleString();
    return `
      <article class="card">
        <div class="card-header">
          <div class="card-meta-left">
            <span class="platform-badge platform-other">${escapeHtml(d.group)}</span>
            <span class="card-time">${escapeHtml(d.file)}</span>
          </div>
          <span class="purpose-badge">${chars}字</span>
        </div>
        <div class="card-body">
          <p class="card-content">${escapeHtml(d.title)}</p>
          <div class="copy-btn-content">
            <button class="copy-btn" data-doc-copy="${i}">まるごとコピー</button>
          </div>
        </div>
        <div class="card-section">
          <div class="card-section-header">
            <span class="card-section-title">📄 本文を開く</span>
            <span class="card-section-toggle">▼</span>
          </div>
          <div class="card-section-body">
            <pre class="doc-text">${escapeHtml(d.text)}</pre>
          </div>
        </div>
      </article>`;
  }).join('');

  // 本文は data 属性に載せず、描画時に配列から引く（申し送りは数万字になる）
  container.querySelectorAll('[data-doc-copy]').forEach(btn => {
    btn.dataset.copy = docs[Number(btn.dataset.docCopy)].text;
  });
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
    document.getElementById('docsSection').hidden = tab !== 'docs';

    if (tab === 'notes' && !notesLoaded) {
      loadNotes();
    }
    if (tab === 'docs' && !docsLoaded) {
      loadDocs();
    }
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  setupPlatformFilter();
  setupSectionToggle();
  setupCopyHandler();
  setupFinalEditor();
  setupWeekCopyHandler();
  setupTabs();
  setupNoteTierFilter();
  loadPosts();
});
