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
- 完成投稿：副社長がCoco確認前に「事実が曲がった / 声が混ざった / 工程に戻っていない」の3点だけを見る。文は直さず、3点以外で止めない。
- 素材不足・事実不明・指示外：推測せず停止。課長が質問を作り、秘書が社長の机の1つのキューへ並べる。
- 同種3回：監査委員会が検知して副社長へ渡し、副社長が提案形式にまとめて秘書経由でCocoへ。
- ルール変更：Coco承認後のみ、次の新規投稿から適用。部長は実装しない。

## 起動

リポジトリのルートで `python3 -m atelier.server.server` を実行し、`http://127.0.0.1:8765/atelier/` を開く。

直接編集にはサーバー側の `ATELIER_TOKEN` と、画面の「Coco操作の認証」に同じ値を入力する。
値は環境で管理し、ファイルやGitHubへ保存しない。未設定なら読取のみ。
サーバーはlocalhostに限定し、インターネットへの公開を想定しない。

取材社員（素材を話す）・投稿社員・副社長のAI呼び出しを動かすには、サーバー起動前に
`ATELIER_ANTHROPIC_LIVE=1` と `ANTHROPIC_API_KEY` も環境変数で設定する（下記「AI接続」）。
未設定のままでも画面は開けるが、「素材を話す」はAI未接続のエラーになる。

起動例：
```bash
export ATELIER_TOKEN=（任意の値）
export ATELIER_ANTHROPIC_LIVE=1
export ANTHROPIC_API_KEY=（GitHub Secretsと同じ鍵）
python3 -m atelier.server.server
```

## 作業DB

作業DBは `atelier/.local/work.sqlite3`。
SQLiteはGit管理しない。
weeklyの公開正本は読取対象であり、Atelierの作業状態から公開JSONを自動変更しない。

## AI接続

**取材社員・投稿社員はAnthropic（Claude）、課長・取締役会・副社長はOpenAI（ChatGPT）に接続**
（2026-10-10 実接続を対象に変更。正典は `docs/coco_atelier_company_spec.md`「プロバイダ（provider）の役割分担」）。
監査委員会・秘書はモデルなし。

`ATELIER_ANTHROPIC_LIVE=1` と `ANTHROPIC_API_KEY`（Anthropic用）、必要に応じて
`ATELIER_OPENAI_LIVE=1` と `OPENAI_API_KEY`（OpenAI用）を設定しない限り、各providerは未接続のまま
安全停止する（`ProviderUnavailable`）。指示文（正典）はproviderで変えない。

## 検証

```bash
python3 -m unittest discover -s atelier/tests -v
node --test atelier/tests/*.test.mjs
```

PlaywrightとChromiumが利用可能な環境では：

```bash
python3 atelier/tests/browser_check.py
```
