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
- **Monitoring → topic の publisher IAM は明示付与が必要**: 「自動付与される」のは Budget 側だけ。Monitoring の Pub/Sub notification channel は publisher 権限を一切自動付与しない。落とし穴の症状は「alert policy も channel も ACTIVE / 検証も OK なのに Discord に何も来ない」+ Monitoring 側にエラーログも残らない (silent drop)。`google_pubsub_topic_iam_member.monitoring_publisher` で `service-<proj_num>@gcp-sa-monitoring-notification` に `roles/pubsub.publisher` を付与
- **Budget の publisher IAM は Terraform 管理外**: `billing-budgets@system` は "Budget を Pub/Sub topic 宛に設定" した瞬間に GCP が自動付与する。Budget 未設定の段階で Terraform から付与しようとすると 400 になるため任せる
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

## 管理している Alert Policy (他ツール向け)

このツールは Pub/Sub → Discord の「通知配信インフラ」も兼ねている。`infra/gcp_alert_discord_bot/main.tf` に他ツールのエラー監視用 alert policy をまとめて定義している:

| Policy | 対象 | 通知先 |
|---|---|---|
| `cloud_run_error` | Cloud Run services (gcp-alert-discord-bot 除く) の `severity>=ERROR` | Discord (pubsub channel 経由) |
| `cloud_run_job_error` | Cloud Run Jobs の `severity>=ERROR` | Discord |
| `self_error` | gcp-alert-discord-bot 自身の `severity>=ERROR` | email (`local.self_alert_email`) |

### フィルタ設計の注意点

- **Cloud Run access log (5xx) の除外**: `NOT httpRequest.status:*` を付けてアプリログのみ拾う。Cloud Run は 5xx リクエストを severity=ERROR の access log として残すが、これは `httpRequest.status` フィールドを持つので除外できる。`logger.exception` 由来の traceback log は持たないので通る
- **通知ループ防止**: `cloud_run_error` は `service_name!="gcp-alert-discord-bot"` で自身を除外必須。自身のエラーを Discord 経路に流すと、失敗した通知処理が再度 ERROR を出して無限ループする
- **self_error → email**: 自身のエラーは別経路の email で受ける。email channel は初回 apply 後に GCP から verification メールが届くので受信者がリンクを踏む必要あり
- **新規サービスは自動で拾う**: `cloud_run_error` は service_name の allow-list ではなく deny-list (自身のみ除外) なので、新しい Cloud Run service を deploy すれば自動で監視対象になる。ノイズが多ければ filter に exclusion を追加する方針

### 連動する各ツール側の挙動

alert が警報ループしないように、監視される側のツールでは「リトライで救える失敗」を `logger.exception` ではなく `logger.warning` に落としておく設計が推奨。例: `notion_discord_bot` worker は Cloud Tasks の `X-CloudTasks-TaskRetryCount` を見て最終試行のみ exception を呼ぶ。
