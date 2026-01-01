"""Cloud Run スクレイピングAPIを呼び出すツール（Agent Engine用）"""

import os

import requests


def _get_scraper_api_url() -> str:
    """スクレイピングAPIのURLを取得"""
    return os.getenv("SCRAPER_API_URL", "http://localhost:8080")


def fetch_jcanet_news() -> dict:
    """
    日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得する。
    Cloud RunのスクレイピングAPIを呼び出す。
    """
    try:
        api_url = _get_scraper_api_url()
        response = requests.get(f"{api_url}/api/jcanet", timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
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
    """
    try:
        api_url = _get_scraper_api_url()
        response = requests.get(f"{api_url}/api/panamusica", timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
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
    """
    try:
        api_url = _get_scraper_api_url()
        response = requests.post(
            f"{api_url}/api/article",
            json={"url": url},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "url": url,
            "title": "",
            "content": "",
            "error_message": str(e),
        }


def send_discord_notification(
    title: str, summary: str, url: str, source: str, date: str
) -> dict:
    """
    要約した記事をDiscordに通知する。
    Cloud RunのAPIを呼び出し、固有名詞解説も自動追加される。

    Args:
        title: 記事のタイトル
        summary: 記事の要約（日本語）
        url: 記事のURL
        source: ソースサイト名
        date: 公開日

    Returns:
        dict: 送信結果
    """
    try:
        api_url = _get_scraper_api_url()
        response = requests.post(
            f"{api_url}/api/discord",
            json={
                "title": title,
                "summary": summary,
                "url": url,
                "source": source,
                "date": date,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Failed to send: {str(e)}",
        }
