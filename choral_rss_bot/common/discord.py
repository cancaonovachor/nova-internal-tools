"""Discord通知ヘルパー"""

import os

import requests


def send_discord_message(message: str, webhook_url: str = None) -> bool:
    """
    Discordにメッセージを送信する

    Args:
        message: 送信するメッセージ
        webhook_url: Discord Webhook URL（省略時は環境変数から取得）

    Returns:
        bool: 送信成功したかどうか
    """
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return False

    try:
        response = requests.post(url, json={"content": message})
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        return False


def format_article_message(
    title: str, summary: str, url: str, source: str, date: str
) -> str:
    """
    記事通知用のメッセージをフォーマットする

    Args:
        title: 記事タイトル
        summary: 要約
        url: 記事URL
        source: ソース名
        date: 公開日

    Returns:
        str: フォーマットされたメッセージ
    """
    return f"""**{source}** の新着記事
**タイトル**: {title}
**公開日**: {date}
**URL**: {url}

**要約**:
{summary}
"""
