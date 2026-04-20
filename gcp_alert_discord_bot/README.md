# gcp_alert_discord_bot

GCP の Cloud Billing 予算アラート / Cloud Monitoring アラートポリシーを Pub/Sub 経由で受け取り、Discord に整形通知するツール。

## 構成

```
Budget alert  ─┐
               ├─▶ Pub/Sub topic: gcp-alerts ─▶ Push subscription (OIDC) ─▶ Cloud Run ─▶ Discord webhook
Monitoring ───┘         (Cloud Monitoring notification channel type=pubsub)
```

## ローカル開発

```bash
cd gcp_alert_discord_bot
uv sync
cp .env.example .env            # DISCORD_WEBHOOK_URL は空のままで OK
uv run uvicorn app.main:app --reload --port 8080
```

動作確認: サンプル Budget ペイロードを base64 で包んで POST する。

```bash
python - <<'PY'
import base64, json, requests
data = {
  "budgetDisplayName": "starlit monthly",
  "alertThresholdExceeded": 0.5,
  "costAmount": 600,
  "budgetAmount": 1000,
  "currencyCode": "JPY",
}
body = {"message": {"data": base64.b64encode(json.dumps(data).encode()).decode(),
                    "attributes": {"billingAccountId": "019660-72BCBE-D80153"}}}
print(requests.post("http://localhost:8080/pubsub/push", json=body).text)
PY
```

`discord.txt` に整形結果が追記される。

## デプロイ

このツールは **tfvars を使わない**。固定値は `terraform/main.tf` の `locals`、機密値 (Discord webhook URL) は Secret Manager に直接投入する。

### 初回セットアップ

```bash
cd terraform
terraform init

# 1) APIs / AR / secret resource / SA を先行 (Cloud Run はイメージ必須なので後回し)
terraform plan -out tfplan \
  -target=google_project_service.apis \
  -target=google_artifact_registry_repository.repo \
  -target=google_secret_manager_secret.discord_webhook \
  -target=google_service_account.worker \
  -target=google_service_account.invoker
terraform apply tfplan

# 2) Discord webhook URL を Secret Manager に投入 (tfvars 経由しない)
echo -n 'https://discord.com/api/webhooks/...' | \
  gcloud secrets versions add gcp-alert-bot-discord-webhook --data-file=- \
    --project=starlit-road-203901

# 3) イメージを build & push
cd ..
gcloud builds submit . --config deploy/cloudbuild.yaml

# 4) 残り全部を apply
cd terraform
terraform plan -out tfplan
terraform apply tfplan
```

### 以後の運用

- **コード変更**: `gcloud builds submit` でイメージ push → `gcloud run deploy gcp-alert-discord-bot --image=<latest> --region=asia-northeast1` で新リビジョン
- **webhook URL のローテーション**: `gcloud secrets versions add` で新 version → `gcloud run deploy` (同じイメージでも OK) で Cloud Run に新 version を読ませる

## Budget を接続

1. Cloud Billing Console → Budgets & alerts → 対象予算を編集
2. Pub/Sub 通知で `projects/starlit-road-203901/topics/gcp-alerts` を指定
   - `terraform apply` 時点で `billing-budgets@system.gserviceaccount.com` への publisher 権限は付与済み

## Cloud Monitoring アラートを接続

1. `terraform output notification_channel_id` の値をコピー
2. 既存 or 新規のアラートポリシーの notification channels にそのチャンネルを追加
   - CLI:
     ```bash
     gcloud alpha monitoring policies update <policy-id> \
       --add-notification-channels=<channel-id> --project=starlit-road-203901
     ```

## ペイロード仕様参考

- Budget: https://cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications#notification_format
- Monitoring (Pub/Sub): https://cloud.google.com/monitoring/support/notification-options#pubsub
