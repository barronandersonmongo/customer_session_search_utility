# bfind project status

## Current state

The initial C++ command-line application is implemented and builds successfully. It searches plain-text notes, verifies bounded excerpts through Grove using GPT-6 Astra, displays ranked session details, and offers interactive folder selection for Dolphin. Configuration, build and run instructions, and operating limits are documented in `README.md`.

## Completed

- Added a one-line stderr notice after nonempty LLM-generated results, preserving stdout and excluding local-only, empty-result, and connection-check modes.
- Added a 50% distinct-term coverage requirement, rounded up, for direct relevance 3. Coverage counts only note text retained in the submitted excerpt, excluding path/filename metadata and omitted lines. Insufficient coverage caps 3 to 2 without dropping results or changing recency-first eligibility. The threshold is centralized in `kMinimumDirectCoveragePercent`.
- Named the program `bfind` (Barry Find), including its executable, build target, installation target, and CLI help.

- Configured the GitHub repository as `origin`, with small, focused commits and pushes at the end of each interaction.
- Added `.env.example` and ignore rules for local credentials and build artifacts.
- Added a Linux/C++17 executable and CMake build using Boost.JSON and installed ripgrep/curl executables.
- Implemented literal, case-insensitive topic-word retrieval, bounded context, folder grouping, excerpt deduplication, and lexical candidate selection.
- Implemented one bounded Grove request per search, using the full configured endpoint and `api-key` authentication without exposing credentials in command-line arguments.
- Added validation for completion status, result IDs, relevance, duplicate results, calendar dates, and quoted date evidence.
- Implemented newest-first ranking within the on-topic group (relevance 2/3), followed by retained peripheral sessions. Unknown dates follow dated results within each group; ties resolve by relevance, local score, and candidate order. The LLM is instructed to select the newest on-topic delivery within a folder as well.
- Excluded evidenced future delivery dates using one snapshot of today's system-local date per verification, also supplied to the LLM. Invalid or unsupported evidence continues to produce Unknown dates.
- Preserved bounded lexical shortlisting without promoting unverified dates and added an explicit warning that a newer session may be outside the shortlist.
- Implemented Dolphin selection with result 1 as default, input validation, quitting, and noninteractive prompt suppression. Dolphin launches independently of the CLI.
- Added `--local-only`, `--check-connection`, configurable search roots, request limits, and CLI help.
- Replaced implicit cwd `.env` loading with an absolute XDG/HOME user-config location, retaining explicit `--env` and environment-variable precedence.
- Added permission and ownership warnings using `fstat()` on the same descriptor used for reading. Nonregular config files are rejected without blocking on FIFOs.
- Documented user-run migration from the project `.env`; the real file was not read, moved, or modified for this change.
- Added 56 offline integration cases using synthetic notes, real ripgrep, and mocked curl/Dolphin.

## Verification completed

- Completion-headroom change: configure/build and the offline suite passed (55 passed, one root-only ownership test skipped). Named caps are 16384 for searches and 2048 for connection checks; tests distinguish truncation, malformed envelopes, and other incomplete responses. No live request or real `.env` access was used.

- For the coverage cap, the build and CTest succeeded: 53 cases passed and the root-only ownership case was skipped. New tests observe ranking to verify sparse-term capping, odd/even thresholds, full/half coverage, duplicate/case-insensitive terms, single-term queries, metadata exclusion, excerpt-budget omissions, unchanged peripheral ratings, and continued eligibility of newer capped results. Existing future-date and notice tests pass. No live API call was made, and the real `.env` was not accessed.
- For the model-generated notice, configure/build and CTest succeeded: 43 cases passed and the root-only ownership test was skipped. Tests assert exact unchanged stdout and a single stderr notice, plus its absence in local-only, no-match, empty verified-result, and connection-check modes. No live API calls were made and the real `.env` was not accessed.
- For the ranking and future-date change, `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`, `cmake --build build -j2`, and `ctest --test-dir build --output-on-failure` succeeded. Of 42 cases, 41 passed and the root-only ownership test was skipped.
- New ranking cases verify that newer relevance-2 sessions outrank older relevance-3 sessions, peripheral results follow the entire on-topic group, unknown dates follow dated sessions within each group, and ties use relevance, local score, and deterministic candidate order even when mock results are reversed.
- Future-date cases verify that evidenced future deliveries are omitted, today's deliveries are retained, the cutoff follows the system timezone across UTC-12/UTC+14 boundaries, and invalid or unsupported evidence still becomes Unknown. Result limits and Dolphin selection continue to follow the displayed ranking. No live API calls were made and the real project `.env` was not accessed for this change.
- GCC 15.2.0 builds the C++17 application through CMake with `-Wall -Wextra -Wpedantic` and no reported warnings.
- The config change passed configure/build and offline verification (33 passed, one root-only test skipped). CLI help describes the new defaults.
- New cases cover hostile cwd `.env` isolation with a shell-provided key, XDG selection, HOME fallback, relative/empty XDG handling, missing or relative HOME, explicit config selection, environment-only and local-only operation, permission warnings, symlink target checks, and rejection of nonregular files.
- Existing retrieval, ranking, date evidence, malformed-output, HTTP-error, literal-argument, configuration-precedence, resource-limit, UTF-8, noninteractive, no-persistence, and Dolphin prompt checks continue to pass. No live API call was made for the config change.
- A live end-to-end request from the compiled application successfully retrieved and extracted a synthetic Acme Vector Search workshop delivered on 2026-10-22. No real customer notes were used; synthetic live-test files were removed.
- Earlier minimal connectivity verification returned HTTP 200 and `OK` from `gpt-6-astra-2026-09-03`, using 15 tokens. The working authentication header is `api-key`.
- `.env` remains local and Git-ignored. Documentation and test fixtures contain no real credentials or private endpoints.

## Build and run readiness

The executable is `build/bfind`. Verified build and offline-test commands are in the README. The existing project `.env` must now be selected explicitly with `--env .env` or copied by the user to the XDG/HOME default location, following the README migration instructions.

## Remaining validation and limitations

- Matching date evidence does not authenticate a delivery. Customer and subject are not independently verified against excerpts; convincing planted notes with forged past dates can still mislead the model and ranking.
- The coverage cap is a lexical consistency check, not a prompt-injection security barrier. Planted text can include all query terms. Ratings 2 and 3 remain on-topic, so the cap affects relevance tie-breaking, not recency-first ordering or eligibility. Evidenced future deliveries remain excluded.
- Actual customer-note searches have not been used for acceptance testing. Evaluate extraction quality against known sessions during normal use and adjust retrieval context if needed.
- The ownership-warning branch has a root-only synthetic test; it was not exercised in this non-root test run. Group/other permission warnings were exercised for both default and explicit config files.
- Dolphin's launch arguments and selection flow are tested with a mock; an actual desktop window has not been opened during automated verification.
- Retrieval depends on literal query-word matches and bounded candidates. It does not extract PDFs or slides, guarantee exhaustive retrieval, or identify multiple sessions separately within the same directory.
- LLM interpretation can still misidentify a customer, subject, or the meaning of a date despite ID and evidence validation. Unrecognized date formats are shown as unknown.

## Maintenance

Update this document when implementation progress, readiness, completed verification, or remaining work changes. Keep it consistent with `README.md` and `AGENTS.md`, while keeping project status details out of the README.

## Retrieval layout and scope decisions

The user confirmed customer/date/document folders, potentially with multiple documents per session. Text search remains sufficient; no PDF/slide extraction is requested. The user does not expect hidden files and does not need ignore rules: ordinary ignored files will be included, with hidden files and binary content still excluded. Grouping and ignore behavior will be implemented in focused changes.
