# bfind — Barry Find

Find relevant, recent customer sessions so you can reuse prior notes, slides, and other materials when preparing a new delivery. Results highlight the customer, delivery date, subject, and full folder path while suppressing repetitive details.

## Why it exists

Delivering similar content to multiple customers leaves useful material scattered across many folders. Ordinary text searches find the topic but often return repetitive details that make it difficult to identify the latest useful delivery. This utility shortens preparation time by making those prior sessions easy to identify and open.

## What you can do

- Search plain-text customer event notes for a topic.
- Identify past sessions with their customer, delivery date, subject, and full folder path.
- See the newest on-topic deliveries first, followed by peripheral material. Future-dated deliveries are excluded.
- Open a result folder in Dolphin by entering its number; Enter selects result 1.

Missing or unsupported delivery dates appear as `Unknown`. Example output:

```text
1. Acme | 2026-10-22 | Vector Search Workshop
   /home/barry/GoogleDrive/Builder Relations/Customers/Acme/2026-10-22

2. Example Corp | 2026-09-14 | Vector Search Introduction
   /home/barry/GoogleDrive/Builder Relations/Customers/Example Corp/Search

Open result [1], or q to quit:
```

## Technical details

Repository: [customer_session_search_utility](https://github.com/barronandersonmongo/customer_session_search_utility). Progress and verification are tracked separately in [PROJECT_STATUS.md](PROJECT_STATUS.md).

### Architecture

1. The C++ CLI loads configuration and accepts a topic.
2. Ripgrep searches for any of the topic's whitespace-separated words as case-insensitive literal text, collecting matching lines and nearby context.
3. The application groups matches by their containing folder, removes duplicate lines, and selects candidates using term coverage, exact-phrase presence, and match count.
4. A single Grove Chat Completions request sends the query, candidate IDs, folder paths, and bounded excerpts to GPT-6 Astra.
5. The application validates IDs, relevance levels, and date evidence, excludes future deliveries, then places direct/substantially related sessions first, newest delivery first. Peripheral sessions follow.
6. Condensed results are displayed. In an interactive terminal, an optional selection prompt launches Dolphin independently of the CLI.

### Technical decisions and limits

- C++17 on Linux, CMake, and Boost.JSON for parsing and serialization. Boost.JSON's bundled implementation is compiled into the executable; no separate Boost.JSON binary library is linked.
- Curl handles HTTPS through an argument-safe child process. The key and request body travel through stdin, never command-line arguments or temporary request files. Redirects are not followed, and curl's user configuration is disabled.
- Ripgrep and Dolphin are invoked directly without a shell. Queries and folder names are passed as arguments.
- Search results and intermediate note content remain in memory. There is no persistent cache, index, or embeddings database.
- Default limits: 20 candidate folders, 3,000 excerpt bytes per folder, and 4,096 output tokens in one LLM request. Candidate IDs and paths add a small amount of context beyond the excerpt budget.
- Retrieval limits: 2 MiB per file, 12 matches per file, six surrounding lines, 1,200 bytes per retained line, 12 files and 100 lines per file per folder. Search output is capped at 16 MiB and the local search times out after 30 seconds. Hitting the output cap prints a warning and uses the complete records collected so far.
- API connection timeout is 10 seconds; the full request timeout is 55 seconds. Requests are not automatically retried.
- Dates require a valid calendar date plus a matching quote from the supplied notes or path. Supported evidence formats include `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY.MM.DD`, U.S. `MM/DD/YYYY`, and English month names with a four-digit year. File modification times are not used. A result with an evidenced delivery date after today is excluded entirely; today's deliveries are accepted. Today is captured once per verification using the system clock and local timezone (including `TZ`, if set), and is also supplied to the LLM. Dates without valid matching evidence remain `Unknown`.
- Retrieval follows ripgrep's normal hidden-file, ignore-file, binary-file, and symlink exclusions. It does not extract text from PDFs or slide decks, and it cannot retrieve synonyms that share no literal query words.
- Candidate selection is bounded and lexical, so the newest session may be omitted before LLM processing. Newest-first ordering applies to verified candidates, not every session on disk. Local selection does not promote folders based on unverified dates; narrow `--root`, refine the topic, or increase `--candidates` when needed. A warning calls out the recency limitation when the candidate limit is reached.
- Each containing directory is one candidate; nested folders are separate candidates. If several sessions share one directory, the LLM is instructed to select its newest evidenced on-topic delivery on or before today, preferring dated on-topic sessions to undated ones. It returns a peripheral session only if none are on-topic. At most one session is returned per directory. LLM interpretations of relevance, customer, subject, and delivery context can still be wrong.
- Relevance 2 (substantially related) and 3 (direct) form one on-topic group, sorted by validated date newest first, with unknown dates last. Relevance 1 (peripheral) is retained after that entire group and sorted the same way. Remaining ties use relevance, local search score, and original candidate order, in that sequence. Thus an unknown-dated on-topic session still appears before a dated peripheral session. The on-topic threshold lives in the named `on_topic()` function.
- Folder-opening prompts are skipped when stdin is not a terminal or `--no-open` is supplied.

### Limits of verification

After an LLM search returns results, a short stderr notice reminds you to check the customer, delivery date, and subject in the folder before relying on them. It does not appear for local-only searches, empty results, or connection checks, and the stdout result list is unchanged.

Local checks validate candidate IDs, relevance ranges, calendar dates, and matching date evidence; they do not authenticate what the notes claim. Customer and subject are not independently verified against excerpts. A convincing planted note with a forged past delivery date can still mislead the model and rank highly. Matching evidence proves that the source contains a date, not that a delivery happened.

A direct relevance rating of 3 requires at least 50% of the distinct query terms, rounded up, in the note text actually retained in the submitted excerpt. Otherwise it is capped at 2; ratings 1 and 2 are unchanged, and the check never drops a result. Coverage uses case-insensitive literal matching and excludes folder paths, filename prefixes, and lines omitted by the excerpt budget. A single-term query passes when that term is present in the submitted note text. The percentage is centralized in `kMinimumDirectCoveragePercent`.

This is a lexical sanity check, not a prompt-injection defense: planted content can include all query terms. Because ratings 2 and 3 both qualify as on-topic and recency takes priority, this cap affects relevance tie-breaking, not on-topic eligibility or the date ordering. Evidenced future deliveries remain excluded entirely.

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

The default configuration file is `$XDG_CONFIG_HOME/bfind/.env` when `XDG_CONFIG_HOME` is an absolute path; otherwise it is `$HOME/.config/bfind/.env`. Empty or relative `XDG_CONFIG_HOME` values are ignored. `HOME` must be absolute when used as the fallback. If neither variable supplies a valid base directory, use `--env FILE` or correct the environment.

Create a private configuration file at that location using `.env.example` as the template, then fill in the connection details. Never overwrite an existing configuration during setup. A missing config file is allowed: environment variables or `--local-only` may be sufficient.

`./.env` is never loaded implicitly. To use a trusted file elsewhere, pass `--env FILE` explicitly; a relative path is resolved against your current directory. Only select files you trust, because configuration controls both the API destination and the search root.

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
| `SEARCH_ROOT` | Notes directory; the fallback is `/home/barry/GoogleDrive/Builder Relations/Customers/`. |

Configuration supports `NAME=value`, single- or double-quoted values, optional `export`, and comments. Quoted values are literal: shell expansion and escape substitution are not performed. Environment variables override config-file values individually; `--root` overrides `SEARCH_ROOT`. API settings are required only for LLM requests, not local searches with no matches or `--local-only`.

The application checks the opened file with `fstat()` and reads that same descriptor. It prints a one-line warning to stderr if any group/other permission bits are set or the file is not owned by the effective current user, then continues. Use a user-owned file with mode `0600`. Symlinks are checked against their opened target; nonregular files are rejected. Warnings include no credentials, endpoint values, or config paths. These warnings are advisory; they do not establish that a file or endpoint is trusted.

Grove receives OpenAI-style requests with `model`, `messages`, and `max_completion_tokens`. Extraction requests also set `response_format` to `json_object`; text is read from `choices[0].message.content`. Responses with an incomplete finish reason or invalid result IDs are rejected. Unsupported date evidence becomes `Unknown`.

`.env` is ignored by Git. Keep real credentials and private endpoint details out of documentation, test fixtures, logs, and commits. The template contains no credentials. Normal searches send the selected excerpts and folder paths to the configured company endpoint.

### Run

From the repository directory, using configuration at the default user location (or environment variables):

```sh
./build/bfind "vector search"
./build/bfind --no-open --limit 5 "aggregation workshop"
./build/bfind --root "/path/to/customer/notes" "schema design"
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
--limit N        Maximum displayed results (default 10, maximum 30)
--candidates N   Maximum folders sent to the LLM (default 20, maximum 40)
--context N      Surrounding lines per match (default 6, maximum 30)
--no-open        Suppress the Dolphin prompt
--help           Show command-line help
```

Use `--` before a topic beginning with a hyphen. At the folder prompt, enter a listed number, press Enter for result 1, or enter `q` to quit. Invalid selections prompt again. Launch success means Dolphin was started; desktop integration is handled by Dolphin.

The CLI exits with code 0 for successful searches (including no matches) and code 1 for errors. Diagnostics go to stderr; results go to stdout.

### Development and documentation maintenance

Offline integration tests use real ripgrep, synthetic notes, and mocked curl and Dolphin processes. They require no credentials or network connection.

Keep this file, `AGENTS.md`, and `PROJECT_STATUS.md` synchronized with changes. Keep progress, readiness, verification results, and outstanding work in `PROJECT_STATUS.md`. Keep the opening README sections focused on functional needs and benefits, with architecture, decisions, configuration, and build and run instructions below.

Commit each completed logical change after verification, including related documentation, then push to `origin` before ending each interaction. No separate push request is required. Do not create empty commits for interactions without changes; push any pending local commits.
