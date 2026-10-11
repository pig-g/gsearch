"""Command-line interface for gsearch."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from typing import List

from .core import search, check_trust, warmup, profile_dir
from .profile import (
    ProfileLock,
    ProfileState,
    load_state,
    save_state,
    mark_trusted,
    mark_blocked,
    mark_captcha,
    profile_exists,
    browser_installed,
    install_hint,
    STATE_FILENAME,
)
from . import __version__

# ANSI colors (disabled when not a TTY or when NO_COLOR is set).
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _err(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Output renderers
# --------------------------------------------------------------------------- #

def _print_text(data: dict, show_snippets: bool, show_urls: bool) -> None:
    if data["blocked"]:
        print(_c("BLOCKED (Google 'unusual traffic')", "31"), file=sys.stderr)
        return
    pages = data.get("pages_fetched", 1)
    suffix = f"  ({pages} pages)" if pages > 1 else ""
    print(_c(f"# {data['count']} results for: {data['query']}", "1") + _c(suffix, "2"))
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


# --------------------------------------------------------------------------- #
# Profile status / first-run guidance
# --------------------------------------------------------------------------- #

def _human_age(seconds: float) -> str:
    if seconds == float("inf"):
        return "never"
    s = int(seconds)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def profile_report(profile: str, state: ProfileState) -> str:
    lines = [
        f"profile dir : {profile}",
        f"exists      : {profile_exists(profile)}",
        f"initialized : {state.initialized}",
        f"trusted     : {state.trusted}",
        f"last trusted: {_human_age(state.trust_age_seconds)}",
        f"trust events: {state.trust_events}",
        f"captchas seen: {state.captchas_seen}",
        f"recent blocks: {state.consecutive_blocks}",
    ]
    return "\n".join(lines)


def _first_run_guidance(quiet: bool) -> None:
    """Explain setup to a user whose profile is not initialized yet."""
    if quiet:
        return
    _err(
        _c("\nThis looks like the first run on this machine.", "33") + "\n"
        "  No Search profile exists yet, so Google may show a CAPTCHA once.\n"
        "  Recommended: run the guided setup first:\n\n"
        f"      {_c('gsearch init', '1')}\n\n"
        "  A browser window will open; solve the CAPTCHA if shown, then press\n"
        "  Enter in the terminal. Proceeding with the search anyway…\n"
    )


# --------------------------------------------------------------------------- #
# init command
# --------------------------------------------------------------------------- #

def _cmd_init(args) -> int:
    profile = profile_dir()

    if not browser_installed():
        _err(_c("Playwright's Chromium is not available.", "31"))
        _err(install_hint())
        return 1

    try:
        lock = ProfileLock(profile)
        lock.acquire()
    except OSError as e:
        _err(f"error: could not lock profile: {e}")
        return 1
    if not lock._acquired:
        pid = lock.holder_pid()
        where = f" (pid {pid})" if pid else ""
        _err(f"error: profile is already in use by another run{where}: {profile}")
        return 1

    state = load_state(profile)
    try:
        _err(_c("Initializing gsearch search profile…", "1"))
        _err(f"  profile: {profile}")
        if args.headless:
            _err(_c("  warning: --headless cannot solve a CAPTCHA; use the "
                    "default (headed) mode for setup.", "33"))
        _err(
            "\n  A browser window will open at Google. If a CAPTCHA or\n"
            "  'unusual traffic' page appears, solve it there.\n"
            "  Google trust sometimes takes a few visits — this will load\n"
            f"  Google up to {args.rounds} time(s).\n"
        )

        result = warmup(
            rounds=args.rounds,
            lang=args.lang,
            headless=args.headless,
            wait_ms=args.wait,
            captcha_wait_s=args.captcha_wait,
            between_ms=args.between,
            verbose=True,
        )
    except KeyboardInterrupt:
        _err("\ninterrupted — profile may be partially initialized.")
        return 130
    except Exception as e:
        _err(f"error during setup: {e}")
        return 1
    finally:
        lock.release()

    history = result["history"]
    captchas = result.get("captchas", 0)
    _err("")
    for i, ok in enumerate(history, 1):
        mark = _c("ok", "32") if ok else _c("blocked", "31")
        _err(f"  visit {i}: {mark}")
    if captchas:
        _err(f"  ({captchas} CAPTCHA page(s) solved)")

    if result["trusted"]:
        mark_trusted(state)
        if captchas:
            mark_captcha(state)
            # mark_captcha counts one; record the true number seen.
            state.captchas_seen += max(0, captchas - 1)
        save_state(state, profile)
        _err(_c("\n✓ Profile initialized and trusted.", "32"))
        _err("  You can now search normally, e.g.:")
        _err("      " + _c('gsearch "your query"', "1"))
        if not args.headless:
            _err("  Tip: --headless is faster, but re-run `gsearch init` if it "
                 "gets blocked.")
        return 0

    mark_blocked(state)
    state.initialized = True
    if captchas:
        mark_captcha(state)
        state.captchas_seen += max(0, captchas - 1)
    save_state(state, profile)
    _err(_c("\n✗ Google still showed 'unusual traffic'.", "33"))
    _err("  Google trust often takes more than one visit. Try again:")
    _err("      " + _c("gsearch init --rounds 6", "1"))
    _err("  If it persists, wait a little while, or use a different network,")
    _err("  then run `gsearch init` again.")
    return 2


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

def build_init_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="gsearch init",
        description=(
            "Set up the persistent Chromium profile used by gsearch.\n"
            "Opens Google in a visible browser and loads it several times,\n"
            "pausing whenever a CAPTCHA appears so you can solve it. Google\n"
            "trust can take a few visits, so this command is repeatable."
        ),
        epilog=(
            "examples:\n"
            "  gsearch init\n"
            "      Guided setup with 3 Google visits (default).\n"
            "\n"
            "  gsearch init --rounds 6\n"
            "      Try harder if Google keeps showing 'unusual traffic'.\n"
            "\n"
            "After a successful init you can search normally:\n"
            "  gsearch \"your query\"\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--rounds", type=int, default=3, metavar="N",
                    help="number of Google visits to attempt (default: %(default)s)")
    ap.add_argument("--lang", default="en", metavar="LANG",
                    help="Google interface language (default: %(default)s)")
    ap.add_argument("--headless", action="store_true",
                    help="run hidden (NOT recommended: cannot solve a CAPTCHA)")
    ap.add_argument("--wait", type=int, default=2500, metavar="MS",
                    help="ms to wait after each page load (default: %(default)s)")
    ap.add_argument("--between", type=int, default=4000, metavar="MS",
                    help="ms to wait between visits (default: %(default)s)")
    ap.add_argument("--captcha-wait", type=int, default=300, metavar="SEC",
                    help="seconds to wait for you to solve each CAPTCHA "
                         "(default: %(default)s)")
    return ap


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="gsearch",
        description=(
            "Google search (web or news) from the command line.\n"
            "\n"
            "gsearch drives a real, persistent Chromium profile via Playwright in a\n"
            "visible window, so Google's automated-traffic block does not trigger.\n"
            "It prints clean results (title, source, URL, snippet) in several\n"
            "formats, with an optional window that lets you solve a CAPTCHA.\n"
            "\n"
            "First run on a new machine: use 'gsearch init' to set up the search\n"
            "profile (a browser opens so you can solve Google's CAPTCHA once)."
        ),
        epilog=(
            "commands:\n"
            "  gsearch \"QUERY\"        run a search\n"
            "  gsearch init          first-run setup (opens browser, solve CAPTCHA)\n"
            "  gsearch status        show profile/trust state\n"
            "\n"
            "examples:\n"
            "  gsearch init\n"
            "      Guided first-run setup. Opens Google; solve the CAPTCHA if shown.\n"
            "      Repeatable: trust sometimes needs more than one visit.\n"
            "\n"
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
            "  gsearch \"nvidia rma\" --pages 3\n"
            "      Follow Google's \"Next\" link to fetch 3 result pages.\n"
            "\n"
            "  gsearch \"nvidia rma\" --all --format urls\n"
            "      Every available page, URLs only (follows Next until the end).\n"
            "\n"
            "  gsearch \"rust async book\" --format urls\n"
            "      Print only the result URLs, one per line.\n"
            "\n"
            "  gsearch \"ai news\" --format markdown --tbs qdr:d > ai-news.md\n"
            "      Markdown output limited to the past day; save to a file.\n"
            "\n"
            "  gsearch status\n"
            "      Show whether the profile is initialized/trusted and when it was\n"
            "      last known good.\n"
            "\n"
            "output formats: text (default), json, csv, markdown, urls\n"
            "exit codes:     0 ok, 1 error, 2 blocked/not trusted, 130 interrupted\n"
            "env variables:  GSEARCH_PROFILE (profile dir), NO_COLOR (disable colors)\n"
            "docs:           ~/git/gsearch/README.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ---- default search query (positional) ----
    ap.add_argument("query", nargs="?", help="the search query (quote multi-word queries)")

    g = ap.add_argument_group("search options")
    g.add_argument("-n", "--num", type=int, default=10, metavar="N",
                   help="results requested per page (default: %(default)s)")
    g.add_argument("-p", "--pages", type=int, default=1, metavar="P",
                   help="number of result pages to fetch by following 'Next' "
                        "(default: %(default)s); Google shows ~10 per page")
    g.add_argument("--all", dest="all_pages", action="store_true",
                   help="follow 'Next' until there are no more pages "
                        "(equivalent to a large --pages)")
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
                        "full article URLs). Automatic for text/markdown/urls "
                        "output; use --no-resolve to disable.")
    l.add_argument("--no-resolve", action="store_true",
                   help="do not auto-resolve google.com/goto links even for "
                        "formats that normally resolve them")

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
    b.add_argument("--no-lock", action="store_true",
                   help="do not take the profile lock (allows concurrent runs, "
                        "but Chromium may refuse to start)")
    b.add_argument("-q", "--quiet", action="store_true",
                   help="suppress progress messages on stderr")

    ap.add_argument("-V", "--version", action="version",
                    version=f"gsearch {__version__}")
    return ap


def _cmd_status(args) -> int:
    profile = profile_dir()
    state = load_state(profile)
    print(profile_report(profile, state))
    if not browser_installed():
        print(_c("\nbrowser: NOT installed — run `playwright install chromium`", "31"))
    else:
        print("browser: installed")
    if not profile_exists(profile):
        print(_c("\nNot initialized. Run `gsearch init` first.", "33"))
    elif not state.trusted:
        print(_c("\nNot currently trusted. Run `gsearch init` to (re)establish trust.", "33"))
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Route subcommands explicitly so a bare query still works
    # (argparse subparsers would otherwise treat the query as a command).
    if argv and argv[0] in {"init", "status"}:
        sub = argv[0]
        rest = argv[1:]
        if sub == "init":
            return _cmd_init(build_init_parser().parse_args(rest))
        return _cmd_status(build_parser().parse_args([]))

    ap = build_parser()
    args = ap.parse_args(argv)

    # No query.
    if not args.query:
        ap.print_help()
        return 1

    if not browser_installed():
        _err(_c("error: Playwright's Chromium is not available.", "31"))
        _err(install_hint())
        return 1

    profile = profile_dir()
    state = load_state(profile)
    if not state.initialized and not profile_exists(profile):
        _first_run_guidance(args.quiet)

    lock = None
    if not args.no_lock:
        lock = ProfileLock(profile)
        if not lock.acquire():
            pid = lock.holder_pid()
            where = f" (pid {pid})" if pid else ""
            _err(f"error: profile is already in use by another gsearch run{where}: {profile}")
            _err("wait for it to finish, or pass --no-lock if you are sure.")
            return 1

    try:
        data = search(
            query=args.query,
            num=args.num,
            news=args.news,
            lang=args.lang,
            headless=args.headless,
            # Resolve redirect links for formats where the URL is the point
            # (urls, text, markdown) unless the user opted out.
            navigate_resolve=args.navigate_resolve or (
                args.format in {"urls", "text", "markdown"} and not args.no_resolve
            ),
            tbs=args.tbs,
            wait_ms=args.wait,
            captcha_wait_s=args.captcha_wait,
            pages=(50 if args.all_pages else args.pages),
            verbose=not args.quiet,
        )
    except KeyboardInterrupt:
        _err("\ninterrupted")
        return 130
    except Exception as e:
        _err(f"error: {e}")
        return 1
    finally:
        if lock:
            lock.release()

    # Update trust state based on the outcome.
    if data.get("captcha") or data.get("captcha_seen"):
        mark_captcha(state)
    if data["blocked"]:
        mark_blocked(state)
        save_state(state, profile)
    else:
        mark_trusted(state)
        save_state(state, profile)

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

    if data["blocked"]:
        if not args.quiet:
            _err(
                _c("\nGoogle is blocking this profile/IP right now.", "33") + "\n"
                "  Try:  gsearch init         (solve the CAPTCHA, rebuild trust)\n"
                "  Or:   wait a bit, then retry."
            )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())