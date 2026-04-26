# coconocanvas / weekly リポジトリ 運用ルール

## ブランド
「関係の温度と距離を整える技術」

## リポジトリ構造
```
posts/
  index.json                        ← 全週ファイルの一覧（新週追加のたびに更新）
  week_YYYY_MM_DD_YYYY_MM_DD.json   ← 週ごとの投稿データ（月曜〜日曜）
assets/
  app.js
  style.css
index.html
```

## 投稿JSONフォーマット
各投稿オブジェクトのフィールド：
- `date` — YYYY-MM-DD
- `platform` — "X" or "Threads"
- `time` — "HH:MM"
- `character` — 🌸Coco / 🐈‍⬛しらたま / 🐢しずく / 🕊ひより
- `purpose` — 共感獲得 / 保存獲得 / 返信獲得 / プロフィール遷移
- `stamp` — 対応するLINEスタンプのセリフ（シリーズ投稿時のみ）
- `content` — 投稿本文
- `quote` — 💍 or 💎 で始まるまとめのひと言

## LINEスタンプシリーズ投稿のプッシュルール

### シリーズ情報
- ブランド：「関係の温度と距離を整える技術」
- 現行シリーズ：「きょうも、そのままで」③（以降④⑤と更新）
- 1シリーズ = 21スタンプ = 7日分

### コミット・プッシュの単位
**3スタンプ（3投稿）ずつ、計7コミットで1週間分を完結させる。**

| コミット | 対応日 | 内容 |
|---------|--------|------|
| 1/7 | Day 1 | スタンプ01〜03 |
| 2/7 | Day 2 | スタンプ04〜06 |
| 3/7 | Day 3 | スタンプ07〜09 |
| 4/7 | Day 4 | スタンプ10〜12 |
| 5/7 | Day 5 | スタンプ13〜15 |
| 6/7 | Day 6 | スタンプ16〜18 |
| 7/7 | Day 7 | スタンプ19〜21 |

### コミットメッセージ形式
```
Add LINE stamp series Day N (YYYY-MM-DD): [シリーズタイトル]

スタンプ収録：[セリフ1] / [セリフ2] / [セリフ3]
キャラクター：[キャラ]（プラットフォーム×投稿数）
[テーマ補足]
```

### ブランチ
`claude/friendly-archimedes-chdq3`

### 投稿スタイルガイド
- **X投稿**：短文。核心的な洞察＋💎＋「〜するか」「〜するか」▶ の二択で終わる
- **Threads投稿（通常）**：複数の短い段落。「感情はある。依存はしない。そんな距離の整え方を、ここに残していく💍」で締める
- **Threads投稿（スタンプ告知）**：シリーズ紹介文を添え、「きょうも、そのままで。③ / LINEストアにて販売中🌿」で締める
- 1日3投稿（Threads×2＋X×1、またはThreads×1＋X×2）を基本配分とする

## 完了報告
全7コミット・プッシュ終了後、ユーザーに以下を報告する。

1. 完了メッセージ
2. 以下のURLを表示する：
   - **ブランチURL**：`https://github.com/coco930118/weekly/tree/[branch-name]`
   - **週次ファイルURL**：`https://github.com/coco930118/weekly/blob/[branch-name]/posts/week_YYYY_MM_DD_YYYY_MM_DD.json`
   - **コミット履歴URL**：`https://github.com/coco930118/weekly/commits/[branch-name]`
