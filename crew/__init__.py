"""The Crew — a proto-CrossTalk work queue for cheap roster models.

An architect (Claude, Crush, or Kris) submits AtomicTask-shaped jobs over MCP;
a crew member (Hoss by default) works them with READ-ONLY tools; deterministic
gates check the result; output is staged for review and only lands in the
workspace when a reviewer approves it or the member's Autonomy Stage for that
task type allows auto-apply. Every state change is an ActionNode in the
action log; every job updates the member's Performance Profile.

CrossTalk mapping: jobs = Atomic Task System, action_log = ActionLog as
Directed Graph, roster = Performance Profile + Autonomy Stages, playbooks =
Three-Layer Context Injection layer 1 + Registry probation, claims with
leases = MAIN-arbitrated task_claim.
"""

__version__ = "0.1.0"
