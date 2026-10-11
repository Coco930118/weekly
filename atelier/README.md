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

## 起動（普段はクラウド、ローカルは開発・非常用）

**社長の机はPCとiPhoneの両方から、同じ作業DBを1つだけ使う。** そのため本番はクラウドに1つだけ置き、
いつものURLを開けばよい状態にする（2026-10-11 Coco決定）。ローカル起動は開発・動作確認・クラウドが
落ちたときの非常用として残す。

### クラウド（本番）

手順と月額の目安は「クラウド配置」節。**URL：（設置後にここへ記載）**

### ローカル（開発・非常用）

リポジトリのルートで `python3 -m atelier.server.server` を実行し、`http://127.0.0.1:8765/atelier/` を開く。

直接編集にはサーバー側の `ATELIER_TOKEN` と、画面の「Coco操作の認証」に同じ値を入力する。
値は環境で管理し、ファイルやGitHubへ保存しない。未設定なら読取のみ。
既定はlocalhost限定（`--host` 省略時）で、インターネットへの公開を想定しない。

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

`--host 0.0.0.0` を渡すとlocalhost以外からも待ち受ける（コンテナ内での実行向け。手元のPCで
ローカルネットワーク公開する用途ではない——`ATELIER_TOKEN`の値が平文HTTPで流れるため）。
`--port`・`--db` も指定できる（`python3 -m atelier.server.server --help`）。

## クラウド配置

**候補の比較（2026-10-11時点の調査）。実際の請求は為替・規約変更で動く——費用はCocoが最終確認してから設置する。**

| | Fly.io | Render |
|---|---|---|
| 実行環境 | shared-cpu-1x・256MB、24時間稼働 | Starterプラン（0.5CPU・512MB） |
| 月額（実行） | 約$2.19 | $7 |
| 永続ストレージ | $0.15/GB/月（1GBで$0.15） | $0.25/GB/月（1GB以上から。Freeプランは不可） |
| HTTPS | 自動（`*.fly.dev`、無料） | 自動（`*.onrender.com`、無料） |
| 月額合計の目安 | **約$2.34**（≒350円） | 約$7.25（≒1,100円） |

作業DBはSQLiteファイル1つ（数MB程度）なので、どちらでも永続ストレージは最小構成（1GB）で足りる。
**Fly.ioを推奨**（実行コストが素員の桁で安い。固定の静的IPは不要——`*.fly.dev`のURLで足りるため、
追加の$2/月は発生させない）。為替レートで円換算は変わる。

### 手順（Fly.io・Cocoの承認後に実施）

1. Cocoが [fly.io](https://fly.io) でアカウントを作成し、支払い方法を登録する（Claudeの側では
   アカウント作成・支払い登録はできない）。`flyctl`（Fly CLI）をインストールし `fly auth login`。
2. リポジトリのルートで `fly launch --no-deploy` を実行。Dockerfileを検出して `fly.toml` を生成・
   確認する（リポジトリに下書きの `fly.toml` を用意済み。上書きされたら
   `[http_service] internal_port=8080` と `[mounts]`（`/data`への永続ボリューム）が入っているか確認）。
   永続ボリュームを聞かれたら作成する（1GBで十分）。聞かれなければ
   `fly volumes create coco_atelier_data --region nrt --size 1` を実行し、`fly.toml`の`[mounts]`に
   `source`を合わせる。
3. シークレットを設定（コード・画面には一切出さない）：
   ```bash
   fly secrets set ATELIER_TOKEN=（新しい値。ローカルの値と揃えなくてよい）
   fly secrets set ATELIER_ANTHROPIC_LIVE=1 ANTHROPIC_API_KEY=（鍵）
   fly secrets set ATELIER_OPENAI_LIVE=1 OPENAI_API_KEY=（鍵・使うなら）
   fly secrets set ATELIER_ORIGIN=https://（アプリ名）.fly.dev
   ```
4. `fly deploy`。完了後 `https://（アプリ名）.fly.dev/atelier/` がPC・iPhone Safariの両方から同じ
   作業DBを開く入口になる。
5. 動作確認後、このREADMEの「URL：（設置後にここへ記載）」を実際のURLに更新する。

**どちらが実施するか**：Cocoがこの手順をそのまま実行してもよいし（アカウント・支払いは必ずCoco）、
アプリ作成とボリューム作成だけ済ませたあと `fly tokens create deploy -a （アプリ名）` で作ったデプロイ
専用トークンをこのセッションに渡せば、Claude側で `fly deploy` を代行できる（アカウント全体の権限は渡らない）。

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
