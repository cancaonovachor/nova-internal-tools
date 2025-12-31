"""Vertex AI Agent Engine用のエージェント定義（ルートディレクトリに配置）"""

import os

import requests
from google.adk.agents import Agent

from scraper.api_tools import (
    fetch_article_content,
    fetch_jcanet_news,
    fetch_panamusica_news,
)


def send_discord_notification(
    title: str, summary: str, url: str, source: str, date: str
) -> dict:
    """要約した記事をDiscordに通知する。"""
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not discord_webhook_url:
        return {"status": "error", "message": "DISCORD_WEBHOOK_URL is not set"}

    message = f"""**{source}** の新着記事
**タイトル**: {title}
**公開日**: {date}
**URL**: {url}

**要約**:
{summary}
"""

    try:
        response = requests.post(discord_webhook_url, json={"content": message})
        response.raise_for_status()
        return {"status": "success", "message": f"Sent notification for: {title}"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Failed to send: {str(e)}"}


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
