"""Playwrightを使用したWebスクレイピングツール"""

from typing import Optional

from playwright.async_api import Browser, async_playwright


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

    async def fetch_jcanet_news(self) -> dict:
        """日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得"""
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
                        const links = document.querySelectorAll('a');

                        for (const link of links) {
                            const href = link.href;
                            const text = link.textContent.trim();
                            if (!href || !text || seen.has(href)) continue;
                            if (href.includes('#') && !href.includes('.htm') && !href.includes('.pdf')) continue;
                            if (text.length < 5) continue;

                            seen.add(href);
                            results.push({
                                date: '',
                                title: text.substring(0, 200),
                                url: href
                            });
                        }
                        return results.slice(0, 15);
                    }
                """)

                return {
                    "status": "success",
                    "articles": news_items,
                    "source": "日本合唱指揮者協会",
                }
            finally:
                await page.close()

        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e),
                "articles": [],
                "source": "日本合唱指揮者協会",
            }

    async def fetch_panamusica_news(self) -> dict:
        """パナムジカ(panamusica.co.jp)のお知らせを取得"""
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
                            if (!href || !text) continue;
                            if (!href.includes('/info/archives/')) continue;
                            if (!href.endsWith('.html')) continue;
                            if (seen.has(href)) continue;

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
                    "source": "パナムジカ",
                }
            finally:
                await page.close()

        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e),
                "articles": [],
                "source": "パナムジカ",
            }

    async def fetch_article_content(self, url: str) -> dict:
        """記事ページに遷移してコンテンツを取得"""
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                result = await page.evaluate("""
                    () => {
                        ['script', 'style', 'nav', 'header', 'footer', 'iframe', 'noscript',
                         '.sidebar', '#sidebar', '.navigation', '.menu', '.advertisement', '.ads'
                        ].forEach(sel => {
                            document.querySelectorAll(sel).forEach(el => el.remove());
                        });

                        let title = '';
                        const h1 = document.querySelector('h1');
                        if (h1) {
                            title = h1.textContent.trim();
                        } else {
                            const h2 = document.querySelector('h2');
                            title = h2 ? h2.textContent.trim() : (document.title || '');
                        }

                        const selectors = ['.entry-content', '.post-content', '.article-content',
                                          'article', 'main', '.content', '#content', '#main'];
                        let content = '';
                        for (const selector of selectors) {
                            const el = document.querySelector(selector);
                            if (el) {
                                content = el.innerText.trim();
                                if (content.length > 50) break;
                            }
                        }
                        if (content.length < 50) {
                            content = document.body ? document.body.innerText.trim() : '';
                        }

                        content = content.replace(/\\n{3,}/g, '\\n\\n').trim();

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
                    "content": result["content"],
                }
            finally:
                await page.close()

        except Exception as e:
            return {
                "status": "error",
                "url": url,
                "title": "",
                "content": "",
                "error_message": str(e),
            }


# シングルトンインスタンス
_scraper_instance: Optional[WebScraperTools] = None


def _get_scraper() -> WebScraperTools:
    """スクレイパーのシングルトンインスタンスを取得"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = WebScraperTools(headless=True)
    return _scraper_instance


async def fetch_jcanet_news() -> dict:
    """日本合唱指揮者協会(jcanet.or.jp)の新着情報を取得する。"""
    scraper = _get_scraper()
    return await scraper.fetch_jcanet_news()


async def fetch_panamusica_news() -> dict:
    """パナムジカ(panamusica.co.jp)のお知らせを取得する。"""
    scraper = _get_scraper()
    return await scraper.fetch_panamusica_news()


async def fetch_article_content(url: str) -> dict:
    """指定された記事URLからコンテンツを取得する。"""
    scraper = _get_scraper()
    return await scraper.fetch_article_content(url)


async def cleanup_scraper():
    """スクレイパーのリソースをクリーンアップ"""
    global _scraper_instance
    if _scraper_instance is not None:
        await _scraper_instance.close()
        _scraper_instance = None
