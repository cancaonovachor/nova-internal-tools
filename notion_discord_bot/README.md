# notion-discord-bot

Notion の webhook を受け取って Discord に通知するツール。

## 全体構成（最終形）

```
Notion ──(webhook)──▶ Cloud Run (receiver)
                          │ publish
                          ▼
                      Pub/Sub topic ──▶ DLQ
                          │ push subscription
                          ▼
                     Cloud Run (worker) ──▶ Discord
```

receiver は受信して即 ack することに専念し、重い処理・リトライは Pub/Sub と worker に任せる。

## フェーズ

- **Phase 1 (今ここ)**: receiver のみ。Pub/Sub publish は stdout + `log.txt` に出力するスタブ。ngrok で Notion からの疎通を確認する。
- **Phase 2**: Pub/Sub を実配線し、worker サービスを追加（まだ Discord へはログ出力）。
- **Phase 3**: Discord Webhook 実送信、Cloud Run へデプロイ、署名検証本番化。

## Phase 1 の使い方

### 1. セットアップ

```bash
cd notion_discord_bot
uv sync
cp .env.example .env
```

### 2. 起動

```bash
uv run uvicorn receiver.main:app --reload --port 8080
```

疎通確認:

```bash
curl http://localhost:8080/healthz
```

### 3. ngrok で公開

別ターミナルで:

```bash
ngrok http 8080
```

表示された `https://xxxx.ngrok-free.app` を Notion の integration 設定の webhook URL に `/webhook/notion` を付けて登録する:

```
https://xxxx.ngrok-free.app/webhook/notion
```

### 4. verification_token の取り込み

Notion は最初のリクエストで `{"verification_token": "..."}` を POST してくる。
receiver のログに以下のような warning が出るので、その値を Notion 側の UI に入力して登録を完了させる:

```
WARNING  Notion verification_token received: secret_xxxxxxxxxxxxxxxxxx
```

同じ値を `.env` の `NOTION_VERIFICATION_TOKEN` にも設定してサーバーを再起動すると、以降のリクエストで署名検証が有効になる。

### 5. 受信イベントの確認

Notion 側で対象ページを更新すると、`log.txt` に JSON 1行で追記されていく。

```bash
tail -f log.txt
```

## ディレクトリ構成

```
notion_discord_bot/
├── receiver/            # Phase 1: FastAPI webhook 受信
│   ├── main.py
│   └── publisher.py     # Pub/Sub publish スタブ（stdout + log.txt）
├── common/
│   └── signature.py     # X-Notion-Signature 検証
├── pyproject.toml
├── .env.example
└── README.md
```
