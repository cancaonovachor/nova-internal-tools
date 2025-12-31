"""RSSフィード処理メイン"""

import argparse
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import yaml
from dotenv import load_dotenv
from rich.console import Console

from common.discord import send_discord_message
from common.storage import FirestoreStorage, JsonFileStorage
from rss.llm_helper import extract_and_explain_proper_nouns, translate_title

load_dotenv()
console = Console()


def load_config():
    """設定ファイルを読み込む"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_storage(config, ignore_history: bool):
    """ストレージバックエンドを取得"""
    if ignore_history:
        return None

    is_cloud_run = (
        os.getenv("K_SERVICE") is not None or os.getenv("CLOUD_RUN_JOB") is not None
    )

    if is_cloud_run:
        console.print("[green]Running in Cloud Run environment. Using Firestore.[/green]")
        return FirestoreStorage(collection_name="choral_rss_bot", document_id="history")
    else:
        console.print("[blue]Running locally. Using JsonFileStorage.[/blue]")
        return JsonFileStorage(config["settings"]["history_file"])


def format_date(date_struct) -> str:
    """日付をフォーマット"""
    if not date_struct:
        return datetime.now().strftime("%Y/%m/%d %H:%M")
    try:
        dt = datetime.fromtimestamp(time.mktime(date_struct))
        return dt.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return datetime.now().strftime("%Y/%m/%d %H:%M")


def is_within_days(entry, days: int = 30) -> bool:
    """エントリが指定日数以内かどうか判定"""
    date_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not date_struct:
        return True

    try:
        entry_date = datetime.fromtimestamp(time.mktime(date_struct))
        cutoff_date = datetime.now() - timedelta(days=days)
        return entry_date >= cutoff_date
    except Exception:
        return True


def process_entry(entry, feed_config, mode: str) -> dict:
    """エントリを処理して記事データを生成"""
    title = entry.get("title", "No Title")
    link = entry.get("link", "")
    feed_name = feed_config["name"]
    is_japanese = feed_config.get("language") == "ja"

    if mode == "local":
        console.print(f"[yellow]Processing...[/yellow] {title}")

    # タイトルを日本語に翻訳
    title_ja = translate_title(title)

    # 固有名詞の抽出と解説
    noun_result = extract_and_explain_proper_nouns(title)

    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    formatted_date = format_date(published_parsed)

    # タイトルセクションの構築
    if is_japanese:
        title_section = f"📄タイトル: {title_ja}"
    else:
        title_section = f"🇺🇸英語タイトル: {title}\n🇯🇵日本語タイトル: {title_ja}"

    # 解説セクションの構築
    explanation_section = ""
    if noun_result.get("explanations"):
        explanation_section = f"""

📚 用語解説

{noun_result.get('explanations')}"""

    message_text = f"""📰 『{feed_name}』ジャンルの新着記事です！
📆公開日時: {formatted_date}
{title_section}
🔗リンク: {link}{explanation_section}"""

    return {
        "title": title,
        "link": link,
        "display_title": title_ja,
        "message_text": message_text,
        "source": feed_name,
    }


def main():
    parser = argparse.ArgumentParser(description="Choral RSS Bot")
    parser.add_argument(
        "--mode",
        choices=["local", "discord"],
        default="local",
        help="Execution mode: 'local' or 'discord'",
    )
    parser.add_argument(
        "--ignore-history",
        action="store_true",
        help="Ignore history file and process all items",
    )
    args = parser.parse_args()

    config = load_config()
    max_history_items = config["settings"]["max_history_items"]

    storage = get_storage(config, args.ignore_history)

    if args.ignore_history:
        history = []
        processed_links = set()
        console.print("[yellow]Ignoring history file...[/yellow]")
    else:
        history = storage.load_history() if storage else []
        processed_links = set(history)

    new_links = []

    if args.mode == "local":
        console.print(f"[bold cyan]Starting Choral RSS Bot in {args.mode} mode[/bold cyan]")

    for feed in config["rss_feeds"]:
        if args.mode == "local":
            console.print(f"Checking feed: {feed['name']}...")

        try:
            d = feedparser.parse(feed["url"])
            entries = d.entries[::-1]

            for entry in entries:
                link = entry.get("link")
                if not link or link in processed_links:
                    continue

                if not is_within_days(entry, days=3):
                    if args.mode == "local":
                        console.print(f"[dim]Skipping old article: {entry.get('title', 'No Title')}[/dim]")
                    continue

                try:
                    article_data = process_entry(entry, feed, args.mode)
                except Exception as e:
                    console.print(f"[bold red]Error processing entry {link}: {e}[/bold red]")
                    continue

                if args.mode == "local":
                    console.print("\n" + "=" * 40)
                    console.print(article_data["message_text"])
                    console.print("=" * 40 + "\n")
                else:
                    success = send_discord_message(article_data["message_text"])
                    if success:
                        console.print(f"[green]Sent to Discord:[/green] {article_data['display_title']}")
                        processed_links.add(link)
                        new_links.append(link)
                        history.append(link)
                        if storage and not args.ignore_history:
                            storage.save_history(history, max_items=max_history_items)
                        time.sleep(1)

        except Exception as e:
            console.print(f"[red]Error checking feed {feed['name']}: {e}[/red]")

    if args.mode != "local":
        if new_links:
            console.print(f"[green]Completed: {len(new_links)} new items processed.[/green]")
        else:
            console.print("No new items found.")


if __name__ == "__main__":
    main()
