# Project status

## Current state

The initial C++ command-line application is implemented and builds successfully. It searches plain-text notes, verifies bounded excerpts through Grove using GPT-6 Astra, displays ranked session details, and offers interactive folder selection for Dolphin. Configuration, build and run instructions, and operating limits are documented in `README.md`.

## Completed

- Configured the GitHub repository as `origin`, with small, focused commits and pushes at the end of each interaction.
- Added `.env.example` and ignore rules for local credentials and build artifacts.
- Added a Linux/C++17 executable and CMake build using Boost.JSON and installed ripgrep/curl executables.
- Implemented literal, case-insensitive topic-word retrieval, bounded context, folder grouping, excerpt deduplication, and lexical candidate selection.
- Implemented one bounded Grove request per search, using the full configured endpoint and `api-key` authentication without exposing credentials in command-line arguments.
- Added validation for completion status, result IDs, relevance, duplicate results, calendar dates, and quoted date evidence.
- Implemented relevance and recency sorting, condensed numbered output, unknown fields, and result limits.
- Implemented Dolphin selection with result 1 as default, input validation, quitting, and noninteractive prompt suppression. Dolphin launches independently of the CLI.
- Added `--local-only`, `--check-connection`, configurable search roots, request limits, and CLI help.
- Added 21 offline integration tests using synthetic notes, real ripgrep, and mocked curl/Dolphin.

## Verification completed

- GCC 15.2.0 builds the C++17 application through CMake with `-Wall -Wextra -Wpedantic` and no reported warnings.
- `ctest --test-dir build --output-on-failure` passes all 21 offline integration cases. These cover grouping, ranking, date evidence, malformed output, HTTP errors, literal argument handling, configuration precedence, candidate/excerpt limits, UTF-8 boundaries, search-output truncation, noninteractive use, no persistent results, and Dolphin prompt behavior.
- A live end-to-end request from the compiled application successfully retrieved and extracted a synthetic Acme Vector Search workshop delivered on 2026-10-22. No real customer notes were used; synthetic live-test files were removed.
- Earlier minimal connectivity verification returned HTTP 200 and `OK` from `gpt-6-astra-2026-09-03`, using 15 tokens. The working authentication header is `api-key`.
- `.env` remains local and Git-ignored. Documentation and test fixtures contain no real credentials or private endpoints.

## Build and run readiness

The executable is `build/customer-session-search`. Verified build and offline-test commands are in the README. The existing local `.env` supplies the Grove connection settings and customer notes root.

## Remaining validation and limitations

- Actual customer-note searches have not been used for acceptance testing. Evaluate extraction quality against known sessions during normal use and adjust retrieval context if needed.
- Dolphin's launch arguments and selection flow are tested with a mock; an actual desktop window has not been opened during automated verification.
- Retrieval depends on literal query-word matches and bounded candidates. It does not extract PDFs or slides, guarantee exhaustive retrieval, or identify multiple sessions separately within the same directory.
- LLM interpretation can still misidentify a customer, subject, or the meaning of a date despite ID and evidence validation. Unrecognized date formats are shown as unknown.

## Maintenance

Update this document when implementation progress, readiness, completed verification, or remaining work changes. Keep it consistent with `README.md` and `AGENTS.md`, while keeping project status details out of the README.
