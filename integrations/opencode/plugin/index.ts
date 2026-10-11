// ---------------------------------------------------------------------------
// gsearch plugin for OpenCode (v2 plugin API)
//
// Registers a `google_search` tool that wraps the locally installed `gsearch`
// CLI. gsearch drives a headed Playwright browser with a persistent profile,
// which lets it bypass Google's automated-traffic block and return clean,
// parsed results.
//
// The plugin exports a default definition with an `id` and a `setup(ctx)`
// function, which is the shape the OpenCode v2 plugin loader expects.
// ---------------------------------------------------------------------------

const CANDIDATES = [
  process.env.GSEARCH_BIN,
  "gsearch",
  `${process.env.HOME}/.local/bin/gsearch`,
  "/opt/homebrew/bin/gsearch",
  "/usr/local/bin/gsearch",
].filter(Boolean) as string[]

function resolveBin(): string {
  for (const candidate of CANDIDATES) {
    try {
      const found = Bun.which(candidate)
      if (found) return found
    } catch {
      // ignore and try the next candidate
    }
  }
  // Fall back to the bare name; the shell will report a clear error.
  return "gsearch"
}

type Result = {
  title: string
  source?: string
  url: string
  snippet?: string
}

type SearchOutput = {
  query: string
  news: boolean
  count: number
  pages_fetched?: number
  blocked: boolean
  captcha?: boolean
  results: Result[]
}

function render(out: SearchOutput): string {
  if (out.blocked) {
    return [
      "Google returned its 'unusual traffic' / CAPTCHA page, so no results",
      "were parsed. The user usually needs to run `gsearch init --rounds 6`",
      "once to teach Google this browser is trusted, then retry.",
    ].join(" ")
  }
  if (!out.results.length) {
    return `No results for "${out.query}".`
  }
  const head =
    `# ${out.count} result(s) for: ${out.query}` +
    (out.pages_fetched && out.pages_fetched > 1
      ? `  (${out.pages_fetched} pages)`
      : "")
  const body = out.results
    .map((r, i) => {
      const lines = [`${i + 1}. ${r.title}`]
      if (r.source) lines.push(`   ${r.source}`)
      lines.push(`   ${r.url}`)
      if (r.snippet) lines.push(`   ${r.snippet}`)
      return lines.join("\n")
    })
    .join("\n\n")
  return `${head}\n\n${body}`
}

async function runSearch(args: {
  query: string
  news?: boolean
  num?: number
  pages?: number
  all?: boolean
  tbs?: string
  lang?: string
  no_resolve?: boolean
  timeout_ms?: number
}): Promise<string> {
  const bin = resolveBin()
  const cli: string[] = [bin, args.query, "--format", "json", "-q"]
  if (args.news) cli.push("--news")
  if (args.num) cli.push("-n", String(args.num))
  if (args.all) cli.push("--all")
  else if (args.pages) cli.push("--pages", String(args.pages))
  if (args.tbs) cli.push("--tbs", args.tbs)
  if (args.lang) cli.push("--lang", args.lang)
  // JSON stays fast by default; resolve real URLs unless asked not to.
  if (!args.no_resolve) cli.push("--navigate-resolve")

  const timeout = args.timeout_ms ?? 180_000
  let proc: ReturnType<typeof Bun.spawn>
  try {
    proc = Bun.spawn(cli, {
      stdout: "pipe",
      stderr: "pipe",
      env: { ...process.env },
    })
  } catch (error) {
    return (
      `Could not start gsearch (${bin}). Is it installed and on PATH? ` +
      `Install it from https://github.com/pig-g/gsearch.\n\n${String(error)}`
    )
  }

  const timer = setTimeout(() => {
    try {
      proc.kill()
    } catch {
      // ignore
    }
  }, timeout)

  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]).finally(() => clearTimeout(timer))

  if (exitCode === 2) {
    return (
      "gsearch reported that Google is blocking this browser (exit 2). " +
      "Ask the user to run `gsearch init --rounds 6` once, then retry the " +
      "search.\n\n" +
      (stderr.trim() || stdout.trim())
    )
  }
  if (exitCode !== 0) {
    return (
      `gsearch failed (exit ${exitCode}).\n\n` +
      (stderr.trim() || stdout.trim() || "(no output)")
    )
  }

  let data: SearchOutput
  try {
    data = JSON.parse(stdout) as SearchOutput
  } catch {
    return "gsearch returned output that was not valid JSON:\n\n" + stdout.trim()
  }
  return render(data)
}

export default {
  id: "gsearch",
  async setup(ctx: {
    tool: {
      transform(callback: (editor: {
        add(tool: {
          name: string
          description: string
          input: unknown
          execute: (input: Record<string, unknown>) => Promise<{ content: string }>
        }): void
      }) => void): Promise<unknown>
    }
  }) {
    await ctx.tool.transform((editor) => {
      editor.add({
      name: "google_search",
      description:
        "Search Google or Google News via a real headed browser (the local " +
        "`gsearch` CLI). Use this for current web results, headlines, and " +
        "research when the built-in websearch is unavailable or you need " +
        "more/real links. Returns titles, URLs, sources and snippets. URLs " +
        "are automatically resolved to their real destinations.",
      input: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "The search query, e.g. 'nvidia rma how to apply'.",
          },
          news: {
            type: "boolean",
            description: "Search Google News instead of the web. Default false.",
          },
          num: {
            type: "integer",
            minimum: 1,
            maximum: 100,
            description: "Results requested per page (default 10).",
          },
          pages: {
            type: "integer",
            minimum: 1,
            maximum: 50,
            description:
              "Number of result pages to fetch by following 'Next' " +
              "(default 1, ~10 results per page).",
          },
          all: {
            type: "boolean",
            description:
              "Follow 'Next' until no more pages. Slower; overrides `pages`.",
          },
          tbs: {
            type: "string",
            description:
              "Time filter: qdr:h (hour), qdr:d (day), qdr:w (week), " +
              "qdr:m (month), qdr:y (year).",
          },
          lang: {
            type: "string",
            description: "Result language, e.g. 'en' (default) or 'ko'.",
          },
          no_resolve: {
            type: "boolean",
            description:
              "Skip resolving google.com/goto redirect links (faster, but " +
              "URLs may be opaque redirects).",
          },
          timeout_ms: {
            type: "integer",
            minimum: 5000,
            maximum: 600000,
            description: "Hard timeout for the whole search (default 180000 ms).",
          },
        },
        required: ["query"],
        additionalProperties: false,
      },
      execute: async (input: Record<string, unknown>) => {
        const content = await runSearch(input as Parameters<typeof runSearch>[0])
        return { content }
      },
      })
    })
  },
}