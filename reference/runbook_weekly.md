# セッション指示文（全7本）

**この7本が、実際にスケジュール実行される指示文の正本。** 変えるときはここを直す。

**指示文はルールを持たない。** ルールの正典は `CLAUDE.md` と `rules/*.md` だけ。
指示文に書くのは「何を・どのファイルに・どの順で」だけで、書き方の基準は書かない。
（旧ver.7.1／7.2の指示文はルールを二重に持ち、20箇所以上食い違って、従うと必ず違反が出る状態だった）

| 曜日・時刻 | セッション | 担当ファイル |
|---|---|---|
| 火 7:00 | X診断 生成 | `posts/shindan_x_*.json` |
| 火 12:00 | X診断 週次レビュー | `reference/weekly_metrics.json` ＋ 上記 |
| 水 7:00 | Threads診断 生成 | `posts/shindan_th_*.json` |
| 水 12:00 | Threads診断 週次レビュー | `reference/weekly_metrics.json` ＋ 上記 |
| 金 7:00 | 35投稿 生成 | `posts/week_*.json` |
| 金 12:00 | 35投稿 週次レビュー | `reference/weekly_metrics.json` ＋ 上記 |
| 土 7:00 | note 生成 | `notes/` ＋ `reference/note_archive.json` |

**12:00の3本は「グローアップ」から「週次レビュー」に変えた（2026-08-25 Coco決定）。**
旧グローアップは、7:00の生成が回したのと同じチェックを同じ物差しでもう一度回していた。
固有の入力が一つもないので、2回目は1回目の再実行にしかならない。
レビューには固有の入力がある——**前週の実測**。対象（今朝作った翌週分）はまだ配信前なので直せる。

---

## 共通の型（7本すべてに入れる）

```
【最重要】ルールの正典は CLAUDE.md と rules/ です。この指示文にルールを書きません。
食い違ったら CLAUDE.md と rules/ を優先し、どこが食い違ったかを報告してください。

■ 読むファイル（この順で・これだけ）
1. CLAUDE.md
2. rules/〈担当媒体〉.md
3. rules/check.md
※ 素材・エピソードを使うときだけ rules/source.md も読む

■ 担当範囲（厳守）
・触るのは〈担当ファイル〉のみ。他の媒体は1バイトも変えない
・「全入れ替え」「全削除して作り直し」は禁止
・index.json は自分の項目だけ追加・削除する

■ push
git pull origin main --no-rebase → 自分のファイルだけ add/commit →
git push -u origin <branch> → main にも push。
ネットワーク起因の失敗のみ 2s→4s→8s→16s で最大4回リトライ。生成データは消さない。
```

---

## ① 火 7:00｜X診断 生成

```
X診断7本を生成してください。対象週：YYYY-MM-DD（火）〜YYYY-MM-DD（月）

【最重要】ルールの正典は CLAUDE.md と rules/shindan.md です。この指示文にルールを書きません。
食い違ったら正典を優先し、どこが食い違ったかを報告してください。

■ 読むファイル
1. CLAUDE.md  2. rules/shindan.md  3. rules/check.md  4. rules/source.md
5. reference/shindan_series.json（next_no）
6. reference/weekly_metrics.json（直近実測・設問の型の配分根拠）
7. reference/episode_usage_log.json ＋ reference/episodes_soshiki.json

■ 担当ファイル
posts/shindan_x_YYYY-MM-DD.json のみ。他の媒体は1バイトも変えない。

■ やること
1. shindan_series.json の next_no から7本の通し番号を振る
2. 7本それぞれに1エピソードを1対1で割り当てる（30日除外・使い回し禁止・episode_ref に記録）
   ウィット一滴を入れる回は tatazumai_episode_ref も記録する
3. 直近1週間のビジネス・マネジメント系トレンドを角度合わせに使う
   （テーマの軸は割り当てエピソード。トレンドで上書きしない。直近4週のテーマと重複させない）
4. 1日ずつ生成してJSONに逐次保存（途中停止時は未完了日から再開）

■ 完成後
1. python3 tools/shindan_check.py posts/shindan_x_YYYY-MM-DD.json → 要修正0件まで直す
2. ツール末尾の【判断チェック】5項目を目視で埋める
3. shindan_series.json（technique_log・numbering）と episode_usage_log.json を更新
報告は、機械で確認した項目と目視で確認した項目を分けて書く。
目視していない項目を「クリア」と書かない。
```

---

## ② 火 12:00｜X診断 週次レビュー

```
X診断の週次レビューをしてください。

【最重要】ルールの正典は CLAUDE.md と rules/shindan.md です。この指示文にルールを書きません。

■ 読むファイル
1. reference/weekly_metrics.json（配信が終わった週の実測。これがこのセッション固有の入力）
2. posts/shindan_x_*.json（配信が終わった週と、今朝生成した翌週分）
3. CLAUDE.md ／ rules/shindan.md ／ reference/todo.md

■ このセッションの仕事は3つだけ。作り直さない。
1. 【測る】配信が終わった週7本の実測を読む。診断は必ず2値で見る
   ——本文（frame）の表示回数／コメント（comment）の表示回数／いつ時点か。
   経過日数が揃っていない日同士を強弱で比べない。判定はコメント到達率で行う。
2. 【判定】設問の型ごとに到達率を出し、weekly_metrics.json に追記する。
   reference/todo.md に判定期限の来た試験があれば、その基準で判定してCocoに提案する。
3. 【次に渡す】今朝生成した翌週分（まだ配信前なので直せる）に、実測を反映する。
   直すのは配分・型・用量だけ。本文の書き直しはしない。
   ・素の行動型が多すぎないか（週2本まで）
   ・勝った型に寄せられるか
   ・ウィット一滴の本数が実測に合っているか

■ 出力（3行の申し送り＋根拠）
　増やす：〈型〉が中央値の〇倍。翌週は〇本→〇本
　減らす：〈型〉が2週連続で下回った。〇本に落とす
　試す：〈試験名〉の判定が〇/〇。継続／用量変更／中止のどれかをCocoに提案

■ 触らないもの
・配信が終わった週の本文（配信実態と食い違うため）
・X診断は「内容は絶対に変更しない」が恒久ルール。翌週分の配分調整も、
　本文の書き直しではなく次の生成への申し送りで返す（Cocoが「直して」と言った回のみ反映）
```

---

## ③ 水 7:00｜Threads診断 生成

```
Threads診断7本を生成してください。対象週：YYYY-MM-DD（火）〜YYYY-MM-DD（月）

【最重要】ルールの正典は CLAUDE.md と rules/shindan.md です。この指示文にルールを書きません。
食い違ったら正典を優先し、どこが食い違ったかを報告してください。

■ 読むファイル
1. CLAUDE.md  2. rules/shindan.md  3. rules/check.md  4. rules/source.md
5. reference/weekly_metrics.json（直近実測・特にコメント到達率）
6. reference/episode_usage_log.json ＋ reference/episodes_soshiki.json

■ 担当ファイル
posts/shindan_th_YYYY-MM-DD.json のみ。他の媒体は1バイトも変えない。

■ やること
1. 7本それぞれに1エピソードを1対1で割り当てる（30日除外・使い回し禁止・episode_ref に記録）
   割り当てたエピソードの原文表現を、返信欄の「素材の一行」にそのまま使う（創作ゼロ）
2. 直近1週間のThreadsの恋愛・人間関係トレンドを角度合わせに使う
   （テーマの軸は割り当てエピソード。直近4週のテーマと重複させない）
3. 曜日ごとの読者の感情温度は rules/shindan.md の表に従う
4. 1日ずつ生成してJSONに逐次保存

■ 完成後
1. python3 tools/shindan_check.py posts/shindan_th_YYYY-MM-DD.json → 要修正0件まで直す
2. ツール末尾の【判断チェック】5項目を目視で埋める
3. episode_usage_log.json を更新
報告は、機械で確認した項目と目視で確認した項目を分けて書く。
```

---

## ④ 水 12:00｜Threads診断 週次レビュー

```
Threads診断の週次レビューをしてください。

【最重要】ルールの正典は CLAUDE.md と rules/shindan.md です。この指示文にルールを書きません。

■ 読むファイル
1. reference/weekly_metrics.json（配信が終わった週の実測。このセッション固有の入力）
2. posts/shindan_th_*.json（配信が終わった週と、今朝生成した翌週分）
3. CLAUDE.md ／ rules/shindan.md ／ reference/todo.md

■ このセッションの仕事は3つだけ。作り直さない。
1. 【測る】配信が終わった週7本を2値で読む（本文の表示／コメントの表示／いつ時点か）。
   判定はコメント到達率で行う。経過日数が揃っていない日同士を比べない。
2. 【判定】設問の型ごとの到達率を weekly_metrics.json に追記する。
   reference/todo.md に判定期限の来た試験（ウィット一滴など）があれば、
   その基準で判定してCocoに提案する。
3. 【次に渡す】今朝生成した翌週分（まだ配信前）に配分・型・用量を反映する。
   本文の書き直しはしない。

■ 出力（3行の申し送り＋根拠）
　増やす／減らす／試す を各1行。数字を添える。

■ 触らないもの
・配信が終わった週の本文
・修正が要ると判断したら提案のみ。Cocoの承認を得てから反映する
```

---

## ⑤ 金 7:00｜35投稿 生成

```
週次35投稿を生成してください。対象週：YYYY-MM-DD〜YYYY-MM-DD（火曜〜翌月曜）

【最重要】ルールの正典は CLAUDE.md と rules/posts.md です。この指示文にルールを書きません。
食い違ったら正典を優先し、どこが食い違ったかを報告してください。

■ 読むファイル
1. CLAUDE.md  2. rules/posts.md  3. rules/check.md  4. rules/source.md  5. rules/image.md
6. reference/coco_methodology.json  7. reference/coco_voice_source.json
8. reference/weekly_metrics.json（直近2週の実測。勝った型に配分を寄せる）
9. reference/episodes_soshiki.json ＋ reference/episode_usage_log.json
10. reference/image_prompt_rules.json（画像プロンプトの正典）

■ 担当ファイル
posts/week_YYYY_MM_DD_YYYY_MM_DD.json のみ（アンダースコア区切り）。
posts/index.json は自分の週を追加するだけ。他の媒体は1バイトも変えない。

■ 本数と枠
X：1日2本（06:00 / 22:00）×7日＝14本／Threads：1日3本（07:00 / 10:00 / 19:00）×7日＝21本。
1日ずつ生成してJSONに逐次保存（途中停止時は未完了日から再開）。

■ エピソード割り当て
・各投稿日の30日前より後に使ったものは除外（基準日は「その投稿の日付 − 30日」。
　週の初日で一律に計算しない）
・1投稿1エピソードの1対1。使い回し禁止
・生成後、episode_usage_log.json に追記し、episodes_soshiki.json の used_in も更新

■ 完成後
1. python3 tools/full_check.py posts/week_YYYY_MM_DD_YYYY_MM_DD.json → 要修正0件まで直す
   （Xの曜日固定テーマのfunnel土日配置のみ例外可）
2. ツール末尾の【判断チェック】を目視で埋める
報告は、機械で確認した項目と目視で確認した項目を分けて書く。
目視していない項目を「クリア」と書かない。
完了後、公開URL（https://coco930118.github.io/weekly/）を添えて報告。
```

---

## ⑥ 金 12:00｜35投稿 週次レビュー

```
35投稿の週次レビューをしてください。

【最重要】ルールの正典は CLAUDE.md と rules/posts.md です。この指示文にルールを書きません。

■ 読むファイル
1. reference/weekly_metrics.json（配信が終わった週の実測。このセッション固有の入力）
2. posts/week_*.json（配信が終わった週と、今朝生成した翌週分）
3. CLAUDE.md ／ rules/posts.md ／ reference/todo.md

■ このセッションの仕事は3つだけ。作り直さない。
1. 【測る】配信が終わった週の5指標を読む
   （拡散帯の平均表示／最高表示の型／フォロワー純増／noteの週間ビュー／新規入会数）。
   記入がない週はスキップして、その旨を報告する。
2. 【判定】型ごとの表示を出し、weekly_metrics.json に追記する。
   reference/todo.md に判定期限の来た試験（逆説の言い切り型など）があれば、
   その基準で判定してCocoに提案する。
3. 【次に渡す】今朝生成した翌週分（まだ配信前）に、配分・型・用量を反映する。
   ・型配分の目安（実験10・場面4・問い3）を実測で組み替える
   ・ウィット一滴／佇まい枠／観察締めの本数
   ・funnel8本の置き場所
   本文の全面書き直しはしない。差し替えるのは配分に関わる部分だけ。

■ 出力（3行の申し送り＋根拠）
　増やす：〈型〉が中央値の〇倍。翌週は〇本→〇本
　減らす：〈型〉が2週連続で下回った。〇本に落とす
　試す：〈試験名〉の判定が〇/〇。継続／用量変更／中止のどれかをCocoに提案

■ 触らないもの
・配信が終わった週の本文（配信実態と食い違うため。記録として直す場合はその旨を明示）
・修正は提案のみ。Cocoの承認を得てから確定する
・承認後に修正したら、機械チェックを再実行して要修正0件を確認してから push
```

---

## ⑦ 土 7:00｜note 生成

```
週次noteを生成してください。対象週：YYYY-MM-DD〜YYYY-MM-DD

【最重要】ルールの正典は CLAUDE.md と rules/note.md です。この指示文にルールを書きません。
食い違ったら正典を優先し、どこが食い違ったかを報告してください。
画像プロンプトの正典は reference/image_prompt_rules.json（横長1280x670・Canva安全版）。

■ 読むファイル
1. CLAUDE.md  2. rules/note.md  3. rules/check.md  4. rules/source.md  5. rules/image.md
6. reference/coco_methodology.json  7. reference/coco_voice_source.json
8. reference/brand_profile.json  9. reference/sold_article_patterns.json
10. reference/note_archive.json（公開した全noteの永久索引。
    週またぎの既視感チェックと、あわせて読むの候補探しはここを見る）
11. reference/image_prompt_rules.json  12. reference/weekly_metrics.json
13. reference/episodes_soshiki.json ＋ reference/episode_usage_log.json

■ 担当ファイル
notes/ 配下のみ。例外は reference/note_archive.json と
reference/episode_usage_log.json への追記だけ。他の媒体は1バイトも変えない。

■ 判断材料＝最新週の全49投稿
posts/week_*.json（35本）＋ posts/shindan_x_*.json（7本）＋ posts/shindan_th_*.json（7本）。
診断は読んで判断材料にするだけ。診断ファイルは一切変更しない。

■ やること
1. note_funnel: true の投稿をすべて拾い、X群／Threads群に分ける
   （診断はリンク起点にしない）
2. 各群の中で「同じ主題・同じ原理 かつ 予告日が同じ」ものをクラスタにまとめる
   X由来とThreads由来を混ぜない。予告日が違うものも混ぜない
3. クラスタごとに1本のnoteを作る。上限なし。予告した全部を回収する（空手形ゼロ）
4. 公開日＝そのクラスタの予告日
5. あわせて読むの候補は note_archive.json から探す（notes/ に残っていない過去記事も載っている）
6. ファイル名は notes/note_YYYY-MM-DD_{slug}.json

■ 完成後
1. python3 tools/note_check.py --week YYYY-MM-DD_YYYY-MM-DD → 要修正0件まで直す
2. ツール末尾の【判断チェック】を目視で埋める
3. notes/index.json に追記（ここに載せないとサイトに出ない。出ない原因の第一位）
4. reference/note_archive.json に1本1行を追記（principle_no まで埋める）
5. エピソードを使った週のみ episode_usage_log.json を更新

■ 報告に必ず書くこと
作成本数と内訳（プラン別・tier別）／各noteの publish_date と funnel_targets の対応／
機械チェックと目視チェックを分けた結果／note_archive.json に追記した本数／
恒久ルールと個別指定がぶつかった箇所／Cocoの判断に返す点／
実体験がほしい箇所（CLAUDE.md の「Cocoへの質問の作法」に従う）
```

---

## 2026-08-25 の書き直しで直したもの

旧7本を正典と突き合わせた結果。**古い記述をそのまま回すと事故になるものが5件あった。**

### ★ note指示文の画像プロンプトが、いま回すと生成できない
- **サイズ**：旧「`9:16 vertical (1080x1920)`」→ 正典は**横長 1280x670**（2026-08-24 Coco決定。
  縦長はnoteの表示枠に合わず上下が切れていた）
- **Cocoの定義**：旧指示文の `a refined young woman, brand age 40s but drawn to look early 30s
  — ... smooth youthful complexion` は、**そのすべてがCanvaの禁止語**。
  8/18週のサムネイルが実際にこの定義で弾かれ、8/24にCanva安全版へ置き換え済み。
  旧指示文どおりに書くと、生成が通らない
- **季節モチーフ**：旧「春夏秋冬の4区分」→ 正典は**12ヶ月の表**（6月＝梅雨を独立させた。
  季節名で引くと月の境目が空き、6月の記事に朝顔・蓮を当てる事故が実際に起きた）
- **`image_prompt_short`**：現行必須だが旧指示文に記述なし
- **有料エリアの境界**：現行必須だが旧指示文に記述なし

### ★ X診断指示文の置換先が、禁止語になっている
旧「設計 →『仕組み』または『仕組み化』（絶対ルール）」。**「仕組み」も現行の禁止語。**
置換すると別の違反になる。正典の置換先は「実際に起きている出来事を2つ並べる」。

### そのほか
- note指示文のファイル名が2箇所で食い違い（`note_YYYY-MM-DD.json` と `note_YYYY-MM-DD_{slug}.json`）
- X診断の保持期間が「4週間（30日）」（4週間は28日。正典は30日）
- Threads診断グローアップの「公開サイトから最新7本を読み取る」→ サイトはJSONから描画しているのでJSONを読む
- 各指示文が読むファイルを7〜13個並べていた → 3層化により `CLAUDE.md` → `rules/〈媒体〉.md` → `rules/check.md` の3つが基本
- **7本のうち5本がルール本体を持っていた**（正しく作られていたのは35投稿の2本だけ）。全部 `rules/` に寄せて指示文から抜いた
