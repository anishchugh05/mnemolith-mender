# Mnemolith Mender

AI coding tools save facts about your project ("we use Postgres"). When the code
changes, those memories quietly go stale. [Mnemolith](https://mnemolith.dev) flags
them; **Mender drafts the fix** with NVIDIA Nemotron on Nebius Token Factory, and you
approve it. Nothing is written to your memory store without your approval.

## How it works
1. Mender asks Mnemolith for memories whose linked files changed.
2. **Nemotron Nano** triages each one: is it really invalidated, or did unrelated lines change?
3. **Nemotron Ultra** runs as a small agent for the ones that matter. It checks the repo
   (grep, file reads, git history) and, for dependency bumps, web search (Tavily)
   before drafting the corrected memory with a reason and a confidence score.
4. You review each draft next to its diff: approve, edit or reject.

## Pre-existing vs. built for the hackathon
**Pre-existing:** Mnemolith (engine, MCP server, file fingerprinting, stale detection, dashboard).
**Built during the hackathon (this repo):** triage + drafting pipeline, agent tools,
review queue and terminal UI, watch mode, git hook, dependency-bump research via Tavily.

## Nebius / NVIDIA usage
- Nebius Token Factory: all inference (OpenAI-compatible API)
- NVIDIA Nemotron Nano: triage; Nemotron Ultra: tool-using drafting agent
- Tavily: release notes for dependency changes
TODO: add measured numbers (changes seen, triaged out by Nano, sent to Ultra, tokens).

## Setup
TODO: confirm Mnemolith install command, Python 3.10+, Java 11+.
    git clone https://github.com/anishchugh05/mnemolith-mender
    cd mnemolith-mender && uv venv && source .venv/bin/activate && uv pip install -e .
    cp .env.example .env   # NEBIUS_API_KEY, TAVILY_API_KEY

## Usage
    mender --repo /path/to/repo init
    mender --repo /path/to/repo run      # find stale memories, draft fixes
    mender --repo /path/to/repo review   # approve / edit / reject
    mender --repo /path/to/repo watch    # keep checking, including uncommitted edits
    mender --repo /path/to/repo hook     # run automatically after each commit

License: MIT
