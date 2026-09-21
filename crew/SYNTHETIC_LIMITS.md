# Synthetic rate limits

Source: https://synthetic.new/rate-limits, as published on 2026-09-21 (Kris pasted it in).
The governor (`crew/ratelimit.py`) reads the live truth from the `x-synthetic-quotas`
response header; `config.json -> rate_limit` holds these numbers only as the fallback
before the provider has answered once.

## Three limits, all per subscription pack

| Limit | Per pack | Regenerates | Worst-case wait |
|---|---|---|---|
| Requests | 500 per 5 hours | 5% every 15 minutes (full in 5 h) | 15 minutes |
| Weekly credits | $24 of API credit per week | 2% every 202 minutes (full in 1 week) | ~3.4 hours |
| Concurrency | 1 request per model at full speed | - | extra requests to the same model queue |

**Kris's plan until 2026-09-30: 2 packs** - 1000 requests / 5 h, $48 / week, 2 concurrent
requests per model.

## Requests are weighted by model price

The baseline is the default model, moonshotai/Kimi-K3: one call = 1 request. Cheaper models
count as a fraction - GLM-5.3-Flash is 10x cheaper, so a call is about **0.1 requests**. The
crew's measured cost on 2026-09-20 was ~0.033 requests per cheap-model call. Credits are
spent the same way, by price. So:

- The crew's request count in campaign reports is *calls*, not quota. Five hours of crew
  work on 2026-09-21 (JS harness, packer, guide, with a little Kimi) cost Kris **$1.35**.
- Kimi (and Claude as a senior) are the expensive calls. Keep seniors capped
  (`max_escalations`).

## What this means for scheduling

- **No cooldown penalty for bursts.** Regeneration is continuous; running out means waiting
  for the next 15-minute tick, not a lockout.
- **Parallelism is per model.** Different models run side by side; two jobs on the SAME
  model share its slot(s). With 2 packs a campaign could run up to 2 jobs per member
  concurrently, and teams with different members never block each other. (Campaigns
  currently run tasks one at a time - there is throughput left on the table.)
- **Crush/Kimi and the crew share both pools.** The weekly credit pool is usually the
  binding one, and a heavy Kimi session drains it far faster than the crew does.
