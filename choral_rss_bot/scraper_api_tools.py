"""
Cloud Run スクレイピングAPIを呼び出すツール
Vertex AI Agent Engineから使用する
"""

import os

import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# Cloud RunのスクレイピングAPIのURL（環境変数で設定）
SCRAPER_API_URL = os.getenv("SCRAPER_API_URL", "http://localhost:8080")


def fetch_jcanet_news() -> dict:
    """
    日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得する。
    Cloud RunのスクレイピングAPIを呼び出す。

    Returns:
        dict: 取得した記事リストを含む辞書。
              - status: "success" または "error"
              - articles: 記事のリスト（date, title, url を含む）
              - source: ソース名
    """
    try:
        response = requests.get(
            f"{SCRAPER_API_URL}/api/jcanet",
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error calling scraper API: {e}[/red]")
        return {
            "status": "error",
            "error_message": str(e),
            "articles": [],
            "source": "日本合唱指揮者協会",
        }


def fetch_panamusica_news() -> dict:
    """
    パナムジカ(panamusica.co.jp)のお知らせを取得する。
    Cloud RunのスクレイピングAPIを呼び出す。

    Returns:
        dict: 取得した記事リストを含む辞書。
              - status: "success" または "error"
              - articles: 記事のリスト（date, title, url を含む）
              - source: ソース名
    """
    try:
        response = requests.get(
            f"{SCRAPER_API_URL}/api/panamusica",
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error calling scraper API: {e}[/red]")
        return {
            "status": "error",
            "error_message": str(e),
            "articles": [],
            "source": "パナムジカ",
        }


def fetch_article_content(url: str) -> dict:
    """
    指定された記事URLからコンテンツを取得する。
    Cloud RunのスクレイピングAPIを呼び出す。

    Args:
        url: 記事のURL

    Returns:
        dict: 記事の内容を含む辞書。
              - status: "success" または "error"
              - url: 記事のURL
              - title: 記事のタイトル
              - content: 記事の本文（最大5000文字）
    """
    try:
        response = requests.post(
            f"{SCRAPER_API_URL}/api/article",
            json={"url": url},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error calling scraper API: {e}[/red]")
        return {
            "status": "error",
            "url": url,
            "title": "",
            "content": "",
            "error_message": str(e),
        }
