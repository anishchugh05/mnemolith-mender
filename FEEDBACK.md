# Feedback: Nebius Token Factory and NVIDIA Nemotron

Notes from building Mnemolith Mender (Nemotron Nano for triage, Nemotron Ultra as a
tool-using drafting agent, on Token Factory). What worked, what got in the way, and what
we would change.

## What worked well
- **OpenAI-compatible API.** The stock `openai` client worked against Token Factory by
  changing only the base URL and key. No custom SDK, no surprises.
- **Tool calling on Nemotron Ultra worked reliably.** A drafting run is a loop of 3 to 6
  calls (read a file, search the repo, search the web, then a final `submit_draft` call).
  It followed the tool schema every time in our testing, and `mender doctor --live` can
  verify it in one call.
- **Speed.** On our demo repo Nano averaged about 2.2 s per call and Ultra about 1.7 s per
  call, so a full review cycle (triage plus an agent loop) takes seconds, not minutes.
- **The Nano / Ultra split fits the job.** Nano settles "is this change even relevant?"
  cheaply, and only the memories that matter reach Ultra.
- **Token use is easy to track.** Responses include usage, so we report measured token counts
  per model instead of estimates.

## What got in the way
- **Card authorization at signup.** Creating the account asked for a card ("a temporary $0
  authorization to verify the card"). For a hackathon with free credits that was a hurdle;
  a clearer note on why, or a no-card path for builder credits, would help.
- **Credit setup was confusing.** The $1 trial credit and the hackathon promo code are
  separate steps, and it was not obvious where to apply the code or how to see the balance.
- **Model IDs are inconsistent in casing and naming** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
  vs `nvidia/Nemotron-3-Ultra-550b-a55b`) and differ by account, so we ship a `mender models`
  command and env overrides. A stable alias per model family would remove that.
- **Ultra fabricated a quotation.** In a dependency-bump test it wrote a reason quoting
  "release notes" with specific numbers (timeouts, buffer size, pool size) that were not in
  any search result. It also gave itself confidence 0.95 to 1.00. We now verify quotes against
  the actual tool results and cap confidence when they do not match. Better calibrated
  self-reported confidence, or a built-in way to constrain answers to tool output, would help
  agent builders.
- **Reasoning text in replies.** Nano's output can include reasoning with braces before the
  JSON, which breaks naive parsing. We extract the last valid JSON object; a documented way to
  switch reasoning output off for classification calls would be welcome.

## Tavily (used for dependency release notes)
- Searching for a specific old version ("redis-py 5.0.0 release notes") mostly returned the
  newest release page, not that version's notes. Version-aware ranking, or a way to pin a
  release page, would make it far more useful for this use case.
- Results with multi-line content are easiest to use when flattened; a field for a clean
  single-line snippet would help.

## Wishes
- A per-request token and cost readout in the Token Factory dashboard that is easy to match
  to the usage in each response.
- Example agent loops with tool calling for Nemotron Ultra in the docs.
