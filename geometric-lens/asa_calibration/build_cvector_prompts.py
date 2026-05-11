#!/usr/bin/env python3
"""Build positive.txt / negative.txt for llama-cvector-generator from a
JSONL contrast-pair file.

May 2026 BiasBusters #4 — ASA-style activation steering. The contrast
pairs encode the ast_edit-vs-edit_file decision as positive/negative
examples; cvector-generator extracts the residual-stream difference
between them; llama-server applies the difference at inference time
via --control-vector-scaled.

Usage:
    python build_cvector_prompts.py \\
        --pairs contrast_pairs.jsonl \\
        --positive ast_edit_positive.txt \\
        --negative ast_edit_negative.txt

Then run upstream cvector-generator (built from llama.cpp tools/):
    llama-cvector-generator \\
        -m /models/Qwen3.5-9B-Q6_K.gguf \\
        --positive-file ast_edit_positive.txt \\
        --negative-file ast_edit_negative.txt \\
        --method mean \\
        -o ast_edit_steering.gguf \\
        -ngl 99

And add to inference/entrypoint-v3.1-9b.sh (or set the env var the
entrypoint reads):
    --control-vector-scaled /path/to/ast_edit_steering.gguf:0.5
"""

import argparse
import json
import sys
from pathlib import Path


# Qwen3.5 chat-template format. cvector-generator wants one prompt per
# line with literal `\n` for newlines. Each prompt is the model's full
# context up through the assistant prefix — the prefix is what shifts
# the residual stream toward "I'm about to emit ast_edit" (positive) or
# "I'm about to emit edit_file" (negative).
QWEN_PROMPT_TEMPLATE = (
    "<|im_start|>system\\n"
    "You are ATLAS, a coding assistant. Choose the right tool for the job.\\n"
    "<|im_end|>\\n"
    "<|im_start|>user\\n"
    "{user}\\n"
    "<|im_end|>\\n"
    "<|im_start|>assistant\\n"
    "{assistant_prefix}"
)


def render(pair: dict) -> str:
    return QWEN_PROMPT_TEMPLATE.format(
        user=pair["user"].replace("\n", "\\n"),
        assistant_prefix=pair["assistant_prefix"].replace("\n", "\\n"),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True, type=Path,
                    help="JSONL file with one pair per line "
                         "({label, user, assistant_prefix, tool})")
    ap.add_argument("--positive", required=True, type=Path,
                    help="output file for label==ast_edit prompts")
    ap.add_argument("--negative", required=True, type=Path,
                    help="output file for label==edit_file prompts")
    args = ap.parse_args()

    pos: list[str] = []
    neg: list[str] = []
    with args.pairs.open() as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                pair = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"line {lineno}: bad JSON: {exc}", file=sys.stderr)
                return 1
            for key in ("label", "user", "assistant_prefix"):
                if key not in pair:
                    print(f"line {lineno}: missing field {key!r}", file=sys.stderr)
                    return 1
            rendered = render(pair)
            if pair["label"] == "ast_edit":
                pos.append(rendered)
            elif pair["label"] == "edit_file":
                neg.append(rendered)
            else:
                print(f"line {lineno}: unknown label {pair['label']!r} "
                      f"(expected 'ast_edit' or 'edit_file')", file=sys.stderr)
                return 1

    if not pos or not neg:
        print(f"need both ast_edit and edit_file pairs; "
              f"got {len(pos)} positive, {len(neg)} negative", file=sys.stderr)
        return 1
    if len(pos) != len(neg):
        # cvector-generator pairs them positionally — line N of positive
        # is contrasted against line N of negative. Mismatched counts
        # silently truncate the longer side, which biases the vector.
        print(f"warning: {len(pos)} positive vs {len(neg)} negative — "
              f"cvector-generator will use min(N) pairs, biasing the result",
              file=sys.stderr)

    args.positive.write_text("\n".join(pos) + "\n")
    args.negative.write_text("\n".join(neg) + "\n")
    print(f"wrote {len(pos)} positive prompts to {args.positive}")
    print(f"wrote {len(neg)} negative prompts to {args.negative}")
    print()
    print("Next: run cvector-generator (see header docstring for the command).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
