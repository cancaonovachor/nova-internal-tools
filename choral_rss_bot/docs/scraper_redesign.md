# Web Scraper リファクタリング設計

## 概要

Agent Engine を削除し、Cloud Run Jobs + LLM でシンプルに実装する。

## アーキテクチャ

### Before (現状)
```
Cloud Scheduler
       ↓
Agent Engine (Gemini) ← 削除対象
       ↓
Cloud Run (Scraper API) ← 削除対象
       ↓
Webサイト → Discord
```

### After (新設計)
```
Cloud Scheduler (日次)
       ↓
Cloud Run Jobs
       ↓
Playwright + Gemini (HTML解析・要約)
       ↓
Webサイト → Discord
```

## 処理フロー

```
1. Cloud Run Job起動
2. 対象サイトごとにループ:
   a. Playwrightでページ取得 → HTML取得
   b. GeminiにHTML渡して記事リスト抽出 (JSON)
   c. 各記事URLにアクセス → 本文HTML取得
   d. Geminiで本文要約
   e. 重複チェック (Firestore)
   f. Discord通知 (固有名詞解説付き)
   g. Firestoreに履歴保存
3. 完了
```

## ファイル構成

### 削除対象
```
scraper/api.py           # FastAPI (不要)
scraper/api_tools.py     # Agent用ツール (不要)
scraper/agent.py         # ローカルAgent (不要)
agent_engine_agent.py    # Agent Engine定義 (不要)
deploy/deploy_agent_engine.py  # Agent Engineデプロイ (不要)
deploy/Dockerfile.web_scraper  # Cloud Run API用 (不要)
deploy/cloudbuild.web_scraper.yaml  # (不要)
```

### 変更対象
```
scraper/main.py          # エントリーポイント (大幅修正)
scraper/tools.py         # スクレイピングツール (LLM統合)
```

### 新規作成
```
scraper/llm_helper.py    # LLM関連処理 (HTML解析、要約)
scraper/config.yaml      # サイト設定
```

### 既存流用
```
common/storage.py        # Firestore (そのまま使用)
common/discord.py        # Discord通知 (そのまま使用)
rss/llm_helper.py        # 固有名詞抽出 (参考・流用)
```

## 設定ファイル (scraper/config.yaml)

```yaml
sites:
  - id: jcanet
    name: 日本合唱連盟
    url: https://jcanet.or.jp/index.html
    max_articles: 5

  - id: panamusica
    name: パナムジカ
    url: https://panamusica.co.jp/ja/info/
    max_articles: 5

settings:
  max_history_items: 500
  article_age_days: 30
```

## LLMプロンプト

### 1. 記事リスト抽出

```python
EXTRACT_ARTICLES_PROMPT = """
以下のHTMLから新着記事・お知らせのリストを抽出してください。

HTML:
{html}

【抽出対象】
- 新着情報、お知らせ、ニュースなどのリンク
- イベント告知、更新情報

【除外対象】
- ナビゲーションメニュー
- フッターリンク
- SNSリンク
- 広告

【出力形式】JSON:
{{
  "articles": [
    {{"title": "記事タイトル", "url": "https://...", "date": "2025/01/02"}},
    ...
  ]
}}

日付が不明な場合は空文字。最大{max_articles}件まで。
"""
```

### 2. 記事本文抽出

```python
EXTRACT_CONTENT_PROMPT = """
以下のHTMLから記事本文を抽出してください。

HTML:
{html}

【抽出対象】
- 記事の本文テキスト
- 重要な情報（日時、場所、詳細）

【除外対象】
- ナビゲーション、ヘッダー、フッター
- サイドバー、広告
- スクリプト、スタイル

【出力形式】プレーンテキストのみ（最大2000文字）
"""
```

### 3. 要約生成

```python
SUMMARIZE_PROMPT = """
以下の記事を3-4文で要約してください。

タイトル: {title}
本文:
{content}

【ルール】
- 日本語で要約
- 重要な情報（日時、場所、内容）を含める
- 合唱関係者が興味を持つポイントを強調
"""
```

## 実装詳細

### scraper/llm_helper.py

```python
"""Webスクレイピング用LLMヘルパー"""

import json
import os
from google import genai
from google.genai import types

def extract_articles_from_html(html: str, max_articles: int = 5) -> list[dict]:
    """HTMLから記事リストを抽出"""
    # Gemini API呼び出し
    # JSON形式でarticlesを返す
    pass

def extract_content_from_html(html: str) -> str:
    """HTMLから本文を抽出"""
    pass

def summarize_article(title: str, content: str) -> str:
    """記事を要約"""
    pass

def extract_and_explain_proper_nouns(title: str) -> dict:
    """固有名詞抽出・解説（rss/llm_helper.pyから流用）"""
    pass
```

### scraper/tools.py

```python
"""Playwrightスクレイピングツール"""

async def fetch_page_html(url: str) -> str:
    """ページのHTMLを取得"""
    pass

async def scrape_site(site_config: dict) -> list[dict]:
    """サイトをスクレイピング"""
    # 1. ページHTML取得
    # 2. LLMで記事リスト抽出
    # 3. 各記事の本文取得・要約
    pass
```

### scraper/main.py

```python
"""Webスクレイパーメイン"""

def main():
    # 1. 設定読み込み
    # 2. ストレージ初期化
    # 3. サイトごとにスクレイピング
    # 4. 重複チェック・Discord通知
    pass
```

## Discord通知フォーマット

```
📰 『{source}』の新着記事です！
📆公開日時: {date}
📄タイトル: {title}
🔗リンク: {url}

📝 要約
{summary}

📚 用語解説
{explanations}
```

## デプロイ

### Dockerfile

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.57.0-noble
# 既存のDockerfile.web_scraperを流用、CMD変更
CMD ["uv", "run", "python", "-m", "scraper.main", "--mode", "discord"]
```

### Cloud Run Jobs

```bash
gcloud run jobs create choral-web-scraper \
  --image=REGION-docker.pkg.dev/PROJECT/REPO/choral-web-scraper:latest \
  --region=asia-northeast1 \
  --set-env-vars="DISCORD_WEBHOOK_URL=...,GEMINI_API_KEY=..."
```

### Cloud Scheduler

```bash
gcloud scheduler jobs create http choral-web-scraper-daily \
  --schedule="0 9 * * *" \
  --uri="https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/..." \
  --http-method=POST
```

## 実装順序

1. `scraper/llm_helper.py` 作成 (HTML解析・要約)
2. `scraper/tools.py` 修正 (LLM統合)
3. `scraper/config.yaml` 作成
4. `scraper/main.py` 修正 (rss/main.py参考)
5. ローカルテスト
6. 不要ファイル削除
7. Dockerfile更新
8. デプロイ・動作確認
9. Agent Engine削除
