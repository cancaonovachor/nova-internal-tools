"""
Webスクレイピング用のADKツール
Playwrightを使用してheadlessモードでWebページをスクレイピングする
"""

import asyncio
import re
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, Page
from rich.console import Console

console = Console()


class WebScraperTools:
    """Playwrightベースのスクレイピングツール"""

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

    async def _get_page_content(self, url: str) -> str:
        """指定URLのページコンテンツを取得"""
        browser = await self._ensure_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            content = await page.content()
            return content
        finally:
            await page.close()

    async def fetch_jcanet_news(self) -> dict:
        """
        日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得

        Returns:
            dict: {
                "status": "success" or "error",
                "articles": [{"date": str, "title": str, "url": str}, ...],
                "error_message": str (エラー時のみ)
            }
        """
        url = "https://jcanet.or.jp/index.html"
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                news_items = await page.evaluate("""
                    () => {
                        const results = [];
                        const seen = new Set();

                        // ページ内のすべてのリンクを取得
                        const links = document.querySelectorAll('a');
                        for (const link of links) {
                            const href = link.href;
                            const text = link.textContent.trim();

                            // 空のリンクやすでに処理済みのリンクはスキップ
                            if (!href || !text || seen.has(href)) continue;

                            // jcanet.or.jpのリンクのみ対象（外部リンクも含める）
                            // ハッシュリンクや単なるアンカーは除外
                            if (href.includes('#') && !href.includes('.htm') && !href.includes('.pdf')) continue;

                            // 意味のあるコンテンツのリンクのみ
                            if (text.length < 5) continue;

                            seen.add(href);
                            results.push({
                                date: '',  // jcanetのページには明確な日付表示がない
                                title: text.substring(0, 200),
                                url: href
                            });
                        }

                        return results.slice(0, 15);  // 最新15件に制限
                    }
                """)

                return {
                    "status": "success",
                    "articles": news_items,
                    "source": "日本合唱指揮者協会"
                }
            finally:
                await page.close()

        except Exception as e:
            console.print(f"[red]Error fetching jcanet news: {e}[/red]")
            return {
                "status": "error",
                "error_message": str(e),
                "articles": []
            }

    async def fetch_panamusica_news(self) -> dict:
        """
        パナムジカ(panamusica.co.jp)のお知らせを取得

        Returns:
            dict: {
                "status": "success" or "error",
                "articles": [{"date": str, "title": str, "url": str}, ...],
                "error_message": str (エラー時のみ)
            }
        """
        url = "https://panamusica.co.jp/ja/info/"
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                articles = await page.evaluate("""
                    () => {
                        const results = [];
                        const seen = new Set();
                        const links = document.querySelectorAll('a');

                        for (const link of links) {
                            const href = link.href;
                            const text = link.textContent.trim();

                            // 記事リンクのみを対象（.htmlで終わるもの）
                            // 月別アーカイブページ（/archives/YYYY/MM/で終わるもの）は除外
                            if (!href || !text) continue;
                            if (!href.includes('/info/archives/')) continue;
                            if (!href.endsWith('.html')) continue;
                            if (seen.has(href)) continue;

                            // URLから日付を抽出 (例: /archives/2025/12/post.html)
                            const dateMatch = href.match(/\\/archives\\/(\\d{4})\\/(\\d{2})\\//);
                            const dateText = dateMatch ? dateMatch[1] + '/' + dateMatch[2] : '';

                            seen.add(href);
                            results.push({
                                date: dateText,
                                title: text.substring(0, 200),
                                url: href
                            });
                        }

                        return results.slice(0, 10);
                    }
                """)

                return {
                    "status": "success",
                    "articles": articles,
                    "source": "パナムジカ"
                }
            finally:
                await page.close()

        except Exception as e:
            console.print(f"[red]Error fetching panamusica news: {e}[/red]")
            return {
                "status": "error",
                "error_message": str(e),
                "articles": []
            }

    async def fetch_article_content(self, url: str) -> dict:
        """
        記事ページに遷移してコンテンツを取得

        Args:
            url: 記事のURL

        Returns:
            dict: {
                "status": "success" or "error",
                "url": str,
                "title": str,
                "content": str,
                "error_message": str (エラー時のみ)
            }
        """
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                result = await page.evaluate("""
                    () => {
                        // 不要な要素を削除
                        const removeSelectors = [
                            'script', 'style', 'nav', 'header', 'footer',
                            'iframe', 'noscript', '.sidebar', '#sidebar',
                            '.navigation', '.menu', '.header', '.footer',
                            '.advertisement', '.ads', '.social-share'
                        ];
                        removeSelectors.forEach(sel => {
                            document.querySelectorAll(sel).forEach(el => el.remove());
                        });

                        // タイトルを取得（h1を優先）
                        let title = '';
                        const h1 = document.querySelector('h1');
                        if (h1) {
                            title = h1.textContent.trim();
                        } else {
                            const h2 = document.querySelector('h2');
                            if (h2) {
                                title = h2.textContent.trim();
                            } else {
                                title = document.title || '';
                            }
                        }

                        // メインコンテンツを取得（複数のセレクタを試行）
                        const contentSelectors = [
                            '.entry-content',
                            '.post-content',
                            '.article-content',
                            '.content-body',
                            'article',
                            'main',
                            '.content',
                            '#content',
                            '#main'
                        ];

                        let content = '';
                        for (const selector of contentSelectors) {
                            const element = document.querySelector(selector);
                            if (element) {
                                content = element.innerText.trim();
                                if (content.length > 50) break;
                            }
                        }

                        // まだコンテンツが取れない場合はbodyから取得
                        if (content.length < 50) {
                            const body = document.body;
                            if (body) {
                                content = body.innerText.trim();
                            }
                        }

                        // 改行を整理（3つ以上の連続改行を2つに）
                        content = content.replace(/\\n{3,}/g, '\\n\\n');
                        // 空白行の連続を削除
                        content = content.replace(/^\\s*$/gm, '');
                        content = content.trim();

                        return {
                            title: title.substring(0, 500),
                            content: content.substring(0, 5000)
                        };
                    }
                """)

                return {
                    "status": "success",
                    "url": url,
                    "title": result["title"],
                    "content": result["content"]
                }
            finally:
                await page.close()

        except Exception as e:
            console.print(f"[red]Error fetching article content from {url}: {e}[/red]")
            return {
                "status": "error",
                "url": url,
                "title": "",
                "content": "",
                "error_message": str(e)
            }


# ADKツールとして使用するための非同期関数
_scraper_instance: Optional[WebScraperTools] = None


def _get_scraper() -> WebScraperTools:
    """スクレイパーのシングルトンインスタンスを取得"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = WebScraperTools(headless=True)
    return _scraper_instance


async def fetch_jcanet_news() -> dict:
    """
    日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得する。

    Returns:
        dict: 取得した記事リストを含む辞書。
              - status: "success" または "error"
              - articles: 記事のリスト（date, title, url を含む）
              - source: ソース名
    """
    scraper = _get_scraper()
    return await scraper.fetch_jcanet_news()


async def fetch_panamusica_news() -> dict:
    """
    パナムジカ(panamusica.co.jp)のお知らせを取得する。

    Returns:
        dict: 取得した記事リストを含む辞書。
              - status: "success" または "error"
              - articles: 記事のリスト（date, title, url を含む）
              - source: ソース名
    """
    scraper = _get_scraper()
    return await scraper.fetch_panamusica_news()


async def fetch_article_content(url: str) -> dict:
    """
    指定された記事URLからコンテンツを取得する。

    Args:
        url: 記事のURL

    Returns:
        dict: 記事の内容を含む辞書。
              - status: "success" または "error"
              - url: 記事のURL
              - title: 記事のタイトル
              - content: 記事の本文（最大5000文字）
    """
    scraper = _get_scraper()
    return await scraper.fetch_article_content(url)


async def cleanup_scraper():
    """スクレイパーのリソースをクリーンアップ"""
    global _scraper_instance
    if _scraper_instance is not None:
        await _scraper_instance.close()
        _scraper_instance = None
