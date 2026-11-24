"""Verify English Wikipedia titles and Wikidata ids for the canonical names (#311).

The issue asks for exact English Wikipedia article titles wherever a genuinely equivalent article
exists. "Exact" is the operative word: this module never invents a title, it *verifies* one. Given a
candidate, it asks the API whether that page exists, follows redirects, and records the canonical
title, the URL and the Wikidata QID — or reports that there is no match, which is a legitimate and
recorded outcome.

Wikimedia asks for an identifying User-Agent and modest request rates; both are respected.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "LaclauGPT-merge-lab/1.0 (research curation; contact: repository owner)"
_MIN_INTERVAL = 0.15

#: What a failed API call may raise. Anything else is a bug and should surface.
NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError)  # seconds between calls, well inside the API's guidance
_last_call = [0.0]


@dataclass
class WikipediaMatch:
    title: str
    url: str
    qid: str
    exists: bool
    redirect_from: str = ""
    error: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "qid": self.qid,
            "exists": self.exists,
            "redirect_from": self.redirect_from,
            **({"error": self.error} if self.error else {}),
        }


def _get(params: dict[str, str], *, timeout: int = 20) -> dict[str, Any]:
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        _last_call[0] = time.time()
        return json.loads(response.read())


def verify(candidate: str) -> WikipediaMatch:
    """Does this exact title exist? Return it with its URL and QID, following redirects."""
    if not candidate or not candidate.strip():
        return WikipediaMatch("", "", "", False, error="empty candidate")
    try:
        payload = _get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "redirects": "1",
                "prop": "pageprops|info",
                "inprop": "url",
                "titles": candidate.strip(),
            }
        )
    except NETWORK_ERRORS as exc:  # recorded, never turned into a match
        return WikipediaMatch("", "", "", False, error=f"{type(exc).__name__}: {exc}")

    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        return WikipediaMatch("", "", "", False, error="no page object")
    page = pages[0]
    if page.get("missing"):
        return WikipediaMatch("", "", "", False)
    redirects = payload.get("query", {}).get("redirects", [])
    return WikipediaMatch(
        title=page.get("title", ""),
        url=page.get("fullurl", ""),
        qid=page.get("pageprops", {}).get("wikibase_item", ""),
        exists=True,
        redirect_from=redirects[0]["from"] if redirects else "",
    )


def search(query: str, *, limit: int = 3) -> list[str]:
    """Candidate titles for a query, most relevant first. Used only to *find* candidates to verify."""
    try:
        payload = _get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "list": "search",
                "srsearch": query,
                "srlimit": str(limit),
            }
        )
    except NETWORK_ERRORS:
        return []
    return [item["title"] for item in payload.get("query", {}).get("search", [])]


def english_title_from_other_language(language: str, title: str) -> str:
    """Follow a language link: a Finnish article's English counterpart, if it has one."""
    try:
        payload = _get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "langlinks",
                "lllang": "en",
                "titles": title,
                "redirects": "1",
                **({"meta": "siteinfo", "siprop": "general"} if False else {}),
            }
        )
    except NETWORK_ERRORS:
        return ""
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        return ""
    for link in pages[0].get("langlinks", []) or []:
        if link.get("lang") == "en":
            return link.get("title", "")
    _ = language
    return ""


def resolve(candidate: str, *, fallback_query: str = "", allow_search: bool = False) -> WikipediaMatch:
    """Verify a candidate title. A near-miss is reported as no match, not as something else.

    The search fallback is opt-in because it is the one way this module could do the forbidden
    thing: forcing a label into a merely related article. With it off, a label that no reviewer
    could name precisely stays unmatched — which is a recorded, legitimate outcome.
    """
    match = verify(candidate)
    if match.exists or not allow_search:
        return match
    for title in search(fallback_query or candidate):
        if title.casefold() != candidate.casefold():
            continue
        found = verify(title)
        if found.exists:
            found.redirect_from = found.redirect_from or f"search:{candidate}"
            return found
    return match
