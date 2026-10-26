---
name: no-per-call-injection
trigger: model_decision
description: when designing a hook, a prompt or anything that adds text to calls
---
Nothing may run or add text on every call - it burned the weekly limits.
Render once: into a brief at session start, into a job's system prompt at job start.
