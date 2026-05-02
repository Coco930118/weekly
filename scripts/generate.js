#!/usr/bin/env node
'use strict';

/**
 * Weekly SNS Post Generator for coconocanvas
 *
 * Generates posts for the next Tue–Mon window using the Claude API.
 * Processes one day at a time and saves incrementally so a mid-run
 * crash does not lose completed days.
 *
 * Environment variables:
 *   ANTHROPIC_API_KEY  (required)
 *   TARGET_DATE        (optional) Override the Tuesday start date (YYYY-MM-DD)
 *
 * Run from the /posts directory (GitHub Actions cwd) or any directory;
 * paths are resolved relative to this file's location.
 */

const Anthropic = require('@anthropic-ai/sdk');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ── Paths ────────────────────────────────────────────────────────────────────
const POSTS_DIR = path.resolve(__dirname, '..', 'posts');

// ── Helpers ──────────────────────────────────────────────────────────────────
function pad2(n) { return String(n).padStart(2, '0'); }
function fmtDate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** Next Tuesday from today (or the day after Saturday's run). */
function calcWeekStart(overrideDate) {
  if (overrideDate) {
    const d = new Date(overrideDate + 'T00:00:00+09:00');
    if (!isNaN(d)) return d;
  }
  const now = new Date();
  const dow = now.getDay(); // 0=Sun … 6=Sat
  const daysUntilTue = (2 - dow + 7) % 7 || 7;
  const d = new Date(now);
  d.setDate(now.getDate() + daysUntilTue);
  d.setHours(0, 0, 0, 0);
  return d;
}

function getWeekDays(start) {
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    days.push(d);
  }
  return days;
}

function weekFilename(start, end) {
  return `week_${fmtDate(start).replace(/-/g, '_')}_${fmtDate(end).replace(/-/g, '_')}.json`;
}

function log(tag, msg) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] [${tag}] ${msg}`);
}

// ── Post-index helpers ────────────────────────────────────────────────────────
function loadIndex() {
  const p = path.join(POSTS_DIR, 'index.json');
  if (!fs.existsSync(p)) return { weeks: [] };
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function saveIndex(index) {
  index.weeks.sort().reverse();
  fs.writeFileSync(
    path.join(POSTS_DIR, 'index.json'),
    JSON.stringify(index, null, 2),
    'utf8'
  );
}

// ── ID helpers ────────────────────────────────────────────────────────────────
function buildIdMap(posts) {
  const xNums = posts
    .filter(p => p.platform === 'X' && p.id)
    .map(p => parseInt(p.id.replace('x_', ''), 10) || 0);
  const thNums = posts
    .filter(p => p.platform === 'Threads' && p.id)
    .map(p => parseInt(p.id.replace('th_', ''), 10) || 0);
  return {
    nextX: (Math.max(0, ...xNums) + 1),
    nextTh: (Math.max(0, ...thNums) + 1),
  };
}

// ── Claude generation ─────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `あなたは「coconocanvas」の投稿を生成するAIアシスタントです。
以下のブランドプロトコルに厳密に従い、指定された日付の投稿をJSON形式で出力してください。

## キャラクター
- 🐢しずく：組織の調律師。20年の現場経験から来る静かな鋭さ。
- 🐈‍⬛しらたま：生活の中の違和感を拾う観察者。距離感の解像度が高い。
- 🕊ひより：夜の静かな共犯者。余韻と余白を重んじる。

## Xのルール（06:00 / 22:00）
- キャラ：06:00=🐢しずく、22:00=🕊ひより
- 140字以内。句点と絵文字の併用禁止。
- 構成：現場の体温（自嘲/違和感）→ 構造的指摘💎 → 明日の一手▶ → 二者択一の問い
- 名言：15文字以内、💎を先頭に。

## Threadsのルール（07:00 / 10:00 / 19:00）
- キャラ：07:00=🐢しずく、10:00=🐈‍⬛しらたま、19:00=🕊ひより
- 説明ではなく、人柄がにじむ「こぼれた言葉」。
- 本文末尾（7〜8割）：「感情はある。依存はしない。そんな距離の整え方を、ここに残していく💍」
- 除外：「送れなかった言葉」「消したメッセージ」など深い余韻の投稿は末尾フレーズなし。
- お守り言葉：15文字以内、💍を先頭に。

## コア・ロジック
「ネガティブ→ポジティブ」への安易な励ましは厳禁。
一見悪い状態を「誠実さの兆し」「回復への過程」として意味を書き換える。
生理的描写（心臓の鼓動・指先の冷たさ・深夜の静寂）を1つ以上入れる。
映像が浮かぶ具体場面（会議の最後3分・送らなかった文面・謝る直前の1秒）を含む。

## 出力形式（厳守）
以下のJSON配列のみを出力すること。余計な説明・コードブロック記号は不要。

[
  {
    "platform": "X",
    "time": "06:00",
    "character": "🐢しずく",
    "purpose": "共感獲得",
    "content": "本文",
    "quote": "💎 名言"
  },
  ...5投稿（X×2、Threads×3）
]`;

async function generateDayPosts(client, dateStr, dayName, idMap) {
  const prompt = `日付：${dateStr}（${dayName}）

この日の5投稿（X×2、Threads×3）を生成してください。
IDは以下の番号から採番してください：
- X投稿のid：x_${pad2(idMap.nextX)}、x_${pad2(idMap.nextX + 1)}
- Threads投稿のid：th_${pad2(idMap.nextTh)}、th_${pad2(idMap.nextTh + 1)}、th_${pad2(idMap.nextTh + 2)}

出力はJSON配列のみ（idフィールドも含めてください）。`;

  const response = await client.messages.create({
    model: 'claude-opus-4-7',
    max_tokens: 3000,
    system: SYSTEM_PROMPT,
    messages: [{ role: 'user', content: prompt }],
  });

  const raw = response.content[0].text.trim();

  // Extract JSON array from response
  const match = raw.match(/\[[\s\S]*\]/);
  if (!match) throw new Error(`No JSON array found in response:\n${raw.slice(0, 200)}`);

  const posts = JSON.parse(match[0]);

  // Attach date and validate
  return posts.map((p, i) => {
    if (!p.id) {
      const prefix = p.platform === 'X' ? 'x' : 'th';
      const xIdx = posts.slice(0, i).filter(q => q.platform === 'X').length;
      const thIdx = posts.slice(0, i).filter(q => q.platform === 'Threads').length;
      p.id = p.platform === 'X'
        ? `x_${pad2(idMap.nextX + xIdx)}`
        : `th_${pad2(idMap.nextTh + thIdx)}`;
      void prefix; // suppress lint
    }
    return { ...p, date: dateStr };
  });
}

// ── Git helpers ───────────────────────────────────────────────────────────────
function gitPushWithRetry(weekLabel, maxAttempts = 3, delaySec = 5) {
  const { execSync } = require('child_process');
  try {
    execSync('git config user.email "weekly-bot@coconocanvas"', { stdio: 'inherit' });
    execSync('git config user.name "Weekly Generator"', { stdio: 'inherit' });
    execSync('git add posts/', { stdio: 'inherit', cwd: path.resolve(__dirname, '..') });
    execSync(`git commit -m "auto: weekly posts ${weekLabel}"`, {
      stdio: 'inherit',
      cwd: path.resolve(__dirname, '..'),
    });
  } catch (e) {
    log('GIT', 'Nothing new to commit or commit error: ' + e.message);
    return;
  }

  for (let i = 1; i <= maxAttempts; i++) {
    const result = spawnSync('git', ['push', '-u', 'origin', 'HEAD'], {
      cwd: path.resolve(__dirname, '..'),
      stdio: 'inherit',
    });
    if (result.status === 0) {
      log('GIT', 'Push successful');
      return;
    }
    log('GIT', `Push attempt ${i}/${maxAttempts} failed`);
    if (i < maxAttempts) {
      // Synchronous sleep
      const end = Date.now() + delaySec * 1000;
      while (Date.now() < end) { /* spin */ }
    }
  }
  log('GIT', `Push failed after ${maxAttempts} attempts. Data saved locally — will retry on next run.`);
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY is not set');

  const client = new Anthropic.default({ apiKey });

  const weekStart = calcWeekStart(process.env.TARGET_DATE);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  const filename = weekFilename(weekStart, weekEnd);
  const filepath = path.join(POSTS_DIR, filename);

  log('INIT', `Target week: ${fmtDate(weekStart)} – ${fmtDate(weekEnd)}`);
  log('INIT', `File: ${filename}`);

  // Load or create week data
  let weekData;
  if (fs.existsSync(filepath)) {
    weekData = JSON.parse(fs.readFileSync(filepath, 'utf8'));
    log('RESUME', `Found existing file with ${weekData.posts.length} posts`);
  } else {
    weekData = {
      week: `${fmtDate(weekStart)}_${fmtDate(weekEnd)}`,
      generated_at: new Date().toISOString(),
      source: 'weekly_sns_run',
      trend_summary: [],
      posts: [],
    };
  }

  const days = getWeekDays(weekStart);
  const existingDates = new Set(weekData.posts.map(p => p.date));
  const DAY_NAMES = ['日', '月', '火', '水', '木', '金', '土'];

  for (const day of days) {
    const dateStr = fmtDate(day);
    if (existingDates.has(dateStr)) {
      log('SKIP', `${dateStr} — already generated`);
      continue;
    }

    const dayName = DAY_NAMES[day.getDay()];
    log('GEN', `Generating ${dateStr}（${dayName}）…`);

    const idMap = buildIdMap(weekData.posts);

    try {
      const dayPosts = await generateDayPosts(client, dateStr, dayName, idMap);
      weekData.posts.push(...dayPosts);

      // Incremental save — data is never lost even on crash
      fs.writeFileSync(filepath, JSON.stringify(weekData, null, 2), 'utf8');
      log('SAVE', `${dateStr} — ${dayPosts.length} posts written to ${filename}`);
    } catch (err) {
      log('ERROR', `${dateStr}: ${err.message}`);
      // Save what we have and exit with non-zero so CI marks failure
      fs.writeFileSync(filepath, JSON.stringify(weekData, null, 2), 'utf8');
      log('SAVE', 'Partial data saved. Re-run to continue from this day.');
      process.exit(1);
    }
  }

  // Update index.json
  const index = loadIndex();
  if (!index.weeks.includes(filename)) {
    index.weeks.push(filename);
    saveIndex(index);
    log('INDEX', `Added ${filename}`);
  }

  log('DONE', `All ${weekData.posts.length} posts generated for ${fmtDate(weekStart)}–${fmtDate(weekEnd)}`);

  // Push to remote
  const weekLabel = `${fmtDate(weekStart)}_${fmtDate(weekEnd)}`;
  gitPushWithRetry(weekLabel);
}

main().catch(err => {
  console.error('[FATAL]', err.message);
  process.exit(1);
});
