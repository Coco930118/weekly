# coconocanvas 週次投稿管理サイト — 運用メモ

## 毎週の実行手順

### タイミング
毎週土曜（または依頼時）に次週分（火〜月）を生成・プッシュする。

### 手順

1. **前々週のデータを削除**
   - `posts/week_YYYY_MM_DD_YYYY_MM_DD.json`（2週前のファイル）を削除
   - `posts/index.json` から該当エントリを削除

2. **新週のJSONを1日ずつ生成・プッシュ**（計7回プッシュ）
   - ファイル名：`posts/week_YYYY_MM_DD_YYYY_MM_DD.json`
   - 1日5投稿（X×2 + Threads×3）
   - 各日のコミット後に `git push origin <branch>`

3. **index.json に新週を追加**（最初の日に一緒に実施）

4. **main へ PR 作成→マージ**

### 削除ルール例
| 作成する週 | 削除する週 |
|-----------|-----------|
| 5/5〜5/11 | 4/21〜4/27 |
| 5/12〜5/18 | 4/28〜5/4 |
| 5/19〜5/25 | 5/5〜5/11 |

### 投稿構成
- **X**：6:00 🐢しずく / 22:00 🕊ひより（各1日2投稿）
- **Threads**：7:00 🐢しずく / 10:00 🐈‍⬛しらたま / 19:00 🕊ひより（各1日3投稿）
- 合計：35投稿／週

### JSONフォーマット
```json
{
  "week": "YYYY-MM-DD_YYYY-MM-DD",
  "generated_at": "YYYY-MM-DDT10:00:00+09:00",
  "source": "weekly_sns_run",
  "trend_summary": ["トレンド1", "トレンド2", "トレンド3"],
  "posts": [
    {
      "id": "x_01",
      "date": "YYYY-MM-DD",
      "platform": "X",
      "time": "06:00",
      "character": "🐢しずく",
      "purpose": "共感獲得",
      "content": "本文",
      "quote": "💎 名言"
    }
  ]
}
```

### GitHub Pages URL
https://coco930118.github.io/weekly/
