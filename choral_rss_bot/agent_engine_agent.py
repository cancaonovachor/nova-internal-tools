"""Vertex AI Agent Engine用のエージェント定義（ルートディレクトリに配置）"""

import os

import requests
from google.adk.agents import Agent


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
    重複チェックもAPI側で行われる。

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


root_agent = Agent(
    name="choral_news_scraper_agent",
    model="gemini-2.0-flash",
    description="合唱関連サイトの新着情報を収集し、要約してDiscordに通知するエージェント",
    instruction="""あなたは合唱コミュニティのための情報収集エージェントです。

【重要】各記事の要約を作成する前に、必ずfetch_article_content()で記事本文を取得してください。
タイトルだけで要約を推測してはいけません。

手順：
1. fetch_jcanet_news() で日本合唱指揮者協会の新着情報を取得
2. fetch_panamusica_news() でパナムジカのお知らせを取得
3. 【必須】各記事について fetch_article_content(url) で本文を取得
4. 取得した本文を基に、3-4文程度で要約を作成
5. send_discord_notification() でDiscordに通知

処理する記事数：各サイトから最新3件ずつ
""",
    tools=[
        fetch_jcanet_news,
        fetch_panamusica_news,
        fetch_article_content,
        send_discord_notification,
    ],
)
