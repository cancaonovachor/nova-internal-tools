"""Cloud Run用のスクレイピングAPIサービス"""

import json
import os
from contextlib import asynccontextmanager
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel

from common.storage import FirestoreStorage
from scraper.tools import WebScraperTools

load_dotenv()

_scraper: Optional[WebScraperTools] = None
_history_storage: Optional[FirestoreStorage] = None


def _extract_and_explain_proper_nouns(title: str) -> str:
    """タイトルから固有名詞を抽出し解説を生成"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return ""

    client = genai.Client(api_key=api_key)

    extract_prompt = f"""以下のタイトルから、合唱音楽に関連する固有名詞を抽出してください。

タイトル: {title}

【抽出対象】
- 人名（作曲家、指揮者、歌手など）
- 合唱団・オーケストラ名
- 作品名・曲名
- 音楽イベント・フェスティバル名

【抽出しないもの】
- 月名、曜日、年号
- 一般的な場所名
- 普通名詞や形容詞

出力形式（JSON）:
{{"proper_nouns": ["固有名詞1", "固有名詞2", ...]}}

固有名詞が見つからない場合は空の配列を返してください。"""

    try:
        extract_response = client.models.generate_content(
            model="gemini-2.0-flash-lite-preview-02-05",
            contents=extract_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        extract_text = extract_response.text.strip()
        if extract_text.startswith("```"):
            extract_text = extract_text.split("\n", 1)[1]
            if extract_text.endswith("```"):
                extract_text = extract_text.rsplit("\n", 1)[0]

        extract_result = json.loads(extract_text.strip())
        proper_nouns = extract_result.get("proper_nouns", [])

        if not proper_nouns:
            return ""

        search_prompt = f"""以下の固有名詞について、それぞれ1-2文で簡潔に日本語で解説してください。
合唱音楽や音楽に関連する文脈を優先して説明してください。

固有名詞: {', '.join(proper_nouns)}

【重要なルール】
- 前置きや挨拶は絶対に書かないこと
- 解説は必ず日本語で書くこと
- 以下の形式のみで出力すること：

・固有名詞名: 解説文

わからない場合や一般的すぎる単語はスキップしてください。"""

        search_response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        return search_response.text.strip()

    except Exception as e:
        print(f"Proper noun extraction error: {e}")
        return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    global _scraper, _history_storage
    _scraper = WebScraperTools(headless=True)
    _history_storage = FirestoreStorage(
        collection_name="choral_web_scraper", document_id="discord_history"
    )
    yield
    if _scraper:
        await _scraper.close()


app = FastAPI(
    title="Choral News Scraper API",
    description="合唱関連サイトの新着情報をスクレイピングするAPI",
    version="1.0.0",
    lifespan=lifespan,
)


class ArticleRequest(BaseModel):
    url: str


class DiscordNotificationRequest(BaseModel):
    title: str
    summary: str
    url: str
    source: str
    date: str


class ArticlesResponse(BaseModel):
    status: str
    articles: list
    source: str
    error_message: Optional[str] = None


class ArticleContentResponse(BaseModel):
    status: str
    url: str
    title: str
    content: str
    error_message: Optional[str] = None


class DiscordNotificationResponse(BaseModel):
    status: str
    message: str


@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}


@app.get("/api/jcanet", response_model=ArticlesResponse)
async def fetch_jcanet():
    """日本合唱指揮者協会の新着情報を取得"""
    if not _scraper:
        raise HTTPException(status_code=500, detail="Scraper not initialized")

    result = await _scraper.fetch_jcanet_news()
    if result.get("status") == "error":
        print(f"jcanet scraping error: {result.get('error_message', 'unknown')}")
    else:
        print(f"jcanet: fetched {len(result.get('articles', []))} articles")
    return ArticlesResponse(**result)


@app.get("/api/panamusica", response_model=ArticlesResponse)
async def fetch_panamusica():
    """パナムジカのお知らせを取得"""
    if not _scraper:
        raise HTTPException(status_code=500, detail="Scraper not initialized")

    result = await _scraper.fetch_panamusica_news()
    if result.get("status") == "error":
        print(f"panamusica scraping error: {result.get('error_message', 'unknown')}")
    else:
        print(f"panamusica: fetched {len(result.get('articles', []))} articles")
    return ArticlesResponse(**result)


@app.post("/api/article", response_model=ArticleContentResponse)
async def fetch_article(request: ArticleRequest):
    """指定URLの記事コンテンツを取得"""
    if not _scraper:
        raise HTTPException(status_code=500, detail="Scraper not initialized")

    result = await _scraper.fetch_article_content(request.url)
    return ArticleContentResponse(**result)


@app.post("/api/discord", response_model=DiscordNotificationResponse)
async def send_discord_notification(request: DiscordNotificationRequest):
    """Discord通知を送信（固有名詞解説付き、重複チェックあり）"""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise HTTPException(status_code=500, detail="DISCORD_WEBHOOK_URL is not set")

    # 重複チェック
    history = []
    if _history_storage:
        history = _history_storage.load_history()
        if request.url in history:
            print(f"Skipping already sent: {request.url}")
            return DiscordNotificationResponse(
                status="already_sent", message=f"Already sent: {request.title}"
            )

    # 固有名詞の解説を取得
    explanations = _extract_and_explain_proper_nouns(request.title)
    explanation_section = ""
    if explanations:
        explanation_section = f"""

📚 用語解説
{explanations}"""

    message = f"""📰 『{request.source}』の新着記事です！
📆公開日時: {request.date}
📄タイトル: {request.title}
🔗リンク: {request.url}

📝 要約
{request.summary}{explanation_section}
"""

    try:
        response = requests.post(webhook_url, json={"content": message})
        response.raise_for_status()

        # 送信成功したらFirestoreに保存
        if _history_storage:
            history.append(request.url)
            _history_storage.save_history(history, max_items=500)
            print(f"Saved to history: {request.url}")

        return DiscordNotificationResponse(
            status="success", message=f"Sent notification for: {request.title}"
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to send: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
