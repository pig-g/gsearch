"""Core Google search scraping logic using a headed Playwright browser.

Uses a persistent Chromium profile so Google's automation checks pass, the
same technique that works when driving a normal browser by hand.
"""

from __future__ import annotations

import base64
import os
import re
import sys
import urllib.parse
from typing import Optional

from playwright.sync_api import sync_playwright

# Persistent Chromium profile directory. Override with GSEARCH_PROFILE.
DEFAULT_PROFILE = os.path.join(os.path.expanduser("~"), ".playwright-google-profile")

# Chromium launch args that reduce automation fingerprinting.
CHROMIUM_ARGS = ["--disable-blink-features=AutomationControlled"]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def profile_dir() -> str:
    return os.environ.get("GSEARCH_PROFILE", DEFAULT_PROFILE)


def build_url(query: str, news: bool = False, lang: str = "en",
              num: int = 10, tbs: Optional[str] = None) -> str:
    """Build a Google search URL.

    tbs accepts Google time filters, e.g. 'qdr:d' (past day), 'qdr:w'.
    """
    params = {"q": query, "num": str(num), "hl": lang}
    if news:
        params["tbm"] = "nws"
    if tbs:
        params["tbs"] = tbs
    return "https://www.google.com/search?" + urllib.parse.urlencode(params)


def resolve_redirect(url: str) -> str:
    """Google wraps results in /goto?url=... or /url?q=... redirects.

    Try to decode to the real destination; return the original if we can't.
    """
    if not url:
        return url
    if "google.com/url" in url:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if params.get("q"):
            return params["q"][0]
    if "google.com/goto" in url:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        val = (params.get("url") or [""])[0]
        if val:
            # /goto values are protobuf-ish base64; best-effort decode.
            try:
                pad = "=" * (-len(val) % 4)
                raw = base64.urlsafe_b64decode(val + pad)
                m = re.search(rb"https?://[^\x00-\x1f\x7f-\xff\"'<> ]+", raw)
                if m:
                    return m.group(0).decode("utf-8", "ignore")
            except Exception:
                pass
        return "(google redirect)"
    return url


def is_blocked(page) -> bool:
    """Detect Google's 'unusual traffic' / CAPTCHA interstitial."""
    try:
        body = page.inner_text("body")[:1500]
    except Exception:
        body = ""
    url = page.url or ""
    return (
        "unusual traffic" in body
        or "not a robot" in body
        or "/sorry/" in url
    )


# In-page scraper. Google's SERP markup changes often; we anchor on <h3>
# titles (stable) and read the <cite> element for the real destination URL.
# Google News uses div[role="heading"] cards instead.
EXTRACT_JS = r"""
() => {
  const out = [];
  const seen = new Set();

  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  const citeToUrl = (s) => {
    if (!s) return '';
    s = s.replace(/\s*›\s*/g, '/').replace(/\s*·.*$/, '').trim();
    if (!/^https?:\/\//.test(s)) {
      if (/^[\w.-]+\.[a-z]{2,}/i.test(s)) s = 'https://' + s;
      else return '';
    }
    return s;
  };

  const push = (title, source, url, cite, snippet) => {
    title = clean(title);
    snippet = clean(snippet);
    source = clean(source);
    const real = citeToUrl(cite) || (url || '').trim();
    if (!title) return;
    url = real || (url || '').trim();
    if (seen.has(title)) return;
    seen.add(title);
    out.push({ title, source, url, snippet, _raw_url: (url || '').trim() });
  };

  document.querySelectorAll('h3').forEach(h3 => {
    let a = h3.closest('a[href]');
    let block = h3.parentElement;
    for (let i = 0; i < 7 && block; i++) {
      if (block.querySelector('cite')) break;
      block = block.parentElement;
    }
    const citeEl = block ? block.querySelector('cite') : null;
    const cite = citeEl ? citeEl.innerText : '';

    if (!a) {
      let up = h3.parentElement;
      for (let i = 0; i < 6 && up && !a; i++) {
        a = up.querySelector('a[href^="http"]');
        up = up.parentElement;
      }
    }

    let snippet = '';
    let source = '';
    if (block) {
      const snipEl = block.querySelector(
        'div[data-sncf], .VwiC3b, div[style*="-webkit-line-clamp"], span.aCOpRe, div.IsZvec'
      );
      snippet = snipEl ? snipEl.innerText : '';
      const srcEl = block.querySelector('span.VuuXrf, div[data-n-tid], span[aria-label]');
      source = srcEl ? srcEl.innerText : '';
    }
    push(h3.innerText, source, a ? a.href : '', cite, snippet);
  });

  // ---- Google News (tbm=nws) layout ----
  const newsHeads = document.querySelectorAll('div[role="heading"], div.n0jPhd');
  newsHeads.forEach(h => {
    const title = (h.innerText || '').trim();
    if (!title || title.length < 12) return;
    if (/choose what you|feedback|date range/i.test(title)) return;
    let card = h;
    for (let i = 0; i < 8 && card; i++) {
      if (card.querySelector && card.querySelector('a[href*="/goto?url="]')) break;
      if (card.querySelector && card.querySelector('a[href^="http"]')) break;
      card = card.parentElement;
    }
    let a = null, source = '', snippet = '';
    if (card) {
      a = card.querySelector('a[href*="/goto?url="]')
          || card.querySelector('a[href^="http"]');
      const srcEl = card.querySelector('.vr1PYe, .CEMjEf, .bInasb, span');
      if (srcEl) source = (srcEl.innerText || '').trim().split('\n')[0];
      const snipEl = card.querySelector('.GI74Re, .Y3v8qd, div[role="text"], .nDgy9c');
      if (snipEl) snippet = snipEl.innerText || '';
    }
    if (a) {
      push(title, source, a.href, '', snippet);
    } else {
      if (!seen.has(title)) {
        seen.add(title);
        out.push({ title: title, source: source, url: '', snippet: snippet });
      }
    }
  });

  return out.slice(0, 40);
}
"""


def _launch(playwright, profile: str, headless: bool):
    """Launch a persistent Chromium context for the given profile."""
    return playwright.chromium.launch_persistent_context(
        user_data_dir=profile,
        headless=headless,
        args=CHROMIUM_ARGS,
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
    )


def check_trust(
    lang: str = "en",
    headless: bool = False,
    wait_ms: int = 2500,
    captcha_wait_s: int = 180,
    verbose: bool = False,
) -> dict:
    """Load a Google page and report whether this profile/IP is trusted.

    Returns {'trusted': bool, 'blocked': bool, 'page_title': str,
             'final_url': str, 'captcha': bool}.
    """
    profile = profile_dir()
    os.makedirs(profile, exist_ok=True)
    with sync_playwright() as p:
        ctx = _launch(p, profile, headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.google.com/search?q=test&hl=" + lang,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)
            captcha = is_blocked(page)
            if captcha and not headless:
                waited = 0
                while waited < captcha_wait_s:
                    page.wait_for_timeout(1000)
                    waited += 1
                    if not is_blocked(page):
                        captcha = False
                        break
            blocked = is_blocked(page)
            return {
                "trusted": not blocked,
                "blocked": blocked,
                "captcha": captcha,
                "page_title": page.title(),
                "final_url": page.url,
            }
        finally:
            ctx.close()


def warmup(
    rounds: int = 3,
    lang: str = "en",
    headless: bool = False,
    wait_ms: int = 2500,
    captcha_wait_s: int = 300,
    between_ms: int = 4000,
    verbose: bool = False,
) -> dict:
    """Visit Google a few times to establish trust cookies.

    Google often does not fully trust a fresh profile on the first visit, so
    this performs several loads, pausing for the user to solve a CAPTCHA each
    time it appears. Returns {'trusted': bool, 'passes': int, 'blocked': bool,
    'history': [bool, ...]}.
    """
    profile = profile_dir()
    os.makedirs(profile, exist_ok=True)
    history: list[bool] = []

    with sync_playwright() as p:
        ctx = _launch(p, profile, headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for i in range(max(1, rounds)):
                if verbose:
                    print(f"  [warmup {i + 1}/{rounds}] loading Google…",
                          file=sys.stderr, flush=True)
                try:
                    page.goto("https://www.google.com/search?q=hello&hl=" + lang,
                              wait_until="domcontentloaded")
                except Exception as exc:
                    if verbose:
                        print(f"  [warmup {i + 1}] navigation error: {exc}",
                              file=sys.stderr, flush=True)
                    history.append(False)
                    continue

                page.wait_for_timeout(wait_ms)
                if is_blocked(page) and not headless:
                    if verbose:
                        print(
                            "  [!] CAPTCHA / 'unusual traffic' shown — solve it in "
                            "the browser window. Waiting…",
                            file=sys.stderr, flush=True,
                        )
                    waited = 0
                    while waited < captcha_wait_s:
                        page.wait_for_timeout(1000)
                        waited += 1
                        if not is_blocked(page):
                            break
                blocked = is_blocked(page)
                history.append(not blocked)
                # A short settle so cookies are written and Google sees a
                # human-like gap between visits.
                page.wait_for_timeout(between_ms)
        finally:
            ctx.close()

    return {
        "trusted": bool(history) and history[-1] and all(history),
        "passes": sum(1 for h in history if h),
        "blocked": bool(history) and not history[-1],
        "history": history,
    }


def search(
    query: str,
    num: int = 10,
    news: bool = False,
    lang: str = "en",
    headless: bool = False,
    navigate_resolve: bool = False,
    tbs: Optional[str] = None,
    wait_ms: int = 2500,
    captcha_wait_s: int = 180,
    verbose: bool = False,
) -> dict:
    """Run a Google search and return a result dict.

    Returns keys: query, news, url, final_url, page_title, blocked, count,
    results (list of {title, source, url, snippet}).
    """
    profile = profile_dir()
    os.makedirs(profile, exist_ok=True)
    url = build_url(query, news=news, lang=lang, num=num, tbs=tbs)

    with sync_playwright() as p:
        ctx = _launch(p, profile, headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)

            if is_blocked(page) and not headless:
                if verbose:
                    print(
                        "[!] CAPTCHA / 'unusual traffic' detected. Solve it in the "
                        "window; the browser continues automatically once results load.",
                        file=sys.stderr,
                        flush=True,
                    )
                waited = 0
                while waited < captcha_wait_s:
                    page.wait_for_timeout(1000)
                    waited += 1
                    if not is_blocked(page):
                        break

            results = page.evaluate(EXTRACT_JS)
            for r in results:
                r["url"] = resolve_redirect(r["url"])

            if navigate_resolve:
                for r in results:
                    u = r.get("url") or ""
                    if "google.com/goto" in u or u == "(google redirect)" or not u:
                        orig = r.get("_raw_url") or ""
                        if not orig:
                            continue
                        try:
                            page.goto(orig, wait_until="domcontentloaded", timeout=20000)
                            r["url"] = page.url
                        except Exception:
                            pass

            blocked = is_blocked(page)
            final_url = page.url
            title = page.title()
        finally:
            ctx.close()

    for r in results:
        r.pop("_raw_url", None)

    return {
        "query": query,
        "news": news,
        "url": url,
        "final_url": final_url,
        "page_title": title,
        "blocked": blocked,
        "count": len(results),
        "results": results,
    }