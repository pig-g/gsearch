"""Command-line interface for gsearch."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import List

from .core import search
from . import __version__

# ANSI colors (disabled when not a TTY or when NO_COLOR is set).
import os as _os

_USE_COLOR = sys.stdout.isatty() and not _os.environ.get("NO_COLOR")


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _print_text(data: dict, show_snippets: bool, show_urls: bool) -> None:
    if data["blocked"]:
        print(_c("BLOCKED (Google 'unusual traffic')", "31"), file=sys.stderr)
        return
    print(_c(f"# {data['count']} results for: {data['query']}", "1"))
    print()
    for i, r in enumerate(data["results"], 1):
        title = _c(r["title"], "1")
        src = f" {_c('—', '2')} {r['source']}" if r.get("source") else ""
        print(f"{i}. {title}{src}")
        if show_urls and r.get("url"):
            print(f"   {_c(r['url'], '34')}")
        if show_snippets and r.get("snippet"):
            print(f"   {_c(r['snippet'][:200], '2')}")
        print()


def _print_csv(data: dict) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["index", "title", "source", "url", "snippet"])
    for i, r in enumerate(data["results"], 1):
        w.writerow([i, r.get("title", ""), r.get("source", ""),
                    r.get("url", ""), r.get("snippet", "")])
    sys.stdout.write(buf.getvalue())


def _print_markdown(data: dict) -> None:
    print(f"# {data['query']}\n")
    for i, r in enumerate(data["results"], 1):
        src = f" — {r['source']}" if r.get("source") else ""
        if r.get("url"):
            print(f"{i}. [{r['title']}]({r['url']}){src}")
        else:
            print(f"{i}. {r['title']}{src}")
        if r.get("snippet"):
            print(f"   > {r['snippet'][:240]}")
        print()


def _print_urls(data: dict) -> None:
    for r in data["results"]:
        if r.get("url"):
            print(r["url"])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="gsearch",
        description=(
            "Google search (web or news) from the command line.\n"
            "\n"
            "gsearch drives a real, persistent Chromium profile via Playwright in a\n"
            "visible window, so Google's automated-traffic block does not trigger.\n"
            "It prints clean results (title, source, URL, snippet) in several\n"
            "formats, with an optional window that lets you solve a CAPTCHA."
        ),
        epilog=(
            "examples:\n"
            "  gsearch \"nvidia rma how to apply\"\n"
            "      Basic web search, default 10 results, human-readable text.\n"
            "\n"
            "  gsearch \"trump zelensky\" --news --navigate-resolve\n"
            "      Google News headlines with real article URLs (resolves the\n"
            "      opaque google.com/goto redirect links one by one).\n"
            "\n"
            "  gsearch \"openai\" -n 20 --format json | jq '.results[].url'\n"
            "      Machine-readable JSON, pipe into jq.\n"
            "\n"
            "  gsearch \"rust async book\" --format urls\n"
            "      Print only the result URLs, one per line.\n"
            "\n"
            "  gsearch \"ai news\" --format markdown --tbs qdr:d > ai-news.md\n"
            "      Markdown output limited to the past day; save to a file.\n"
            "\n"
            "  gsearch \"mechanical keyboards\" --format csv > kb.csv\n"
            "      CSV you can open in a spreadsheet.\n"
            "\n"
            "  GSEARCH_PROFILE=~/.my-gprofile gsearch \"query\"\n"
            "      Use a different persistent browser profile.\n"
            "\n"
            "output formats: text (default), json, csv, markdown, urls\n"
            "exit codes:     0 ok, 1 error, 2 blocked by Google, 130 interrupted\n"
            "env variables:  GSEARCH_PROFILE (profile dir), NO_COLOR (disable colors)\n"
            "docs:           ~/git/gsearch/README.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    ap.add_argument("query", help="the search query (quote multi-word queries)")

    g = ap.add_argument_group("search options")
    g.add_argument("-n", "--num", type=int, default=10, metavar="N",
                   help="maximum number of results to request (default: %(default)s)")
    g.add_argument("--news", action="store_true",
                   help="search Google News (tbm=nws) instead of the web")
    g.add_argument("--lang", default="en", metavar="LANG",
                   help="interface/results language, e.g. en, ko, ja (default: %(default)s)")
    g.add_argument("--tbs", default=None, metavar="FILTER",
                   help="restrict by time: qdr:h=hour, qdr:d=day, qdr:w=week, "
                        "qdr:m=month, qdr:y=year (default: no limit)")

    o = ap.add_argument_group("output options")
    ofmt = o.add_mutually_exclusive_group()
    ofmt.add_argument("-f", "--format", choices=["text", "json", "csv", "markdown", "urls"],
                      default="text", metavar="FMT",
                      help="output format: text, json, csv, markdown, urls "
                           "(default: %(default)s)")
    ofmt.add_argument("--json", dest="format", action="store_const", const="json",
                      help="shortcut for --format json")
    o.add_argument("--no-snippets", action="store_true",
                   help="text format: omit result snippets")
    o.add_argument("--no-urls", action="store_true",
                   help="text format: omit result URLs")

    l = ap.add_argument_group("link resolution")
    l.add_argument("--navigate-resolve", action="store_true",
                   help="resolve opaque google.com/goto links to their real "
                        "destination URLs by loading each one (slower, but gives "
                        "full article URLs, especially useful with --news)")

    b = ap.add_argument_group("browser options")
    b.add_argument("--headless", action="store_true",
                   help="run the browser hidden. Faster, but Google is much more "
                        "likely to show 'unusual traffic'; CAPTCHA wait is skipped")
    b.add_argument("--wait", type=int, default=2500, metavar="MS",
                   help="milliseconds to wait after page load before scraping "
                        "(default: %(default)s)")
    b.add_argument("--captcha-wait", type=int, default=180, metavar="SEC",
                   help="in headed mode, seconds to wait for you to solve a "
                        "CAPTCHA before giving up (default: %(default)s)")
    b.add_argument("-q", "--quiet", action="store_true",
                   help="suppress progress messages on stderr")

    ap.add_argument("-V", "--version", action="version",
                    version=f"gsearch {__version__}")
    return ap


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        data = search(
            query=args.query,
            num=args.num,
            news=args.news,
            lang=args.lang,
            headless=args.headless,
            navigate_resolve=args.navigate_resolve,
            tbs=args.tbs,
            wait_ms=args.wait,
            captcha_wait_s=args.captcha_wait,
            verbose=not args.quiet,
        )
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as e:  # surface a clean error
        print(f"error: {e}", file=sys.stderr)
        return 1

    fmt = args.format
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif fmt == "csv":
        _print_csv(data)
    elif fmt == "markdown":
        _print_markdown(data)
    elif fmt == "urls":
        _print_urls(data)
    else:
        _print_text(data, show_snippets=not args.no_snippets,
                    show_urls=not args.no_urls)

    return 2 if data["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())