import httpx
import re
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote_plus
from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.utils.logger import app_logger

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
]

class MultiEngineSearchAggregator:
    @staticmethod
    def get_headers() -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1"
        }

    @classmethod
    def search_duckduckgo(cls, query: str, max_results: int = 5) -> List[str]:
        urls = []
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            with httpx.Client(timeout=8.0, headers=cls.get_headers(), follow_redirects=True) as client:
                resp = client.get(search_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", class_="result__url"):
                        href = a.get("href", "")
                        if "uddg=" in href:
                            match = httpx.URL(href).params.get("uddg")
                            if match and match.startswith("http"):
                                urls.append(match)
                        elif href.startswith("http"):
                            urls.append(href)
        except Exception as e:
            app_logger.warning(f"DuckDuckGo search error: {e}")
        return urls[:max_results]

    @classmethod
    def search_bing(cls, query: str, max_results: int = 5) -> List[str]:
        urls = []
        try:
            search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
            with httpx.Client(timeout=8.0, headers=cls.get_headers(), follow_redirects=True) as client:
                resp = client.get(search_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for li in soup.find_all("li", class_="b_algo"):
                        a = li.find("a")
                        if a and a.get("href", "").startswith("http"):
                            urls.append(a["href"])
        except Exception as e:
            app_logger.warning(f"Bing search error: {e}")
        return urls[:max_results]

    @classmethod
    def search_wikipedia(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={max_results}&namespace=0&format=json"
            with httpx.Client(timeout=8.0, headers=cls.get_headers()) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) >= 4 and isinstance(data[3], list):
                        urls.extend(data[3])
        except Exception as e:
            app_logger.warning(f"Wikipedia search error: {e}")
        return urls

    @classmethod
    def search_github(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page={max_results}"
            with httpx.Client(timeout=8.0, headers=cls.get_headers()) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        if item.get("html_url"):
                            urls.append(item["html_url"])
        except Exception as e:
            app_logger.warning(f"GitHub search error: {e}")
        return urls

    @classmethod
    def aggregate_search(cls, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Queries multiple search engines (DuckDuckGo, Bing, Wikipedia, GitHub) sequentially 
        to ensure broad, unrestricted coverage.
        """
        query = query.strip()
        found_urls = []
        engines_used = []

        # Engine 1: DuckDuckGo
        ddg_urls = cls.search_duckduckgo(query, max_results=max_results)
        if ddg_urls:
            found_urls.extend(ddg_urls)
            engines_used.append("DuckDuckGo")

        # Engine 2: Bing
        if len(found_urls) < max_results:
            bing_urls = cls.search_bing(query, max_results=max_results)
            if bing_urls:
                found_urls.extend(bing_urls)
                engines_used.append("Bing")

        # Engine 3: Wikipedia (for technical/conceptual topics)
        if len(found_urls) < max_results or "what is" in query.lower() or "wiki" in query.lower():
            wiki_urls = cls.search_wikipedia(query, max_results=2)
            if wiki_urls:
                found_urls.extend(wiki_urls)
                engines_used.append("Wikipedia")

        # Engine 4: GitHub (for code / repository topics)
        if "github" in query.lower() or "code" in query.lower() or "repo" in query.lower():
            github_urls = cls.search_github(query, max_results=2)
            if github_urls:
                found_urls.extend(github_urls)
                engines_used.append("GitHub")

        # Deduplicate while preserving order
        unique_urls = list(dict.fromkeys(found_urls))[:max_results]

        return {
            "query": query,
            "engines_used": engines_used,
            "urls": unique_urls,
            "total_urls_found": len(unique_urls)
        }

class WebResearcher:
    @classmethod
    def scrape_url(cls, url: str) -> Dict[str, Any]:
        """
        Fetches web page HTML and extracts clean text, headings, code blocks, and domain info.
        """
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        domain = urlparse(url).netloc
        headers = MultiEngineSearchAggregator.get_headers()

        try:
            with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html_content = resp.text

            soup = BeautifulSoup(html_content, "html.parser")

            # Extract title
            title = soup.title.string.strip() if soup.title and soup.title.string else domain

            # Extract code blocks before stripping scripts
            code_blocks = []
            for code_tag in soup.find_all(["pre", "code"]):
                code_text = code_tag.get_text().strip()
                if len(code_text) > 10 and code_text not in code_blocks:
                    code_blocks.append(code_text)

            # Strip script, style, nav, header, footer, form elements
            for element in soup(["script", "style", "nav", "header", "footer", "form", "iframe"]):
                element.decompose()

            # Extract structured text
            text_blocks = []
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'td']):
                t = tag.get_text().strip()
                if t and len(t) > 5 and t not in text_blocks:
                    text_blocks.append(t)

            clean_text = "\n\n".join(text_blocks)

            if len(clean_text) < 100:
                clean_text = soup.get_text(separator="\n", strip=True)

            return {
                "success": True,
                "url": url,
                "domain": domain,
                "title": title,
                "content": clean_text[:20000],  # Truncate to safe character limit
                "code_blocks": code_blocks[:5],
                "text_length": len(clean_text)
            }
        except Exception as e:
            app_logger.warning(f"Error scraping URL '{url}': {e}")
            return {
                "success": False,
                "error": f"Failed to scrape web page '{url}': {str(e)}",
                "url": url,
                "domain": domain,
                "title": domain,
                "content": "",
                "code_blocks": [],
                "text_length": 0
            }

    @classmethod
    def search_and_scrape(cls, query: str, max_results: int = 3) -> Dict[str, Any]:
        """
        Unrestricted Multi-Engine Web Search & Scraping pipeline.
        Searches across DuckDuckGo, Bing, Wikipedia, and GitHub, then scrapes top result pages.
        """
        query = query.strip()
        app_logger.info(f"Conducting multi-engine web research for: '{query}'")

        # Multi-engine search aggregation
        agg = MultiEngineSearchAggregator.aggregate_search(query, max_results=max_results)
        scraped_pages = []

        for u in agg["urls"]:
            scraped = cls.scrape_url(u)
            if scraped["success"] and len(scraped["content"]) > 100:
                scraped_pages.append(scraped)

        return {
            "query": query,
            "engines_used": agg["engines_used"],
            "results_count": len(scraped_pages),
            "pages": scraped_pages
        }

    @classmethod
    def learn_from_article(cls, url: str, complexity: str = "main") -> Dict[str, Any]:
        """
        Scrapes an article URL and summarizes key takeaways & learned knowledge using Qwen.
        """
        scraped = cls.scrape_url(url)
        if not scraped["success"]:
            return scraped

        article_text = scraped["content"][:12000]
        code_snippet_str = ""
        if scraped.get("code_blocks"):
            code_snippet_str = "\n\nCode Snippets Found:\n" + "\n---\n".join(scraped["code_blocks"])

        system_prompt = (
            "You are an AI research analyst. Your job is to read the provided article "
            "and extract actionable facts, core technical takeaways, and source citations."
        )

        user_prompt = f"""
Analyze the following article (Title: "{scraped['title']}", URL: {scraped['url']}):

Article Text:
\"\"\"
{article_text}
{code_snippet_str}
\"\"\"

Please extract:
1. **Summary**: 2-3 sentence overview of the article.
2. **Key Actionable Takeaways**: List 3-5 core facts or instructions learned.
3. **Important Technical Details & Code**: Specific code, rules, settings, or values mentioned.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity=complexity,
                max_tokens=1000
            )

            ai_summary = "No summary generated."
            if llm_res.get("choices") and len(llm_res["choices"]) > 0:
                ai_summary = llm_res["choices"][0]["message"]["content"]

            return {
                "success": True,
                "url": scraped["url"],
                "title": scraped["title"],
                "domain": scraped["domain"],
                "ai_summary": ai_summary,
                "raw_text_snippet": article_text[:400] + "..."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error summarizing article with AI: {str(e)}",
                "url": scraped["url"],
                "title": scraped["title"],
                "domain": scraped["domain"],
                "ai_summary": ""
            }
