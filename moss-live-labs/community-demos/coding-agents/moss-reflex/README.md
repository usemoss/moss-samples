# moss-reflex: procedural memory for coding agents

[moss-reflex](https://github.com/Naut1cal5/moss-reflex) records what a coding agent tried,
what happened, and whether that action fixed, worsened, or reverted a recurring failure. It turns
Claude Code's tool execution trail into a local Moss session and exposes procedural recall over
MCP.

## What this demo shows

- `PostToolUse`, `PostToolUseFailure`, and `Stop` hooks capture execution context automatically.
- Exit codes, test-count deltas, and Git diff fingerprints label outcomes without an LLM.
- Trace normalization strips volatile addresses, line numbers, timestamps, and absolute path
  prefixes while retaining exception types, frame functions, and relative module paths.
- Moss structured payloads preserve the original raw trace for verbatim retrieval.
- Metadata filters scope recall by repository, language, error class, tool, outcome, and time.
- Exponential recency reranking keeps fixes from the current dependency era above stale ones.
- Native local disk snapshots make restarts fast; append-only JSONL rebuilds a missing or damaged
  snapshot without uploading the corpus.

## Try it

```bash
git clone https://github.com/Naut1cal5/moss-reflex.git
cd moss-reflex
python -m venv .venv
source .venv/bin/activate
python -m pip install .

export MOSS_PROJECT_ID="your-project-id"
export MOSS_PROJECT_KEY="your-project-key"

# Run this from the repository Claude Code should remember.
moss-reflex init
```

Restart Claude Code, then call `recall_similar_situations` before retrying a familiar failure.
`reflex_stats` summarizes the local episode store.

## Why Moss sessions fit

Agent procedures arrive continuously during a coding session. A Moss `SessionIndex` supports
local embedding, immediate mutation, metadata-filtered semantic search, and single-digit
millisecond queries in the agent process. `moss-reflex` keeps both the source JSONL and native
snapshot on the developer's machine and uses the built-in local embedding model, so there is no
embedding provider or LLM-labeling cost. Local Moss queries are unmetered on the Developer plan.

The complete implementation, tests, benchmark harness, MIT license, and issue tracker live in the
[standalone repository](https://github.com/Naut1cal5/moss-reflex).
