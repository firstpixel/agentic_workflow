# src/tools/duckduckgo_scraper.py
from __future__ import annotations
from typing import List, Dict, Optional
import re
import time
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as convert


class DuckDuckGoScraper:
    """
    Lightweight wrapper around DuckDuckGo search + HTML scraping → Markdown.
    Safe to import without ddgs installed (lazy import inside search method).
    """

    def __init__(self, timeout: int = 10, delay: float = 1.0, user_agent: Optional[str] = None):
        """
        Args:
            timeout: per-request timeout (seconds)
            delay: delay between page fetches (seconds)
            user_agent: optional custom UA string
        """
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent or (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/115.0 Safari/537.36'
            )
        })

    def search_duckduckgo(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """
        Search DuckDuckGo and return [{'title','url','snippet'}, ...].
        """
        try:
            from ddgs import DDGS  # lazy import
        except Exception as e:
            raise RuntimeError("ddgs library not available; install `ddgs`.") from e

        results: List[Dict[str, str]] = []
        try:
            with DDGS() as ddgs:
                for result in ddgs.text(query=query, max_results=max_results):
                    results.append({
                        "title": result.get("title", "No Title"),
                        "url": result.get("href", ""),
                        "snippet": result.get("body", "No snippet available"),
                    })
        except Exception as e:
            raise RuntimeError(f"DuckDuckGo search failed: {e}") from e

        return results

    def extract_content(self, url: str) -> Optional[str]:
        """
        Fetch a page and convert the main content to Markdown (best effort).
        """
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.content, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "advertisement"]):
                tag.decompose()

            main = None
            for sel in ["main", "article", ".content", "#content", ".post", ".entry"]:
                main = soup.select_one(sel)
                if main:
                    break
            if not main:
                main = soup.find("body") or soup

            md = convert(str(main))
            md = re.sub(r"\n\s*\n\s*\n+", "\n\n", md)
            md = re.sub(r"^\s+", "", md, flags=re.MULTILINE)
            return md.strip()
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None

    def load_url(self, url: str) -> Dict[str, str]:
        """
        Convenience: load a single URL and return {'url','content'}.
        """
        content = self.extract_content(url)
        return {"url": url, "content": content or "Failed to extract content"}

    def scrape_search_results(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """
        Convenience: search then scrape each result.
        """
        items = self.search_duckduckgo(query=query, max_results=max_results)
        out: List[Dict[str, str]] = []
        for i, item in enumerate(items, 1):
            content = self.extract_content(item["url"])
            out.append({
                "title": item["title"],
                "url": item["url"],
                "snippet": item["snippet"],
                "content": content or "Failed to extract content"
            })
            if i < len(items) and self.delay > 0:
                time.sleep(self.delay)
        return out
