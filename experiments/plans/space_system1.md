# Checkpoints: SIGNAL LOST → "System 1: Home Belt" (design evolution after human test #2)

From Kris's human test (2026-09-18) — the tutorial exists but is not yet a
game. These checkpoints turn it into Level 1 of a mobile-ready, gravity-
slingshot collection game. Hoss implements; seniors only after real
exhaustion (repair 3 per part, Kimi last-resort).

## Core loop (Level 1 identity)
Collect ALL 4 ore in one solar system; timer runs from level start; dock at
the beacon to bank. Records: fastest time (TIME_BEST) + combo bonuses
(collect ore within 5s of the last → COMBO_xN, bonus = 100 × N). Speedrun
glory = short line + high combo; thoughtful play = still completable
(watchdog 150s). Speed + completion both score.

## Gravity (the game's physics identity)
- gravity_well.gd (Area3D, exported mass, group "gravity_well"): contributes
  pull = dir × (G × mass / max(dist², min_dist²)) each frame to bodies' ship
  velocity (ship integrates; cap to avoid singularities; subtle = forgiving).
- STAR: yellow, giant, at (0, 26), mass 900000, well zone r=60. PLANET A:
  blue, (16, 2), mass 250000, r=35. PLANET B: purple, (-18, -12),
  mass 150000, r=25. Ship feels star everywhere (faint), planets locally
  (strong) → slingshot arcs to orbit ore fields. Masses/distances/radii are
  CRUSH spec, not Hoss invention.
- Autopilot unaffected: well pull applies too (it must also slingshot;
  arrive-clamp already caps approach speed).

## Human test #2 fixes (checklist, all in P7)
- [ ] Up/down: tester reports reversed ⇒ flip sign via named constant
      Y_SIGN (documented, Kris-tunable). Controls: keep THRUST/damp feel but
      SOFTER: THRUST 420, DRAG 0.55, MAX_SPEED 240 (slower ramp, long glide).
- [ ] Bounding box: world bounds x ±30, y ±18; outside → inward push +
      HUD warning "RETURN TO BELT" + soft clamp at ±34/±22 (never losable).
- [ ] Camera follows ship: main.gd per-physics-frame Camera3D x/y = ship x/y
      (z stays 20).
- [ ] Debug reset: press R → ship to (0, -6, 0), velocity ZERO, print RESET.
- [ ] Visibility: YOU Label3D bigger (font_size 96, cyan-white); ALL objects
      self-lit: material.emission_enabled = true, emission = albedo color,
      emission_energy_multiplier = 0.4 (ANGLE renderer washed colors to
      grey — self-lit fixes the flatness).
- [ ] Stage text 0 mentions gravity so the mechanic is taught, not found.

## Deferrals (explicit, for Claude's ledger)
Touch controls (mobile), multiple systems beyond System 1, star/planet
variety pass, scoreboard persistence, anti-frustration autobrake toggle,
Qwen/Barry experiments (parked), "bad game completely" from original brief
= superseded by System-1 quality bar per Kris.
