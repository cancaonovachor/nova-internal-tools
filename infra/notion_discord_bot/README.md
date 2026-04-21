# Terraform for notion-discord-bot

Cloud Run (ingress + worker) / Cloud Tasks / Artifact Registry / Secret Manager を管理する。

## 方針

- **tfvars は作らない**。固定値は `variables.tf` の default / `main.tf` の locals に寄せる
- **機密値 (Notion token / API key / Discord webhook URL) は Terraform で管理しない**。
  secret リソースのみ Terraform で作成し、version は `gcloud secrets versions add` で投入する
- state backend は GCS (`gs://starlit-road-203901-tfstate`, prefix `notion-discord-bot`)

## 前提

- `gcloud auth application-default login` 済み
- Terraform >= 1.5
- `starlit-road-203901` で billing が有効

## 初回デプロイ

Cloud Run が secret の `:latest` を参照するため、secret に version が存在しない状態で
Cloud Run を作ると起動に失敗する。以下の順で apply する。

### 1) API / secret resource / 周辺を先行作成

```bash
cd infra/notion_discord_bot
terraform init
terraform apply \
  -target=google_project_service.apis \
  -target=module.artifact_registry \
  -target=google_secret_manager_secret.verification_token \
  -target=google_secret_manager_secret.api_key \
  -target=google_secret_manager_secret.discord_webhook \
  -target=google_secret_manager_secret.discord_deletion_webhook \
  -target=google_cloud_tasks_queue.queue \
  -target=google_service_account.ingress \
  -target=google_service_account.worker \
  -target=google_service_account_iam_member.ingress_self_user
```

### 2) Secret に version を投入

```bash
# Notion integration の Internal Integration Token
printf %s "$NOTION_API_KEY" | \
  gcloud secrets versions add notion-api-key --data-file=- --project=starlit-road-203901

# Notion subscription の verification token (subscribe 後の最初の POST から拾う)
printf %s "$NOTION_VERIFICATION_TOKEN" | \
  gcloud secrets versions add notion-verification-token --data-file=- --project=starlit-road-203901

# Discord webhook URL (enable_discord_webhook=true のとき必須)
printf %s "$DISCORD_WEBHOOK_URL" | \
  gcloud secrets versions add notion-bot-discord-webhook --data-file=- --project=starlit-road-203901

# page.deleted 用の別チャネル webhook (enable_discord_deletion_webhook=true のときのみ必要)
printf %s "$DISCORD_DELETION_WEBHOOK_URL" | \
  gcloud secrets versions add notion-bot-discord-deletion-webhook --data-file=- --project=starlit-road-203901
```

### 3) コンテナイメージを build & push

```bash
cd ../../notion_discord_bot
gcloud builds submit . --config deploy/cloudbuild.yaml
```

### 4) 残りを apply (Cloud Run x2 + IAM)

```bash
cd ../infra/notion_discord_bot
terraform apply
```

### 5) Notion subscription に webhook URL を登録

```bash
terraform output ingress_webhook_url
# このURL を Notion integration 側に登録
```

## 旧構成からの移行 (一度きり)

旧 `notion_discord_bot/terraform/` ディレクトリから当ディレクトリへ state を移行する手順。

```bash
cd infra/notion_discord_bot
terraform init

# 旧構成にあった secret_version リソース (tfvars からの流し込み) を state から除外。
# 実体の secret version は Secret Manager に残るので、Cloud Run の起動には影響しない。
terraform state rm google_secret_manager_secret_version.verification_token_v1 || true
terraform state rm google_secret_manager_secret_version.api_key_v1 || true
terraform state rm 'google_secret_manager_secret_version.discord_webhook_v1[0]' || true
terraform state rm 'google_secret_manager_secret_version.discord_deletion_webhook_v1[0]' || true

# moved ブロックで artifact_registry 移動は自動。確認:
terraform plan
# → "No changes" になれば完了。差分が出た場合は enable_discord_* フラグと
#   既存リソースの状態 (env の有無) が一致しているか確認すること。
```

## 更新

コード変更後の再デプロイ:

```bash
# 新イメージを push (同タグ上書きでも可)
cd notion_discord_bot
gcloud builds submit . --config deploy/cloudbuild.yaml

# Cloud Run は同じ image_url を参照しているので revision を強制するには:
cd ../infra/notion_discord_bot
terraform apply \
  -replace=google_cloud_run_v2_service.ingress \
  -replace=google_cloud_run_v2_service.worker \
  -replace=google_cloud_run_v2_service_iam_member.ingress_public \
  -replace=google_cloud_run_v2_service_iam_member.ingress_invokes_worker
# (IAM member も一緒に -replace しないと invoker binding が落ちる)
```

## 出力

```bash
terraform output
# ingress_webhook_url = "https://notion-discord-bot-ingress-xxxxx-an.a.run.app/webhook/notion"
```
