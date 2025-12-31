"""LLM関連ヘルパー"""

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def extract_and_explain_proper_nouns(title: str) -> dict:
    """
    タイトルから固有名詞を抽出し、Web検索で解説を生成する

    Args:
        title: 記事タイトル

    Returns:
        dict: proper_nouns(抽出された固有名詞リスト), explanations(解説テキスト)
    """
    if not GEMINI_API_KEY:
        return {"proper_nouns": [], "explanations": ""}

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Step 1: 固有名詞を抽出
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

        # Step 2: Google Searchを使って固有名詞の解説を生成
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

        # Google Search grounding を使用
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
