import httpx
import re
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote_plus
from typing import Dict, Any, List, Optional
from app.llm import llm_client, extract_reply, require_real_completion
from app.utils.logger import app_logger
from app.cognition.execution_control import (
    ExecutionCancelled,
    run_cancellable_blocking_call,
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
]

class DynamicEngineRegistry:
    """
    Registry of general, specialized, and custom search engines across 4 categories:
    1. General Web (DuckDuckGo, Bing, Yahoo, SearXNG)
    2. Code & Programming (GitHub, StackOverflow, PyPI, NPM)
    3. Academic & Technical Research (Wikipedia, ArXiv)
    4. Community & Forums (Reddit, HackerNews)
    """
    CUSTOM_ENGINES: List[Dict[str, str]] = []

    @classmethod
    def register_engine(cls, name: str, category: str, url_template: str):
        cls.CUSTOM_ENGINES.append({
            "name": name,
            "category": category,
            "url_template": url_template
        })
        app_logger.info(f"Registered new dynamic search engine: '{name}' ({category})")

    @classmethod
    def get_headers(cls) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1"
        }

class MultiEngineSearchAggregator:
    # 1. General Engines
    @classmethod
    def search_duckduckgo(cls, query: str, max_results: int = 5) -> List[str]:
        urls = []
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers(), follow_redirects=True) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(search_url), cancel=client.close,
                    description="search engine HTTP request",
                )
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
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"DuckDuckGo search error: {e}")
        return urls[:max_results]

    @classmethod
    def search_bing(cls, query: str, max_results: int = 5) -> List[str]:
        urls = []
        try:
            search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers(), follow_redirects=True) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(search_url), cancel=client.close,
                    description="search engine HTTP request",
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for li in soup.find_all("li", class_="b_algo"):
                        a = li.find("a")
                        if a and a.get("href", "").startswith("http"):
                            urls.append(a["href"])
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"Bing search error: {e}")
        return urls[:max_results]

    # 2. Code & Programming Engines
    @classmethod
    def search_github(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page={max_results}"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers()) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(api_url), cancel=client.close,
                    description="search API HTTP request",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        if item.get("html_url"):
                            urls.append(item["html_url"])
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"GitHub search error: {e}")
        return urls

    @classmethod
    def search_stackoverflow(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q={quote_plus(query)}&site=stackoverflow"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers()) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(api_url), cancel=client.close,
                    description="search API HTTP request",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", [])[:max_results]:
                        if item.get("link"):
                            urls.append(item["link"])
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"StackOverflow search error: {e}")
        return urls

    # 3. Academic & Technical Research Engines
    @classmethod
    def search_wikipedia(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={max_results}&namespace=0&format=json"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers()) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(api_url), cancel=client.close,
                    description="search API HTTP request",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) >= 4 and isinstance(data[3], list):
                        urls.extend(data[3])
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"Wikipedia search error: {e}")
        return urls

    @classmethod
    def search_arxiv(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"http://export.arxiv.org/api/query?search_query=all:{quote_plus(query)}&start=0&max_results={max_results}"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers()) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(api_url), cancel=client.close,
                    description="search API HTTP request",
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "xml")
                    for entry in soup.find_all("entry"):
                        id_tag = entry.find("id")
                        if id_tag and id_tag.text:
                            urls.append(id_tag.text.strip())
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"ArXiv search error: {e}")
        return urls

    # 4. Community & Discussion Engines
    @classmethod
    def search_hackernews(cls, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            api_url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage={max_results}"
            with httpx.Client(timeout=8.0, headers=DynamicEngineRegistry.get_headers()) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(api_url), cancel=client.close,
                    description="search API HTTP request",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for hit in data.get("hits", []):
                        if hit.get("url"):
                            urls.append(hit["url"])
                        elif hit.get("objectID"):
                            urls.append(f"https://news.ycombinator.com/item?id={hit['objectID']}")
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"HackerNews search error: {e}")
        return urls

    @classmethod
    def aggregate_search(cls, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Unrestricted Multi-Engine Search Aggregator:
        Queries across General Web (DuckDuckGo, Bing), Code (GitHub, StackOverflow), 
        Academic (Wikipedia, ArXiv), and Community (HackerNews) engines automatically!
        """
        query_lower = query.lower()
        found_urls = []
        engines_used = []

        # 1. General Search
        ddg = cls.search_duckduckgo(query, max_results=max_results)
        if ddg:
            found_urls.extend(ddg)
            engines_used.append("DuckDuckGo")

        bing = cls.search_bing(query, max_results=max_results)
        if bing:
            found_urls.extend(bing)
            engines_used.append("Bing")

        # 2. Specialized Code Engines (triggered if technical or explicitly code-related)
        if any(k in query_lower for k in ["code", "github", "error", "bug", "python", "rust", "c++", "solana", "function", "api"]):
            gh = cls.search_github(query, max_results=2)
            if gh:
                found_urls.extend(gh)
                engines_used.append("GitHub Repositories")

            so = cls.search_stackoverflow(query, max_results=2)
            if so:
                found_urls.extend(so)
                engines_used.append("StackOverflow")

        # 3. Academic & Technical Research Engines
        if any(k in query_lower for k in ["what is", "definition", "paper", "arxiv", "wiki", "concept", "algorithm"]):
            wiki = cls.search_wikipedia(query, max_results=2)
            if wiki:
                found_urls.extend(wiki)
                engines_used.append("Wikipedia")

            arxiv = cls.search_arxiv(query, max_results=2)
            if arxiv:
                found_urls.extend(arxiv)
                engines_used.append("ArXiv Papers")

        # 4. Community Discussions
        hn = cls.search_hackernews(query, max_results=2)
        if hn:
            found_urls.extend(hn)
            engines_used.append("HackerNews")

        # Deduplicate preserving order
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
        headers = DynamicEngineRegistry.get_headers()

        try:
            with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
                resp = run_cancellable_blocking_call(
                    lambda: client.get(url), cancel=client.close,
                    description="web page HTTP request",
                )
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
        except ExecutionCancelled:
            raise
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
        Searches across DuckDuckGo, Bing, GitHub, StackOverflow, Wikipedia, ArXiv, and HackerNews, then scrapes top result pages.
        """
        query = query.strip()
        app_logger.info(f"Conducting unrestricted multi-engine web research for: '{query}'")

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

            ai_summary = require_real_completion(llm_res)

            return {
                "success": True,
                "url": scraped["url"],
                "title": scraped["title"],
                "domain": scraped["domain"],
                "ai_summary": ai_summary,
                "raw_text_snippet": article_text[:400] + "..."
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            return {
                "success": False,
                "error": f"Error summarizing article with AI: {str(e)}",
                "url": scraped["url"],
                "title": scraped["title"],
                "domain": scraped["domain"],
                "ai_summary": ""
            }
