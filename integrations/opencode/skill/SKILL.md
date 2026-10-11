---
name: Google Search (gsearch)
description: >-
  Use when the user wants to search Google or Google News, look up current web
  results, find articles/headlines, or research something on the web and the
  built-in websearch tool is unavailable, blocked, or needs richer results.
  Wraps the local `gsearch` CLI, which drives a real browser so Google does not
  block it.
---

# Google Search with `gsearch`

`gsearch` is a locally installed CLI that queries Google (web or news) through
a headed Playwright browser with a persistent profile. It bypasses Google's
automated-traffic block and returns clean, parsed results.

Always call it as `gsearch` (it is on `PATH` via `~/.local/bin/gsearch`).

## Quick usage

```bash
gsearch "your query"                       # web results (default 10)
gsearch "your query" --news                # Google News
gsearch "your query" --pages 3             # follow "Next" for ~30 results
gsearch "your query" --all                 # every available page
gsearch "your query" --format json         # machine-readable
gsearch "your query" --format urls         # URLs only
gsearch "your query" --format markdown     # markdown
gsearch "your query" --tbs qdr:d           # past day (h/d/w/m/y)
gsearch "your query" -n 20 --pages 2       # 20 per page, 2 pages
```

## When to use each option

| Goal | Command |
|------|---------|
| Current web results | `gsearch "QUERY"` |
| Headlines / news | `gsearch "QUERY" --news` |
| Recent content | add `--tbs qdr:d` (day), `qdr:w` (week) |
| More than one page | add `--pages N` or `--all` |
| Parse output in code | `--format json` and read `.results[]` |
| Feed links to another step | `--format urls` |

## Output

Text output is human-readable:

```
# 10 results for: nvidia rma

1. Product Warranties — NVIDIA
   https://www.nvidia.com/en-us/support/warranty/
   <snippet>
```

JSON output shape:

```json
{
  "query": "nvidia rma",
  "count": 10,
  "pages_fetched": 1,
  "blocked": false,
  "results": [
    {"title": "...", "source": "...", "url": "...", "snippet": "..."}
  ]
}
```

Use `--format json` whenever you need to extract fields programmatically;
prefer `--format urls` when you only need links.

## Important behavior

- **First run on a machine may need setup.** If `gsearch` reports Google is
  blocking it (exit code 2, `blocked: true`, or "unusual traffic"), run:
  ```bash
  gsearch init --rounds 6
  ```
  This opens a browser window for the user to solve a CAPTCHA. Trust is not
  always granted in one visit, so retry if needed. Check state with
  `gsearch status`.
- **Exit codes:** `0` ok, `1` error, `2` blocked/not trusted, `130` interrupted.
- **URLs auto-resolve** for `text`, `markdown`, and `urls` output (Google wraps
  links in `google.com/goto` redirects; gsearch follows them). JSON stays fast
  unless you pass `--navigate-resolve`.
- **One run at a time.** A profile lock prevents concurrent runs; if you see
  "profile is already in use", wait and retry.
- **Slower than HTTP search.** Each run launches a browser; pagination and link
  resolution add a few seconds. Prefer small `-n`/`--pages` unless more is needed.
- **Headless caveat:** `--headless` is faster but much more likely to be
  blocked; use the default (headed) mode unless speed matters and it works.

## Examples

```bash
# Latest news on a topic
gsearch "trump zelensky" --news --navigate-resolve

# Research with more sources
gsearch "nvidia rma how to apply" --pages 2 --format markdown

# Scriptable extraction
gsearch "rust async book" -n 20 --format json | jq -r '.results[].url'

# Recent results only
gsearch "ai regulation" --tbs qdr:w --pages 2
```

## Reference

- Source / docs: `~/git/gsearch` (README.md)
- Profile: `~/.playwright-google-profile` (override with `GSEARCH_PROFILE`)
- Full help: `gsearch --help`, `gsearch init --help`