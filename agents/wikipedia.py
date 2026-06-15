"""Live English-Wikipedia retrieval over the MediaWiki API (no caching).

RETRIEVAL CONTRACT (recon-verified 2026-06-15 against en.wikipedia.org)
======================================================================
Request:
    GET https://en.wikipedia.org/w/api.php
        action=query  format=json  generator=search
        gsrsearch=<query>  gsrlimit=<limit>
        prop=extracts|info  inprop=url
        exintro=1  explaintext=1  exlimit=max
        header: User-Agent: <identifying string>   (Wikipedia API etiquette)

Why these parameters:
  - exintro=1 is MANDATORY. It is the only mode that returns one extract per
    search hit. Whole-article mode (exchars/exsentences) forces exlimit -> 1,
    which would drop every hit but the first — so truncation is done here in
    Python instead (see _truncate), never via the API.
  - inprop=url yields each page's `fullurl`.
  - explaintext=1 yields plain text with "\\n\\n" paragraph breaks.

Result ordering:
  generator=search returns pages keyed by pageid, NOT in search-rank order.
  We re-sort by each page's `index` field to restore relevance order.

Three-way status — discriminate on the top-level "error" key, NEVER on HTTP
status (empty and error both return HTTP 200):
  - error : "error" key present in the JSON body, OR a network/HTTP exception,
            OR a non-JSON / unexpected body.            is_error = True
  - empty : no "error" key and no query.pages
            (shape: {"batchcomplete":"","limits":{...}}).  is_error = False
  - ok    : query.pages present.                            is_error = False

A per-search `empty` (Wikipedia has nothing) is distinct from a *zero-searches*
run (the worker never called the tool) — the latter is tracked by the agent loop.

Truncation: each intro extract is cut boundary-safe at ~max_chars (last
paragraph, else sentence, else word boundary) with an ellipsis appended.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# Module-level so a no-key selftest can point it at a bad endpoint to exercise
# the error path deterministically.
API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "wiki-agent/0.1 (Anthropic prompt-engineering take-home)"

DEFAULT_LIMIT = 3
DEFAULT_MAX_CHARS = 1200
_TIMEOUT = 30

TOOL_NAME = "search_wikipedia"

# Tool description is my DRAFT, pending your sign-off — edit freely.
SEARCH_WIKIPEDIA_TOOL = {
    "name": TOOL_NAME,
    "description": (
        "Search English Wikipedia for the most relevant article intros. Use this whenever "
        "answering needs facts you are not fully certain of — names, dates, numbers, niche or "
        "recent topics. Returns up to a few results, each with the article title, URL, and a "
        "truncated intro. Signals \"no results\" distinctly from a retrieval error; on no "
        "results, rephrase and retry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
        },
        "required": ["query"],
    },
}


@dataclass
class Snippet:
    title: str
    url: str
    extract: str


@dataclass
class SearchResult:
    query: str
    status: str  # "ok" | "empty" | "error"
    results: list[Snippet] = field(default_factory=list)
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.status == "error"


def search_wikipedia(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> SearchResult:
    """Search English Wikipedia and return ranked intro snippets. See module docstring
    for the full request/status/truncation contract. Never raises — failures resolve
    to status="error"."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": str(limit),
        "prop": "extracts|info",
        "inprop": "url",
        "exintro": "1",
        "explaintext": "1",
        "exlimit": "max",
    }
    try:
        data = _request(params)
    except Exception as e:  # network, HTTP, JSON, timeout — all collapse to error
        return SearchResult(query=query, status="error", error=f"{type(e).__name__}: {e}")

    if not isinstance(data, dict):
        return SearchResult(query=query, status="error", error="unexpected (non-object) response")

    if "error" in data:
        err = data["error"]
        info = err.get("info") if isinstance(err, dict) else str(err)
        return SearchResult(query=query, status="error", error=info or "MediaWiki error")

    pages = (data.get("query") or {}).get("pages")
    if not pages:
        return SearchResult(query=query, status="empty")

    # pages is keyed by pageid; re-sort by search rank (`index`).
    ordered = sorted(pages.values(), key=lambda p: p.get("index", 1_000_000))
    snippets = [
        Snippet(
            title=p.get("title", ""),
            url=p.get("fullurl", ""),
            extract=_truncate((p.get("extract") or "").strip(), max_chars),
        )
        for p in ordered
    ]
    return SearchResult(query=query, status="ok", results=snippets)


def render_result(result: SearchResult) -> str:
    """Render a SearchResult as the text content of a tool_result block for the worker."""
    if result.status == "error":
        return f"Search error: {result.error or 'unknown error'}"
    if result.status == "empty":
        return "No Wikipedia results found for this query."
    blocks = [
        f"[{i}] {s.title}\nURL: {s.url}\n{s.extract}"
        for i, s in enumerate(result.results, 1)
    ]
    return "\n\n".join(blocks)


def _request(params: dict) -> dict:
    """GET the MediaWiki API and parse JSON. Raises on network/HTTP/JSON errors."""
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _truncate(text: str, max_chars: int) -> str:
    """Cut text to ~max_chars at a paragraph, else sentence, else word boundary;
    append an ellipsis when truncated. Returns text unchanged if already short."""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    floor = max_chars // 2  # don't cut absurdly early

    para = window.rfind("\n\n")
    if para >= floor:
        return text[:para].rstrip() + " …"

    sentence = -1
    for term in (". ", ".\n", "! ", "? "):
        i = window.rfind(term)
        if i != -1:
            sentence = max(sentence, i + 1)  # keep the terminator
    if sentence >= floor:
        return text[:sentence].rstrip() + " …"

    space = window.rfind(" ")
    cut = space if space >= floor else max_chars
    return text[:cut].rstrip() + " …"
