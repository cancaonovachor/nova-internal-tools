# Terraform for notion-discord-bot

Cloud Run (ingress + worker) / Cloud Tasks / Artifact Registry / Secret Manager を管理する。

## 前提

- `gcloud` で対象プロジェクトに認証済み（`gcloud auth application-default login`）
- Terraform >= 1.5
- Billing が有効な GCP プロジェクト

## 変数の設定

```bash
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集して secrets を入れる
```

> `*.tfvars` は `.gitignore` 済み。Terraform state には sensitive 値が入るので、共有する場合は GCS backend + state 暗号化を検討すること。

## 初回デプロイ手順

Cloud Run のコンテナイメージが Artifact Registry に存在していないと Terraform が失敗するため、以下の順で apply する。

```bash
# 1) init と API / AR / Secrets / Cloud Tasks / SA の先行作成
terraform init
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

# 2) イメージを build & push (リポジトリルートから実行)
gcloud auth configure-docker asia-northeast1-docker.pkg.dev
cd notion_discord_bot
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest \
  --config ../<none> .  # Dockerfile の場所に応じて調整
# もしくは手動ビルド:
# docker build -f deploy/Dockerfile -t ... .
# docker push ...

# 3) 残りを apply（Cloud Run 2サービス + IAM）
cd terraform
terraform apply
```

## ビルドコマンド例（リポジトリルートから）

```bash
gcloud builds submit notion_discord_bot \
  --tag asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest \
  --dockerfile notion_discord_bot/deploy/Dockerfile
```

> 注: `gcloud builds submit` の `--dockerfile` はバージョンによってはサポートされない。その場合は `cloudbuild.yaml` を使うか、`docker build -f deploy/Dockerfile -t <image> .` + `docker push <image>` で対応。

## 出力

```bash
terraform output
# ingress_webhook_url = "https://notion-discord-bot-ingress-xxxxx-an.a.run.app/webhook/notion"
```

この URL を Notion の integration の subscription webhook URL に登録する。

## 更新

コード変更後の再デプロイ：

```bash
# 新しいイメージを push (same tag を上書きするか新タグを使う)
gcloud builds submit notion_discord_bot \
  --tag asia-northeast1-docker.pkg.dev/YOUR_PROJECT/notion-discord-bot/notion-discord-bot:latest

# Cloud Run は同じ image_url を参照しているので、revision を強制するには
terraform apply -replace=google_cloud_run_v2_service.ingress -replace=google_cloud_run_v2_service.worker
# もしくは image_tag を変更して apply
```

## クリーンアップ

```bash
terraform destroy
```

Secret Manager の secret は `deletion_protection` なしで作っているが、実運用では有効化を検討。
