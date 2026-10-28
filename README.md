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
4. Every draft carries an **evidence box**: the tool calls Ultra actually made (files read,
   repo searches, web searches with source links and snippets), recorded from what the tools
   returned, not from what the model says it did.
5. You review each draft next to its diff, in the terminal (`mender review`) or in a
   local web page (`mender ui`): approve, edit or reject.

### Safety rules
- **No silent rewrites.** Drafts wait in a local queue (`.mender/queue.json`) until you approve.
- **Stale-draft guard.** Each draft stores the hashes of the files it was based on. If a file
  changes again before you approve, approval is refused and the memory is re-drafted
  (`mender run`), so Mender never saves a fact that is already out of date.
- **Renames are not deletions.** A moved file is detected (same content, or git's rename
  detection) and the draft updates the path instead of saying "this no longer applies".
- **Deleted files get a human.** If every linked file is gone, nothing is invented: it goes to
  the queue as a manual decision, where you can retire the memory (marked outdated in
  Mnemolith, history kept) or dismiss it.
- **No conflicting fixes.** If the memory was already fixed elsewhere (say Claude replaced it
  through Mnemolith), approving does nothing and the draft is dropped.
- **Grounding check.** Mender checks the draft against the tool results. A passage quoted in
  the reason must really appear in a source the agent looked at, and for a dependency bump a
  search result must name the new version. A failed check sends Ultra back once to fix it; if
  it still fails, the card shows an "Unverified" warning and the confidence is capped at 0.5.
  (Without this, Ultra once "quoted" release notes that were not in any source.)
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
- `mender stats` reports measured routing and token use: decisions made, how many Nano settled
  alone, how many went to Ultra (a memory re-drafted after another edit counts again).

Measured on a small demo repo during development (`mender stats`, all test runs including
re-drafts, so treat it as a rough sample, not a benchmark):

| | calls | tokens in / out | time |
|---|---|---|---|
| Nemotron Nano (triage) | 9 | 2,425 / 1,260 | 20.0 s |
| Nemotron Ultra (drafting agent) | 29 | 46,106 / 4,666 | 49.3 s |

Of 15 routing decisions, 1 was settled by Nano alone, 8 went to Ultra, and 6 were manual
(every linked file deleted, so no model drafts anything).

## Try it (test build)
There is no hosted copy: Mender runs on your machine against your repo and your Mnemolith
store, so memories and code never leave it except for the model calls. You need a Nebius Token
Factory key (the hackathon's Nebius Builder credits work) and optionally a Tavily key.

A five-minute walkthrough:
1. Install and run `mender doctor --live` (see Setup).
2. In any git repo, save a memory with Claude Code, linked to a file ("we run Postgres via
   docker-compose.yml").
3. Change that file (switch to `mysql:8`), then `mender --repo . run` and `mender --repo . ui`.
4. Approve the draft; Mnemolith now holds the corrected memory.
Also try: delete the file (Retire), rename it (path updated), or bump a dependency in
`requirements.txt` (web research with sources).

## Setup
Needs Python 3.10+, Java 11+ (Mnemolith's engine), and [Mnemolith](https://mnemolith.dev)
(`pip install mnemolith`; it's also installed as a dependency below).

    git clone https://github.com/anishchugh05/mnemolith-mender
    cd mnemolith-mender && uv venv && source .venv/bin/activate && uv pip install -e .
    cp .env.example .env        # add NEBIUS_API_KEY (and TAVILY_API_KEY)
    mender doctor --live        # checks repo, Mnemolith, key, model IDs, Ultra tool calling

If the `mender` command is not found after install, run `python -m mender.cli` instead.

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
