# bfind — Barry Find

Find relevant, recent customer sessions so you can reuse prior notes, slides, and other materials when preparing a new delivery. Results highlight the customer, delivery date, subject, and full folder path while suppressing repetitive details.

## Why it exists

Delivering similar content to multiple customers leaves useful material scattered across many folders. Ordinary text searches find the topic but often return repetitive details that make it difficult to identify the latest useful delivery. This utility shortens preparation time by making those prior sessions easy to identify and open.

## What you can do

- Search plain-text customer event notes for a topic.
- Identify past sessions with their customer, delivery date, subject, and full folder path.
- See deliveries matching a specifically requested presentation first, newest first, then other on-topic deliveries and peripheral material. Future-dated deliveries are excluded.
- Open a result folder in Dolphin by pressing its letter (either case), without Enter; Enter selects result a.

When the delivery day is unknown but a year is known, January 1 is used for ranking and shown as `YYYY-01-01*`. If neither is known, the date appears as `Unknown`. Example output:

```text
a. Acme | 2026-10-22 | Vector Search Workshop
   /home/barry/GoogleDrive/Builder Relations/Customers/Acme/2026-10-22

b. Example Corp | 2026-09-14 | Vector Search Introduction
   /home/barry/GoogleDrive/Builder Relations/Customers/Example Corp/Search

Open result [a], or q to quit:
```

## Known presentation titles

The LLM receives the team's curated presentation catalog for relevance assessment and subject identification. When session evidence identifies a known presentation, including an abbreviation or paraphrase, it is instructed to return the exact catalog title. Broad topic overlap alone is insufficient; ambiguous or unrecognized presentations retain an evidence-based subject (or `Unknown`). The catalog does not establish that a delivery occurred. Subject identification remains a model judgment, without independent local verification.

The catalog is maintained in [`src/presentation_titles.hpp`](src/presentation_titles.hpp). Add titles there and rebuild to extend it. For a query identifying a specific presentation, the LLM also reports whether each session matches that presentation. On-topic title matches rank ahead of other on-topic results, with newest dates first within each group. Broad topic queries retain recency-first ordering. This semantic judgment can be wrong and is not independently verified. Local retrieval, candidate limits, date validation, and `--local-only` lexical ranking are unchanged.

## Technical details

Repository: [customer_session_search_utility](https://github.com/barronandersonmongo/customer_session_search_utility). Progress and verification are tracked separately in [PROJECT_STATUS.md](PROJECT_STATUS.md).

### Architecture

1. The C++ CLI loads configuration and accepts a topic.
2. Ripgrep searches for distinct whitespace-separated query words as case-insensitive literal text, dropping common English stopwords unless that would remove every term, and collects nearby context.
3. The application groups documents by customer/year/dated-topic session folder, removes duplicate lines, and selects candidates using term rarity across retrieved folders, original-query phrase presence, and match count. Integer term weights range from 100 to 999; the phrase bonus is 50 and the hit bonus is capped at 20. Equal scores use ascending folder path order, never unverified folder dates.
4. A single Grove Chat Completions request sends the query, candidate IDs, folder paths, and bounded excerpts to GPT-6 Astra.
5. The application validates IDs, relevance levels, and date evidence, excludes future deliveries, then places direct/substantially related sessions first, prioritizing identified presentation matches and then newest delivery within each group. Peripheral sessions follow.
6. Condensed results are displayed. In an interactive terminal, an optional selection prompt launches Dolphin independently of the CLI.

### Technical decisions and limits

Entries with resolved dates or date references older than six calendar months are excluded. The cutoff is inclusive and uses today in the system timezone; subtracting six months clamps to the last valid day of the destination month. Before scoring/shortlisting or calling the LLM, candidates are filtered using an ISO date at the start of the session-folder name or loose-note filename, then January 1 of the customer/year folder when only that year is known. Future references are also excluded. These metadata dates are references, not proof of delivery; an old reference can exclude a folder even if its contents describe newer work. Candidates with no usable metadata date/year remain eligible for LLM verification, and final validated dates/year references are checked against the same window. No file modification times are used.

- C++17 on Linux, CMake, and Boost.JSON for parsing and serialization. Boost.JSON's bundled implementation is compiled into the executable; no separate Boost.JSON binary library is linked.
- CMake enforces Boost 1.75.0 or newer as the compatibility minimum, not an exact dependency lock. All application and test targets use `-fstack-protector-strong` when supported. Optimized GNU/Clang glibc builds enable `_FORTIFY_SOURCE` at least 2 before libc headers, preserving stronger supplied settings; unoptimized builds do not force fortification.
- Curl handles HTTPS through an argument-safe child process. The key and request body travel through stdin, never command-line arguments or temporary request files. Redirects are not followed, and curl's user configuration is disabled.
- Curl requires TLS 1.2 or newer and receives only an explicit environment allowlist: executable lookup/locale/timezone, existing proxy settings, custom CA file/directory settings, and TLS backend selection. `SSLKEYLOGFILE`, application API credentials, dynamic-loader settings, and unrelated variables are not passed to curl. Proxy and CA settings are preserved by user decision and remain trusted inputs; proxy bypass is not forced. Other child environments, including Dolphin's desktop integration, are unchanged. This policy does not sandbox executable lookup through PATH or an already-compromised parent process.
- Ripgrep and Dolphin are invoked directly without a shell. Queries and folder names are passed as arguments.
- Search results and intermediate note content remain in memory. There is no persistent cache, index, or embeddings database.
- Default limits: 40 session candidates, 3,000 excerpt bytes per folder, and 16,384 completion tokens in one LLM request (2,048 for connection checks). The completion limit includes visible output and reasoning tokens. Candidate IDs and paths add a small amount of context beyond the excerpt budget. These limits provide headroom; they do not guarantee completion within the request timeout.
- Retrieval limits: 2 MiB per file, 12 matches per file, six surrounding lines, 1,200 bytes per retained line, 12 files and 100 lines per file per folder. Search output is capped at 16 MiB and the local search times out after 30 seconds. Hitting the output cap prints a warning and uses the complete records collected so far.
- API connection timeout is 10 seconds; the full request timeout is 55 seconds. Requests are not automatically retried.
- Curl failures distinguish DNS/proxy resolution, connection, timeout, TLS handshake/certificate configuration, and empty/failed responses using only exit codes. Unmapped failures include their numeric code. Responses exceeding 1 MiB have a separate error, checked before the child exit status. Curl stderr, URLs, headers, and response bodies are never printed as diagnostics.
- The child-process deadline also covers waiting after stdout closes. An overdue child is killed and reaped rather than leaving the CLI waiting indefinitely.
- The CLI ignores SIGPIPE for its own pipe handling, but restores default SIGPIPE behavior in ripgrep, curl, and Dolphin before executing them.
- A ripgrep timeout preserves complete records received so far and prints an incomplete-coverage warning. Filesystem failures skip only the affected file, with one stderr count; canonical paths (including failures) are cached per file for that search. Empty results from a partial search are explicitly labeled incomplete. Curl timeouts remain errors and partial API responses are never accepted.
- Dates require a valid calendar date plus a matching quote from the supplied notes or path. Supported evidence formats include `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY.MM.DD`, U.S. `MM/DD/YYYY`, and English month names with a four-digit year. File modification times are not used. A result with an evidenced delivery date after today is excluded entirely; today's deliveries are accepted. Today is captured once per verification using the system clock and local timezone (including `TZ`, if set), and is also supplied to the LLM. Without a validated delivery day, a known year supplies January 1 as a clearly labeled year reference. The year comes from an exact four-digit customer/year folder or a year-only model value backed by a matching source quote. A validated full date takes precedence; year references after today are also excluded. Without either kind of evidence, dates remain `Unknown`.
- Retrieval uses `--no-ignore`, so `.gitignore`, `.ignore`, and other ignore-file rules do not silently exclude ordinary notes. Hidden files/folders, binary files, and symlinks retain ripgrep's normal exclusions. Text in any ordinary file extension can match; PDFs and slides are not text-extracted. Queries cannot retrieve synonyms that share no literal query words.
- Ripgrep uses `--sort path` for deterministic file order. On an unchanged tree, output-limit truncation retains the same prefix; timing-based cutoffs and concurrent filesystem changes can still vary coverage. Sorted traversal can be slower than parallel unsorted search.
- Candidate selection is bounded and lexical, so the newest session may be omitted before LLM processing. Title-match and newest-first ordering apply to verified candidates, not every session on disk. Local selection does not promote folders based on unverified dates; refine the topic or increase `--candidates` when needed. A warning calls out the recency limitation when the candidate limit is reached.
- The main layout is `Customers/customer/year/YYYY-MM-DD - Topic/documents`, including nested document subfolders. Each dated-topic folder forms one candidate, keeping different sessions in the same year separate. `customer/YYYY-MM-DD - Topic` sessions without a year are also recognized. Loose notes directly under a year, and files in undated collections under that year, are individual candidates; several results may therefore open the same year folder. Other flat folders fall back to their containing folder. The fixed Customers folder anchors grouping. Folder-name dates identify boundaries only; delivery dates still require evidence and validation. If several deliveries share one session directory, the LLM is instructed to prefer a delivery matching the specifically requested presentation, then select the newest evidenced delivery within that match group or otherwise its newest on-topic delivery on or before today, preferring dated on-topic sessions to undated ones. It returns a peripheral session only if none are on-topic. At most one result is returned per candidate. LLM interpretations of relevance, customer, subject, and delivery context can still be wrong.
- Relevance 2 (substantially related) and 3 (direct) form one on-topic group. Within it, LLM-identified matches to a specifically requested presentation precede other on-topic sessions; each subgroup is sorted by validated date newest first, with year references treated as January 1 and unknown dates last. Relevance 1 (peripheral) is retained after that entire group and sorted the same way. Missing, null, or non-boolean model `title_match` fields default to false; peripheral results never receive title-match priority. Remaining ties use relevance, local search score, and original candidate order, in that sequence. Thus an unknown-dated on-topic session still appears before a dated peripheral session. The on-topic threshold lives in the named `on_topic()` function.
- Folder-opening prompts require both stdin and stdout to be terminals, and are suppressed by `--no-open`. Piped or redirected output contains only the normal result list and never waits for an invisible selection prompt.
- Opening Dolphin requires a nonempty `DISPLAY` or `WAYLAND_DISPLAY`. Without either, selection fails clearly without launching a child. A set variable is only a prerequisite; it does not guarantee display access or a successful window. Dolphin's later GUI startup remains independent of the CLI.

### Limits of verification

Year-only references are conservative sorting placeholders, not confirmed January 1 deliveries. Local-only mode shows metadata dates from session names or loose-note filenames, falling back to January 1 of the folder year; `*` marks a year-only reference. Without an LLM call, the customer is derived from the first folder below Customers, while the actual delivery day and relevance remain unverified.

Folder containment is checked before launching Dolphin, but a concurrent folder/symlink swap between validation and launch remains possible. The launcher is not an atomic filesystem sandbox.

Terminal output escapes C1 controls, bidi formatting controls, Unicode line/paragraph separators, and invalid UTF-8 bytes. Ordinary international text is preserved. Escaping affects display only; folder opening uses the actual validated path. The application does not keep a usage audit or persistent usage log.

Customer names always come from the first folder below the fixed Customers root, including local-only results; for example, `Customers/Warner Bros./2026/...` gives `Warner Bros.`. Any model-supplied customer value is ignored. Files directly in the Customers root display `Unknown Customer`. Missing, null, or non-string subject/date fields are treated as unknown, and unusable date evidence becomes empty. A subject over 300 bytes skips only that item with one stderr count; if every item is oversized, the response fails. Non-object items, invalid IDs or relevance, and duplicate IDs still reject the whole response. A response containing only evidenced future deliveries is a successful empty result.

After an LLM search returns results, a short stderr notice reminds you to check the customer, delivery date, and subject in the folder before relying on them. It does not appear for local-only searches, empty results, or connection checks, and the stdout result list is unchanged.

Local checks validate candidate IDs, relevance ranges, calendar dates, and matching date evidence; they do not authenticate what the notes claim. Customer is determined by folder placement, not by the model; subject is not independently verified against excerpts. A convincing planted note with a forged past delivery date can still mislead the model and rank highly. Matching evidence proves that the source contains a date, not that a delivery happened.

A direct relevance rating of 3 requires at least 50% of the distinct non-stopword query terms (or all terms for an all-stopword query), rounded up, in the note text actually retained in the submitted excerpt. Otherwise it is capped at 2; ratings 1 and 2 are unchanged, and the check never drops a result. Coverage uses case-insensitive literal matching and excludes folder paths, filename prefixes, and lines omitted by the excerpt budget. A single-term query passes when that term is present in the submitted note text. The percentage is centralized in `kMinimumDirectCoveragePercent`.

This is a lexical sanity check, not a prompt-injection defense: planted content can include all query terms. Because ratings 2 and 3 both qualify as on-topic and title-match grouping and then recency take priority, this cap affects relevance tie-breaking, not on-topic eligibility or the date ordering. Evidenced future deliveries remain excluded entirely.

### Build

Dependencies: a C++17 compiler, CMake 3.18+, Boost headers with Boost.JSON (1.75+), ripgrep, and curl. Python 3 is used for offline tests; Dolphin is optional for opening folders.

For Ubuntu/Debian, install the corresponding packages if needed:

```sh
sudo apt install g++ cmake libboost-json-dev ripgrep curl python3 dolphin
```

From the repository directory:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

To build without the Python test dependency, add `-DBUILD_TESTING=OFF` to the configure command. The executable is `build/bfind`.

### Configuration

Searches are restricted to the exact fixed folder `/home/barry/GoogleDrive/Builder Relations/Customers/`. It is not derived from `$HOME`, the working directory, or another environment value. `--root` is rejected. A legacy `SEARCH_ROOT` setting is accepted only when it exactly equals that literal (including the trailing slash); it never routes searches. Other values, including empty values, fail before searching or making an API request. You may launch bfind from any working directory.

The default configuration file is `$XDG_CONFIG_HOME/bfind/.env` when `XDG_CONFIG_HOME` is an absolute path; otherwise it is `$HOME/.config/bfind/.env`. Empty or relative `XDG_CONFIG_HOME` values are ignored. `HOME` must be absolute when used as the fallback. If neither variable supplies a valid base directory, use `--env FILE` or correct the environment.

Create a private configuration file at that location using `.env.example` as the template, then fill in the connection details. Never overwrite an existing configuration during setup. A missing config file is allowed: environment variables or `--local-only` may be sufficient.

`./.env` is never loaded implicitly. To use a trusted file elsewhere, pass `--env FILE` explicitly; a relative path is resolved against your current directory. Only select files you trust, because configuration controls the API destination.

#### One-time migration from the project `.env`

You can continue using the existing project configuration explicitly:

```sh
./build/bfind --env .env "vector search"
```

Alternatively, from the project directory, copy it to the default location. For the HOME fallback:

```sh
mkdir -p "$HOME/.config/bfind"
(umask 077; cp -n .env "$HOME/.config/bfind/.env")
chmod 600 "$HOME/.config/bfind/.env"
```

If `XDG_CONFIG_HOME` is set to an absolute path, use `$XDG_CONFIG_HOME/bfind` instead of `$HOME/.config/bfind` in those commands. `cp -n` avoids replacing an existing destination. These steps are for you to run; the application never migrates or overwrites configuration automatically.

#### Settings and precedence

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | Company-provided Grove API key, sent in the `api-key` header. |
| `LLM_BASE_URL` | Complete Grove HTTPS Chat Completions endpoint, including `/chat/completions`; used directly. |
| `LLM_MODEL` | Model identifier; use `gpt-6-astra`. |

Configuration supports `NAME=value`, single- or double-quoted values, optional `export`, and comments. Quoted values are literal: shell expansion and escape substitution are not performed. Environment variables override API config-file values individually. Search location is not configurable. API settings are required only for LLM requests, not local searches with no matches or `--local-only`.

The application checks the opened file with `fstat()` and reads that same descriptor. It prints a one-line warning to stderr if any group/other permission bits are set or the file is not owned by the effective current user, then continues. Use a user-owned file with mode `0600`. Symlinks are checked against their opened target; nonregular files are rejected. Warnings include no credentials, endpoint values, or config paths. These warnings are advisory; they do not establish that a file or endpoint is trusted.

Grove receives OpenAI-style requests with `model`, `messages`, and `max_completion_tokens`. Extraction requests also set `response_format` to `json_object`; text is read from `choices[0].message.content`. Truncation, incomplete completions, and malformed response envelopes have distinct errors; partial completions and invalid result IDs are rejected. Unsupported full-date evidence falls back to a grounded year reference when available, otherwise `Unknown`. See the [Chat Completions API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) for completion-token semantics.

`.env` is ignored by Git. Keep real credentials and private endpoint details out of documentation, test fixtures, logs, and commits. The template contains no credentials. Normal searches send the selected excerpts and folder paths to the configured company endpoint.

### Run

For convenient command-line access with the existing project configuration, link the repository launcher into your user bin directory:

```sh
ln -s /home/barry/barry_tools/barry_customer_session_search_utility/bin/bfind /home/barry/.local/bin/bfind
```

With `/home/barry/.local/bin` on PATH, run `bfind "vector search"` from any directory. The launcher executes the repository's `build/bfind` with `--env /home/barry/barry_tools/barry_customer_session_search_utility/.env` and forwards your arguments unchanged. It contains no credentials and never sources the file; the executable parses it normally. Rebuilds at the same location are picked up automatically. Moving the repository or deleting the build directory breaks the launcher. The installed symlink now points to this launcher.

From the repository directory, using configuration at the default user location (or environment variables):

```sh
./build/bfind "vector search"
./build/bfind --verbose "vector search"
./build/bfind --no-open --limit 5 "aggregation workshop"
./build/bfind "schema design"
```

Check model access without sending notes:

```sh
./build/bfind --check-connection
```

Inspect unverified local matches without an API call:

```sh
./build/bfind --local-only "vector search"
```

Additional options:

```text
--env FILE       Explicit trusted config file (default: XDG/HOME user config)
--verbose, -v    Show live progress, counts, timings, and limits on stderr
--limit N        Maximum displayed results (default 10, maximum 25)
--candidates N   Maximum session candidates sent to the LLM (default 40, maximum 40)
--context N      Surrounding lines per match (default 6, maximum 30)
--no-open        Suppress the Dolphin prompt
--help           Show command-line help
```

Use `--` before a topic beginning with a hyphen. At the folder prompt, press a listed letter in either case to open it immediately, press Enter for result a, or press `q`/`Q` to quit immediately. Labels run a–p and r–z, reserving q for quit; at most 25 results can be displayed. Invalid selections prompt again. Terminal settings are restored before opening a folder, on quit, and before delivering interruption/termination signals. Launch success means Dolphin was started; desktop integration is handled by Dolphin.

The CLI exits with code 0 for successful searches (including no matches) and code 1 for errors. Diagnostics go to stderr; results go to stdout.

Use `bfind --verbose "vector search"` to see where time is being spent. Timestamped stderr messages cover configuration readiness, folder availability, ripgrep progress and match counts, grouping and candidate selection, excerpt sizes, LLM request progress and optional token usage, validation outcomes, ranking, and display. Running child processes emit a heartbeat about every two seconds. Local search may take up to 30 seconds and an LLM request up to 55 seconds; verbose mode does not change those limits or add retries. Verbose explanations include sanitized matched/missing query terms, exact-phrase checks in retained note text and folder names, source paths (including legacy-note filenames), up to three actual matching note lines per displayed result, with filenames and line numbers (up to 1,200 bytes retained per line, terminal controls escaped), score components, submitted-excerpt coverage, and model/effective relevance ratings and the LLM presentation-title-match decision. Result letters map to candidate IDs after ranking. These explain literal retrieval and ranking, not independent proof of topical relevance; no extra LLM request is made. Matching note text is shown only in verbose mode; surrounding nonmatching context is omitted. API configuration values and raw model responses are not logged. Progress is console-only and is not persisted as an audit log. Normal stdout remains unchanged.

### Development and documentation maintenance

Offline integration tests use real ripgrep, synthetic notes, and mocked curl and Dolphin processes. They require no credentials or network connection. A separate, non-installed `bfind-fixture` target has a compile-time fixed folder under `build/` so tests never search real customer notes. It has no runtime root override; the production target always uses the exact customer folder. Tests also verify override rejection against the production executable.

Keep this file, `AGENTS.md`, and `PROJECT_STATUS.md` synchronized with changes. Keep progress, readiness, verification results, and outstanding work in `PROJECT_STATUS.md`. Keep the opening README sections focused on functional needs and benefits, with architecture, decisions, configuration, and build and run instructions below.

Commit each completed logical change after verification, including related documentation, then push to `origin` before ending each interaction. No separate push request is required. Do not create empty commits for interactions without changes; push any pending local commits.
