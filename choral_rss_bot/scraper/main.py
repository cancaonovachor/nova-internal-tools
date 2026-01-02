"""Webスクレイパーメイン（LLM統合版）"""

import argparse
import asyncio
import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console

from common.discord import send_discord_message
from common.storage import FirestoreStorage, JsonFileStorage
from scraper.tools import WebScraperTools

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
        return FirestoreStorage(
            collection_name="choral_web_scraper", document_id="discord_history"
        )
    else:
        console.print("[blue]Running locally. Using JsonFileStorage.[/blue]")
        return JsonFileStorage("scraper_history.json")


def format_discord_message(article: dict) -> str:
    """Discord用メッセージをフォーマット"""
    title = article.get("title", "No Title")
    url = article.get("url", "")
    date = article.get("date", "")
    summary = article.get("summary", "")
    source = article.get("source", "")
    explanations = article.get("explanations", "")

    date_section = f"📆公開日時: {date}\n" if date else ""
    summary_section = f"\n📝 要約\n{summary}" if summary else ""
    explanation_section = f"\n\n📚 用語解説\n{explanations}" if explanations else ""

    return f"""📰 『{source}』の新着記事です！
{date_section}📄タイトル: {title}
🔗リンク: {url}{summary_section}{explanation_section}"""


async def process_sites(config, mode: str, storage, ignore_history: bool):
    """全サイトを処理"""
    max_history_items = config["settings"]["max_history_items"]
    article_age_days = config["settings"].get("article_age_days", 3)

    if ignore_history:
        history = []
        processed_links = set()
        console.print("[yellow]Ignoring history file...[/yellow]")
    else:
        history = storage.load_history() if storage else []
        processed_links = set(history)

    new_links = []
    scraper = WebScraperTools(headless=True)

    try:
        for site in config["sites"]:
            console.print(f"[cyan]Scraping: {site['name']}...[/cyan]")

            try:
                articles = await scraper.scrape_site(site, article_age_days)
                console.print(f"  Found {len(articles)} articles")

                for article in articles:
                    url = article.get("url", "")

                    if not url:
                        continue

                    if url in processed_links:
                        if mode == "local":
                            console.print(f"  [dim]Skipping (already sent): {article['title'][:50]}...[/dim]")
                        continue

                    message = format_discord_message(article)

                    if mode == "local":
                        console.print("\n" + "=" * 50)
                        console.print(message)
                        console.print("=" * 50 + "\n")
                    else:
                        success = send_discord_message(message)
                        if success:
                            console.print(f"  [green]Sent:[/green] {article['title'][:50]}...")
                            processed_links.add(url)
                            new_links.append(url)
                            history.append(url)
                            if storage and not ignore_history:
                                storage.save_history(history, max_items=max_history_items)
                            time.sleep(1)

            except Exception as e:
                console.print(f"  [red]Error scraping {site['name']}: {e}[/red]")

    finally:
        await scraper.close()

    return new_links


def main():
    parser = argparse.ArgumentParser(description="Choral Web Scraper")
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

    console.print(f"[bold cyan]Starting Choral Web Scraper in {args.mode} mode[/bold cyan]")

    config = load_config()
    storage = get_storage(config, args.ignore_history)

    new_links = asyncio.run(process_sites(config, args.mode, storage, args.ignore_history))

    if args.mode != "local":
        if new_links:
            console.print(f"[green]Completed: {len(new_links)} new items processed.[/green]")
        else:
            console.print("No new items found.")


if __name__ == "__main__":
    main()
