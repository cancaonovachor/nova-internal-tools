# Choral RSS Bot

合唱コミュニティのためのRSS収集・通知Botです。
世界中の合唱ニュースを収集し、LLM (Google Gemini) を使用して日本語に翻訳・要約した上でDiscordに通知します。

## 機能
- **マルチソースRSS**: 国内・海外の複数のRSSフィードを監視
- **記事全文スクレイピング**: 可能であれば記事ページから本文を取得し、より詳細な要約を生成
- **LLM要約・翻訳**: 英語記事も日本語記事も、Google Geminiで要約して読みやすく整形
- **Discord通知**: Webhookを使用して指定のチャンネルにリッチなメッセージを送信
- **Dry Runモード**: ローカルで挙動を確認できるテストモード搭載
- **重複防止**: 送信済み記事を記録し、重複投稿を回避

## 必要要件
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (Dependency Manager)
- Google AI Studio API Key (Gemini)
- Discord Webhook URL

## セットアップ

### 1. インストール
本プロジェクトは `uv` で管理されています。

```bash
cd choral_rss_bot
uv sync
```

### 2. 環境変数の設定
`.env.example` をコピーして `.env` を作成してください。

```bash
cp .env.example .env
```

`.env` を編集し、以下の値を設定します：
- `DISCORD_WEBHOOK_URL`: 通知先のDiscord Webhook URL
- `GEMINI_API_KEY`: Google GeminiのAPI Key

### 3. 設定ファイル (Optional)
`config.yaml` で監視対象のRSSフィードを変更できます。

## 使い方

### Web Scraper Agent (Google ADK)
Google ADKを使用したAIエージェントで、合唱関連サイト（日本合唱連盟、パナムジカ）をスクレイピングし、記事を要約してDiscordに通知します。

#### Cloud Run APIを使用する場合（推奨）
デプロイ済みのCloud Run APIを使用してスクレイピングを実行します。

```bash
# 表示のみ（Discord送信しない）
SCRAPER_API_URL="https://choral-scraper-api-938216897098.asia-northeast1.run.app" \
  uv run python -m scraper.main --mode local --ignore-history

# Discord送信あり
SCRAPER_API_URL="https://choral-scraper-api-938216897098.asia-northeast1.run.app" \
  uv run python -m scraper.main --mode discord --ignore-history
```

#### ローカルでAPIも起動する場合
Playwrightを使用してローカルでスクレイピングを実行します。

```bash
# ターミナル1: API起動
uv run python -m scraper.api

# ターミナル2: エージェント実行
SCRAPER_API_URL="http://localhost:8080" \
  uv run python -m scraper.main --mode local
```

**オプション:**
- `--mode local`: 表示のみ（Discord送信しない）
- `--mode discord`: Discord送信あり
- `--ignore-history`: 履歴を無視して全記事を処理

### RSS Bot（従来版）
RSSフィードから記事を収集し、Discordに通知します。

```bash
# 表示のみ（Discord送信しない）
uv run python -m rss.main --mode local

# Discord送信あり
uv run python -m rss.main --mode discord
```

送信した記事は履歴に記録され、次回以降スキップされます。

## ディレクトリ構成
```
choral_rss_bot/
├── rss/                    # RSS Bot
│   ├── main.py             # メインスクリプト
│   ├── llm_helper.py       # LLM処理（固有名詞解説など）
│   └── config.yaml         # RSSフィード設定
├── scraper/                # Web Scraper Agent
│   ├── main.py             # エージェント実行スクリプト
│   ├── agent.py            # ADKエージェント定義
│   ├── api.py              # Cloud Run用FastAPI
│   ├── api_tools.py        # API呼び出しツール
│   └── tools.py            # Playwrightスクレイピング
├── common/                 # 共通モジュール
│   └── storage.py          # 履歴保存（JSON/Firestore）
├── deploy/                 # デプロイ設定
│   ├── Dockerfile          # RSS Bot用
│   ├── Dockerfile.web_scraper  # Scraper API用
│   └── cloudbuild.*.yaml   # Cloud Build設定
├── agent_engine_agent.py   # Vertex AI Agent Engine用
└── pyproject.toml          # 依存関係定義
```

## クラウドデプロイ (Google Cloud Run Jobs)

このBotはGoogle Cloud Run Jobsでの定期実行（Cron）に対応しています。履歴管理にはFirestoreを使用します。

### 前提条件
- Google Cloud Project (GCP) プロジェクトがあること
- `gcloud` コマンドがインストール・設定されていること
- Artifact Registry のリポジトリが作成されていること (例: `my-repo`)
- Firestore データベースが作成されていること (Native mode 推奨)

### デプロイ手順

1.  **イメージのビルドとプッシュ**:
    ```bash
    # 環境変数をセット (適宜変更してください)
    export PROJECT_ID="your-project-id"
    export REGION="asia-northeast1"
    export REPO_NAME="my-repo"
    export IMAGE_NAME="choral-rss-bot"
    
    # Cloud Build でビルド & Push
    gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest .
    ```

2.  **Cloud Run Jobs の作成**:
    ```bash
    gcloud run jobs create choral-rss-bot-job \
      --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest \
      --region ${REGION} \
      --set-env-vars DISCORD_WEBHOOK_URL="your-webhook-url" \
      --set-env-vars GEMINI_API_KEY="your-gemini-api-key" \
      --set-env-vars GOOGLE_CLOUD_PROJECT=${PROJECT_ID} \
      --max-retries 0 \
      --task-timeout 10m
    ```

3.  **Cloud Scheduler の設定 (Cron)**:
    1時間ごとに実行する場合の設定例です。
    ```bash
    gcloud scheduler jobs create http choral-rss-bot-scheduler \
      --schedule "0 * * * *" \
      --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/choral-rss-bot-job:run" \
      --http-method POST \
      --oauth-service-account-email "your-service-account-email" \
      --location ${REGION}
    ```
    ※ **注意**: Cloud SchedulerからCloud Run Jobsを呼び出すための権限設定（Service Account）が別途必要になる場合があります。最も簡単な方法は、GCPコンソールの「Cloud Run」>「ジョブ」>「トリガー」タブから「スケジューラトリガーを追加」することです。

### 構成
- **Dockerfile**: `python:3.12-slim` ベース。`uv` を使用して依存関係をインストールします。
- **Firestore**: クラウド実行時は自動的にFirestore (`choral_rss_bot/history`) に記事の送信履歴を保存します。