"""
Google ADKを使用したWebスクレイピングエージェント
jcanet.or.jpとpanamusica.co.jpの新着情報を取得し、要約してDiscordに通知する
"""

import os

import requests
from dotenv import load_dotenv
from google.adk.agents import Agent
from rich.console import Console

from web_scraper_tools import (
    fetch_article_content,
    fetch_jcanet_news,
    fetch_panamusica_news,
)

load_dotenv()
console = Console()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def send_discord_notification(
    title: str, summary: str, url: str, source: str, date: str
) -> dict:
    """
    要約した記事をDiscordに通知する。

    Args:
        title: 記事のタイトル
        summary: 記事の要約（日本語）
        url: 記事のURL
        source: ソースサイト名
        date: 公開日

    Returns:
        dict: 送信結果
              - status: "success" または "error"
              - message: 結果メッセージ
    """
    if not DISCORD_WEBHOOK_URL:
        return {"status": "error", "message": "DISCORD_WEBHOOK_URL is not set"}

    message = f"""**{source}** の新着記事
**タイトル**: {title}
**公開日**: {date}
**URL**: {url}

**要約**:
{summary}
"""

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        response.raise_for_status()
        return {"status": "success", "message": f"Sent notification for: {title}"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Failed to send: {str(e)}"}


# エージェントの定義
root_agent = Agent(
    name="choral_news_scraper_agent",
    model="gemini-2.0-flash",
    description="合唱関連サイトの新着情報を収集し、要約してDiscordに通知するエージェント",
    instruction="""あなたは合唱コミュニティのための情報収集エージェントです。

以下の手順でタスクを実行してください：

1. まず、fetch_jcanet_news() を使って日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得します。
2. 次に、fetch_panamusica_news() を使ってパナムジカ(panamusica.co.jp)のお知らせを取得します。
3. 取得した各記事について、fetch_article_content(url) を使って記事の詳細を取得します。
4. 取得したコンテンツを日本語で3-4文程度に要約します。
5. send_discord_notification() を使ってDiscordに通知を送信します。

重要なポイント：
- 各記事の要約は、合唱指揮者や合唱団員にとって有用な情報を中心にまとめてください
- 記事が日本語以外の場合は、日本語に翻訳してから要約してください
- エラーが発生した場合は、スキップして次の記事に進んでください
- 最新の記事から順に処理してください（最大5件程度）

出力フォーマット：
処理が完了したら、処理結果のサマリーを報告してください。
""",
    tools=[
        fetch_jcanet_news,
        fetch_panamusica_news,
        fetch_article_content,
        send_discord_notification,
    ],
)
