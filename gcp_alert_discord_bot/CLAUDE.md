# CLAUDE.md — gcp_alert_discord_bot

GCP Billing Budget / Cloud Monitoring の通知を Pub/Sub 経由で受けて Discord に流す単一 Cloud Run サービス。

## 構成の要点

- **単一 Cloud Run** (`gcp-alert-discord-bot`): Pub/Sub push (OIDC) を `/pubsub/push` で受けて整形 → Discord webhook へ
- **Pub/Sub topic**: `gcp-alerts` に Budget / Monitoring の両方を流す。`common/formatter.py::format_pubsub_message` がペイロード形状で判別
- **SA 2 つ**: `gcp-alert-bot-worker` (Cloud Run runtime), `gcp-alert-bot-invoker` (Pub/Sub push の OIDC identity)
- **Secret**: `gcp-alert-bot-discord-webhook`。空なら `FileDiscordSender` にフォールバック

## notion_discord_bot との違い

- worker/ingress を分けていない (Discord へ投げるだけで重い処理なし)
- 署名検証は Pub/Sub push の OIDC で代替 (invoker SA only で Cloud Run を invoke 可)
- 受信側は正規化済み JSON を返せばよく Cloud Tasks 不要 (Pub/Sub 自体が retry する)

## ローカル開発

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8080
```

`README.md` に curl/python でのサンプル POST 例あり。

## 落とし穴 (想定 / 踏んだもの)

- **Pub/Sub push の OIDC**: subscription 作成前に `pubsub service agent` に `serviceAccountTokenCreator` を付ける必要がある (Terraform で済ませている)
- **Budget / Monitoring publisher IAM は Terraform で管理しない**: 対象 SA (`billing-budgets@system`, `service-<proj_num>@gcp-sa-monitoring-notification`) は "Budget 設定" / "Monitoring 通知チャンネル作成" の時点で初めてプロジェクトに現れる。先回りして IAM を振ろうとすると 400。GCP が自動付与するので任せる
- **Cloud Run の `/healthz` 予約**: 今回は `/health` を使用 (notion_discord_bot と同様)

## 設定ポリシー (feedback_no_tfvars.md 参照)

- **tfvars を使わない**。`terraform.tfvars` ファイルは作らない
- 固定値 (project_id / project_number / region 等) は `main.tf` の `locals` に集約
- 機密値 (Discord webhook URL) は Terraform で **secret resource のみ管理**。version は `gcloud secrets versions add` でアウトオブバンドに投入
- Cloud Run は secret `:latest` ref なので、初回は **Secret version を投入してから** 全体 apply しないと Cloud Run が起動失敗する

## ペイロード判別ルール (`common/formatter.py`)

| 条件 | 種別 |
|---|---|
| `body["incident"]` あり | Cloud Monitoring |
| `body["budgetDisplayName"]` or `body["budgetAmount"]` | Budget |
| attrs に `billingAccountId` / `schemaVersion` | Budget (fallback) |
| その他 | `format_unknown` で JSON をそのまま表示 |

## コード規約

- Python 3.12+ / uv / FastAPI
- secrets は Secret Manager → Cloud Run env
- ログは stdout (`logging.INFO`)。Cloud Run 側で拾える
