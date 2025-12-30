import os
import json
import yaml
import requests
import feedparser
import argparse
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time
from rich.console import Console
from rich.table import Table
from rich import print as rprint
import dateutil.parser

# Import LLM helper, Scraper & Storage
try:
    from llm_helper import summarize_and_translate
    from storage import JsonFileStorage, FirestoreStorage
except ImportError:
    # Fallback if running directly without uv context potentially
    try:
        from .llm_helper import summarize_and_translate
        from .storage import JsonFileStorage, FirestoreStorage
    except ImportError:
        summarize_and_translate = lambda t, c, f: {"title_ja": t, "summary_ja": c[:200] + "..." if c else ""}
        JsonFileStorage = None
        FirestoreStorage = None

console = Console()

# Load environment variables
load_dotenv()
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_storage(config, args):
    """
    Returns the appropriate storage backend based on args/env.
    """
    if args.ignore_history:
        return None # Special case handled in main

    # Check for Cloud Run environment or explicit flag (if we added one)
    # Cloud Run sets K_SERVICE, K_REVISION etc.
    is_cloud_run = os.getenv('K_SERVICE') is not None

    if is_cloud_run:
        console.print("[green]Running in Cloud Run environment. Using Firestore.[/green]")
        return FirestoreStorage(
            collection_name="choral_rss_bot",
            document_id="history"
        )
    else:
        console.print("[blue]Running locally. Using JsonFileStorage.[/blue]")
        return JsonFileStorage(config['settings']['history_file'])


def get_content_text(entry):
    if 'summary' in entry:
        return entry['summary']
    if 'content' in entry:
        return entry['content'][0].get('value', '')
    return ""

def format_date(date_struct):
    if not date_struct:
        return datetime.now().strftime("%Y/%m/%d %H:%M")
    try:
        dt = datetime.fromtimestamp(time.mktime(date_struct))
        return dt.strftime("%Y/%m/%d %H:%M")
    except:
        return datetime.now().strftime("%Y/%m/%d %H:%M")


def is_within_days(entry, days=30):
    """
    エントリの公開日が指定日数以内かどうかを判定する。
    日付情報がない場合はTrueを返す（フィルタリングしない）。
    """
    date_struct = entry.get('published_parsed') or entry.get('updated_parsed')
    if not date_struct:
        return True

    try:
        entry_date = datetime.fromtimestamp(time.mktime(date_struct))
        cutoff_date = datetime.now() - timedelta(days=days)
        return entry_date >= cutoff_date
    except:
        return True


def process_entry(entry, feed_config, mode):
    title = entry.get('title', 'No Title')
    link = entry.get('link', '')
    rss_summary = get_content_text(entry)
    feed_name = feed_config['name']

    # Use RSS summary for content
    content_to_use = rss_summary
    if mode == 'local':
         console.print("[blue]Using RSS summary[/blue]")

    # Process with LLM for ALL articles now
    if mode == 'local':
         console.print(f"[yellow]Processing with LLM...[/yellow] {title}")

    llm_result = summarize_and_translate(title, content_to_use, feed_name)

    # Format the message
    # Date
    published_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    formatted_date = format_date(published_parsed)

    # Title Section construction
    is_japanese = False
    if feed_config.get('language') == 'ja':
        is_japanese = True
    elif llm_result.get('language') == 'ja':
        is_japanese = True

    if not is_japanese:
        # English or other language article logic
        # Show both Original (English) and Translated (Japanese)
        title_section = f"🇺🇸英語タイトル: {llm_result.get('title_en', title)}\n🇯🇵日本語タイトル: {llm_result.get('title_ja')}"
    else:
        # Japanese article logic
        # Show only Japanese title
        title_section = f"🇯🇵日本語タイトル: {llm_result.get('title_ja')}"

    # Construct final message text
    message_text = f"""📰 『{feed_name}』ジャンルの新着記事です！
📆公開日時: {formatted_date}
{title_section}
🔗リンク: {link}

📝 要約

{llm_result.get('summary_ja')}"""

    return {
        "title": title,
        "link": link,
        "display_title": llm_result.get('title_ja'),
        "message_text": message_text,
        "source": feed_name
    }

def send_to_discord(article):
    if not WEBHOOK_URL:
        console.print("[red]Error: DISCORD_WEBHOOK_URL is not set.[/red]")
        return False

    # Use 'content' for the formatted text instead of embed description to match the user's request
    data = {"content": article['message_text']}

    try:
        response = requests.post(WEBHOOK_URL, json=data)
        response.raise_for_status()
        console.print(f"[green]Sent to Discord:[/green] {article['display_title']}")
        return True
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Failed to send to Discord: {e}[/red]")
        return False

def main():
    parser = argparse.ArgumentParser(description="Choral RSS Bot")
    parser.add_argument("--mode", choices=['local', 'discord'], default='local', help="Execution mode: 'local' or 'discord'")
    parser.add_argument("--ignore-history", action='store_true', help="Ignore history file and process all items (useful for testing)")
    args = parser.parse_args()

    config = load_config()
    # history_file = config['settings']['history_file'] # Handled by storage now
    max_history_items = config['settings']['max_history_items']

    # Initialize Storage
    storage = get_storage(config, args)

    if args.ignore_history:
        history = []
        processed_links = set()
        console.print("[yellow]Ignoring history file...[/yellow]")
    else:
        if storage:
            history = storage.load_history()
        else:
            history = []
        processed_links = set(history)

    new_links = []

    # In local mode, we might want to verify headers are processed correctly
    if args.mode == 'local':
        console.print(f"[bold cyan]Starting Choral RSS Bot in {args.mode} mode[/bold cyan]")

    for feed in config['rss_feeds']:
        if args.mode == 'local':
            console.print(f"Checking feed: {feed['name']}...")

        try:
            d = feedparser.parse(feed['url'])
            entries = d.entries[::-1]

            for entry in entries:
                link = entry.get('link')
                if not link:
                    continue

                if link in processed_links:
                    continue

                # 過去30日以内の記事のみ処理
                if not is_within_days(entry, days=30):
                    if args.mode == 'local':
                        console.print(f"[dim]Skipping old article: {entry.get('title', 'No Title')}[/dim]")
                    continue

                # Found new item
                try:
                    article_data = process_entry(entry, feed, args.mode)
                except Exception as e:
                    console.print(f"[bold red]Error processing entry {link}: {e}[/bold red]")
                    continue

                if args.mode == 'local':
                    console.print("\n" + "="*40)
                    console.print(article_data['message_text'])
                    console.print("="*40 + "\n")
                    pass
                else:
                    success = send_to_discord(article_data)
                    if success:
                        processed_links.add(link)
                        new_links.append(link)
                        history.append(link) # Keep track in memory for saving
                        time.sleep(1)

        except Exception as e:
            console.print(f"[red]Error checking feed {feed['name']}: {e}[/red]")

    if args.mode != 'local':
        if new_links and not args.ignore_history and storage:
            storage.save_history(history, max_items=max_history_items)
            console.print(f"[blue]Updated history with {len(new_links)} new items.[/blue]")
        elif not new_links:
            console.print("No new items found.")

if __name__ == "__main__":
    main()
