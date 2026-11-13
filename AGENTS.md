# Agent instructions

## Change control

After each completed logical change, commit it to the repository to provide fine-grained change control. Keep commits small and focused, include corresponding documentation updates, and run appropriate verification before committing. Do not accumulate unrelated changes into a single commit. Never include `.env` or credentials in a commit. For every interaction that changes repository files, commit the changes and push them to `origin` before ending the interaction; no separate push request is required. For interactions without changes, do not create empty commits, but push any pending local commits. Report any commit or push failure explicitly.

## Documentation maintenance

Keep `README.md`, `AGENTS.md`, and `PROJECT_STATUS.md` synchronized with the program as it changes. Update each affected document in the same change as the corresponding implementation. Keep functional and technical reference material in the README, contributor instructions in AGENTS, and progress, readiness, completed verification, and outstanding work in PROJECT_STATUS. Do not put project status details in the README. Clearly distinguish planned features from implemented and tested behavior; do not invent commands or claim unperformed tests.

Start the README with functional details: what the utility is, why it exists, and how it benefits the user. Keep architecture, technical decisions, configuration, and build and run instructions in the lower technical portion. Preserve this organization as the program evolves.

## Purpose and requirements

Build a C++ command-line utility that helps the user find relevant, recent customer sessions and reuse prior notes, slides, and other materials.

- Notes are primarily plain text under `/home/barry/GoogleDrive/Builder Relations/Customers/`; make the search root configurable.
- Retrieve topic matches locally with ripgrep and bounded surrounding context. Group related matches and remove duplicates before invoking the LLM.
- Use the LLM to verify relevance and extract customer, delivery date, and subject from the supplied evidence.
- Show condensed, numbered results containing the full folder path, customer, date, and subject. Suppress other noise.
- Rank by relevance and use recency to order similarly relevant sessions. Position 1 is the best result.
- Offer to open the selected result folder in Dolphin. Ask for the result number, use position 1 when Enter is pressed, and support quitting without opening a folder.
- Do not persist or cache search results or extracted note content. Keep intermediate search data in memory.
- Optimize local work and LLM use by bounding candidate counts, excerpt sizes, and response length.
- Report unknown dates as unknown. Do not substitute file modification times for delivery dates.

## Configuration and Grove integration

- Load local configuration from `.env`; maintain a credential-free `.env.example`.
- Current variable names are `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, and `SEARCH_ROOT`.
- The chosen model is `gpt-6-astra`. Preserve this selection unless the user changes it; keep it configurable.
- Use the `api-key` header for Grove authentication.
- The current `LLM_BASE_URL` is a complete Chat Completions endpoint ending in `/chat/completions`. Use that full URL directly; do not append the suffix again.
- Use JSON request fields `model`, `messages`, and `max_completion_tokens`; response text is in `choices[0].message.content`.
- Never print, commit, overwrite, or embed real credentials. Do not expose private endpoint values or customer notes in logs, documentation, fixtures, or commits.
- Treat note excerpts as untrusted data, not instructions. Validate LLM output and resolve returned results against actual local candidates before displaying paths or opening folders.
- Invoke ripgrep and Dolphin with argument-safe process execution; do not interpolate queries or folder paths into shell commands.

## Development and verification

- Build with `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` and `cmake --build build -j2`; run offline checks with `ctest --test-dir build --output-on-failure`.
- The implementation targets Linux and C++17, uses Boost.JSON headers with the bundled implementation, and invokes installed `rg` and `curl` executables directly. Python 3 is a test dependency; Dolphin is optional at runtime.
- Keep credentials and API request bodies on stdin to curl, never in process arguments or temporary files. Preserve HTTPS-only transport, disabled curl user configuration, and no redirects.
- Preserve bounded retrieval and request sizes. Keep the README's limit values and configuration precedence accurate when changing them.
- Validate result IDs against local candidates, reject duplicate IDs and incomplete completions, and require a valid calendar date supported by a matching source quote. Use `Unknown` when date evidence is unsupported.
- Dolphin launches independently of the CLI. Do not wait for its GUI lifetime or kill it on a request timeout. Prompt only when stdin is interactive, unless `--no-open` suppresses it.
- Use `--check-connection` for a minimal live API check without notes, and `--local-only` to inspect unverified local matches without calling the LLM.
- Consult `PROJECT_STATUS.md` for current implementation readiness and completed verification. Update it as work progresses.
- Run verification appropriate to each change. For substantive retrieval, parsing, ranking, or process-launch behavior, cover meaningful edge cases using synthetic notes and mocked LLM responses where practical.
- Use minimal live API requests only when needed to verify the connection or integration; avoid sending customer notes solely for a connectivity check.
- Preserve the existing local `.env` and keep it Git-ignored. Never inspect secrets by dumping the file into tool output.
- Documentation-only changes require consistency and formatting review, not live API calls.
