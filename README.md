# gsearch

Google search from the command line — web or news — powered by a **headed
Playwright browser** with a persistent profile.

This avoids Google's `unusual traffic` / CAPTCHA block that plain HTTP
scrapers and headless browsers hit, because it drives a real, persistent
Chromium profile the same way a manual browser session would.

## Install

```bash
cd /Users/mac5/git/gsearch
python3 -m venv .venv
./.venv/bin/pip install -e .
./.venv/bin/playwright install chromium
```

This creates a `gsearch` command inside that venv. To run it from anywhere:

```bash
# Option A: put the venv's bin on PATH (add to ~/.zshrc)
export PATH="/Users/mac5/git/gsearch/.venv/bin:$PATH"

# Option B: symlink the entry point into a dir already on PATH
ln -s /Users/mac5/git/gsearch/.venv/bin/gsearch /usr/local/bin/gsearch
```

Then, from any directory:

```bash
gsearch "nvidia rma how to apply"
```

## Usage

```
gsearch QUERY [options]
```

| Option | Description |
|---|---|
| `-n, --num N` | Number of results (default 10) |
| `--news` | Search Google News (`tbm=nws`) |
| `--lang en` | Interface language (default `en`) |
| `--tbs qdr:d` | Time filter: `qdr:h` hour, `qdr:d` day, `qdr:w` week, `qdr:m` month |
| `-f, --format FMT` | Output: `text` (default), `json`, `csv`, `markdown`, `urls` |
| `--json` | Shortcut for `--format json` |
| `--no-snippets` | Hide snippets in text output |
| `--no-urls` | Hide URLs in text output |
| `--navigate-resolve` | Resolve opaque `google.com/goto` links to real URLs (slow) |
| `--headless` | Run hidden (may trigger Google's block) |
| `--wait MS` | ms to wait after page load (default 2500) |
| `--captcha-wait S` | Seconds to wait for you to solve a CAPTCHA (default 180) |
| `-q, --quiet` | Suppress progress messages |
| `-V, --version` | Show version |

## Examples

```bash
# Basic web search
gsearch "nvidia rma how to apply"

# News headlines with real article URLs
gsearch "trump zelensky" --news --navigate-resolve

# JSON for scripting
gsearch "openai" -n 20 --format json | jq '.results[].url'

# Only the URLs
gsearch "rust async book" --format urls

# Markdown (great for notes)
gsearch "ai news" --format markdown --tbs qdr:d > ai-news.md

# CSV
gsearch "mechanical keyboards" --format csv > kb.csv
```

## Environment variables

| Variable | Purpose |
|---|---|
| `GSEARCH_PROFILE` | Override the persistent Chromium profile directory (default `~/.playwright-google-profile`) |
| `NO_COLOR` | Disable ANSI colors in text output |

## Using it as a library

```python
from gsearch import search

data = search("nvidia rma", num=5, news=False)
for r in data["results"]:
    print(r["title"], "->", r["url"])
```

`search()` accepts: `query, num, news, lang, headless, navigate_resolve, tbs,
wait_ms, captcha_wait_s, verbose`.

## Notes

- First run creates the profile at `~/.playwright-google-profile`. If Google
  shows a CAPTCHA, a Chromium window opens (headed mode) and the tool waits up
  to `--captcha-wait` seconds for you to solve it; the profile then caches the
  trust cookies for later runs.
- If Google blocks you, wait a while or run with a visible window and solve the
  CAPTCHA once. `--headless` bypasses the CAPTCHA wait and is more likely to be
  blocked.
- Requires a Chromium that Playwright can launch. Install once with
  `playwright install chromium`.

## License

MIT