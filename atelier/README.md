# Coco Atelier

会社運用・社員編成の正典は [Coco Atelier 会社運用・社員編成 正典 v2.0](../docs/coco_atelier_company_spec.md)。
投稿本文の指示文は `atelier/canon/` の媒体別正典を使用し、社長Cocoの承認なしに変更しない。

## 会社の目的

**Cocoの現場の事実を、軍師と哲学者の声のまま、規則を破らずに出し続ける。**

ミスは隠さず、人ではなく工程へ戻し、次の仕組みに変える。

## 稼働部門

- X01〜X14
- Threads01〜Threads21
- X短文01〜X短文14
- note：保留・未稼働

社員構成は `config/employees.json`、通常ルート・停止ルート・改善ルートは `config/workflow.json`。

## 判断境界

- 指示文内で迷う：取締役会が現行ルール内で最適解を選び、進める。
- 素材不足・事実不明・指示外：推測せず停止して課長へ。
- ルール変更：実行せず副社長から社長Cocoへ提案。Coco承認後のみ、次の新規投稿から適用。
- 副社長が会社として止めるのは「事実が曲がった / 声が混ざった / 工程に戻っていない」の3つだけ。

## 起動

リポジトリのルートで `python3 -m atelier.server.server` を実行し、`http://127.0.0.1:8765/atelier/` を開く。

直接編集にはサーバー側の `ATELIER_TOKEN` と、画面の「Coco操作の認証」に同じ値を入力する。
値は環境で管理し、ファイルやGitHubへ保存しない。未設定なら読取のみ。
サーバーはlocalhostに限定し、インターネットへの公開を想定しない。

## 作業DB

作業DBは `atelier/.local/work.sqlite3`。
SQLiteはGit管理しない。
weeklyの公開正本は読取対象であり、Atelierの作業状態から公開JSONを自動変更しない。

## AI接続

**未接続のまま。**
今回の社員編成・会社運用の変更ではOpenAI接続、AI生成、x_06 / E567送信、公開処理の変更を行わない。
`openai_driver.py` は実通信を行わず、実行要求は安全停止する。

## 検証

```bash
python3 -m unittest discover -s atelier/tests -v
node --test atelier/tests/*.test.mjs
```

PlaywrightとChromiumが利用可能な環境では：

```bash
python3 atelier/tests/browser_check.py
```
