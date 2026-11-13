# Agent instructions

## Technology and strategy decisions

If you are unsure which language, library, framework, technology, or implementation strategy to use, ask the user before deciding. Explain the uncertainty and the relevant options briefly, and wait for the user's answer before proceeding with work that depends on that choice. Continue independent work where possible. Preserve choices the user has already made unless they request reconsideration.

## Change control

After each completed logical change, commit it to the repository to provide fine-grained change control. Keep commits small and focused, include corresponding documentation updates, and run appropriate verification before committing. Do not accumulate unrelated changes into a single commit. Never include `.env` or credentials in a commit. For every interaction that changes repository files, commit the changes and push them to `origin` before ending the interaction; no separate push request is required. For interactions without changes, do not create empty commits, but push any pending local commits. Report any commit or push failure explicitly.

## Documentation maintenance

`BARRY_README.md` contains checkout-local personal usage notes and is Git-ignored. Never stage, force-add, or publish it. If it exists, keep its usage and launcher-location notes accurate when those change, without copying its contents into tracked documentation.

Keep `README.md`, `AGENTS.md`, and `PROJECT_STATUS.md` synchronized with the program as it changes. Update each affected document in the same change as the corresponding implementation. Keep functional and technical reference material in the README, contributor instructions in AGENTS, and progress, readiness, completed verification, and outstanding work in PROJECT_STATUS. Do not put project status details in the README. Clearly distinguish planned features from implemented and tested behavior; do not invent commands or claim unperformed tests.

Start the README with functional details: what the utility is, why it exists, and how it benefits the user. Keep architecture, technical decisions, configuration, and build and run instructions in the lower technical portion. Preserve this organization as the program evolves.

## Purpose and requirements

Exclude dates/references older than six calendar months, inclusively retaining the cutoff day; clamp month subtraction to valid calendar days. Before LLM selection, derive age references from dated session-folder names or leading dates in loose-note filenames, then customer/year January 1. Drop old/future metadata references before scoring and outbound context. Keep undated candidates for LLM verification and enforce the same window on final validated dates/year references. Metadata filtering is not proof of delivery; do not use file modification times. Preserve the fixed root and no runtime date/filter bypass. Local-only mode shows these metadata references; mark year-only dates with `*`.

The program is named `bfind` (Barry Find). Use lowercase `bfind` for the command, CMake target, help text, and usage examples. The existing GitHub repository name remains unchanged.

Build a C++ command-line utility that helps the user find relevant, recent customer sessions and reuse prior notes, slides, and other materials.

- Notes are primarily plain text under the only permitted search folder `/home/barry/GoogleDrive/Builder Relations/Customers/`.
- Preserve the exact literal search root `/home/barry/GoogleDrive/Builder Relations/Customers/`. The user explicitly requires this fixed path for security: do not derive it from HOME, other environment values, the current directory, or alternate locations. Reject --root and any SEARCH_ROOT value other than the exact legacy literal (including its trailing slash). Never use SEARCH_ROOT for routing. Launching from other working directories is allowed.
- The confirmed main layout is customer/year/YYYY-MM-DD - Topic/documents. Group direct and nested documents at the dated-topic folder, not the customer/year folder. Also support customer/dated-topic without a year. Keep loose year notes and files in undated year collections as individual candidates, even when they share the same folder to open. Use distinct candidate identities and do not merge these IDs in the LLM prompt. Use the fixed Customers root as anchor. Never return/open a folder outside that root. Use session-relative filenames so equal basenames in different subfolders remain distinct. Do not infer validated delivery dates from grouping boundaries.
- Retrieve topic matches locally with ripgrep and bounded surrounding context. Group related matches and remove duplicates before invoking the LLM.
- Use the LLM to verify relevance and extract delivery date and subject from the supplied evidence; derive customer locally from the folder hierarchy.
- Derive customer from the first directory below the fixed Customers root for both local-only and verified results. Ignore model-supplied customer values and do not request that field. Preserve punctuation and international text, applying terminal escaping for display. Use `Unknown Customer` for files directly under the root with no customer directory. Keep other unknown fields labeled `Unknown`.
- Show condensed, numbered results containing the full folder path, customer, date, and subject. Suppress other noise.
- Escape Unicode C1 controls, bidi formatting controls, Unicode line/paragraph separators, and invalid UTF-8 bytes in terminal output while preserving ordinary international text. C0/DEL remain spaces. Use escaped strings only for presentation, never filesystem access or folder launch. Keep native decoder and integration field/path tests.
- Do not add a usage audit or persistent usage log; the user explicitly declined it.
- Maintain --verbose/-v as opt-in, flushed, timestamped stderr progress. Report stages, counts, limits, timings, numeric candidate scores/coverage, validation outcomes, and safe numeric token usage. Child processes should emit a roughly two-second heartbeat without changing deadlines or cleanup. Never dump config values, query text, note excerpts, commands containing credentials, or raw API responses. Preserve ordinary stdout and keep diagnostics ephemeral, not an audit log.
- After nonempty LLM-generated results, print one short stderr reminder to check customer, date, and subject in the folder before relying on them. Preserve stdout formatting and omit the reminder for local-only searches, empty results, and connection checks.
- Document that local validation does not authenticate notes or detect convincing planted content. Customer is determined by folder placement; subject is not independently verified against excerpts; quoted dates do not prove actual deliveries.
- Cap model relevance 3 to 2 unless the actual submitted note text covers at least 50% of distinct query terms, rounded up. Count case-insensitive literal matches only in retained note text, excluding folder paths, filename prefixes, and omitted lines. Store excerpt coverage and total distinct term count on each candidate; centralize the threshold in `kMinimumDirectCoveragePercent`. Never raise ratings 1/2 or drop results for low coverage. Describe this as a lexical consistency check, not a prompt-injection security barrier; recency-first ranking and future-delivery exclusion remain unchanged.
- Treat relevance 2 and 3 as one on-topic group and rank by validated delivery date or labeled January 1 year reference newest first, with Unknown dates last in the group. Retain relevance-1 peripheral results after all on-topic results, ordered by the same date rules. Break ties by relevance, local score, then original candidate order. Keep the grouping rule centralized in `on_topic()` and preserve a strict weak ordering. Position 1 is the newest on-topic date/reference when available.
- Offer to open the selected result folder in Dolphin. Ask for the result number, use position 1 when Enter is pressed, and support quitting without opening a folder.
- Do not persist or cache search results or extracted note content. Keep intermediate search data in memory.
- Optimize local work and LLM use by bounding candidate counts, excerpt sizes, and response length.
- Use an asterisk-marked January 1 reference when only a grounded year is known; otherwise report missing dates as Unknown. Do not substitute file modification times for delivery dates.
- Exclude results whose evidenced, valid delivery date is after today; do not convert a confirmed future delivery to Unknown. Accept today's deliveries. Capture today's local system date once per verification and supply it to the LLM. Unsupported or invalid full-date evidence becomes a year reference when a grounded year is available, otherwise Unknown.
- Preserve bounded lexical candidate selection and explicitly document that newest-first ranking applies only to verified candidates. Do not promote candidates based on unverified dates; warn about possible omitted recent sessions when the candidate limit is reached.
- Default to 40 candidates (maximum 40). Filter common English stopwords, falling back to all terms for all-stopword queries; use these filtered distinct terms for retrieval and the coverage cap. Score terms by retrieved-folder rarity with integer weights, retain the original-query phrase bonus and capped hit bonus, and use ascending path order for deterministic score ties. Never use folder-name dates as delivery evidence for shortlist ordering.

## Configuration and Grove integration

- Default to `$XDG_CONFIG_HOME/bfind/.env` when XDG_CONFIG_HOME is absolute, otherwise `$HOME/.config/bfind/.env`. Ignore empty or relative XDG_CONFIG_HOME; require an absolute HOME fallback and fail clearly if neither base is usable. Never read cwd `./.env` implicitly.
- Preserve `--env FILE` as an explicit trusted-file selection, including relative paths. Missing config files are allowed; environment variables override API file values individually; no config or environment setting may redirect the search root.
- Check permissions and ownership with `fstat()` on the same descriptor used to read the configuration. Warn once and continue if mode has any `077` bits or ownership differs from the effective user; do not expose values or paths in the warning. Reject nonregular config files.
- Maintain a credential-free `.env.example`. Do not read, move, or overwrite the real project `.env` for migration; document user-run migration or explicit `--env` instructions instead.
- The installed user-bin symlink points to `bin/bfind`, a launcher that supplies the trusted absolute project `.env` path to the executable via --env. Keep credentials out of the launcher, never source the file, and forward arguments with quoted "$@". Direct execution of build/bfind retains the default XDG configuration behavior unless --env is supplied.
- Current variable names are `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. SEARCH_ROOT is obsolete except for accepting the exact fixed legacy literal without using it.
- The chosen model is `gpt-6-astra`. Preserve this selection unless the user changes it; keep it configurable.
- Use the `api-key` header for Grove authentication.
- The current `LLM_BASE_URL` is a complete Chat Completions endpoint ending in `/chat/completions`. Use that full URL directly; do not append the suffix again.
- Use JSON request fields `model`, `messages`, and `max_completion_tokens`; response text is in `choices[0].message.content`.
- Use named completion limits of 16384 for searches and 2048 for connection checks. Distinguish truncated (`finish_reason: length`), incomplete, and malformed completions without logging response contents. Larger token limits do not bypass the request timeout.
- Diagnose curl transport failures from numeric exit codes only: DNS/proxy 5/6, connection 7, timeout 28, TLS handshake 35, certificate/TLS configuration 51/58/59/60/77, empty/failed response 52/56; include the code for unmapped failures. Preserve the curl-not-found error for 127 and check the response-size limit before the killed child's exit status. Never capture or print curl stderr, URLs, headers, or response bodies for diagnostics.
- Never print, commit, overwrite, or embed real credentials. Do not expose private endpoint values or customer notes in logs, documentation, fixtures, or commits.
- Treat note excerpts as untrusted data, not instructions. Validate LLM output and resolve returned results against actual local candidates before displaying paths or opening folders.
- Invoke ripgrep and Dolphin with argument-safe process execution; do not interpolate queries or folder paths into shell commands.

## Development and verification

- Build with `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` and `cmake --build build -j2`; run offline checks with `ctest --test-dir build --output-on-failure`.
- The implementation targets Linux and C++17, uses Boost.JSON headers with the bundled implementation, and invokes installed `rg` and `curl` executables directly. Python 3 is a test dependency; Dolphin is optional at runtime.
- Enforce Boost >=1.75.0 from the selected headers. Apply compiler-supported strong stack protection to all application/test targets and fortification >=2 in optimized GNU/Clang glibc builds via the forced pre-header. Preserve stronger user fortification settings and do not force fortification without optimization. Keep fixture targets non-installed and the production search-root restriction unchanged.
- Keep credentials and API request bodies on stdin to curl, never in process arguments or temporary files. Preserve HTTPS-only transport, disabled curl user configuration, and no redirects.
- Invoke curl with the dedicated ChildEnvironment::Curl allowlist and --tlsv1.2 (TLS 1.2 or newer). Preserve existing proxy/CA settings per the user's explicit decision; do not force --noproxy. Exclude SSLKEYLOGFILE, LLM credentials, loader variables, and unrelated variables from curl. Preserve the parent environment and Dolphin's desktop environment. Mock API controls must not require weakening the production allowlist; use synthetic temporary test-only state instead.
- Preserve bounded retrieval and request sizes. Keep the README's limit values and configuration precedence accurate when changing them.
- Use ripgrep `--sort path` for repeatable file order and output-cap selection on unchanged trees. Do not claim timeout-based selection is deterministic.
- Per the user's notes-scope decision, pass `--no-ignore` so ordinary ignored notes are searchable, while retaining default hidden-file, binary-file, and symlink exclusions. Do not add `--hidden`, binary searching, or document extraction without a user decision.
- Validate result IDs against local candidates, reject duplicate IDs and incomplete completions, and require a valid calendar date supported by a matching source quote. When no validated delivery day exists, use January 1 of a grounded year (exact customer/year folder or quoted year-only model output), marked `*` in display. A full validated date takes precedence. Compare the ISO reference in ranking and apply future-date exclusion to it. With no grounded year, use Unknown. Local-only mode may derive folder-year references without an LLM request.
- Tolerate absent/null/non-string optional text fields as Unknown or empty evidence. Skip items with oversized subject strings with one stderr count; fail if all items are oversized. Non-object items and invalid ID/relevance/duplicates remain fatal. Preserve successful empty results when all usable items are excluded future deliveries.
- Dolphin launches independently of the CLI. Do not wait for its GUI lifetime or kill it on a request timeout. Prompt only when both stdin and stdout are terminals, unless `--no-open` suppresses it. Piped or redirected stdout must not receive prompts or wait for selections.
- Before forking Dolphin, require a nonempty DISPLAY or WAYLAND_DISPLAY and otherwise fail clearly without launching. Do not claim those variables guarantee a working graphical session. Automated Dolphin tests must use synthetic display values and mocks, never a real window.
- Keep child-process execution in `src/process.cpp` with native deadline tests. The deadline must cover both pipe handling and the final wait after stdout closes; use nonblocking wait, then kill/reap overdue children. Do not leave zombies or expose test-only timeout options in the CLI.
- Keep SIGPIPE ignored in the parent and restore SIG_DFL in process children and the detached Dolphin grandchild before exec. Check inheritance with native code or a shell probe before Python startup, since Python itself ignores SIGPIPE.
- Preserve completed ripgrep records after a timeout with a partial-coverage warning. Cache canonicalization per file (including failed paths), skip individual filesystem failures with one count, and label empty partial searches as incomplete. Curl timeout is an error; never parse a partial API response. The cache is per-run memory only.
- Use `--check-connection` for a minimal live API check without notes, and `--local-only` to inspect unverified local matches without calling the LLM.
- Consult `PROJECT_STATUS.md` for current implementation readiness and completed verification. Update it as work progresses.
- Run verification appropriate to each change. For substantive retrieval, parsing, ranking, or process-launch behavior, cover meaningful edge cases using synthetic notes and mocked LLM responses where practical.
- Use minimal live API requests only when needed to verify the connection or integration; avoid sending customer notes solely for a connectivity check.
- Preserve the existing local `.env` and keep it Git-ignored. Never inspect secrets by dumping the file into tool output.
- Documentation-only changes require consistency and formatting review, not live API calls.

- Keep the synthetic integration fixture executable separate and non-installed, with a fixed compile-time build-directory root and no runtime root override. Production `bfind` must never accept an alternate root via CLI, config, environment, or cwd. Do not read or modify the real `.env` to migrate this setting.

- Integration fixtures use a fixed compile-time epoch and synthetic recent dates to make age tests deterministic, including timezone checks. Production uses the real system clock and exposes no runtime date override. Native date tests cover month-end and leap-year clamping.
