# Which crew members can see, measured

Kris, 2026-09-21: *"are any of our crew members able to use vision tasks? We should
also be aware of how to best use those abilities."*

The provider's model list (`GET /v1/models`, field `input_modalities`) says what each
model **claims**. Two probes say what it **does**, both with answers known in advance:

- **Shapes** — a 240×120 PNG drawn in code: red circle, blue square, green triangle.
- **Screenshot** — the real Review Desk window, asked three questions a UI check would
  ask: the header count (3), which list items are not marked `[ok]` (speech.py,
  profiles.py, test_profiles.py), and a value in the code panel (`DEFAULT_VOLUME = 45`).

| member | model | claims images | shapes | screenshot | verdict |
|---|---|---|---|---|---|
| **Gordon** | DeepSeek-V4.1-Flash | yes | **correct** | **3/3** | **the vision member** |
| Qwen | Qwen3.8-27B | yes | correct | 2/3 — missed one unmarked item | usable, verify lists |
| Barry | GLM-5.3-Flash | yes | **wrong 4 times out of 4**, a different wrong answer each time | claimed it could not see the image | **do not use for vision** |
| Kimi | Kimi-K3 | yes | not probed | not probed | Crush's model; expensive |
| Hoss | gpt-oss-120b | no | provider refuses (HTTP 400) | — | text only |
| Nemotron | Nemotron-3-Super | no | provider refuses (HTTP 400) | — | text only |
| Haiku | claude-haiku-4-5 | yes | not yet — needs an API key | — | expected strong; measure first |

Barry is the warning. The provider lists him as a vision model, and he answers every
image question in the same confident, well-formatted way whether he is right or not —
"square: green, triangle: blue", then "square: green, triangle: red", then "square:
red". A text-only model that errors is safe; a vision model that invents is not.

## How to use it

- **Give vision work to Gordon.** Qwen as the second reader when two opinions matter.
- **Ask for facts that can be checked, never impressions.** "How many items does the
  header say are waiting" can be gated; "does this look right" cannot. The same rule
  as every other crew task: the gate decides, not the member's confidence.
- **Pair a screenshot with the text you already have.** The window's own widget text
  (from `ui_sweep` or tkinter) is the ground truth; vision is for what text cannot
  give you — layout, colour, overlap, something cut off.
- **Good first jobs:** checking a UI sweep's screenshots for clipped or hidden
  controls (the probe itself found one: at 900×560 the desk's SEND button falls off
  the bottom), reading a chart back into numbers, comparing a before/after screenshot.
- **Not yet wired:** crew jobs carry text only. A `vision_check` task type needs the
  image passed as an `image_url` content part (the probe did exactly that through
  `stages.llm_client.chat_completion`) and a gate that compares answers with known
  values.

Probe cost: 13 requests on cheap models, well under a cent of credits.
