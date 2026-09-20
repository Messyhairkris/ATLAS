# Playbook: ui_sweep

The harness launched the app and pressed its controls for you, highlighting
each one in orange for half a second first so a human could watch. Your job is
to turn the sweep log into a report a developer can act on.

## Entries
- [us-001] (seed) The sweep log is your evidence. Cite it as [src: sweep_log] on every line that states what happened; cite a source file only if you opened it with read_file.
- [us-002] (seed) Quote the sweep's summary line verbatim (for example "0 failed, 20 passed") in your answer paragraph.
- [us-003] (seed) Never name a control that does not appear in the log. Quote control names exactly as the log spells them, including case.
- [us-004] (seed) Structure: frontmatter, a 2-4 line answer, ## Problems (one item per control with a problem: the control, what happened, the log line verbatim), ## Skipped (controls the sweep refused to press and why - destructive names and window frame controls), ## Not reached (controls found but beyond the max, or in menus the sweep could not open), ## Coverage gaps, ## Open questions.
- [us-005] (seed) "problem": true means either no control pattern responded or the app wrote an error while that control was pressed. Say which of the two it was; they mean different things.
- [us-006] (seed) A control that opened a dialog is not a fault: the sweep closes dialogs on purpose. Report it under Problems only if an error accompanied it.
- [us-007] (seed) A clean sweep is a real result. Say what was pressed and, more usefully, what the sweep could NOT reach - menu items behind a click, controls needing text selection first, anything skipped. That list is the next test to write.
- [us-008] (seed) Any claim that something is not covered must cite a file you opened or be marked (inferred); the log cannot evidence an absence.
- [us-009] (review Claude sweep-1) A claim that there are no gaps is itself an absence claim: cite the sweep_limits event and list every limit it names, then add anything else you noticed. A sweep that pressed every discovered control still tested almost nothing about menus, typing, shortcuts and selections.
- [us-010] (review Claude sweep-1) Report the controls the sweep skipped AND the ones it structurally cannot reach in separate sections; the second list is the next test to write.
- [us-011] (review Claude interference) If the log contains human_interference or unreliable presses, name those controls, say the results cannot be trusted, and recommend re-running them on an idle machine.
- [us-012] (review Claude menus) Menus are opened and their items pressed now: report menu items as "Menu > Item" and list any menu that failed to open (menu_did_not_open).
- [us-013] (Kris 2026-09-19) The sweep now waits for readiness instead of a fixed settle time, and it records what never happened. A `nothing_opened` event means a control whose name says it opens something was pressed, the sweep waited to the ceiling, and nothing appeared anywhere on the desktop and no file was written. Report it as a failure by name, with the seconds waited. Kris watched this exact case: "First slowdown noticed on opening the logs (it never did)."
- [us-014] (Kris 2026-09-19) A `stalled` event means the app was still not answering when the wait ceiling ran out. Say so, name the control, and warn that results reported AFTER it may belong to work that was still finishing.
- [us-015] (Kris 2026-09-19) `external_window` means the app opened something in another program (a log in Notepad, a folder in Explorer). That is a success, not a fault: report what opened and in which program. `still_waiting` lines are the sweep narrating a slow action, not an error.
- [us-016] (Kris 2026-09-19) Every "pressed" event now carries `seen`, which is what was OBSERVED (opened X / wrote N files / NOTHING OPENED / no visible change). Report the `seen` value, not what the control's name suggests it should do.
