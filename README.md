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

## First-run setup (`gsearch init`)

On a new machine there is no browser profile yet, so Google may show a
CAPTCHA once. Run the guided setup first:

```bash
gsearch init
```

It opens Google in a visible browser and loads it several times, pausing
whenever a CAPTCHA appears so you can solve it.

**Google trust often takes more than one visit.** If it still shows
`unusual traffic`, run it again (or with more rounds):

```bash
gsearch init --rounds 6
```

Once you see `✓ Profile initialized and trusted`, search normally. Check
the current state any time with:

```bash
gsearch status
```

If a plain search hits a block, gsearch prints a hint to re-run
`gsearch init`. The profile and its trust state are stored under
`~/.playwright-google-profile` (override with `GSEARCH_PROFILE`).

## Usage

```
gsearch QUERY [options]
gsearch init            # first-run setup
gsearch status          # show profile + trust state
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
| `--navigate-resolve` | Resolve opaque `google.com/goto` links to real URLs (slow). **Automatic for `text`, `markdown`, and `urls` output.** |
| `--no-resolve` | Do not auto-resolve `google.com/goto` links |
| `--headless` | Run hidden (may trigger Google's block) |
| `--wait MS` | ms to wait after page load (default 2500) |
| `--captcha-wait S` | Seconds to wait for you to solve a CAPTCHA (default 180) |
| `--no-lock` | Skip the profile lock (allows concurrent runs) |
| `-q, --quiet` | Suppress progress messages |
| `-V, --version` | Show version |

`gsearch init` options:

| Option | Description |
|---|---|
| `--rounds N` | Number of Google visits to attempt (default 3) |
| `--lang LANG` | Google interface language (default `en`) |
| `--between MS` | ms to wait between visits (default 4000) |
| `--captcha-wait S` | Seconds to wait for you to solve each CAPTCHA (default 300) |
| `--headless` | Run hidden (not recommended for setup) |

## Examples

```bash
# Basic web search
gsearch "nvidia rma how to apply"

# News headlines with real article URLs
gsearch "trump zelensky" --news --navigate-resolve

# JSON for scripting
gsearch "openai" -n 20 --format json | jq '.results[].url'

# Only the URLs (auto-resolved to real destinations)
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
from gsearch import search, check_trust, warmup

data = search("nvidia rma", num=5, news=False)
for r in data["results"]:
    print(r["title"], "->", r["url"])

# Is this profile currently trusted?
print(check_trust()["trusted"])

# Attempt to establish trust (opens a browser, waits for CAPTCHA)
result = warmup(rounds=3)
print(result["trusted"], result["history"])
```

`search()` accepts: `query, num, news, lang, headless, navigate_resolve, tbs,
wait_ms, captcha_wait_s, verbose`.

## Trust & blocking

- The first run creates the profile at `~/.playwright-google-profile`. A plain
  search nudges you to run `gsearch init` if the profile is brand new.
- Google trust is **not always granted in one visit**. `gsearch init` loads
  Google several times and waits for you to solve any CAPTCHA; if it is still
  blocked, run it again with more rounds.
- Trust state is recorded in `gsearch-state.json` inside the profile and shown
  by `gsearch status` (initialized, trusted, last-trusted time, block counts).
- `--headless` skips the CAPTCHA wait and is more likely to be blocked; use the
  default headed mode when (re)establishing trust.
- A profile lock prevents two concurrent runs from clobbering the same profile.
  Pass `--no-lock` only if you are sure no other run is active.
- Requires Playwright's Chromium: install once with `playwright install chromium`.

## License

MIT