# notion-discord-bot

Notion webhook を受信し、Notion API で情報を補完して Discord に通知するツール。

アーキテクチャの詳細は [architecture.md](./architecture.md) を参照。

## 構成 (Phase 2)

```
Notion ──(webhook)──▶ Cloud Run ingress ──enqueue──▶ Cloud Tasks ──▶ Cloud Run worker ──▶ Discord
```

- **ingress**: webhook 受信 / 署名検証 / イベントフィルタ / Cloud Tasks への投入
- **Cloud Tasks**: リトライ + `task name` によるイベント ID 単位の重複排除
- **worker**: Notion API で page/author/block を補完 → Discord メッセージに整形 → 送信

## ディレクトリ

```
notion_discord_bot/
├── ingress/            # FastAPI: webhook 受信 + enqueue
│   └── main.py
├── worker/             # FastAPI: Cloud Tasks → enrich → Discord
│   └── main.py
├── common/
│   ├── signature.py        # Notion X-Notion-Signature 検証
│   ├── task_enqueuer.py    # HTTPDirect / CloudTasks の切り替え
│   ├── notion_client.py    # Notion REST API + enrichment
│   ├── discord_format.py   # enriched event → markdown
│   └── discord_sender.py   # File (stub) / Webhook (本番)
├── deploy/
│   ├── Dockerfile          # ingress/worker 共用
│   └── .dockerignore
├── terraform/              # GCP リソース定義
├── architecture.md
└── pyproject.toml
```

## ローカル開発

### セットアップ

```bash
cd notion_discord_bot
uv sync
cp .env.example .env
# .env を編集: NOTION_VERIFICATION_TOKEN / NOTION_API_KEY を設定
```

### 起動（3 ターミナル）

```bash
# ターミナル 1: worker (port 8081)
uv run uvicorn worker.main:app --reload --port 8081

# ターミナル 2: ingress (port 8080) — WORKER_URL で worker を指す
uv run uvicorn ingress.main:app --reload --port 8080

# ターミナル 3: ngrok で 8080 を公開
ngrok http 8080
```

ingress は `CLOUD_TASKS_QUEUE` が未設定だと `HTTPDirectEnqueuer` を使い、`WORKER_URL` に直接 POST する。

### Notion subscription 設定

1. ngrok が出した `https://xxxx.ngrok-free.app` + `/webhook/notion` を Notion integration の webhook URL に登録
2. 初回 webhook 受信時に ingress のログに `verification_token` が出るので、それを Notion UI と `.env` の両方に入れる
3. サーバを再起動すると署名検証が有効になる

### 動作確認

Notion でページを更新 → `log.txt` に生イベント（ingress／worker どちらも標準ログに出る）、`discord.txt` に整形済みメッセージが追記される。

`DISCORD_WEBHOOK_URL` を `.env` に入れると `WebhookDiscordSender` に切り替わり、実際の Discord チャンネルに送信される。

## Cloud Run デプロイ

### 1. Terraform で GCP リソースを準備

詳細は [terraform/README.md](./terraform/README.md) を参照。

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# secrets を記入
terraform init
# Cloud Run 以外を先に作成（イメージがまだ存在しないため）
terraform apply \
  -target=google_project_service.apis \
  -target=google_artifact_registry_repository.repo \
  -target=google_secret_manager_secret.verification_token \
  -target=google_secret_manager_secret_version.verification_token_v1 \
  -target=google_secret_manager_secret.api_key \
  -target=google_secret_manager_secret_version.api_key_v1 \
  -target=google_secret_manager_secret.discord_webhook \
  -target=google_cloud_tasks_queue.queue \
  -target=google_service_account.ingress \
  -target=google_service_account.worker
```

### 2. イメージを build & push

```bash
cd notion_discord_bot
gcloud auth configure-docker asia-northeast1-docker.pkg.dev
gcloud builds submit . \
  --tag asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest \
  --config=- <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'deploy/Dockerfile', '-t', '${_IMAGE}', '.']
  - name: gcr.io/cloud-builders/docker
    args: ['push', '${_IMAGE}']
substitutions:
  _IMAGE: asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest
images:
  - ${_IMAGE}
EOF
```

もしくはローカル Docker で：

```bash
docker build -f deploy/Dockerfile -t asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest .
docker push asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest
```

### 3. Cloud Run を apply

```bash
cd terraform
terraform apply
terraform output ingress_webhook_url
```

出力された webhook URL を Notion subscription に登録する（ローカル開発と同じ verification_token 登録フロー）。

### 再デプロイ

イメージを push し直した後：

```bash
cd terraform
terraform apply -replace=google_cloud_run_v2_service.ingress -replace=google_cloud_run_v2_service.worker
```

## 環境変数まとめ

### ingress
| 変数 | 必須 | 説明 |
|---|---|---|
| `NOTION_VERIFICATION_TOKEN` | 推奨 | 署名検証用。未設定だと検証スキップ |
| `NOTION_ALLOWED_EVENTS` | 任意 | enqueue するイベント種別 (カンマ区切り) |
| `WORKER_URL` | 任意 | HTTPDirectEnqueuer の送信先。デフォルト `http://localhost:8081/tasks/notion-event` |
| `CLOUD_TASKS_QUEUE` | 本番 | 設定すると CloudTasksEnqueuer に切り替わる |
| `CLOUD_TASKS_LOCATION` | 本番 | Cloud Tasks queue のリージョン |
| `GOOGLE_CLOUD_PROJECT` | 本番 | project id |
| `WORKER_INVOKER_SA` | 本番 | Cloud Tasks が OIDC トークン発行に使う SA |

### worker
| 変数 | 必須 | 説明 |
|---|---|---|
| `NOTION_API_KEY` | 推奨 | 未設定だと enrichment をスキップ |
| `DISCORD_WEBHOOK_URL` | 任意 | 設定すると実際に Discord に送信 |
| `DISCORD_OUTPUT_PATH` | 任意 | FileDiscordSender の出力先。デフォルト `discord.txt` |

## 将来拡張 (未実装)

architecture.md priority 4 以降：

- デバウンス（Firestore / Memorystore を使った `page_id` ベースの抑制）
- 監視・メトリクス
- 通知テンプレートのカスタマイズ
