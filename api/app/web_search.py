import logging

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


def get_web_context(query: str, max_results: int = 5) -> tuple[str, list[str]]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            context_parts: list[str] = []
            links: list[str] = []
            for res in results:
                url = str(res.get("link") or res.get("href", "")).strip()
                links.append(url)
                title = str(res.get("title", "")).strip()
                body = str(res.get("body", "")).strip()
                context_parts.append(f"WEB SOURCE: {title} ({url})\nCONTENT: {body}")

            return "\n\n".join(context_parts), links
    except Exception:
        logger.exception("Failed to fetch web context")
        return "", []