import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def summarize_and_translate(title, content, feed_name):
    """
    Summarize and translate article using Google Gemini (google-genai).
    Returns a dict with: title_ja, summary_ja, title_en(optional), language
    """
    if not GEMINI_API_KEY:
        return {
            "title_ja": title,
            "summary_ja": "（API Keyが設定されていないため要約できません）",
            "language": "unknown"
        }

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    You are a helpful assistant for a Choral Music community.
    Analyze the following article content from the feed "{feed_name}".
    
    Article Title: {title}
    Article Content: {content[:4000]} (truncated)

    Task:
    1. Identify the language of the article (ja, en, or other).
    2. If the article is in English (or other non-Japanese), translate the title to Japanese.
    3. Generate a concise summary of the article in JAPANESE (about 3-4 bullet points or short sentences).
    4. Output MUST be a valid JSON object with keys: "language", "title_ja", "summary_ja", "title_en" (original title if unrelated to translation, or just keep original).

    Example JSON:
    {{
        "language": "en",
        "title_en": "Original English Title",
        "title_ja": "Translated Japanese Title",
        "summary_ja": "- Summary point 1\n- Summary point 2"
    }}
    or
    {{
        "language": "ja",
        "title_ja": "Original Japanese Title",
        "summary_ja": "要約..."
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite-preview-02-05", 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        text_response = response.text
        
        # Clean up markdown code blocks more robustly
        text_response = text_response.strip()
        if text_response.startswith("```"):
            # Remove first line (```json or just ```)
            text_response = text_response.split("\n", 1)[1]
            # Remove last line if it is ```
            if text_response.endswith("```"):
                text_response = text_response.rsplit("\n", 1)[0]
        
        text_response = text_response.strip()

        try:
            result = json.loads(text_response)
        except json.JSONDecodeError:
            # Fallback: Try to fix unescaped newlines behavior if that's the issue
            # e.g. "summary": "- Point 1
            # - Point 2"
            try:
                # Naive fix for control characters inside strings
                # This is risky but might work for simple cases
                import re
                fixed_text = re.sub(r'(?<=: ")(.*?)(?=")', lambda m: m.group(1).replace('\n', '\\n'), text_response, flags=re.DOTALL)
                result = json.loads(fixed_text)
            except:
                # Last resort fallback if simple fixes don't work
                print(f"Failed to parse JSON: {text_response}")
                raise

        return result

    except Exception as e:
        print(f"LLM Error: {e}")
        return {
            "title_ja": title,
            "summary_ja": "（要約生成中にエラーが発生しました）",
            "language": "unknown"
        }
