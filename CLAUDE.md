# weekly — Claude 運用ルール

## リポジトリ概要
週次SNS投稿カレンダー。X（14本）+ Threads（21本）+ X診断（7本）= 42本/週。
公開URL: https://coco930118.github.io/weekly/

## ブランチ運用
- 開発: `claude/determined-einstein-3QVKE`
- 本番反映: `main`（GitHub Pages）

---

## 投稿作成ルール（毎回必ず適用）

### 永続ガイドライン
`reference/post_guidelines.json` を毎回読み込んで全35投稿に適用する。

### 絶対禁止
- X診断7本は**いかなる場合も変更しない**
- エピソードの捏造・水増し禁止（渡された事実だけ使う）

---

## エピソード管理ルール

### ファイル
| ファイル | 役割 |
|----------|------|
| `reference/episodes_soshiki.json` | エピソード本体（E1〜En） |
| `reference/episode_usage_log.json` | 使用履歴（自動更新） |

### 新規投稿生成時の手順

1. `episode_usage_log.json` を読み込む
2. 各エピソードの直近使用日を確認
3. **直近30日以内に使用したエピソードは除外**（使用日リストの最新値が今日-30日より新しければ除外）
4. 残りのエピソードからランダムに選択して各投稿に割り当てる
5. 使用したエピソードIDと投稿日を `episode_usage_log.json` に追記
6. 更新したログファイルを main にプッシュ

### エピソード追加時
- `episodes_soshiki.json` の `episodes` 配列に追記（ID採番: E6, E7...）
- `episode_usage_log.json` に新IDを空配列で追加
- 両ファイルを main にプッシュ

### 除外エピソードが全て埋まった場合
使用可能なエピソードがゼロになったら、最終使用日が最も古いものから順に再使用する。

---

## 投稿JSONの構造
`posts/week_YYYY-MM-DD_YYYY-MM-DD.json`
- `week`: `"YYYY-MM-DD_YYYY-MM-DD"`
- `posts[]`: date / platform / time / purpose / character / content / image_prompt / quote（+ comment は X診断のみ）

## 週次スケジュール
| 時刻 | プラットフォーム |
|------|----------------|
| 06:00 | X |
| 07:00 | Threads |
| 10:00 | Threads |
| 12:00 | X診断（変更禁止） |
| 18:00 | Threads |
| 22:00 | X |
