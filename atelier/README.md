# Coco Atelier

確定仕様の復元。役割・制作工程の正典は [実装仕様書](../docs/coco_atelier_spec.md)。投稿・素材・文章ルールの正典は既存weeklyと `rules/`。社員構成は `config/employees.json`、工程・前後工程・レビュー担当は `config/workflow.json`。

過去ソースはGitHub履歴／この作業環境で確認できなかったため、指定された `.mjs`・`server.py`・`ai_runtime.py`・`openai_driver.py` 構成で確定仕様を再構成した。過去ソースとのバイト単位の一致は未検証。

## 起動

リポジトリのルートで `python3 -m atelier.server.server` を実行し、`http://127.0.0.1:8765/atelier/` を開く。Python標準ライブラリのみ使用する。

直接編集にはサーバー側の `ATELIER_TOKEN` と、画面の「Coco操作の認証」に同じ値を入力する。値は環境で管理し、ファイルやGitHubへ保存しない。未設定なら読取のみ。tokenはブラウザのメモリだけで保持する。サーバーはlocalhostに限定し、インターネットへの公開を想定しない。

作業DBは `atelier/.local/work.sqlite3`。`--db /tmp/atelier-work.sqlite3` で場所を指定できる。候補・theme／axis・revision・編集履歴・保護情報・採用・レビュー・実行ログはこのDBへ保存する。SQLiteはGit管理しない。weeklyのpublic_okは読取値であり、Atelier採用／作業状態から書き換えない。投稿本文の公開正本はweeklyであり、DBの候補は作業案である。

## 編集・復元

A/Bを同時表示し、通常SNSはCも表示する。note・診断はA/B。投稿の基準はCocoが設定し、候補から変更できない。編集diffを確認して作業DBへ保存する。競合時は入力を保持し、現在の保存版を提示する。再読込後に差分を比較する。

履歴は投稿単位。復元は新しいrevisionを作り、候補revisionも単調増加させる。基準変更・候補編集・復元ではレビュー／採用を再確認対象にする。

Coco変更位置をrevision・候補・フィールドとともに記録する。保護されたフィールドへのAI変更は、位置の曖昧な再対応付けを避けるためフィールド全体で停止する。ID20の最小変更案は提案diffとして保持し、Cocoが確認して直接編集する。意味・事実・theme／axisの一致を機械的に保証するものではない。NEEDS_SPLITは明示された開始箇所を記録して停止する。

## AI接続・品質監査

OpenAI driverは未完成・未確定。実通信コードはなく、キーが存在してもAIを有効化しない。実行要求は本文・素材をproviderへ送らず停止し、状態コードだけを記録する。x_06／E567をAIへ送信する処理はない。

`ai_runtime.py` はprovider境界と結果保存境界。結果保存時にも社員権限・投稿／候補revision・Coco保護・基準逸脱を検査する。結果保存境界はサーバー内部のもので、HTTPからAI結果を注入するAPIは設けていない。

既存 `tools/full_check.py` 等は維持し、今回の復元では品質検査による公開状態の自動更新や正典変更を行わない。ID24のルール案はCoco確認対象であり、正典書込み権限を持たない。Git push・公開JSON反映・画像生成は今回の対象外。

## 検証

`python3 -m unittest discover -s atelier/tests -v`

`node --test atelier/tests/*.test.mjs`

PlaywrightとChromiumが利用可能な環境では `python3 atelier/tests/browser_check.py` で画面操作も検証する。

テストは一時DB・テスト用投稿・provider保存境界への固定fixtureを使用する。AI通信は行わない。
