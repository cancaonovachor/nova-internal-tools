#!/bin/bash

# Cloud Run Jobデプロイスクリプト

set -e

# 変数設定
PROJECT_ID=${1:-"starlit-road-203901"}
REGION=${2:-"asia-northeast1"}
JOB_NAME="choral-rss-bot"
IMAGE_NAME="choral-rss-bot"

echo "=== Cloud Run Job デプロイ開始 ==="
echo "プロジェクトID: $PROJECT_ID"
echo "リージョン: $REGION"
echo "ジョブ名: $JOB_NAME"
echo ""

# プロジェクトIDを設定
gcloud config set project $PROJECT_ID

# 必要なAPIを有効化
echo "必要なAPIを有効化中..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable bigquery.googleapis.com

# Dockerイメージをビルドしてプッシュ
echo "Dockerイメージをビルド中..."
docker build --platform linux/amd64 -t asia-northeast1-docker.pkg.dev/$PROJECT_ID/$IMAGE_NAME/$IMAGE_NAME:latest .

echo "Dockerイメージをプッシュ中..."
docker push asia-northeast1-docker.pkg.dev/$PROJECT_ID/$IMAGE_NAME/$IMAGE_NAME:latest

# job.yamlのPROJECT_IDを置換
echo "job.yamlを更新中..."
sed "s/PROJECT_ID/$PROJECT_ID/g" job.yaml > job-deployed.yaml

# Cloud Run Jobをデプロイ
echo "Cloud Run Jobをデプロイ中..."
gcloud run jobs replace job-deployed.yaml --region=$REGION

echo ""
echo "=== デプロイ完了 ==="
echo "ジョブを実行するには以下のコマンドを使用してください:"
echo "gcloud run jobs execute $JOB_NAME --region=$REGION"
echo ""
echo "ジョブの状態を確認するには:"
echo "gcloud run jobs describe $JOB_NAME --region=$REGION"
echo ""
echo "ログを確認するには:"
echo "gcloud logging read \"resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME\" --limit=50 --format=\"table(timestamp,textPayload)\""

# 一時ファイルを削除
rm -f job-deployed.yaml