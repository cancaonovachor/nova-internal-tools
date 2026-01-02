#!/bin/bash
set -e

# 色付き出力用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# デフォルト値
REGION="asia-northeast1"
PROJECT_ID=""

# 使い方を表示
usage() {
    echo "Usage: $0 [OPTIONS] COMMAND"
    echo ""
    echo "Choral Web ScraperをCloud Run Jobsにデプロイします。"
    echo ""
    echo "Options:"
    echo "  -p, --project-id     Google Cloud Project ID (必須)"
    echo "  -r, --region         Region (デフォルト: asia-northeast1)"
    echo "  -h, --help           このヘルプを表示"
    echo ""
    echo "Commands:"
    echo "  deploy               Cloud Run Jobsにデプロイ"
    echo "  run                  ジョブを手動実行"
    echo "  logs                 最新のログを表示"
    echo ""
    echo "Examples:"
    echo "  $0 -p my-project deploy"
    echo "  $0 -p my-project run"
    echo "  $0 -p my-project logs"
}

# 引数のパース
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        deploy|run|logs)
            COMMAND="$1"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# 必須パラメータのチェック
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: --project-id is required${NC}"
    usage
    exit 1
fi

if [ -z "$COMMAND" ]; then
    echo -e "${RED}Error: Command (deploy, run, or logs) is required${NC}"
    usage
    exit 1
fi

# プロジェクトIDを設定
echo -e "${YELLOW}Setting project to: ${PROJECT_ID}${NC}"
gcloud config set project "$PROJECT_ID"

# Cloud Run Jobsへのデプロイ
deploy_job() {
    echo -e "${GREEN}=== Deploying Web Scraper to Cloud Run Jobs ===${NC}"

    # Artifact Registryリポジトリの確認・作成
    echo -e "${YELLOW}Checking Artifact Registry repository...${NC}"
    if ! gcloud artifacts repositories describe choral-rss-bot --location="$REGION" &>/dev/null; then
        echo -e "${YELLOW}Creating Artifact Registry repository...${NC}"
        gcloud artifacts repositories create choral-rss-bot \
            --repository-format=docker \
            --location="$REGION" \
            --description="Choral RSS Bot images"
    fi

    # Cloud Run Jobが存在するか確認
    if ! gcloud run jobs describe choral-web-scraper --region="$REGION" &>/dev/null; then
        echo -e "${YELLOW}Creating Cloud Run Job...${NC}"

        # まずイメージをビルド
        gcloud builds submit --config=deploy/cloudbuild.web_scraper.yaml \
            --substitutions=SHORT_SHA=initial

        # ジョブを作成
        gcloud run jobs create choral-web-scraper \
            --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/choral-rss-bot/choral-web-scraper:initial" \
            --region="$REGION" \
            --memory=2Gi \
            --cpu=1 \
            --max-retries=1 \
            --task-timeout=10m \
            --set-env-vars="DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL},GEMINI_API_KEY=${GEMINI_API_KEY}"
    else
        # 既存ジョブを更新
        echo -e "${YELLOW}Updating existing Cloud Run Job...${NC}"
        gcloud builds submit --config=deploy/cloudbuild.web_scraper.yaml \
            --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)
    fi

    echo -e "${GREEN}Web Scraper deployed successfully!${NC}"
}

# ジョブを手動実行
run_job() {
    echo -e "${GREEN}=== Running Web Scraper Job ===${NC}"
    gcloud run jobs execute choral-web-scraper --region="$REGION" --wait
    echo -e "${GREEN}Job execution completed!${NC}"
}

# ログを表示
show_logs() {
    echo -e "${GREEN}=== Recent Logs ===${NC}"
    gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=choral-web-scraper" \
        --limit=50 \
        --format="table(timestamp,textPayload)"
}

# メイン処理
case $COMMAND in
    deploy)
        deploy_job
        ;;
    run)
        run_job
        ;;
    logs)
        show_logs
        ;;
esac

echo -e "${GREEN}=== Done! ===${NC}"
