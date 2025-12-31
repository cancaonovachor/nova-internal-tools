"""Vertex AI Agent Engine用のエージェント定義（ルートディレクトリに配置）"""

import json
import os

import requests
from google import genai
from google.adk.agents import Agent
from google.genai import types

from scraper.api_tools import (
    fetch_article_content,
    fetch_jcanet_news,
    fetch_panamusica_news,
)


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


def send_discord_notification(
    title: str, summary: str, url: str, source: str, date: str
) -> dict:
    """要約した記事をDiscordに通知する。"""
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not discord_webhook_url:
        return {"status": "error", "message": "DISCORD_WEBHOOK_URL is not set"}

    # 固有名詞の解説を取得
    explanations = _extract_and_explain_proper_nouns(title)
    explanation_section = ""
    if explanations:
        explanation_section = f"""

📚 **用語解説**
{explanations}"""

    message = f"""📰 **{source}** の新着記事
📆 **公開日**: {date}
📄 **タイトル**: {title}
🔗 **URL**: {url}

📝 **要約**
{summary}{explanation_section}
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
