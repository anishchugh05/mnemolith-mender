# Mnemolith Mender

AI coding tools save facts about your project ("we use Postgres"). When the code
changes, those memories quietly go stale. [Mnemolith](https://mnemolith.dev) flags
them; **Mender drafts the fix** with NVIDIA Nemotron on Nebius Token Factory, and you
approve it. **Nothing is written to your memory store without your approval.**

## How it works
1. Mender asks Mnemolith for memories whose linked files changed (committed or not).
2. **Nemotron Nano** triages each one: is it really invalidated, or did unrelated lines change?
   Harmless changes never reach the big model.
3. **Nemotron Ultra** runs as a small agent for the ones that matter. It checks the repo
   (`grep_repo`, `read_file`, `git_log`) and, for dependency bumps, web search (Tavily)
   before drafting the corrected memory with a reason and a confidence score.
4. You review each draft next to its diff, in the terminal (`mender review`) or in a
   local web page (`mender ui`): approve, edit or reject.

### Safety rules
- **No silent rewrites.** Drafts wait in a local queue (`.mender/queue.json`) until you approve.
- **Stale-draft guard.** Each draft stores the hashes of the files it was based on. If a file
  changes again before you approve, approval is refused and the memory is re-drafted
  (`mender run`), so Mender never saves a fact that is already out of date.
- **Renames are not deletions.** A moved file is detected (same content, or git's rename
  detection) and the draft updates the path instead of saying "this no longer applies".
- **Deleted files get a human.** If every linked file is gone, nothing is invented: it goes to
  the queue as a manual decision.
- **Read-only agent tools**, confined to the repo.
- **No duplicate work.** The same stale memory is not re-drafted on every commit unless its
  files changed. Failed model calls are retried on the next run, not queued.

## Pre-existing vs. built for the hackathon
**Pre-existing:** Mnemolith (engine, MCP server, file fingerprinting, stale detection, dashboard).
**Built during the hackathon (this repo):** triage + drafting pipeline, agent tools, review queue,
terminal and web review, stale-draft guard, rename handling, watch mode, git hook,
dependency-bump research via Tavily, call/routing stats, tests.

## Nebius / NVIDIA usage
- **Nebius Token Factory:** all inference (OpenAI-compatible API).
- **NVIDIA Nemotron Nano:** triage. **Nemotron Ultra:** tool-using drafting agent.
- **Tavily:** release notes for dependency changes.
- `mender stats` reports measured routing and token use (memories processed, handled by Nano
  alone, sent to Ultra).

TODO: paste measured numbers from the demo repo here.

## Setup
Needs Python 3.10+, Java 11+ (Mnemolith's engine), and Mnemolith itself.
TODO: confirm the Mnemolith install command.

    git clone https://github.com/anishchugh05/mnemolith-mender
    cd mnemolith-mender && uv venv && source .venv/bin/activate && uv pip install -e .
    cp .env.example .env        # add NEBIUS_API_KEY (and TAVILY_API_KEY)
    mender doctor --live        # checks repo, Mnemolith, key, model IDs, Ultra tool calling

Model IDs differ by account; `mender models` lists what your key can use, and
`MENDER_NANO` / `MENDER_ULTRA` in `.env` override the defaults.

## Usage
`--repo` goes before the command (default: the current folder).

    mender --repo /path/to/repo init      # keep .mender/ out of that repo's git history
    mender --repo /path/to/repo run       # find stale memories, draft fixes
    mender --repo /path/to/repo review    # approve / edit / reject in the terminal
    mender --repo /path/to/repo ui        # ...or in a local web page (127.0.0.1 only)
    mender --repo /path/to/repo watch     # keep checking, including uncommitted edits
    mender --repo /path/to/repo hook      # run automatically after each commit
    mender stats                          # calls, tokens, routing

## Tests
    uv pip install -e ".[dev]" && pytest

The suite uses canned model replies and a fake Mnemolith store, so it needs no API key.

License: MIT
