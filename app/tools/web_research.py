import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.utils.logger import app_logger

class WebResearcher:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    @classmethod
    def scrape_url(cls, url: str) -> Dict[str, Any]:
        """
        Fetches web page HTML and extracts clean text, title, and domain information.
        """
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        domain = urlparse(url).netloc

        try:
            with httpx.Client(timeout=15.0, headers=cls.HEADERS, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html_content = resp.text

            soup = BeautifulSoup(html_content, "html.parser")

            # Extract title
            title = soup.title.string.strip() if soup.title and soup.title.string else domain

            # Strip script, style, nav, header, footer, form elements
            for element in soup(["script", "style", "nav", "header", "footer", "form", "iframe"]):
                element.decompose()

            # Extract clean body text
            text_blocks = [p.get_text().strip() for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li']) if p.get_text().strip()]
            clean_text = "\n\n".join(text_blocks)

            if len(clean_text) < 100:
                # Fallback to body text
                clean_text = soup.get_text(separator="\n", strip=True)

            return {
                "success": True,
                "url": url,
                "domain": domain,
                "title": title,
                "content": clean_text[:15000],  # Truncate to safe character limit
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
                "text_length": 0
            }

    @classmethod
    def search_and_scrape(cls, query: str, max_results: int = 3) -> Dict[str, Any]:
        """
        Performs a web search via DuckDuckGo HTML and scrapes top result pages.
        """
        query = query.strip()
        app_logger.info(f"Conducting web search for: '{query}'")
        
        search_url = f"https://html.duckduckgo.com/html/?q={httpx.QueryParams({'q': query})['q']}"
        scraped_pages = []

        try:
            with httpx.Client(timeout=10.0, headers=cls.HEADERS, follow_redirects=True) as client:
                resp = client.get(search_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_="result__url")
                    
                    found_urls = []
                    for link in links:
                        href = link.get("href", "")
                        if "uddg=" in href:
                            # Extract actual URL from DuckDuckGo redirect
                            match = httpx.URL(href).params.get("uddg")
                            if match:
                                found_urls.append(match)
                        elif href.startswith("http"):
                            found_urls.append(href)

                    # Deduplicate and limit
                    target_urls = list(dict.fromkeys(found_urls))[:max_results]

                    for u in target_urls:
                        scraped = cls.scrape_url(u)
                        if scraped["success"] and len(scraped["content"]) > 100:
                            scraped_pages.append(scraped)

        except Exception as e:
            app_logger.warning(f"DuckDuckGo search error for '{query}': {e}")

        return {
            "query": query,
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

        article_text = scraped["content"][:10000]
        
        system_prompt = (
            "You are an AI research analyst. Your job is to read the provided article "
            "and extract actionable facts, core technical takeaways, and source citations."
        )

        user_prompt = f"""
Analyze the following article (Title: "{scraped['title']}", URL: {scraped['url']}):

Article Text:
\"\"\"
{article_text}
\"\"\"

Please extract:
1. **Summary**: 2-3 sentence overview of the article.
2. **Key Actionable Takeaways**: List 3-5 core facts or instructions learned.
3. **Important Technical Details**: Specific code, rules, settings, or values mentioned.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity=complexity,
                max_tokens=800
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
