"""Webスクレイピング用LLMヘルパー"""

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _get_client() -> genai.Client:
    """Gemini クライアントを取得"""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=GEMINI_API_KEY)


def _truncate_html(html: str, max_chars: int = 50000) -> str:
    """HTMLを指定文字数に切り詰める"""
    if len(html) <= max_chars:
        return html
    return html[:max_chars] + "\n... (truncated)"


def extract_articles_from_html(
    html: str, site_name: str, max_articles: int = 5
) -> list[dict]:
    """
    HTMLから記事リストを抽出

    Args:
        html: ページのHTML
        site_name: サイト名（コンテキスト用）
        max_articles: 最大記事数

    Returns:
        list[dict]: 記事リスト [{"title": str, "url": str, "date": str}, ...]
    """
    client = _get_client()

    prompt = f"""以下は「{site_name}」のHTMLです。新着記事・お知らせのリストを抽出してください。

HTML:
{_truncate_html(html)}

【抽出対象】
- 新着情報、お知らせ、ニュースなどのリンク
- イベント告知、更新情報
- 記事タイトルとURL

【除外対象】
- ナビゲーションメニュー（ホーム、会社概要など）
- フッターリンク
- SNSリンク（Twitter、Facebook等）
- 広告、バナー
- カテゴリ一覧、アーカイブリンク

【出力形式】JSON:
{{
  "articles": [
    {{"title": "記事タイトル", "url": "https://example.com/article1", "date": "2025/01/02"}},
    {{"title": "記事タイトル2", "url": "https://example.com/article2", "date": ""}}
  ]
}}

日付が不明な場合は空文字。最大{max_articles}件まで。新しい記事を優先してください。
URLは必ず完全なURL（https://から始まる）で出力してください。"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        result_text = response.text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text.rsplit("\n", 1)[0]

        result = json.loads(result_text.strip())
        return result.get("articles", [])[:max_articles]

    except Exception as e:
        print(f"Article extraction error: {e}")
        return []


def extract_content_from_html(html: str, url: str) -> dict:
    """
    HTMLから記事本文を抽出

    Args:
        html: ページのHTML
        url: ページURL（コンテキスト用）

    Returns:
        dict: {"title": str, "content": str}
    """
    client = _get_client()

    prompt = f"""以下のHTMLから記事の本文を抽出してください。

URL: {url}

HTML:
{_truncate_html(html, 30000)}

【抽出対象】
- 記事のタイトル（h1, h2など）
- 記事の本文テキスト
- 重要な情報（日時、場所、詳細）

【除外対象】
- ナビゲーション、ヘッダー、フッター
- サイドバー、広告
- 関連記事リンク
- コメント欄

【出力形式】JSON:
{{
  "title": "記事タイトル",
  "content": "本文テキスト（最大2000文字）"
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        result_text = response.text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text.rsplit("\n", 1)[0]

        return json.loads(result_text.strip())

    except Exception as e:
        print(f"Content extraction error: {e}")
        return {"title": "", "content": ""}


def summarize_article(title: str, content: str) -> str:
    """
    記事を要約

    Args:
        title: 記事タイトル
        content: 記事本文

    Returns:
        str: 要約テキスト
    """
    if not content or len(content) < 50:
        return ""

    client = _get_client()

    prompt = f"""以下の記事を3-4文で要約してください。

タイトル: {title}

本文:
{content[:3000]}

【ルール】
- 日本語で要約
- 重要な情報（日時、場所、内容）を含める
- 合唱関係者が興味を持つポイントを強調
- 前置きや「この記事は」などの導入文は不要
- 要約のみを出力"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip()

    except Exception as e:
        print(f"Summarization error: {e}")
        return ""


def extract_and_explain_proper_nouns(title: str) -> dict:
    """
    タイトルから固有名詞を抽出し、Web検索で解説を生成する
    （rss/llm_helper.py から流用）

    Args:
        title: 記事タイトル

    Returns:
        dict: proper_nouns(抽出された固有名詞リスト), explanations(解説テキスト)
    """
    if not GEMINI_API_KEY:
        return {"proper_nouns": [], "explanations": ""}

    client = _get_client()

    extract_prompt = f"""以下のタイトルから、合唱音楽に関連する固有名詞を抽出してください。

タイトル: {title}

【抽出対象】
- 人名（作曲家、指揮者、歌手など）
- 合唱団・オーケストラ名
- 作品名・曲名
- 音楽イベント・フェスティバル名

【抽出しないもの】
- 月名、曜日、年号（December, Monday, 2025など）
- 一般的な場所名（葬儀場、大学、ホールなどの一般名詞）
- 普通名詞や形容詞

出力形式（JSON）:
{{
    "proper_nouns": ["固有名詞1", "固有名詞2", ...]
}}

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
            return {"proper_nouns": [], "explanations": ""}

        search_prompt = f"""以下の固有名詞について、それぞれ1-2文で簡潔に日本語で解説してください。
合唱音楽や音楽に関連する文脈を優先して説明してください。

固有名詞: {', '.join(proper_nouns)}

【重要なルール】
- 前置きや挨拶は絶対に書かないこと（「承知しました」「以下に記載します」等は禁止）
- 解説は必ず日本語で書くこと
- 以下の形式のみで出力すること：

・固有名詞名: 解説文
・固有名詞名: 解説文

わからない場合や一般的すぎる単語（月名、曜日など）はスキップしてください。"""

        search_response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        explanations = search_response.text.strip()

        return {"proper_nouns": proper_nouns, "explanations": explanations}

    except Exception as e:
        print(f"Proper noun extraction/explanation error: {e}")
        return {"proper_nouns": [], "explanations": ""}
