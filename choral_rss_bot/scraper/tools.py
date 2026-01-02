"""Playwrightを使用したWebスクレイピングツール（LLM統合版）"""

from typing import Optional

from playwright.async_api import Browser, async_playwright

from scraper.llm_helper import (
    extract_articles_from_html,
    extract_and_explain_proper_nouns,
    extract_content_from_html,
    summarize_article,
)


class WebScraperTools:
    """Playwrightベースのスクレイピングツール（LLM統合）"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def _ensure_browser(self) -> Browser:
        """ブラウザの初期化を保証"""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self._browser

    async def close(self):
        """リソースをクリーンアップ"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def fetch_page_html(self, url: str) -> str:
        """
        ページのHTMLを取得

        Args:
            url: 取得するURL

        Returns:
            str: ページのHTML
        """
        browser = await self._ensure_browser()
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            return await page.content()
        finally:
            await page.close()

    async def scrape_site(self, site_config: dict, article_age_days: int = 3) -> list[dict]:
        """
        サイトをスクレイピングして記事リストを取得

        Args:
            site_config: サイト設定 {"id", "name", "url", "max_articles"}
            article_age_days: 記事の最大経過日数

        Returns:
            list[dict]: 処理済み記事リスト
            [{"title", "url", "date", "content", "summary", "source", "explanations"}, ...]
        """
        site_name = site_config["name"]
        site_url = site_config["url"]
        max_articles = site_config.get("max_articles", 5)

        try:
            html = await self.fetch_page_html(site_url)
        except Exception as e:
            print(f"Failed to fetch {site_url}: {e}")
            return []

        articles = extract_articles_from_html(html, site_name, max_articles, article_age_days)

        if not articles:
            print(f"No articles found on {site_name}")
            return []

        results = []
        for article in articles:
            title = article.get("title", "")
            url = article.get("url", "")
            date = article.get("date", "")

            if not url:
                continue

            try:
                article_html = await self.fetch_page_html(url)
                content_data = extract_content_from_html(article_html, url)
                content = content_data.get("content", "")

                if not title:
                    title = content_data.get("title", "")

                summary = summarize_article(title, content)
                noun_result = extract_and_explain_proper_nouns(title)

                results.append({
                    "title": title,
                    "url": url,
                    "date": date,
                    "content": content,
                    "summary": summary,
                    "source": site_name,
                    "explanations": noun_result.get("explanations", ""),
                })

            except Exception as e:
                print(f"Failed to process article {url}: {e}")
                continue

        return results


_scraper_instance: Optional[WebScraperTools] = None


def _get_scraper() -> WebScraperTools:
    """スクレイパーのシングルトンインスタンスを取得"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = WebScraperTools(headless=True)
    return _scraper_instance


async def scrape_site(site_config: dict) -> list[dict]:
    """サイトをスクレイピング"""
    scraper = _get_scraper()
    return await scraper.scrape_site(site_config)


async def cleanup_scraper():
    """スクレイパーのリソースをクリーンアップ"""
    global _scraper_instance
    if _scraper_instance is not None:
        await _scraper_instance.close()
        _scraper_instance = None
