"""
Webスクレイピングエージェントのメインエントリーポイント
Cloud Run Jobs または ローカルで実行可能
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from rich.console import Console

from storage import FirestoreStorage, JsonFileStorage
from web_scraper_agent import root_agent
from web_scraper_tools import cleanup_scraper

load_dotenv()
console = Console()


def get_storage(use_firestore: bool = False):
    """ストレージバックエンドを取得"""
    is_cloud_run = (
        os.getenv("K_SERVICE") is not None or os.getenv("CLOUD_RUN_JOB") is not None
    )

    if use_firestore or is_cloud_run:
        console.print("[green]Using Firestore storage[/green]")
        return FirestoreStorage(
            collection_name="choral_web_scraper", document_id="history"
        )
    else:
        console.print("[blue]Using local JSON storage[/blue]")
        return JsonFileStorage("web_scraper_history.json")


async def run_agent(mode: str = "local", ignore_history: bool = False):
    """エージェントを実行"""
    console.print(f"[bold cyan]Starting Web Scraper Agent in {mode} mode[/bold cyan]")

    # ストレージの初期化
    storage = None if ignore_history else get_storage(use_firestore=(mode == "discord"))

    # 履歴を読み込み
    processed_urls = set()
    if storage and not ignore_history:
        history = storage.load_history()
        processed_urls = set(history)
        console.print(f"[blue]Loaded {len(processed_urls)} processed URLs from history[/blue]")

    # セッションサービスの初期化
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="choral_news_scraper",
        user_id="system",
    )

    # ランナーの初期化
    runner = Runner(
        agent=root_agent,
        app_name="choral_news_scraper",
        session_service=session_service,
    )

    # プロンプトを構築
    if mode == "local":
        prompt = """以下のサイトから新着情報を取得して表示してください（Discord通知は送信しないでください）：
1. jcanet.or.jp（日本合唱指揮者協会）の新着情報
2. panamusica.co.jp（パナムジカ）のお知らせ

各記事について：
- タイトル
- 公開日
- URL
- 要約（3-4文程度）

を表示してください。最新5件程度で十分です。"""
    else:
        prompt = """以下のサイトから新着情報を収集し、Discordに通知してください：
1. jcanet.or.jp（日本合唱指揮者協会）の新着情報
2. panamusica.co.jp（パナムジカ）のお知らせ

各記事について、内容を取得して日本語で要約し、Discordに通知してください。
最新5件程度を処理してください。"""

    if processed_urls:
        prompt += f"\n\n注意：以下のURLは既に処理済みなのでスキップしてください：\n" + "\n".join(
            list(processed_urls)[:20]
        )

    try:
        # エージェントを実行
        console.print("[yellow]Running agent...[/yellow]")
        content = types.Content(
            role="user", parts=[types.Part.from_text(text=prompt)]
        )

        final_response = None
        async for event in runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=content,
        ):
            if hasattr(event, "content") and event.content:
                final_response = event.content
                if hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            console.print(part.text)

        console.print("[green]Agent execution completed[/green]")

    except Exception as e:
        console.print(f"[red]Error running agent: {e}[/red]")
        import traceback
        traceback.print_exc()
    finally:
        # クリーンアップ
        await cleanup_scraper()


def main():
    parser = argparse.ArgumentParser(description="Web Scraper Agent")
    parser.add_argument(
        "--mode",
        choices=["local", "discord"],
        default="local",
        help="Execution mode: 'local' (display only) or 'discord' (send notifications)",
    )
    parser.add_argument(
        "--ignore-history",
        action="store_true",
        help="Ignore history and process all items",
    )
    args = parser.parse_args()

    # Playwrightのブラウザが必要な場合のメッセージ
    console.print("[bold]Web Scraper Agent[/bold]")
    console.print(f"Mode: {args.mode}")
    console.print(f"Ignore history: {args.ignore_history}")
    console.print("")

    # 非同期実行
    asyncio.run(run_agent(mode=args.mode, ignore_history=args.ignore_history))


if __name__ == "__main__":
    main()
