# gsearch × OpenCode

Two ways to make `gsearch` available to OpenCode agents. They are independent;
install either or both.

| | What it is | How the agent uses it |
|---|---|---|
| **Skill** | Instructions in `SKILL.md` | Loads guidance, then runs `gsearch` in the shell |
| **Plugin (tool)** | A registered `google_search` tool | Calls it directly, no shell needed |

## Install

```sh
./install.sh                 # into ~/.config/opencode
```

Then restart OpenCode:

```sh
opencode service restart
```

Verify:

```sh
opencode plugin list         # should show: gsearch  local  .../plugins/gsearch/index.ts
```

## Skill

`skill/SKILL.md` goes to `~/.config/opencode/skills/gsearch/SKILL.md`.

OpenCode advertises the `gsearch` skill to agents when a request involves web
search, and lets them load it on demand. It documents when to use `--news`,
`--pages`, `--format json`, how to handle the blocking/`gsearch init` flow, and
the output shapes.

## Plugin (tool)

`plugin/index.ts` goes to `~/.config/opencode/plugins/gsearch/index.ts`.

It registers one tool, **`google_search`**:

| Argument | Type | Notes |
|---|---|---|
| `query` | string (required) | The search query |
| `news` | boolean | Use Google News instead of the web |
| `num` | integer 1–100 | Results per page (default 10) |
| `pages` | integer 1–50 | Fetch N result pages by following "Next" |
| `all` | boolean | Follow "Next" until no more pages (overrides `pages`) |
| `tbs` | string | Time filter: `qdr:h`, `qdr:d`, `qdr:w`, `qdr:m`, `qdr:y` |
| `lang` | string | Result language, e.g. `en`, `ko` |
| `no_resolve` | boolean | Skip resolving `google.com/goto` redirect links |
| `timeout_ms` | integer | Hard timeout (default 180000 ms) |

The tool runs `gsearch "<query>" --format json -q --navigate-resolve` and
renders the results as readable text (title, source, URL, snippet). On a
blocked (CAPTCHA) response or exit code 2 it tells the agent to run
`gsearch init --rounds 6` once and retry.

### Binary resolution

The plugin finds the CLI via, in order:

1. `GSEARCH_BIN` environment variable
2. `gsearch` on `PATH`
3. `~/.local/bin/gsearch`, `/opt/homebrew/bin/gsearch`, `/usr/local/bin/gsearch`

Set `GSEARCH_BIN=/path/to/gsearch` if yours lives elsewhere.

## Uninstall

```sh
rm -rf ~/.config/opencode/skills/gsearch ~/.config/opencode/plugins/gsearch
opencode service restart
```