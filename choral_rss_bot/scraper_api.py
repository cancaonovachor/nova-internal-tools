"""
Cloud Run用のスクレイピングAPIサービス
PlaywrightベースのWebスクレイピング機能をREST APIとして提供
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from web_scraper_tools import WebScraperTools

load_dotenv()

# グローバルスクレイパーインスタンス
_scraper: Optional[WebScraperTools] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    global _scraper
    _scraper = WebScraperTools(headless=True)
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


class ArticlesResponse(BaseModel):
    status: str
    articles: list
    source: str


class ArticleContentResponse(BaseModel):
    status: str
    url: str
    title: str
    content: str
    error_message: Optional[str] = None


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
    return ArticlesResponse(**result)


@app.get("/api/panamusica", response_model=ArticlesResponse)
async def fetch_panamusica():
    """パナムジカのお知らせを取得"""
    if not _scraper:
        raise HTTPException(status_code=500, detail="Scraper not initialized")

    result = await _scraper.fetch_panamusica_news()
    return ArticlesResponse(**result)


@app.post("/api/article", response_model=ArticleContentResponse)
async def fetch_article(request: ArticleRequest):
    """指定URLの記事コンテンツを取得"""
    if not _scraper:
        raise HTTPException(status_code=500, detail="Scraper not initialized")

    result = await _scraper.fetch_article_content(request.url)
    return ArticleContentResponse(**result)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
