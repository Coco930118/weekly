# 画像プロンプトの作り方

**正典は `reference/image_prompt_rules.json`。このファイルはその運用ぶんの写しなので、変えるときは必ずJSONを先に直す。**

---

## 画像プロンプト 恒久ルール（X・Threads・note 共通・毎回必ず適用）

`reference/image_prompt_rules.json` を毎回読み込んでから画像プロンプトを書く。**2026-07-14週の35投稿と2026-08-04週のnoteプロンプト（Coco承認済み）を正典として固定したもの。**

### 絶対条件（これを外すとブランド資産が飛ぶ）
- **必ず英語で書く**。日本語の短い情景メモは不可
- **Cocoと動物が必ず登場する**。人物なしの静物・風景のみは作らない
- **Cocoの外見定義は一字一句そのまま使う**：`Coco, a gentle Japanese woman in her early thirties, dark brown bob, warm brown eyes, in a {kimono}, seen from the shoulders up`
  - **旧定義（`a refined young woman, brand age 40s but drawn to look early 30s … smooth youthful complexion` ／ `shown from the chest up`）は2026-08-24に廃止**（Coco決定・恒久ルール）。Canvaの画像生成が①年齢＋容姿の直接描写 ②年齢を操作する指示 ③肌の描写 ④身体部位語（chest／bust）をポリシー違反として弾き、8/18週のnoteで実際に生成できなかったため
  - **Canvaの禁止語**：`young woman` ／ `brand age 40s` ／ `drawn to look` ／ `youthful` ／ `complexion` ／ `chest` ／ `bust-up`。`tools/full_check.py` が検出する
  - **アングル語も置き換える**：`front bust-up` → `head-and-shoulders view` ／ `side-profile bust-up` → `side profile view` ／ `chest-up pose` → `head-and-shoulders pose`
  - 実年齢は40代でも、**絵は30代前半に見えるように描く**。ただし年齢を操作する言い方はしない（`in her early thirties` と書くだけにする）。`elegant 40s woman` も従来どおり使わない（生成結果が50代前後に寄る）
  - **適用開始＝2026-08-25週から**。8/18週以前は画像を生成済みのため遡及しない
- 3匹の外見定義もそのまま使う。**英字表記は Shizuku / Shiratama / Hiyori に統一**（旧表記 Shirotsuma・Shirotama は使わない）
  - しずく＝`Shizuku (small wise turtle)`／しらたま＝`Shiratama (fluffy round white long-haired cat, large gentle eyes, rosy cheeks)`／ひより＝`Hiyori (small soft white bird)`
  - **しらたまは常に白の長毛猫**。黒猫・黒地に白模様・琥珀色の目では絶対に描かない。`character` の絵文字が🐈‍⬛（黒猫）でも**絵は必ず白**。投稿・note・診断・LINEスタンプの全プラットフォーム共通
- 画風は **Quiet Luxury watercolor・soft transparent washes・muted dusty tones** で固定。締めは必ず **No text**（noteは `No text, no letters, no signage.`）
- **X診断・Threads診断の画像プロンプトは廃止**（2026-08-05 Coco決定・恒久ルール）。`posts/shindan_x_*.json`／`posts/shindan_th_*.json` には `image_prompt` を持たせない。新規作成・グローアップ時にも作らない（旧ルール「X診断7本の画像プロンプトは絶対に変更しない」はこの廃止決定で置き換え）

### X・Threads（週35投稿）
**比率は正方形 1:1（1080x1080）に固定**（2026-08-24 Coco決定・恒久ルール）。プロンプトの冒頭に明記する。これまで比率指定が1本も入っておらず、生成のたびに形が変わっていた。**noteサムネイルとは比率を統一しない**（noteはnote側の指定に従う）。
```
A high-quality square 1:1 watercolor illustration (1080x1080) with soft transparent washes. Summer {band}, {angle}.
{coco} stands with {animals} {arrangement}; {shared_action}; {posture}; {background}; {light}.
Refined palette of {c1}, {c2}, {c3}. Quiet Luxury watercolor. No text.
```
- **日付・時刻の昇順に並べてから巡回させる**（この順序を間違えると分布が崩れる）
- **動物は7周期**：しずく→しらたま→ひより→しずく＋しらたま→しずく＋ひより→しらたま＋ひより→3匹全員。週35本で各組合せ5本ずつ
- **アングルは5周期**：front bust-up／side-profile bust-up／looking up／over-the-shoulder／close-up。週35本で各7本ずつ
- **時間帯は投稿時刻から機械的に決める**（〜11:59＝morning／12:00〜20:59＝evening／21:00〜＝night）。**ズレを1本も出さない**
- **朝夕＝絽の着物（淡色）／夜＝浴衣（濃紺系）**
- **佇まいの一文（posture）は35本すべて別文**。その投稿の本文テーマに合わせて書く（ここが投稿と絵を繋ぐ唯一の可変部）

#### パレットはプラットフォームで色分けする（2026-08-24 Coco決定・恒久ルール）
**X（組織）＝寒色 soft blue-grey ／ Threads（恋愛）＝暖色 dusty rose に統一する。** 狙いは、公開サイトやタイムラインに**一覧で並んだとき、青系と桃系の2グループに視覚で割れる**こと。媒体の役割（X＝組織の温度／Threads＝関係の距離）を色でも分ける。

| 組 | X＝組織（寒色） | Threads＝恋愛（暖色） |
|---|---|---|
| 1 | deep indigo, pale slate blue | dusty rose, warm apricot |
| 2 | pale ash blue, muted sage-grey | pale peach, soft coral |
| 3 | deep navy-indigo, pale silver-grey | ash rose, pale apricot |
| 4 | pale celadon, soft steel blue | pale rose, soft gold |

- **3色目（締めの中間色）も分ける**：X＝`cool ivory` ／ Threads＝`warm ivory`
- **温度またぎゼロ**が絶対条件。Xに rose／peach／coral／apricot／gold 系、Threadsに indigo／blue／slate／celadon／silver 系を混ぜない
- **着物の色もパレットに連動**させる（`reference/image_prompt_rules.json` の `kimono_color_pool` をプラットフォーム別に分割済み）。柄＝季節モチーフは従来どおり週替わり、色だけをこの表から選ぶ
- **巡回**：日付・時刻の昇順で、暗い組（1・3）を夜と夕に、淡い組（2・4）を朝に当てる。着物は各組の2色を交互に使って同じ色を並べない
- **旧ルール「週内で完全一致は3回まで」は廃止**（4組運用では成立しないため）。パレットの反復は許容し、代わりにプラットフォーム内で組が偏らないよう巡回で散らす
- **「夜＝浴衣（濃紺系）」はこの色分けより優先**。Threadsに夜スロットが出た場合、浴衣は濃紺のまま、パレットの2色目と `warm ivory` で暖かさを担保する
- **適用開始＝2026-08-25週から**。8/18週以前は画像を生成済みのため遡及しない（`tools/full_check.py` もこの週より前はパレット判定をスキップする）
- **灯りの色は色分けの対象外**（2026-08-24 Coco決定）。X夜（22:00）の `warm amber light` は暖色のまま残す。判定基準は**ぱっと見の感触**で、青系／桃系の印象が保たれていればよい。行灯の暖かさは世界観側の資産なので消さない。**この行が例外の明示であり、「Xに暖色が残っている」として直さないこと**（色分けの検査対象は palette の3色と着物の色だけ）

### note（サムネイル）
- **横長 1280x670px をプロンプト内に明記**（2026-08-24 Coco決定・恒久ルール）。note.comの推奨サイズがこれ。**旧ルール「9:16縦・1080x1920」はこの決定で置き換え**（縦長はnoteの表示枠に合わず、上下が切れていた）
  - 必ず入れる一文：`Horizontal 1280x670 watercolor illustration for a note header.`
  - **35投稿の正方形 1:1 とは統一しない**。noteは横長、35投稿は正方形で別々に持つ
  - **既存noteのプロンプトと画像は作り直しが必要**。noteは別セッションの持ち場なので、そちらで対応する（このルールが引き継ぎ）
- Cocoは note版の定義（`never stern, no sharp eyes or furrowed brow; face fixed by the six reference images`）を使う
- **動物は2匹**を記事テーマに合わせて配置
- **縦を三分割して役割を固定する**（1本も欠かさない。横長になっても役割配分は変えない）
  - **上三分の一＝タイトル文字用のグラデーション余白**（下三分の一に置かない）
  - **中央＝Cocoと動物の主題**。サムネイルで読めるサイズで大きく置く
  - **下三分の一＝静かな余白**
  - 必ず入れる一文：`The upper third is left as a soft {c1}-to-{c2} gradient for title text overlay. The main subject — Coco and the animals — is centred in the middle third of the frame, drawn large and clearly readable at thumbnail size, with the lower third kept as quiet, uncluttered space.`
- **横も三分割して、全キャラを中央3分の1に収める**（2026-08-24 Coco決定・恒久ルール）
  - 生成画像をCanvaに載せると正方形になり、横に切られるとキャラが画面から外れる事故が起きた。**横に三分割したとき、1カットの中にCocoと動物全員が収まっていれば、どの切り方でも使える**
  - 必ず入れる一文：`All characters — Coco and every animal in the scene — are grouped together compactly within the central third of the image's width, so that a square crop taken from the centre contains all of them; the left and right thirds hold only background and quiet space.`
  - 位置はパレット指定と縦三分割の指定の直後、`Quiet Luxury watercolor.` の直前。**キャラを散らさず、横幅の中央3分の1にひとかたまりで置く**。縦の三分割は従来どおり併存させる
- **プラン別にパレットを固定する**（2026-08-24 Coco決定・恒久ルール）
  - 背景：メンバーシップ一覧で6枚とも同じ絵に見え、どちらのプランの記事か判別できなかった。Coco＋動物＋Quiet Luxury固定というブランド資産が、そのまま識別を殺していた。**色は文字より速く処理される**
  - **X由来（組織と仕事）＝寒色**：deep indigo／navy-indigo／pale slate blue／ash blue／pale celadon／soft steel blue／silver-grey／sage-grey。締めの中間色は **cool ivory**
  - **Threads由来（恋愛と関係）＝暖色**：dusty rose／pale rose／ash rose／warm apricot／pale peach／soft coral／soft gold。締めの中間色は **warm ivory**
  - X由来に暖色（dusty rose・peach・coral・gold）を入れない。Threads由来に寒色（slate blue・indigo・steel blue）を入れない。週内で同じ組み合わせを繰り返さないのは従来どおり
  - **既存記事には遡らない**（画像の作り直しが必要なため）。X・Threadsの投稿画像への適用はCocoの判断待ち
- **短縮版（`image_prompt_short`）を必ず併記する**（2026-08-24 Coco指示・恒久ルール）
  - 詳細版は約1,650字あり、固定文だけで54%を占める。一般的な画像生成の入力欄に収まらず、収まっても前半に重みが寄ってブランドの核が薄まる
  - **500字前後**に圧縮した `image_prompt_short` を各noteに持たせる。詳細版（`image_prompt`）は残して併存させる
  - **短縮版に必ず残す**：横長1280x670／`early 30s`／動物2匹（しらたまは `white long-haired cat` と明示）／横の中央3分の1＋上1/3の余白／プラン別パレット／`No text, no chibi, no 3D, no photorealism`／季節モチーフ／行為の途中
  - **短縮版から外す**：`face fixed by the six reference images`（生成側に参照画像がなく機能しない。特定人物の顔の再現指示とも読まれうる）／`brand age 40s`（年齢の二重表記をやめ `early 30s` のみ）／動物の固有名
- **ネガティブ指定を必ず末尾に**：`No POP, no vivid colors, no chibi, no thick outlines, no 3D, no photorealism. No text, no letters, no signage.`
- Cocoは静物ではなく**行為の途中**を描く（お茶を持つ／紙を差し出す等）。記事の具体策を絵にする

### 週1本、無料の案内記事を別枠で足す（2026-08-24 Coco決定・恒久ルール）
**背景（実測）**：2026-08-18週のnote週間ビューは、公開済み114本の合計で**29**（1記事あたり週0.25）。原因は、**114本中108本がメンバー限定で、無料公開が実質ゼロ**だったこと。メンバー以外には本文が見えないため、note内の検索・おすすめ・タグからたどり着いた人が読者になる経路が塞がれていた。一方でスキ率は17%と高く、**流通の問題であって内容の問題ではない**。

- **週8本のfunnel noteは、すべて `members_only` のまま。無料にしない**（週8本の価値を削らない）
- **別枠で、案内型の無料記事を週1本足す**。週の合計は9本になる
  - `visibility: "public"` ／ `price: "0"` ／ `free_ratio: "1.0"` ／ `tier: "free_entry"`
  - `funnel_targets` は空。SNS投稿の予告とは紐づかない独立記事
- **プランを毎週交互にする**。組織 → 恋愛 → 組織…。両プランとも1,000人が目標なので、入口を片側に寄せない
- **その週の記事に紐づけない**。同じ週の記事にリンクすると同日リンクが発生してルール違反になるため、あわせて読むは**前週以前の同プラン記事2本**にする
- **角度は毎週変える**。常設案内2本（`向かない人から先に書く`）と同じ切り口を繰り返さない。例：「答えは配っていない。決め方のほうを置いている」「どんな夜に開く場所か」「一週間の使い方」
- 中身の必須要素：**①何を置いていて何を置いていないか ②向かない場面（先に書く） ③費用と定番プロミス ④在り方署名＋背中押し**
- 完成後チェック：その週に `public` の案内記事が1本あるか／前週と別のプランか／funnel note を無料にしていないか／角度が既存の案内記事と重なっていないか

**常設案内2本（`source_week: standing_guide`）は恒久的に `public`**。メンバーシップを売るための記事が有料だと、読める人が既に会員しかいない。

#### 週1本の無料枠は「まとめ記事（型A）」で書く（2026-08-25 Coco決定・恒久ルール／9/1週から適用）
**背景（実測）**：2026-08-18週のnote週間ビューは公開114本で29（1記事あたり週0.25）。スキ率は17%と高く、**流通の問題であって内容の問題ではない**。原因は無料記事が実質ゼロで、note内の検索・タグ・おすすめからたどり着く経路が塞がれていたこと。**足りないのはストックではなく、既存ストックへ人を連れてくる無料記事**（2026-08-25時点で有料110本に対し無料5本）。

- 週1本の無料枠は、**既存の有料記事8〜10本を一つのテーマで並べて紹介する「まとめ記事」**にする。中身は要約まで、処方は各記事へ送る
- **1本で既存記事8〜10本にリンクが張られる**ので、note内の回遊がいちばん立ち上がる。新規に書く量もいちばん少ない（並べ方だけを新しく書く）
- **未来の週のぶんを先に作らない**（2026-08-25 Coco指示）。**その週が来たタイミングで作る**。先に作ると、どれが公開済みでどれが未アップか分からなくなる
- プランは週ごとに交互（組織 → 恋愛 → 組織…）。既存の無料枠ルール（`visibility: public` ／ `price: "0"` ／ `free_ratio: "1.0"` ／ `tier: "free_entry"` ／ `funnel_targets` は空）はそのまま
- **あわせて読むの1本目は、必ず同プランの有料の代表記事に向ける**。無料で刺さった読者が、有料のいちばん良いところに落ちる形にする
- 型B（既存記事から診断・チェックリストだけを抜いて無料1本にする）と型C（一場面の完結記事・1,500〜2,500字）も使ってよいが、**既定は型A**。型を変えるときは作業報告で理由を書く

---

### noteタイトルの先頭に、プランの記号を置く（2026-08-24 Coco決定・恒久ルール）
一覧でどちらのプランの記事か判別できるようにする。パレットの色分けと併用する（色＝遠目、記号＝確認）。
- **X由来（組織と仕事）＝ `💼`** ／ **Threads由来（恋愛と関係）＝ `💗`**
- **選定基準は3軸：①意味が一発で通じるか ②小サイズ（一覧の16〜20px）で潰れないか ③プランの範囲を全部カバーできるか。**思想より共通認識レベルを優先する（2026-08-24 Coco決定）
- 落とした候補と理由：`🫶`（手が2つで小さいと潰れる）／`💍`（結婚・婚約に限定され、子育て・友人の記事とズレる）／`💕`（2つ重なって小サイズで塊になる）／`🤍`（装飾に見えて信号にならない）／`👔`（男性コード。女性の中間管理職を弾く）／`🤝`『⚖️`（手・細線で潰れる。⚖️は法律に読まれる）／`🏢`（企業に読まれ「働く人の悩み」感がない）／`🏆💰📈`（成果・金で痛みと合わない）
- **記号は単体でなくペアで読まれる。**💼単体なら副業・転職系に見えるが、一覧に💼と💗が並ぶと「仕事と恋愛の両方を同じ人が書いている」が一瞬で伝わる。これは定番プロミスの構造（原理は7つ、場面は無限）そのもので、ペアにすることでコストが差別化に変わる
- **この記号の仕事は「識別」であって「集客」ではない。**記号が出るのはメンバーシップの記事一覧で、見るのはすでに入会した人か販売ページにいる人。記号で新規が流入する経路はほぼないため、惹きつける力ではなく**一瞬で見分けられる力**で選ぶ。その基準で💼が最も速い（学習ゼロで「仕事のほう」と分かる）
- 払っているコスト：💼はnoteで副業・転職・ビジネスハック系が大量に使う記号。ただし**見る人はすでに導線の中にいる**ことと、**💗とペアで並ぶこと**の二点で中和されると判断した（2026-08-24 Coco決定）
- **1プラン1記号に固定する。**複数を使い分けると読者が学習できず、識別子として機能しない
- 旧案の 💎（X）は不採用。投稿のひとことの X＝💎／Threads＝🫶 が2026-08-24に廃止されたため、揃える根拠が消えた。かつ💎は「組織」を意味しない
- 記号はタイトルの1文字目に置く。**本文中の「あわせて読む」のリンク表記には付けない**（散文が濁るため。`internal_links` も記号なしで持つ）
- `reference/note_archive.json` の `title` は、記事の `title` と同じ形（記号あり）で持つ
- **既存記事への遡及はCocoの判断**（note.com側でのタイトル編集が必要）

### 季節モチーフだけ毎週入れ替える（それ以外は固定）

**正典は `reference/image_prompt_rules.json` の `seasonal_motifs.by_month`。下の表はその写しなので、変えるときは必ずJSONを直してからここを揃える。**

**季節名ではなく、公開日の「月」で引く**（2026-08-24 Coco決定・恒久ルール）。季節名で引くと月の境目が空く。実際、旧・7区分の要約から早春（梅）と初夏（紫陽花・菖蒲）が落ちていて、6月の記事に朝顔（旬7〜9月）と蓮（旬7〜8月）を当てる事故が起きた。

| 月 | モチーフ |
|---|---|
| **1月**（冬） | 椿・南天・水仙・初雪・裸木・灯り |
| **2月**（早春） | 梅・寒椿・水仙・残雪・福寿草 |
| **3月**（春の入り） | 梅・菜の花・沈丁花・土筆・桜（下旬） |
| **4月**（春） | 桜・藤・躑躅・霞・燕 |
| **5月**（晩春〜初夏） | 藤・躑躅・新緑・菖蒲・薔薇・若葉 |
| **6月**（梅雨） | **紫陽花・雨・若葉・青梅・菖蒲・蛍** |
| **7月**（夏） | 朝顔・蓮・蛍・風鈴・灯籠・夕立 |
| **8月**（晩夏） | 百日紅・向日葵・夕顔・蜩・夏の月・トンボ |
| **9月**（初秋） | すすき・名月・コスモス・萩・トンボ |
| **10月**（秋） | コスモス・柿・銀杏・紅葉（下旬）・秋の高い空 |
| **11月**（晩秋） | 紅葉・銀杏・山茶花・柿・落ち葉 |
| **12月**（冬） | 椿・南天・初雪・裸木・灯り |

- **6月＝梅雨は独立した月として扱う。** 朝顔と蓮を6月に当てない（1〜2ヶ月早い）。逆に紫陽花・青梅を7月に持ち越さない
- 前後の月にまたがるモチーフは両方に載せてあるので、月初・月末は隣の月から取ってよい
- **モチーフを増やさなくても、背景と空気で季節は出せる**（雨上がり／若葉を透ける光／濡れた石畳／雨の輪が残る水面）。反復が気になるときは、まず背景で散らす

### 完成後チェック（毎回必須）
`reference/image_prompt_rules.json` の `self_check` 12項目を実行する。特に——
- [ ] 全本にCocoと動物が登場しているか（人物なしがゼロか）
- [ ] `in her early thirties` が全本に入っているか／`elegant 40s woman` が残っていないか
- [ ] **Canvaの禁止語（young woman／brand age 40s／youthful／complexion／chest／bust-up）がゼロか**
- [ ] **全本の冒頭に正方形 1:1（1080x1080）の指定が入っているか**
- [ ] 動物とアングルの巡回本数が揃っているか
- [ ] 投稿時刻と時間帯のズレがゼロか
- [ ] **パレットがX＝寒色／Threads＝暖色の4組に収まり、3色目が cool ivory／warm ivory で分かれているか（温度またぎゼロ）**
- [ ] **着物の色がパレットと同じ温度か**（夜の濃紺は例外として可）
- [ ] 佇まいの一文が35本すべて別文で、本文テーマと噛み合っているか
- [ ] 季節モチーフが今週の季節に合っているか（前週の使い回しでないか）

---
