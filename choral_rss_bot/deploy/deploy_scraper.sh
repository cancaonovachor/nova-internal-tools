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
STAGING_BUCKET=""

# 使い方を表示
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Google ADK Webスクレイピングエージェントをデプロイします。"
    echo ""
    echo "Options:"
    echo "  -p, --project-id     Google Cloud Project ID (必須)"
    echo "  -b, --bucket         Staging bucket (gs://で始まる) (Agent Engineデプロイ時に必須)"
    echo "  -r, --region         Region (デフォルト: asia-northeast1)"
    echo "  -h, --help           このヘルプを表示"
    echo ""
    echo "Commands:"
    echo "  scraper              Cloud RunにスクレイピングAPIをデプロイ"
    echo "  agent                Vertex AI Agent Engineにエージェントをデプロイ"
    echo "  all                  両方をデプロイ"
    echo ""
    echo "Examples:"
    echo "  $0 -p my-project scraper"
    echo "  $0 -p my-project -b gs://my-bucket agent"
    echo "  $0 -p my-project -b gs://my-bucket all"
}

# 引数のパース
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        -b|--bucket)
            STAGING_BUCKET="$2"
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
        scraper|agent|all)
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
    echo -e "${RED}Error: Command (scraper, agent, or all) is required${NC}"
    usage
    exit 1
fi

# プロジェクトIDを設定
echo -e "${YELLOW}Setting project to: ${PROJECT_ID}${NC}"
gcloud config set project "$PROJECT_ID"

# Cloud RunスクレイピングAPIのデプロイ
deploy_scraper() {
    echo -e "${GREEN}=== Deploying Scraper API to Cloud Run ===${NC}"

    # Artifact Registryリポジトリの確認・作成
    echo -e "${YELLOW}Checking Artifact Registry repository...${NC}"
    if ! gcloud artifacts repositories describe choral-rss-bot --location="$REGION" &>/dev/null; then
        echo -e "${YELLOW}Creating Artifact Registry repository...${NC}"
        gcloud artifacts repositories create choral-rss-bot \
            --repository-format=docker \
            --location="$REGION" \
            --description="Choral RSS Bot images"
    fi

    # Cloud Buildでビルド＆デプロイ
    echo -e "${YELLOW}Building and deploying with Cloud Build...${NC}"
    gcloud builds submit --config=deploy/cloudbuild.web_scraper.yaml

    # デプロイされたURLを取得
    SCRAPER_URL=$(gcloud run services describe choral-scraper-api \
        --region="$REGION" \
        --format='value(status.url)')

    echo -e "${GREEN}Scraper API deployed successfully!${NC}"
    echo -e "${GREEN}URL: ${SCRAPER_URL}${NC}"

    # URLを環境変数として保存
    export SCRAPER_API_URL="$SCRAPER_URL"
}

# Vertex AI Agent Engineのデプロイ
deploy_agent() {
    if [ -z "$STAGING_BUCKET" ]; then
        echo -e "${RED}Error: --bucket is required for agent deployment${NC}"
        exit 1
    fi

    echo -e "${GREEN}=== Deploying Agent to Vertex AI Agent Engine ===${NC}"

    # スクレイピングAPIのURLを取得（まだ設定されていない場合）
    if [ -z "$SCRAPER_API_URL" ]; then
        SCRAPER_API_URL=$(gcloud run services describe choral-scraper-api \
            --region="$REGION" \
            --format='value(status.url)' 2>/dev/null || echo "")

        if [ -z "$SCRAPER_API_URL" ]; then
            echo -e "${RED}Error: Scraper API not found. Deploy it first with 'scraper' command.${NC}"
            exit 1
        fi
    fi

    echo -e "${YELLOW}Using Scraper API URL: ${SCRAPER_API_URL}${NC}"

    # Discord Webhook URLを環境変数から取得
    if [ -z "$DISCORD_WEBHOOK_URL" ]; then
        echo -e "${YELLOW}Warning: DISCORD_WEBHOOK_URL not set. Agent will not send Discord notifications.${NC}"
    fi

    # Pythonスクリプトでデプロイ
    echo -e "${YELLOW}Deploying agent...${NC}"
    uv run python deploy/deploy_agent_engine.py deploy \
        --project-id "$PROJECT_ID" \
        --location us-central1 \
        --staging-bucket "$STAGING_BUCKET" \
        --scraper-api-url "$SCRAPER_API_URL"

    echo -e "${GREEN}Agent deployed successfully!${NC}"
}

# メイン処理
case $COMMAND in
    scraper)
        deploy_scraper
        ;;
    agent)
        deploy_agent
        ;;
    all)
        deploy_scraper
        echo ""
        deploy_agent
        ;;
esac

echo -e "${GREEN}=== Deployment completed! ===${NC}"
