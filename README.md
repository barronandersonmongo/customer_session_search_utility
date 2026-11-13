# Customer Session Search Utility

Find relevant, recent customer sessions so you can reuse prior notes, slides, and other materials when preparing a new delivery. Results highlight the customer, delivery date, subject, and full folder path while suppressing repetitive details.

## Why it exists

Delivering similar content to multiple customers leaves useful material scattered across many folders. Ordinary text searches find the topic but often return repetitive details that make it difficult to identify the latest useful delivery. This utility is intended to shorten preparation time by making those prior sessions easy to identify and open.

## What it will help you do

- Search plain-text customer event notes for a topic.
- Identify relevant past sessions with their customer, delivery date, subject, and full folder path.
- Rank results by relevance, using recency to order similarly relevant sessions.
- Show condensed, numbered results with the best match at position 1.
- Offer to open a result folder in Dolphin; Enter selects result 1, and the user can choose another result number or quit.

Missing delivery dates will appear as unknown so you can distinguish confirmed dates from missing information.

Example of the intended output:

```text
1. Acme | 2026-10-22 | Vector Search Workshop
   /home/barry/GoogleDrive/Builder Relations/Customers/Acme/2026-10-22/

2. Example Corp | 2026-09-14 | Vector Search Introduction
   /home/barry/GoogleDrive/Builder Relations/Customers/Example Corp/Search/

Open result [1], or q to quit:
```

## Technical details

Repository: [customer_session_search_utility](https://github.com/barronandersonmongo/customer_session_search_utility)

### Status

The project is in initial setup. Configuration templates and documentation exist; the C++ command-line program has not yet been implemented. The example above describes planned behavior.

The development system has GCC 15.2.0, and compilation and execution of a C++17 standard-library program have been verified. A minimal request using the local configuration also successfully authenticated with Grove and received a response from GPT-6 Astra.

### Planned architecture

1. A C++ command-line application accepts a topic and loads configuration.
2. Ripgrep retrieves matching plain-text excerpts with surrounding context.
3. The application groups related matches, removes duplicates, and bounds the context sent to Grove.
4. GPT-6 Astra verifies relevance and extracts session details from the supplied evidence.
5. The application validates the results, ranks sessions, and displays the condensed list.
6. An optional prompt opens the selected folder in Dolphin.

### Technical decisions

- Use local retrieval before LLM processing to limit network traffic and token use.
- Bound candidate counts, excerpt sizes, and output tokens to control latency and resource use.
- Keep search results and intermediate note content in memory without persisting or caching them. No embeddings database or persistent index is planned.
- Use dates supported by notes or paths; do not treat file modification times as delivery dates.
- Keep the model and endpoint configurable through `.env`.

### Configuration

Copy `.env.example` to `.env` if a local configuration does not already exist, then fill in the connection details. Never overwrite an existing `.env` during setup.

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | Company-provided Grove API key. |
| `LLM_BASE_URL` | Grove endpoint. The verified configuration uses a complete HTTPS URL ending in `/chat/completions`. |
| `LLM_MODEL` | Model identifier; currently `gpt-6-astra`. |
| `SEARCH_ROOT` | Notes directory; defaults in the template to `/home/barry/GoogleDrive/Builder Relations/Customers/`. |

The verified Grove endpoint accepts OpenAI-style Chat Completions requests with the credential in the `api-key` header. The configured full endpoint must be used directly without appending `/chat/completions` again. The successful test supplied `model`, `messages`, and `max_completion_tokens` and read text from `choices[0].message.content`.

`.env` is ignored by Git. Keep real credentials and private endpoint details out of documentation, test fixtures, logs, and commits. The local `.env` is already populated; the template contains no credentials.

### Build and run

There is currently no application executable or build system, so build and run commands are not yet available. This section will include verified commands when the initial implementation is added.

Planned runtime dependencies include ripgrep, network access to Grove, and Dolphin for the optional folder-opening action. Additional build dependencies and exact commands will be documented as implementation proceeds.

### Development and documentation maintenance

Keep this file and `AGENTS.md` synchronized with the program as it changes. Document implemented behavior, configuration, dependencies, and verified build and usage commands in the same change that introduces them, and distinguish planned features from working functionality.

Keep the opening sections focused on functional needs and user benefits. Place architecture, technical decisions, configuration, and build and run instructions in the lower technical portion.

Commit each completed logical change after appropriate verification, keeping commits small and focused for fine-grained change control. Include related documentation updates in the same commit. Push commits when requested.
