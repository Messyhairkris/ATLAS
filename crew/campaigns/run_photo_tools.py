"""Run photo_tools campaigns in parallel and wait for all of them.

    python crew/campaigns/run_photo_tools.py 1      # wave 1 (six campaigns)
    python crew/campaigns/run_photo_tools.py 2      # wave 2 (needs wave 1 accepted)
    python crew/campaigns/run_photo_tools.py 1 --resume   # keep accepted tasks of a stopped run
    python crew/campaigns/run_photo_tools.py pt_hoss_2 pt_qwen_2   # named campaigns only

Each campaign is its own `python -m crew campaign run` process, so one stuck campaign
never blocks another; live state is in runs/crew/campaigns/<name>/status.json.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAVES = {
    "1": ["pt_larry", "pt_hoss", "pt_qwen", "pt_nemotron", "pt_gordon", "pt_barry", "pt_kimi"],
    "2": ["pt_hoss_2", "pt_qwen_2", "pt_kimi_2", "pt_gordon_2"],
    "3": ["pt_kimi_3", "pt_nemotron_3", "pt_gordon_3"],
    "4": ["pt_hoss_4", "pt_kimi_4", "pt_qwen_4", "pt_gordon_4", "pt_nemotron_4"],
    "5": ["pt_kimi_5"],
}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    resume = ["--resume"] if "--resume" in sys.argv else []
    # A wave number, or campaign names to start part of a wave whose inputs are ready.
    names = WAVES[args[0]] if args and args[0] in WAVES else (args or WAVES["1"])
    logs = ROOT / "runs" / "crew" / "campaigns"
    logs.mkdir(parents=True, exist_ok=True)
    procs = {}
    for name in names:
        out = open(logs / f"{name}.stdout.log", "a", encoding="utf-8")
        procs[name] = (subprocess.Popen(
            [sys.executable, "-m", "crew", "campaign", "run",
             str(ROOT / "crew" / "campaigns" / f"{name}.json"), *resume],
            cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT), out)
        print(f"started {name}", flush=True)
        time.sleep(5)          # stagger the first requests
    for name, (proc, out) in procs.items():
        code = proc.wait()
        out.close()
        tail = (logs / f"{name}.stdout.log").read_text(encoding="utf-8").splitlines()[-3:]
        print(f"{name}: exit {code} | " + " | ".join(tail), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
