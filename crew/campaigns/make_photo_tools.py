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
    ("hatch", "Larry", "Gordon", "S", ["hatch"], 6, [],
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
    ("contour", "Qwen", "Gordon", "L", ["Loop", "is_junction", "trace"], 8, [],
     "The hardest module: follow rules 1-7 literally. Edges keep the region on the "
     "right; at a saddle turn RIGHT; drop straight-through points unless they are "
     "junctions; rotate to the smallest (y, x) point; sort by label then first point. "
     "Check every worked example, especially the saddle and the T-junction.",
     "Use the worked examples as tests, plus is_junction on its own. Compare whole "
     "Vec<Loop> values."),
    ("sobel", "Nemotron", "Larry", "S", ["magnitude", "edge_mask"], 6, [],
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
    ("smooth", "Gordon", "Barry", "M",
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
    ("despeckle", "Barry", "Larry", "M", ["despeckle"], 6, [],
     "Components are found once on the input (4-connected); one pass in raster order "
     "using CURRENT labels; ties to the smaller label; areas are never recomputed. "
     "Walk both walk-throughs in the contract.",
     "Use the table rows; include the diagonal case and the one-pass row [0, 5, 2]."),
    # wave 2: crate-facing, given the API card
    ("lineart", "Hoss", "Nemotron", "C", ["render"], 6, ["luma.rs", "sobel.rs", "options.rs"],
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
    ("effects", "Nemotron", "Barry", "C", ["EffectOutput", "render"], 6,
     ["luma.rs", "dodge.rs", "dither.rs", "halftone.rs", "hatch.rs", "ascii.rs",
      "options.rs"],
     "Validate first, then the empty check. Gray from crate::luma, never to_luma8. "
     "The hatch spacing is opts.cell. ASCII returns Text; the rest return Image.",
     "Build expected values from the accepted modules; include the (0, 200, 0) Rec. 601 "
     "case and both ASCII variants."),
    ("vector", "Gordon", "Larry", "C", ["render"], 6,
     ["kmeans.rs", "despeckle.rs", "contour.rs", "smooth.rs", "svg.rs", "options.rs"],
     "Pipeline in the contract's order; background = most common label after "
     "despeckle, ties to the smaller label; one shape per palette label in label order.",
     "Include the exact 2x1 document, the background rule, and compare a larger image "
     "with the pipeline built from the accepted modules."),
]

WAVE2 = {"lineart", "cli", "effects", "vector"}


def campaign(author: str, wave: int, rows) -> dict:
    teams, tasks = {}, []
    for (mod, _a, tester, scope, api, min_tests, uses, instr, tinstr) in rows:
        team = f"{mod.capitalize()}"
        teams[team] = {"author": author, "tester": tester}
        task = {"id": f"pt_{mod}", "team": team, "module": f"{mod}.rs",
                "contract": f"{CONTRACTS}/pt_{mod}.md",
                "hidden_tests": [f"{HIDDEN}/hidden_{mod}.rs"],
                "api": api, "depends": [], "min_tests": min_tests,
                "scope": scope,
                "instructions": instr + " Write the module once, in one reply; do not "
                                        "restate the contract.",
                "test_instructions": tinstr}
        if uses:
            task["uses"] = uses
        if scope == "C":
            task["reference"] = [CARD]
        tasks.append(task)
    name = f"pt-{author.lower()}" + ("-2" if wave == 2 else "")
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
    }


def main() -> None:
    by_author = {}
    for row in MODULES:
        wave = 2 if row[0] in WAVE2 else 1
        by_author.setdefault((row[1], wave), []).append(row)
    for (author, wave), rows in sorted(by_author.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        spec = campaign(author, wave, rows)
        path = OUT / f"{spec['name'].replace('-', '_')}.json"
        path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: {', '.join(r[0] for r in rows)}")


if __name__ == "__main__":
    main()
