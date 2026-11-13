# Customer Session Search Utility

Find relevant, recent customer sessions so you can reuse prior notes, slides, and other materials when preparing a new delivery. Results highlight the customer, delivery date, subject, and full folder path while suppressing repetitive details.

Repository: [customer_session_search_utility](https://github.com/barronandersonmongo/customer_session_search_utility)

## Project status

The project is in initial setup. Configuration templates and documentation exist; the C++ command-line program has not yet been implemented. Build and usage commands will be documented when they are available.

The development system has GCC 15.2.0, and compilation and execution of a C++17 standard-library program have been verified. A minimal request using the local configuration also successfully authenticated with Grove and received a response from GPT-6 Astra.

## Intended behavior

- Search plain-text customer event notes for a topic.
- Use local text search to collect bounded excerpts, group related matches, and remove redundant content before sending context to the LLM.
- Identify relevant past sessions with their customer, delivery date, subject, and full folder path.
- Rank results by relevance, using recency to order similarly relevant sessions.
- Show condensed, numbered results with the best match at position 1.
- Offer to open a result folder in Dolphin; Enter selects result 1, and the user can choose another result number or quit.
- Keep results in memory without persisting or caching them.

Delivery dates should come from evidence in the notes or paths. Missing dates should appear as unknown rather than being inferred from file modification times.

Example of the intended output:

```text
1. Acme | 2026-10-22 | Vector Search Workshop
   /home/barry/GoogleDrive/Builder Relations/Customers/Acme/2026-10-22/

2. Example Corp | 2026-09-14 | Vector Search Introduction
   /home/barry/GoogleDrive/Builder Relations/Customers/Example Corp/Search/

Open result [1], or q to quit:
```

## Configuration

Copy `.env.example` to `.env` if a local configuration does not already exist, then fill in the connection details. Never overwrite an existing `.env` during setup.

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | Company-provided Grove API key. |
| `LLM_BASE_URL` | Grove endpoint. The verified configuration uses a complete HTTPS URL ending in `/chat/completions`. |
| `LLM_MODEL` | Model identifier; currently `gpt-6-astra`. |
| `SEARCH_ROOT` | Notes directory; defaults in the template to `/home/barry/GoogleDrive/Builder Relations/Customers/`. |

The verified Grove endpoint accepts OpenAI-style Chat Completions requests with the credential in the `api-key` header. The configured full endpoint must be used directly without appending `/chat/completions` again. The successful test supplied `model`, `messages`, and `max_completion_tokens` and read text from `choices[0].message.content`.

`.env` is ignored by Git. Keep real credentials and private endpoint details out of documentation, test fixtures, logs, and commits. The local `.env` is already populated; the template contains no credentials.

## Implementation direction

Use C++ for the command-line application, with ripgrep for initial plain-text retrieval and GPT-6 Astra through Grove for verification and extraction. Bound candidate counts, excerpt sizes, and output tokens to control latency and resource use. No embeddings database or persistent index is currently planned.

Planned runtime dependencies include ripgrep, network access to Grove, and Dolphin for the optional folder-opening action. Additional build dependencies and exact commands will be documented as implementation proceeds.

## Documentation maintenance

Keep this file and `AGENTS.md` synchronized with the program as it changes. Document implemented behavior, configuration, dependencies, and verified build and usage commands in the same change that introduces them, and distinguish planned features from working functionality.

Commit each completed logical change after appropriate verification, keeping commits small and focused for fine-grained change control. Include related documentation updates in the same commit. Push commits when requested.
