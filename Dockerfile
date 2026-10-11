# Coco Atelier（社長の机）クラウド配置用。標準ライブラリのみで動くので依存インストールは無い。
# 作業DBは永続ボリュームを /data にマウントして使う（デプロイ・再起動で消えない）。
FROM python:3.12-slim

WORKDIR /app
COPY . /app

EXPOSE 8080

CMD ["python3", "-m", "atelier.server.server", "--host", "0.0.0.0", "--port", "8080", "--db", "/data/work.sqlite3"]
