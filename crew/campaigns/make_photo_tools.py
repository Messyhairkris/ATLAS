"""Write the photo_tools Rust campaigns (image_convert, 2026-10-20) from one table.

    python crew/campaigns/make_photo_tools.py

Kris: make every member a Rust hand and find the scope that suits each. So every member
authors and tests, at different scopes: S = one or two small pure functions on bytes,
M = an exact algorithm or a byte-exact format, L = the largest exact algorithm (contour),
C = a crate-facing module (image/imageproc/clap) given the API card as reference.
Wave 1 is pure std; wave 2 uses the modules accepted in wave 1.
"""

import json
from pathlib import Path

ROOT = "C:/Users/user/ATLAS-api-harness"
CONTRACTS = f"{ROOT}/crew/contracts"
HIDDEN = f"{ROOT}/crew/hidden_tests/rs_photo_tools"
CARD = f"{CONTRACTS}/cards/image_imageproc_clap_card.md"
OUT = Path(__file__).resolve().parent

# module, author, tester, scope, api, min_tests, uses, instructions, test_instructions
MODULES = [
    ("luma", "Larry", "Hoss", "S", ["luma", "rgb_to_gray", "invert"], 6, [],
     "Widen each byte to u32 BEFORE multiplying. Walk every table row, including the "
     "rounding rows (0,0,5) -> 1 and (0,0,4) -> 0.",
     "Cover each rule and every table row; include a partial trailing triple."),
    ("dodge", "Larry", "Nemotron", "S", ["color_dodge", "dodge_layers"], 6, [],
     "Rules 1-3 in order: base 0 first, then blend 255, then the formula in u32 with "
     "d / 2 added before dividing.",
     "One test per rule plus the table; include (0, 255) for the rule order and "
     "(1, 253) for the d / 2 rounding."),
    # Larry (GLM-4.7-Flash) gave nine 504s in 50 minutes on 2026-10-20; Kris: Larry is at his best
    # as a gofer, monitor and single-task agent - give his jobs to Kimi if he stays down.
    ("hatch", "Kimi", "Gordon", "S", ["hatch"], 6, [],
     "Four layers, strict < comparisons, spacing below 2 counts as 2. Check the 4x3 "
     "table row by row.",
     "Test each layer threshold at its boundary (192/191, 128/127, 64/63, 32/31) and "
     "the spacing rule."),
    ("dither", "Hoss", "Qwen", "S", ["floyd_steinberg"], 7, [],
     "i32 buffer, never clamped; each share is err * k / 16 with Rust's truncating "
     "division; every row left to right. Walk the 3x3 example step by step.",
     "Include the truncation row [200, 152], the no-clamp row [100, 255, 115] and the "
     "row-order row [128, 128, 100, 100]."),
    ("svg", "Hoss", "Barry", "M", ["fmt_num", "hex", "path_data", "document"], 7, [],
     "Byte-exact. fmt_num works on the rounded integer r = (v * 100).round() as i64 - "
     "never format a float and trim. Copy the document template character for "
     "character, including every \\n.",
     "Compare whole strings. Cover every fmt_num row, an empty loop in path_data, and "
     "a shape with an empty d in document."),
    ("ascii", "Qwen", "Hoss", "M", ["RAMP", "grid", "render"], 7, [],
     "Byte-exact. grid: clamp columns to 1..=width, then cell_h = 2 * cell_w unless "
     "the image is shorter. Means truncate. In ANSI mode the reset comes once per line, "
     "after the last character, before the newline.",
     "Compare whole strings; include the truncating-mean case, ignored pixels past the "
     "last cell, and the ANSI layout."),
    # contour was one L job; Qwen's long reasoning on it hit the provider's 10-minute
    # gateway timeout three times (504), so Kris split it (2026-10-20): three smaller
    # jobs, the last one assembling the first two.
    ("junction", "Qwen", "Gordon", "S", ["is_junction"], 6, [],
     "Do the neighbour arithmetic in i64 (x - 1 at x == 0). OUTSIDE is its own value. "
     "Walk every table row, especially the saddle and the two-labels-but-not-a-"
     "checkerboard rows.",
     "Use the table rows; include border vertices, a saddle, a straight split and an L "
     "corner."),
    ("edges", "Qwen", "Hoss", "M", ["RawLoop", "boundary_edges", "raw_loops"], 7, [],
     "One slot per possible edge, index vertex_index * 4 + direction, holding the owning "
     "label; iterate slots in index order for both functions. Linking: right, else "
     "straight, else left; never back. Walk the hole, saddle and L-shape examples.",
     "Use the worked examples; check edge order at a shared vertex and that every edge "
     "lands in exactly one loop."),
    ("contour", "Qwen", "Gordon", "M", ["Loop", "is_junction", "trace"], 8, [],
     "Assembly only: call crate::edges::raw_loops and crate::junction::is_junction (re-"
     "exported with `pub use`). Keep corners and junctions, rotate to the smallest (y, x) "
     "point (tie: smaller following point), sort by label, first point, second point.",
     "Use the worked examples as tests, plus is_junction through the re-export. Compare "
     "whole Vec<Loop> values.",
     {"depends": ["pt_junction", "pt_edges"]}),
    ("sobel", "Nemotron", "Kimi", "S", ["magnitude", "edge_mask"], 6, [],
     "Clamp sample coordinates to the image; kernels indexed [row][column]; "
     "magnitude rounded with f64::round; the mask uses >=.",
     "Include the clamped border (the vertical step), the single bright pixel and the "
     "threshold boundary 361/362."),
    ("options", "Nemotron", "Qwen", "M",
     ["Error", "EdgeFilter", "LineArtOptions", "VectorOptions", "Style", "EffectOptions",
      "Job", "parse_threshold", "LineArtOptions::validate", "VectorOptions::validate",
      "EffectOptions::validate", "LineArtOptions::default", "VectorOptions::default",
      "EffectOptions::default", "Error::fmt"], 8, [],
     "Exact derives, field names and order; error reasons are copied verbatim from "
     "the contract. Checks run in the listed order and the first failure is returned. "
     "NaN and infinity fail the range checks.",
     "Test defaults, every validation rule at its boundary, the Display text, and every "
     "parse_threshold row."),
    ("kmeans", "Gordon", "Qwen", "M", ["Palette", "quantize"], 7, [],
     "No randomness. Bins in ascending key order; farthest-first initial centres with "
     "the stated tie-breaks; stop when an assignment repeats; f64 for positions and "
     "centres; labels from the ROUNDED palette in integers. Walk every table row.",
     "Use the worked examples; include max_iter 0 (11.5 rounds to 12), k 0, k above the "
     "number of bins, and both tie rules."),
    # smooth tests: Barry's model gave three 504s in a row (10:37-11:11, 2026-10-20);
    # reassigned to Kimi, a strong reasoner, per Kris's rule for harder tasks.
    ("smooth", "Gordon", "Kimi", "M",
     ["Pt", "Cubic", "simplify", "simplify_canonical", "split_chains", "smooth_loop"], 8, [],
     "Write the arithmetic exactly as the contract shows - the two sides of a shared "
     "border must agree bit for bit. Distances strictly greater than epsilon are kept; "
     "ties go to the smallest index. Closed loops wrap the Catmull-Rom neighbours; "
     "chains between junctions clamp them.",
     "Cover simplify's rules, both canonical directions, split_chains with 0, 1 and "
     "several junctions, epsilon 0 versus Catmull-Rom, and that walking a loop backwards "
     "gives the same segments reversed."),
    ("halftone", "Barry", "Gordon", "M", ["halftone"], 6, [],
     "Cells clipped at the edges still use the FULL cell's centre; the mean truncates; "
     "the comparison is strict (<). Check the 128-gray 4x4 and 3x3 rows.",
     "Include white (no dots, odd cell), black, mid-gray corners, a clipped cell and the "
     "cell-below-2 rule."),
    ("despeckle", "Barry", "Kimi", "M", ["despeckle"], 6, [],
     "Components are found once on the input (4-connected); one pass in raster order "
     "using CURRENT labels; ties to the smaller label; areas are never recomputed. "
     "Walk both walk-throughs in the contract.",
     "Use the table rows; include the diagonal case and the one-pass row [0, 5, 2]."),
    # wave 2: crate-facing, given the API card
    # lineart tests: Nemotron failed 6 attempts on his own compile errors (crate:: paths
    # in an integration test, an invented DynamicImage::from_rgb8, &Vec vs Vec), after
    # our two fixes (tester feedback, dependency sources shown). Reassigned to Qwen.
    # 13:40: then Qwen's endpoint stalled (two 504s, 40 minutes silent): -> Kimi.
    ("lineart", "Hoss", "Kimi", "C", ["render"], 6, ["luma.rs", "sobel.rs", "options.rs"],
     "Validate first, then the empty check. Gray comes from crate::luma::rgb_to_gray, "
     "never to_luma8. Only blur when blur > 0. Canny gives white edges: invert them.",
     "Build expected values from the accepted modules and imageproc as the contract "
     "describes; include the red-pixel Rec. 601 case and the threshold rounding rows."),
    ("cli", "Qwen", "Hoss", "C",
     ["ModeArg", "FilterArg", "StyleArg", "Args", "Invocation", "Exit", "parse"], 8,
     ["options.rs"],
     "Use Args::try_parse_from(argv.iter()) only. Check flags against the mode in "
     "field order before building options; error texts are exact.",
     "Cover both spec examples, defaults per mode, each mode's flags, the 'does not "
     "apply' errors, validation errors, help/version code 0 and clap errors code 2."),
    # Kris, 2026-10-20: Qwen, Gordon and Kimi are the strongest reasoners; the harder
    # tasks go to them. effects (7 modules + imageproc) moved from Nemotron to Kimi.
    ("effects", "Kimi", "Barry", "C", ["EffectOutput", "render"], 6,
     ["luma.rs", "dodge.rs", "dither.rs", "halftone.rs", "hatch.rs", "ascii.rs",
      "options.rs"],
     "Validate first, then the empty check. Gray from crate::luma, never to_luma8. "
     "The hatch spacing is opts.cell. ASCII returns Text; the rest return Image.",
     "Build expected values from the accepted modules; include the (0, 200, 0) Rec. 601 "
     "case and both ASCII variants."),
    ("vector", "Gordon", "Kimi", "C", ["render"], 6,
     ["kmeans.rs", "despeckle.rs", "junction.rs", "edges.rs", "contour.rs", "smooth.rs",
      "svg.rs", "options.rs"],
     "Pipeline in the contract's order; background = most common label after "
     "despeckle, ties to the smaller label; one shape per palette label in label order.",
     "Include the exact 2x1 document, the background rule, and compare a larger image "
     "with the pipeline built from the accepted modules."),
    # Kris, 2026-10-20: lasso / polyline / blob-brush selections (Shift adds, Ctrl removes),
    # an eraser on the result, transparent white outside, line art as SVG centerlines.
    # Wave 3 needs nothing new; wave 4 builds on select (and lineart_svg on thin, strokes).
    # 13:40: Qwen's endpoint gave no reply for 40 minutes on three jobs (select, strokes and
    # lineart tests) after two 504s, while the others answered. Kris: rerun Qwen's pieces
    # with Kimi. select -> Kimi; strokes tests -> Hoss (an L-scope test data point).
    ("select", "Kimi", "Gordon", "L",
     ["Shape", "Op", "Mask", "Mask::new", "Mask::from_bits", "Mask::from_luma", "Mask::width",
      "Mask::height", "Mask::bits", "Mask::get", "Mask::count", "Mask::apply", "rasterize",
      "build"], 8, [],
     "Rule 2 is the truth; compute it with rule 3's per-row sweep (sort the crossings, sum "
     "those with xi > px). f64 throughout. Rule 1 first for both shapes. The Mask fields "
     "stay private.",
     "Use every table row. Put a small per-pixel version of rule 2 in your test file and "
     "check a few irregular and self-crossing polygons against it; include build's "
     "Subtract-first rule and Mask::get outside the image."),
    ("thin", "Nemotron", "Kimi", "M", ["thin"], 6, [],
     "Judge every pixel of a sub-iteration against a snapshot taken at its start, then "
     "remove all marked pixels together. Outside the image is background. Walk the 2 x 2 "
     "walk-through in the contract before you write.",
     "Walk the table rows; include the 2 x 2 square, the ring, and that thinning a "
     "result again changes nothing."),
    ("strokes", "Gordon", "Hoss", "L", ["neighbours", "trace"], 8, [],
     "m-neighbours first (rule 2); a node has degree != 2; pass 1 over nodes, then pass 2 "
     "over closed loops; directions always in the order E, SE, S, SW, W, NW, N, NE; a used "
     "link is marked at both ends.",
     "Walk every table row and the neighbours examples; add a check that every foreground "
     "pixel appears in some chain."),
    # 14:42: Larry's endpoint silent 20 minutes on this small task (as at 08:30-09:20);
    # Kris: give Larry's jobs to Kimi if he stays down. Its own campaign (wave 5) because
    # Kimi's wave-4 campaign is still running the editor tests.
    ("composite", "Kimi", "Hoss", "S", ["opaque", "keep", "erase", "flatten", "blank_outside"],
     6, ["select.rs", "options.rs"],
     "Size check first (length for blank_outside); LumaA([v, 255]) kept, LumaA([255, 0]) "
     "outside or erased; error texts are exact.",
     "Use every table row, including both size errors and that nothing changes on an "
     "error.", {"wave": 5}),
    ("shapes_file", "Hoss", "Barry", "M", ["Selection", "parse", "write"], 8,
     ["select.rs", "options.rs"],
     "Errors are exact strings that start with the line number; the first error stops the "
     "parse; check the points before counting them; write uses f32 Display.",
     "Cover every error row, comments, blank lines, \\r\\n, and parse(&write(&s)) == s."),
    # 14:52: Qwen silent 23 minutes on the editor tests (his endpoint again) -> Gordon.
    ("editor", "Kimi", "Gordon", "L",
     ["Tool", "Mods", "Event", "Item", "Editor", "Editor::new", "Editor::tool",
      "Editor::set_tool", "Editor::radius", "Editor::set_radius", "Editor::close_radius",
      "Editor::set_close_radius", "Editor::selection", "Editor::erased", "Editor::can_undo",
      "Editor::can_redo", "Editor::pending", "Editor::selection_mask", "Editor::erase_mask",
      "Editor::handle"], 10, ["select.rs"],
     "Rules 4-13 literally, in f32 with >= for far (rule 3). History is two stacks, DONE and "
     "UNDONE; a deselect remembers the list it cleared. Walk every table row.",
     "Walk every row of the worked-example table; include undo with a shape in progress, "
     "deselect then undo, and the polyline close distance."),
    ("lineart_svg", "Qwen", "Gordon", "C", ["StrokeOptions", "chain_path", "render_svg"], 6,
     ["lineart.rs", "luma.rs", "sobel.rs", "options.rs", "select.rs", "smooth.rs",
      "strokes.rs", "svg.rs", "thin.rs"],
     "Validate opts, then stroke, then render, then the size check; thin -> trace -> "
     "chain_path; ONE <path> element with every chain joined by a space; no background.",
     "Build expected documents from the accepted modules (lineart, thin, strokes, "
     "smooth::simplify, svg::fmt_num); include the RING rows and every validate error."),
    ("vector_select", "Gordon", "Kimi", "C", ["render_selected"], 6,
     ["contour.rs", "despeckle.rs", "edges.rs", "junction.rs", "kmeans.rs", "options.rs",
      "select.rs", "smooth.rs", "svg.rs", "vector.rs"],
     "Follow vector.rs (shown), but: the palette comes from the selected pixels only, the "
     "outside label is palette.colors.len(), unselected pixels go back to it after "
     "despeckle, and there is no rect.",
     "Include the RB rows exactly, and compare everything-selected with vector::render "
     "minus its rect line."),
    # cli revision for --select / --mask: Nemotron at C scope with the accepted cli.rs as
    # a scaffold (his C-scope tests failed on Rust API guesses; this measures authoring).
    ("cli", "Nemotron", "Hoss", "C",
     ["ModeArg", "FilterArg", "StyleArg", "Args", "Invocation", "Exit", "parse"], 8,
     ["options.rs"],
     "This REVISES the accepted cli.rs shown in the references: keep everything it does and "
     "add the two fields --select and --mask (last in Args and in Invocation) and rule 3a. "
     "Use Args::try_parse_from(argv.iter()) only; error texts are exact.",
     "Cover the select/mask rows, rule 3 before 3a, 3a before validation, and that help "
     "mentions both flags; keep the earlier rows (defaults per mode, mode errors).",
     {"wave": 4, "reference": [f"{ROOT}/runs/crew/outbox/workspace/photo_tools/cli.rs"]}),
]

WAVE2 = {"lineart", "cli", "effects", "vector"}
WAVE3 = {"select", "thin", "strokes"}
WAVE4 = {"composite", "shapes_file", "editor", "lineart_svg", "vector_select"}

# Kris: Kimi is great but needs good scoping to keep from overthinking. The wording that
# worked on 2026-10-15 (PERSONNEL.md: 504s from long visible thinking stopped once the
# prompt said the reply is read by a program; reply cap 24576 in config.json).
KIMI_SCOPE = (" YOUR REPLY IS READ BY A PROGRAM. Think silently and briefly - everything you"
              " need is in the contract above; do not reason aloud. Begin your reply with"
              " SUBMIT and the one file, and nothing after it. SCOPE: one file, one reply; do"
              " not explore, re-derive the rules, or add features or extra checks - apply the"
              " numbered rules and the table literally.")
KIMI_BUDGET = {"requests_per_attempt": 6, "tokens_per_attempt": 80000}


def campaign(author: str, wave: int, rows) -> dict:
    teams, tasks = {}, []
    for (mod, _a, tester, scope, api, min_tests, uses, instr, tinstr, *extra) in rows:
        extra = extra[0] if extra else {}
        team = f"{mod.capitalize()}"
        teams[team] = {"author": author, "tester": tester}
        task = {"id": f"pt_{mod}", "team": team, "module": f"{mod}.rs",
                "contract": f"{CONTRACTS}/pt_{mod}.md",
                "hidden_tests": [f"{HIDDEN}/hidden_{mod}.rs"],
                "api": api, "depends": list(extra.get("depends", [])),
                "min_tests": min_tests,
                "scope": scope,
                "instructions": instr + " Write the module once, in one reply; do not "
                                        "restate the contract."
                                + (KIMI_SCOPE if author == "Kimi" else ""),
                "test_instructions": tinstr + (KIMI_SCOPE if tester == "Kimi" else "")}
        if uses:
            task["uses"] = uses
        if scope == "C":
            task["reference"] = [CARD]
        if extra.get("reference"):
            task["reference"] = task.get("reference", []) + list(extra["reference"])
        tasks.append(task)
    name = f"pt-{author.lower()}" + (f"-{wave}" if wave > 1 else "")
    return {
        "name": name,
        "rs_profile": "photo_tools",
        "workspace_subdir": "photo_tools",
        "senior": "Claude",
        "senior_fallback": "Kimi",
        "max_attempts": 3,
        "max_escalations": 1,
        "max_requests": 90,
        "goal": (f"photo_tools (image_convert) wave {wave}: {author} authors "
                 + ", ".join(f"{r[0]}.rs ({r[3]})" for r in rows)
                 + ". First Rust campaigns: measure which scope suits each member. "
                   "S small, M exact/byte-exact, L largest algorithm, C crate-facing "
                   "with the API card."),
        "teams": teams,
        "tasks": tasks,
        **(KIMI_BUDGET if author == "Kimi" else {}),
    }


def main() -> None:
    by_author = {}
    for row in MODULES:
        extra = row[9] if len(row) > 9 else {}
        wave = extra.get("wave") or (2 if row[0] in WAVE2 else 3 if row[0] in WAVE3
                                     else 4 if row[0] in WAVE4 else 1)
        by_author.setdefault((row[1], wave), []).append(row)
    for (author, wave), rows in sorted(by_author.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        spec = campaign(author, wave, rows)
        path = OUT / f"{spec['name'].replace('-', '_')}.json"
        path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: {', '.join(r[0] for r in rows)}")


if __name__ == "__main__":
    main()
