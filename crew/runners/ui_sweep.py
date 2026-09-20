"""Visible UI sweep: press every control in a Windows app and report.

Kris's rule, and it applies to every harness tool, not just this one: a program
must never look like nothing is happening. So each control is HIGHLIGHTED in
the test color (#FF7900) for half a second BEFORE it is pressed, which lets a
human watch the sweep and see what is about to happen, in time to stop it.
Optional beeps give the same signal without looking.

    python ui_sweep.py <app.exe> [--out sweep.jsonl] [--pre 0.5] [--settle 0.6]
                       [--settle-max 10] [--quiet 0.6] [--max 200]
                       [--watch-log PATH] [--beep]
                       [--include-destructive] [--only NAME[,NAME...]]

The sweep does not guess how long an action takes. After every press it waits
until the app pumps messages again, the desktop's window list stops changing,
and the watched folders stop growing (--settle is the floor, --settle-max the
ceiling). Anything longer than --report-wait-after is announced in the banner
and logged as `still_waiting`, so a stall is visible instead of silent.

Output: one JSONL event per control plus, at the end, a pytest-shaped summary
line so the crew's existing "quote the totals" gate works unchanged.
Exit code 1 when any problem was seen.
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TEST_COLOR = "#FF7900"          # Kris: test actions are orange, nothing else is
PROP_NAME, PROP_CTRL, PROP_AID = 30005, 30003, 30011
PROP_ENABLED, PROP_OFFSCREEN, PROP_RECT = 30010, 30022, 30001
PROP_HWND = 30020
CONTROL_NAMES = {50000: "Button", 50002: "CheckBox", 50003: "ComboBox",
                 50004: "Edit", 50005: "Hyperlink", 50006: "Image",
                 50007: "ListItem", 50011: "MenuItem", 50013: "RadioButton",
                 50018: "Tab", 50019: "TabItem", 50021: "ToolBar",
                 50024: "TreeItem", 50025: "Custom", 50033: "Window"}
CLICKABLE = {50000, 50002, 50011, 50013, 50019, 50005, 50024}
# Names a sweep must not press unless explicitly allowed: they destroy work or
# end the run. The sandbox is disposable, but a wiped document still hides the
# bug you were looking for.
DESTRUCTIVE = ("delete", "clear", "erase", "remove", "reset", "exit", "quit",
               "close", "save as", "overwrite", "discard", "new document",
               "shut down", "uninstall")
# Controls whose whole job is to open something. If one of these is pressed and
# nothing opens anywhere on the desktop and nothing is written, that is a
# FAILURE to report, not a quiet pass: Kris watched the sweep "open the logs"
# and the logs never appeared, while the run reported no problem.
OPENERS = ("log", "setting", "preference", "option", "about", "help", "open",
           "browse", "import", "export", "folder", "properties", "dictionary",
           "lexicon", "shortcut", "manual", "guide")
# Window chrome belongs to Windows, not to the app under test.
FRAME_CONTROLS = {"close", "minimize", "maximize", "restore", "system",
                  "system menu", "move", "size"}
# comtypes returns a raw pattern object; it must be cast to the pattern's own
# interface before its methods exist (2026-09-19: every press failed with
# AttributeError until this was added).
MENU_TYPES = {50011}                     # MenuItem
PATTERNS = (("Invoke", 10000, "IUIAutomationInvokePattern", "Invoke"),
            ("Toggle", 10010, "IUIAutomationTogglePattern", "Toggle"),
            ("SelectionItem", 10010 + 7, "IUIAutomationSelectionItemPattern", "Select"),
            ("ExpandCollapse", 10005, "IUIAutomationExpandCollapsePattern", "Expand"))


class Overlay:
    """The orange box around the control under test, plus a status banner.

    Kris's rule, learned the hard way on 2026-09-19: the box used to vanish
    after its half second, so a press that took 13 seconds looked like a frozen
    app, and a finished sweep looked identical to a running one. The box now
    stays up for the whole press and the banner always says what is happening.
    """

    def __init__(self, enabled: bool = True):
        self.root = self.banner = self.label = None
        if not enabled:
            return
        try:
            import tkinter as tk
            self.root = tk.Tk()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.45)
            self.root.configure(bg=TEST_COLOR)
            self.root.withdraw()

            self.banner = tk.Toplevel(self.root)
            self.banner.overrideredirect(True)
            self.banner.attributes("-topmost", True)
            self.banner.configure(bg="#161A20")
            self.label = tk.Label(self.banner, text="starting sweep",
                                  fg=TEST_COLOR, bg="#161A20",
                                  font=("Consolas", 11), padx=12, pady=6,
                                  anchor="w", justify="left")
            self.label.pack(fill="both")
            self.banner.geometry("+24+24")
            self.banner.update()
        except Exception as e:                       # noqa: BLE001
            print(f"[sweep] no overlay ({e}); continuing blind", flush=True)
            self.root = self.banner = self.label = None

    def status(self, text: str) -> None:
        if not self.label:
            return
        try:
            self.label.config(text=text)
            self.banner.update()
            if self.root.state() != "withdrawn":
                self.root.update()
        except Exception:                            # noqa: BLE001
            pass

    def show(self, rect) -> None:
        """rect is UIA BoundingRectangle: (left, top, WIDTH, HEIGHT).
        Reading the last two as right/bottom drew a tiny box in the corner
        (Kris, 2026-09-19) - the box must cover the whole control."""
        if not self.root:
            return
        try:
            left, top, width, height = [int(round(float(v))) for v in rect]
            w, h = max(width, 8), max(height, 8)
            self.root.geometry(f"{w}x{h}+{left}+{top}")
            self.root.deiconify()
            self.root.update()
        except Exception:                            # noqa: BLE001
            pass

    def hide(self) -> None:
        if not self.root:
            return
        try:
            self.root.withdraw()
            self.root.update()
        except Exception:                            # noqa: BLE001
            pass

    def close(self) -> None:
        for win in (self.banner, self.root):
            try:
                if win:
                    win.destroy()
            except Exception:                        # noqa: BLE001
                pass


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]


def last_input_tick() -> int:
    """Tick count of the last real keyboard/mouse input, system wide."""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return int(info.dwTime)
    return 0


def foreground_pid() -> int:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def beep(ok: bool = True) -> None:
    try:
        import winsound
        winsound.Beep(880 if ok else 320, 90)
    except Exception:                                # noqa: BLE001
        pass



class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                ("th32ProcessID", ctypes.c_ulong),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                ("th32ParentProcessID", ctypes.c_ulong),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                ("szExeFile", ctypes.c_char * 260)]


def process_tree(pid: int) -> set:
    """pid plus every descendant. A one-file PyInstaller app (VtoT) re-execs
    itself, so the window we want belongs to a CHILD of the process we
    started (2026-09-19: the sweep saw no window for 90s because of this)."""
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
    parents = {}
    if snap and snap != -1:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k32.Process32First(snap, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = k32.Process32Next(snap, ctypes.byref(entry))
        k32.CloseHandle(snap)
    tree, changed = {pid}, True
    while changed:
        changed = False
        for child, parent in parents.items():
            if parent in tree and child not in tree:
                tree.add(child)
                changed = True
    return tree


def top_level_windows(pid: int) -> set:
    """HWNDs of visible top-level windows belonging to the process TREE."""
    u32 = ctypes.windll.user32
    found = set()
    tree = process_tree(pid)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        wpid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value in tree and u32.IsWindowVisible(hwnd):
            found.add(int(hwnd))
        return True

    u32.EnumWindows(cb, None)
    return found


def window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def all_windows() -> dict:
    """Every visible top-level window on the desktop: hwnd -> pid.

    A control can open a window that is NOT the app's: the log opens in Notepad,
    a path opens in Explorer. Watching only the app's own process tree made
    those presses look like they did nothing at all, so "open the logs" reported
    success while nothing had opened (Kris, 2026-09-19).
    """
    u32 = ctypes.windll.user32
    found = {}

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if u32.IsWindowVisible(hwnd):
            wpid = ctypes.c_ulong()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            found[int(hwnd)] = int(wpid.value)
        return True

    u32.EnumWindows(cb, None)
    return found


def responsive(hwnd: int, timeout_ms: int = 800) -> bool:
    """True when the window is pumping messages: not hung, not mid-open.

    This is the question a fixed settle time was guessing the answer to.
    """
    u32 = ctypes.windll.user32
    try:
        if u32.IsHungAppWindow(ctypes.c_void_p(hwnd)):
            return False
        out = ctypes.c_ulong()
        ok = u32.SendMessageTimeoutW(ctypes.c_void_p(hwnd), 0x0000, 0, 0,
                                     0x0002, timeout_ms, ctypes.byref(out))
        return bool(ok)
    except Exception:                                # noqa: BLE001
        return True


def window_alive(hwnd: int) -> bool:
    u32 = ctypes.windll.user32
    h = ctypes.c_void_p(hwnd)
    return bool(u32.IsWindow(h) and u32.IsWindowVisible(h))


class Sweeper:
    def __init__(self, args):
        self.args = args
        self.hl = None
        self.last_control = "(none)"
        self.interference = 0
        self.stalls = 0
        self.done = 0
        self.main_hwnd = 0
        self.baseline_all: dict = {}
        # Our own status banner and highlight box are windows too, and the first
        # readiness run reported them as windows the app had opened.
        self.own_pid = os.getpid()
        self.open_popups: list = []
        self.events = []
        self.problems = 0
        self.log_pos = 0
        self.watch = Path(args.watch_log) if args.watch_log else None
        if self.watch and self.watch.exists():
            self.log_pos = self.watch.stat().st_size
        self.watch_dirs = [Path(d) for d in (args.watch_dir or "").split(";") if d]
        self._dir_state = self.dir_snapshot()

    def emit(self, **event) -> None:
        event["t"] = round(time.time() - self.t0, 2)
        self.events.append(event)
        line = json.dumps(event, ensure_ascii=False)
        print(line, flush=True)
        if self.args.out:
            with open(self.args.out, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def dir_snapshot(self) -> dict:
        """path -> size for every file under the watched directories."""
        snap = {}
        for d in self.watch_dirs:
            try:
                for f in d.rglob("*"):
                    if f.is_file():
                        snap[str(f)] = f.stat().st_size
            except OSError:
                continue
        return snap

    def dir_changes(self) -> list:
        """New or grown files since the last check, as evidence that a control
        (Save, Export, Copy to file) actually did something."""
        if not self.watch_dirs:
            return []
        now = self.dir_snapshot()
        out = []
        for path, size in now.items():
            was = self._dir_state.get(path)
            if was is None:
                out.append(f"created {path} ({size} B)")
            elif size != was:
                out.append(f"changed {path} ({was} -> {size} B)")
        self._dir_state = now
        return out

    def new_log_lines(self) -> list:
        if not self.watch or not self.watch.exists():
            return []
        try:
            with open(self.watch, encoding="utf-8", errors="replace") as fh:
                fh.seek(self.log_pos)
                text = fh.read()
                self.log_pos = fh.tell()
        except OSError:
            return []
        bad = ("ERROR", "Traceback", "Exception", "CRITICAL", "WARNING")
        return [l for l in text.splitlines() if any(b in l for b in bad)]

    def run(self) -> int:
        import comtypes
        import comtypes.client
        self.t0 = time.time()
        comtypes.CoInitialize()
        mod = comtypes.client.GetModule("UIAutomationCore.dll")
        self.mod = mod
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=mod.IUIAutomation)

        argv = ([sys.executable, self.args.app] if self.args.app.lower().endswith((".py", ".pyw"))
                else [self.args.app])
        proc = subprocess.Popen(argv, cwd=str(Path(self.args.app).resolve().parent))
        self.emit(event="app_started", pid=proc.pid, app=self.args.app)
        # A titled window is not a ready window: it can exist while the app is
        # still loading, and pressing into that is what produced the backlog.
        # Wait until it answers a message before treating it as the app.
        root, t_launch, announced = None, time.time(), 0.0
        while time.time() - t_launch < self.args.launch_wait:
            time.sleep(0.25)
            if proc.poll() is not None:
                self.emit(event="app_exited_early", code=proc.returncode)
                return 1
            for hwnd in sorted(top_level_windows(proc.pid)):
                if not window_title(hwnd) or not responsive(hwnd, 800):
                    continue
                root = uia.ElementFromHandle(ctypes.c_void_p(hwnd))
                self.main_hwnd = hwnd
                break
            if root is not None:
                break
            waited = time.time() - t_launch
            if waited - announced >= 2.0:
                announced = waited
                self.emit(event="still_waiting", control="app launch",
                          waited_s=round(waited, 1),
                          reason="no responsive titled window yet")
        if root is None:
            self.emit(event="no_window", detail=f"no responsive titled window in "
                      f"{self.args.launch_wait}s")
            proc.terminate()
            return 1
        startup = self.wait_until_ready(proc, "app launch")
        self.baseline_all = all_windows()
        self.emit(event="UI_SWEEP_READY", window=window_title(
            int(root.GetCurrentPropertyValue(PROP_HWND) or 0)),
            ready_after_s=startup["waited_s"],
            still_settling=startup["timed_out"])

        hl = Overlay(enabled=not self.args.no_highlight)
        self.hl = hl
        self.hands_off_notice(hl)
        if self.args.seed_text:
            self.seed(uia, root)
        baseline = top_level_windows(proc.pid)
        controls = self.collect(uia, mod, root)
        self.emit(event="controls_found", count=len(controls))
        clicked = 0
        try:
            for name, ctype, rect, el in controls[:self.args.max]:
                if self.args.only and not any(
                        o.lower() in name.lower() for o in self.args.only):
                    continue
                low = name.lower()
                if low in FRAME_CONTROLS:
                    self.emit(event="skipped", control=name, type=ctype,
                              reason="window frame control, not the app's own")
                    continue
                if not self.args.include_destructive and any(d in low for d in DESTRUCTIVE):
                    self.emit(event="skipped", control=name, type=ctype,
                              reason="destructive name; use --include-destructive")
                    continue
                # SHOW FIRST, THEN ACT: the half-second is for the human, and
                # the box stays up for the whole press so a slow one still
                # looks alive. The banner separates what the sweep is ABOUT to
                # do ("next:") from what it has actually OBSERVED ("seen:"). It
                # used to narrate intent only, which is why it claimed actions
                # the screen was not showing yet (Kris, 2026-09-19).
                self.hl = hl
                self.collect_late_dialogs(proc, baseline)
                hl.show(rect)
                hl.status(f"next: {name} ({ctype}) - pressing in "
                          f"{self.args.pre:.1f}s")
                if self.args.beep:
                    beep(True)
                time.sleep(self.args.pre)
                hl.status(f"sent the press to {name} - watching the screen")
                outcome = self.press(el, name, ctype, proc, baseline)
                self.last_control = name
                if ctype == "MenuItem":
                    clicked += self.walk_menu(uia, name, proc, baseline, hl)
                hl.hide()
                self.done += 1
                seen = outcome["seen"]
                hl.status(f"{self.done}/{min(len(controls), self.args.max)} "
                          f"pressed - seen: {name} -> {seen}"
                          + (" (PROBLEM)" if outcome["problem"] else ""))
                clicked += 1
                if outcome["problem"]:
                    self.problems += 1
                    if self.args.beep:
                        beep(False)
                if proc.poll() is not None:
                    self.emit(event="app_crashed", after=name, code=proc.returncode)
                    self.problems += 1
                    break
        finally:
            self.collect_late_dialogs(proc, baseline)
            hl.status("sweep finished - closing the app")
            time.sleep(self.args.linger)
            hl.close()
            self.kill_tree(proc)

        elapsed = time.time() - self.t0
        # State the sweep's structural blind spots, so a report cannot claim
        # "no gaps" without contradicting its own evidence.
        self.emit(event="sweep_limits", limits=[
            f"menus are opened and up to {self.args.menu_max} items in each are "
            f"pressed; anything past that, and submenus, are not reached",
            "controls that need a text selection or a specific mode first are "
            "pressed in whatever state the app happened to be in",
            "keyboard shortcuts, drag, scroll, right-click and typing are not "
            "exercised at all",
            "controls skipped by name (destructive) and window frame controls "
            "were never pressed",
            f"only the first {self.args.max} discovered controls were pressed",
            f"after each press the sweep waits for the app to answer and the "
            f"desktop to stop changing, up to {self.args.settle_max:.0f}s; a "
            f"control that was still working past that is logged as `stalled` "
            f"and anything reported after it may belong to unfinished work"])
        if self.interference:
            self.emit(event="interference_summary", presses_affected=self.interference,
                      detail=("A human or another program used the machine during "
                              "the sweep. Those presses are marked unreliable and "
                              "must be re-run on an idle machine before their "
                              "results mean anything."))
        if self.stalls:
            self.emit(event="stall_summary", stalls=self.stalls,
                      detail=("The app was still busy when the wait ceiling ran "
                              "out. Those presses, and the ones after them, "
                              "were observed in a UI that had not finished "
                              "changing: raise --settle-max and re-run before "
                              "trusting them."))
        self.emit(event="UI_SWEEP_COMPLETE", controls=len(controls),
                  clicked=clicked, problems=self.problems,
                  stalls=self.stalls,
                  unreliable_presses=self.interference)
        # pytest-shaped totals so the crew's existing gate can quote them
        print(f"\n{self.problems} failed, {clicked} passed in {elapsed:.2f}s",
              flush=True)
        return 1 if self.problems else 0

    def wait_until_ready(self, proc, label: str,
                         require_change: bool = False) -> dict:
        """Wait for the machine to be ready instead of guessing how long it
        takes. Three questions, asked until they all agree or --settle-max runs
        out:

          1. does the app's main window still pump messages?
          2. has the window list of the WHOLE DESKTOP stopped changing?
          3. have the watched folders stopped growing?

        --settle is the floor (a human needs a moment to see what happened) and
        --settle-max the ceiling. Any wait past --report-wait-after is announced
        in the banner and logged as `still_waiting`, so a slow action is visible
        rather than silently skipped.

        `require_change` is for a control whose whole job is to open something:
        a quiet desktop is not proof there, so the wait runs until something
        actually appears or the ceiling is reached. Without it, a log viewer that
        takes three seconds was declared missing after half a second.
        """
        t0 = time.time()
        quiet_for = max(0.2, self.args.quiet)
        max_s = max(self.args.settle, self.args.settle_max)
        own, foreign, wrote, foreign_pids = set(), {}, [], set()
        known = dict(self.baseline_all)
        last_change, announced, ok = t0, 0.0, True

        def result(timed_out: bool) -> dict:
            return {"own": sorted(own), "foreign": sorted(foreign.values()),
                    "foreign_pids": set(foreign_pids), "wrote": wrote,
                    "waited_s": round(time.time() - t0, 2),
                    "responsive": ok, "timed_out": timed_out}

        while True:
            now = time.time()
            fresh = {h: pid for h, pid in all_windows().items()
                     if h not in known and pid != self.own_pid}
            if fresh:
                known.update(fresh)
                last_change = now
                tree = process_tree(proc.pid)
                for hwnd, pid in fresh.items():
                    if pid in tree:
                        own.add(hwnd)
                    else:
                        title = window_title(hwnd) or f"hwnd{hwnd}"
                        foreign[hwnd] = f"{title} (pid {pid})"
                        foreign_pids.add(pid)
            new_files = self.dir_changes()
            if new_files:
                wrote.extend(new_files)
                last_change = now
            running = proc.poll() is None
            ok = (not running) or (not self.main_hwnd) or responsive(self.main_hwnd)
            waited = time.time() - t0
            got_evidence = bool(own or foreign or wrote)
            settled = ok and waited >= self.args.settle and (now - last_change) >= quiet_for
            if settled and (got_evidence or not require_change):
                return result(False)
            if waited >= max_s:
                return result(not settled)
            if waited - announced >= self.args.report_wait_after:
                announced = waited
                why = ("the window is not answering" if not ok
                       else "nothing has opened yet" if require_change
                       else "the screen is still changing")
                self.emit(event="still_waiting", control=label,
                          waited_s=round(waited, 1), reason=why)
                if self.hl:
                    self.hl.status(f"waiting after {label}: {why} "
                                   f"({waited:.0f}s of {max_s:.0f}s)")
            time.sleep(0.15)

    def wait_closed(self, hwnds, label: str, limit: float = 4.0) -> list:
        """Wait for windows we asked to close to actually be gone. Carrying on
        while a modal was still up is how a press landed in the wrong window."""
        t0 = time.time()
        still = [h for h in hwnds if window_alive(h)]
        while still and time.time() - t0 < limit:
            time.sleep(0.1)
            still = [h for h in hwnds if window_alive(h)]
        if still:
            self.emit(event="dialog_would_not_close", control=label,
                      dialogs=[window_title(h) or f"hwnd{h}" for h in still],
                      waited_s=round(time.time() - t0, 1),
                      detail="it stayed open after WM_CLOSE; later presses may "
                             "have gone to it instead of the app")
        self.baseline_all = all_windows()
        return still

    def seed(self, uia, root) -> None:
        """Put text in the app's first editable control before pressing
        anything. Kris: "there needs to be text in the field to test the save
        function" - Save, Copy and the formatting buttons are all no-ops on an
        empty document, so an empty sweep proves nothing about them."""
        walker = uia.ControlViewWalker
        stack, target = [(root, 0)], None
        while stack and target is None:
            el, depth = stack.pop()
            if depth > self.args.depth:
                continue
            try:
                child = walker.GetFirstChildElement(el)
            except Exception:                        # noqa: BLE001
                child = None
            while child:
                try:
                    ctype = child.GetCurrentPropertyValue(PROP_CTRL)
                    if ctype in (50004, 50030) and child.GetCurrentPropertyValue(PROP_ENABLED):
                        target = child
                        break
                except Exception:                    # noqa: BLE001
                    pass
                stack.append((child, depth + 1))
                try:
                    child = walker.GetNextSiblingElement(child)
                except Exception:                    # noqa: BLE001
                    break
        if target is None:
            self.emit(event="seed_failed", detail="no editable control found")
            return
        ok = False
        try:                                          # ValuePattern first
            raw = target.GetCurrentPattern(10002)     # UIA_ValuePatternId
            if raw:
                pattern = raw.QueryInterface(self.mod.IUIAutomationValuePattern)
                pattern.SetValue(self.args.seed_text)
                ok = True
        except Exception:                             # noqa: BLE001
            ok = False
        if not ok:                                    # documents: focus and type
            try:
                target.SetFocus()
                time.sleep(0.3)
                for ch in self.args.seed_text:
                    ctypes.windll.user32.keybd_event(0, ord(ch), 0x0004, 0)  # KEYEVENTF_UNICODE
                    ctypes.windll.user32.keybd_event(0, ord(ch), 0x0004 | 0x0002, 0)
                    time.sleep(0.01)
                ok = True
            except Exception as e:                    # noqa: BLE001
                self.emit(event="seed_failed", detail=f"{type(e).__name__}: {e}")
        if ok:
            self.emit(event="seeded_text", chars=len(self.args.seed_text),
                      via="ValuePattern" if not self.args.no_highlight else "typed")

    def hands_off_notice(self, hl) -> None:
        """Tell the human to keep their hands off, and give them a moment to
        finish what they were doing. The test drives the real keyboard focus and
        the real mouse target, so a human click lands in the middle of it."""
        seconds = max(0, int(self.args.hands_off))
        self.emit(event="hands_off_notice", seconds=seconds,
                  message="Do not use the keyboard or mouse while the sweep "
                          "runs: it drives the real window, and your clicks "
                          "will be attributed to the test.")
        if self.args.beep:
            beep(True)
        for left in range(seconds, 0, -1):
            hl.status(f"HANDS OFF - the sweep starts in {left}s. Do not use the "
                      f"keyboard or mouse; watch the orange boxes.")
            time.sleep(1.0)
        hl.status("sweep starting - hands off please")

    def walk_menu(self, uia, menu_name: str, proc, baseline: set, hl) -> int:
        """A menu bar item that only gets Invoke() does not open, so everything
        inside it stays untested (Kris, 2026-09-19). Open it, press what is
        inside, then close it. Returns how many items were pressed."""
        # A popup can take longer to appear than the press call takes to
        # return, and the sweep used to look exactly once and give up.
        t0 = time.time()
        popups = sorted(set(self.open_popups)
                        | (top_level_windows(proc.pid) - baseline))
        while not popups and time.time() - t0 < self.args.settle_max:
            hl.status(f"waiting for the {menu_name} menu to open "
                      f"({time.time() - t0:.0f}s)")
            time.sleep(0.2)
            popups = sorted(top_level_windows(proc.pid) - baseline)
        if not popups:
            self.emit(event="menu_did_not_open", menu=menu_name,
                      waited_s=round(time.time() - t0, 1),
                      detail="no popup window appeared within --settle-max, so "
                             "its items were not reached")
            return 0
        pressed = 0
        for hwnd in popups:
            try:
                root = uia.ElementFromHandle(ctypes.c_void_p(hwnd))
            except Exception as e:                   # noqa: BLE001
                self.emit(event="menu_unreadable", menu=menu_name,
                          detail=f"{type(e).__name__}: {e}")
                continue
            items = [c for c in self.collect(uia, self.mod, root)
                     if c[1] == "MenuItem"][:self.args.menu_max]
            self.emit(event="menu_opened", menu=menu_name, items=len(items),
                      names=[i[0] for i in items])
            for iname, ictype, irect, iel in items:
                low = iname.lower()
                if low in FRAME_CONTROLS:
                    continue
                if not self.args.include_destructive and any(d in low for d in DESTRUCTIVE):
                    self.emit(event="skipped", control=f"{menu_name} > {iname}",
                              type=ictype, reason="destructive name; use --include-destructive")
                    continue
                hl.show(irect)
                hl.status(f"next: {menu_name} > {iname} - pressing in "
                          f"{self.args.pre:.1f}s")
                if self.args.beep:
                    beep(True)
                time.sleep(self.args.pre)
                hl.status(f"sent the press to {menu_name} > {iname} - watching "
                          f"the screen")
                out = self.press(iel, f"{menu_name} > {iname}", ictype, proc,
                                 baseline)
                hl.hide()
                hl.status(f"seen: {menu_name} > {iname} -> {out['seen']}")
                pressed += 1
                # the menu closes when an item is chosen: reopen for the next
                if pressed < len(items):
                    self.reopen_menu(uia, menu_name, proc, baseline)
        for hwnd in popups:                     # close whatever is still open
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
        ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)          # ESC down
        ctypes.windll.user32.keybd_event(0x1B, 0, 0x0002, 0)     # ESC up
        self.open_popups = []
        self.wait_closed(popups, f"the {menu_name} menu", limit=2.0)
        return pressed

    def reopen_menu(self, uia, menu_name: str, proc, baseline: set) -> None:
        """Re-open a top-level menu by name after choosing an item closed it."""
        try:
            for hwnd in sorted(top_level_windows(proc.pid) & baseline):
                root = uia.ElementFromHandle(ctypes.c_void_p(hwnd))
                for name, ctype, rect, el in self.collect(uia, self.mod, root):
                    if ctype == "MenuItem" and name == menu_name:
                        self.press_pattern_only(el)
                        t0 = time.time()      # wait for it to actually open
                        while (time.time() - t0 < self.args.settle_max
                               and not (top_level_windows(proc.pid) - baseline)):
                            time.sleep(0.1)
                        return
        except Exception:                            # noqa: BLE001
            pass

    def press_pattern_only(self, el) -> None:
        for label, pid, iface_name, call in PATTERNS:
            try:
                raw = el.GetCurrentPattern(pid)
                if not raw:
                    continue
                pattern = raw.QueryInterface(getattr(self.mod, iface_name))
                getattr(pattern, call)()
                return
            except Exception:                        # noqa: BLE001
                continue

    def collect_late_dialogs(self, proc, baseline: set) -> None:
        """A modal dialog can take longer to appear than the settle window, and
        was then blamed on the NEXT control (2026-09-19). Anything still open
        when the next press begins belongs to the PREVIOUS one."""
        extra = sorted(top_level_windows(proc.pid) - baseline)
        if not extra:
            return
        titles = [window_title(h) or f"hwnd{h}" for h in extra]
        self.emit(event="late_dialog", opened_by=self.last_control,
                  dialogs=titles,
                  detail="appeared after the settle window; attributed to the "
                         "control pressed before it")
        for h in extra:
            ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE
        self.wait_closed(extra, self.last_control)

    def kill_tree(self, proc) -> None:
        """A one-file PyInstaller app re-execs itself, so terminating the
        process we started leaves the real app running (2026-09-19: it sat on
        Kris's screen after the sweep had finished). Kill the tree, then
        verify."""
        pids = sorted(process_tree(proc.pid))
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, check=False)
        time.sleep(0.6)
        alive = [pid for pid in pids if top_level_windows(pid)]
        self.emit(event="app_closed", pids=pids, still_alive=alive)
        if alive:
            self.emit(event="leftover_process", pids=alive,
                      detail="a window is still open after taskkill /T /F")

    def collect(self, uia, mod, root) -> list:
        """Depth-first walk of the control view, newest-first order preserved."""
        walker = uia.ControlViewWalker
        out, stack, seen = [], [(root, 0)], set()
        while stack:
            el, depth = stack.pop()
            if depth > self.args.depth:
                continue
            try:
                child = walker.GetFirstChildElement(el)
            except Exception:                        # noqa: BLE001
                child = None
            kids = []
            while child:
                kids.append(child)
                try:
                    child = walker.GetNextSiblingElement(child)
                except Exception:                    # noqa: BLE001
                    break
            for k in reversed(kids):
                stack.append((k, depth + 1))
                try:
                    ctype = k.GetCurrentPropertyValue(PROP_CTRL)
                    if ctype not in CLICKABLE:
                        continue
                    if not k.GetCurrentPropertyValue(PROP_ENABLED):
                        continue
                    if k.GetCurrentPropertyValue(PROP_OFFSCREEN):
                        continue
                    name = (k.GetCurrentPropertyValue(PROP_NAME) or "").strip()
                    aid = (k.GetCurrentPropertyValue(PROP_AID) or "").strip()
                    label = name or aid or f"<{CONTROL_NAMES.get(ctype, ctype)}>"
                    key = (label, ctype)
                    if key in seen:
                        continue
                    seen.add(key)
                    rect = k.GetCurrentPropertyValue(PROP_RECT) or (0, 0, 0, 0)
                    out.append((label, CONTROL_NAMES.get(ctype, str(ctype)),
                                rect, k))
                except Exception:                    # noqa: BLE001
                    continue
        return out

    def press(self, el, name: str, ctype: str, proc, baseline: set) -> dict:
        """Invoke a control and report what changed.

        The invoke itself can block for as long as a modal dialog is open, so a
        watcher thread narrates the wait and notices dialogs we would otherwise
        never see (our own polling code cannot run while we are blocked).
        """
        import threading
        stop = threading.Event()
        seen_windows: set = set()
        t_press = time.time()
        input_before = last_input_tick()
        fg_before = foreground_pid()
        tree = process_tree(proc.pid)

        def watch():
            while not stop.is_set():
                extra = top_level_windows(proc.pid) - baseline
                if extra:
                    seen_windows.update(extra)
                waited = time.time() - t_press
                if self.hl and waited > 1.5:
                    titles = ", ".join(sorted(window_title(h) or "?" for h in extra))
                    self.hl.status(f"pressing: {name} - waiting {waited:.0f}s"
                                   + (f" (dialog: {titles})" if titles else ""))
                stop.wait(0.25)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        method, err = None, None
        order = PATTERNS
        if ctype == "MenuItem":
            # A menu must open, not activate: ExpandCollapse first.
            order = tuple(sorted(PATTERNS, key=lambda p: p[0] != "ExpandCollapse"))
        for label, pid, iface_name, call in order:
            try:
                raw = el.GetCurrentPattern(pid)
            except Exception:                        # noqa: BLE001
                raw = None
            if not raw:
                continue
            try:
                iface = getattr(self.mod, iface_name)
                pattern = raw.QueryInterface(iface)
                getattr(pattern, call)()
                method = label
                break
            except Exception as e:                   # noqa: BLE001
                err = f"{label}: {type(e).__name__}: {e}"[:160]
        blocked_for = time.time() - t_press
        # READINESS, NOT A GUESS: wait until the app answers messages again and
        # the desktop stops changing. The old fixed settle window let the next
        # press fire while the previous window was still opening (the backlog
        # Kris saw), and it watched only the app's own windows, so a log opened
        # in Notepad counted as nothing happening.
        expected_open = any(k in name.lower() for k in OPENERS)
        ready = self.wait_until_ready(proc, name, require_change=expected_open)
        seen_windows.update(ready["own"])
        stop.set()
        watcher.join(timeout=1.0)
        # Did a human touch the machine while we pressed or waited? Our own UIA
        # calls are programmatic and never move this clock; only the seed typing
        # does, and that happens before the sweep loop. A window the press
        # itself opened in another program is not interference.
        human_input = last_input_tick() != input_before
        fg_after = foreground_pid()
        stole_focus = (fg_after not in process_tree(proc.pid)
                       and fg_after != fg_before
                       and fg_after not in ready["foreign_pids"])
        opened = sorted(seen_windows)
        foreign = ready["foreign"]
        log_lines = self.new_log_lines()
        wrote = ready["wrote"]      # did this control actually write anything?
        dialogs = [window_title(h) or f"hwnd{h}" for h in opened]
        is_menu = ctype == "MenuItem"
        if is_menu:
            # A menu popup must stay open: the walker reads its items next.
            self.open_popups = opened
        else:
            for h in opened:                         # close what we opened
                ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE
            if opened:
                self.wait_closed(opened, name)
            else:
                self.baseline_all = all_windows()
        nothing_happened = not opened and not foreign and not wrote
        problem = (method is None) or bool(log_lines)
        if expected_open and nothing_happened:
            problem = True
            self.emit(event="nothing_opened", control=name,
                      waited_s=ready["waited_s"],
                      detail=f"this control's name says it opens something, "
                             f"and after waiting {ready['waited_s']}s (up to "
                             f"--settle-max) nothing appeared anywhere on the "
                             f"desktop and no file was written. Kris watched exactly this: the sweep "
                             "moved past opening the logs and the logs never "
                             "opened, and the run reported no problem.")
        if ready["timed_out"]:
            self.stalls += 1
            self.emit(event="stalled", control=name, waited_s=ready["waited_s"],
                      detail="the app never went quiet and responsive inside "
                             "--settle-max, so whatever is reported after this "
                             "control may belong to work that was still "
                             "finishing")
        if foreign:
            self.emit(event="external_window", control=name, windows=foreign,
                      detail="a window outside the app's own process tree "
                             "appeared, so the app opened it in another program")
        slow = blocked_for > (self.args.pre + self.args.settle + 4)
        if human_input or stole_focus:
            self.interference += 1
            reason = ("keyboard or mouse input arrived" if human_input
                      else "another program took the foreground")
            self.emit(event="human_interference", control=name, reason=reason,
                      foreground_pid=fg_after, blocked_s=round(blocked_for, 1),
                      detail=("This result is UNRELIABLE: a human or another "
                              "program acted during the press, so what the app "
                              "did cannot be attributed to the test alone. "
                              "Re-run this control with the machine idle."))
            if self.hl:
                self.hl.status(f"HANDS OFF - input detected during {name}; "
                               f"that result is unreliable")
            if self.args.beep:
                beep(False)
        # What the banner and the report may claim: only what was OBSERVED.
        if dialogs:
            seen = "opened " + ", ".join(dialogs[:2])
        elif foreign:
            seen = "opened " + ", ".join(foreign[:2])
        elif wrote:
            seen = f"wrote {len(wrote)} file(s)"
        elif method is None:
            seen = "nothing: no control pattern responded"
        elif expected_open:
            seen = "NOTHING OPENED"
        else:
            seen = "no visible change"
        if ready["timed_out"]:
            seen += f" - still busy after {ready['waited_s']}s"
        self.emit(event="pressed", control=name, type=ctype, via=method,
                  error=err, dialogs=dialogs, external=foreign, seen=seen,
                  log=log_lines[:5],
                  menu_popups=(opened if ctype == "MenuItem" else []),
                  wrote=wrote[:5], problem=problem,
                  blocked_s=round(blocked_for, 1), waited_s=ready["waited_s"],
                  still_busy=ready["timed_out"], slow=slow,
                  unreliable=bool(human_input or stole_focus),
                  detail=("no control pattern responded" if method is None
                          else ("the call blocked far longer than the settle "
                                "budget: the app was busy, a modal dialog was "
                                "open, or a human was interacting" if slow
                                else None)))
        return {"problem": problem, "seen": seen}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("--out", default="")
    ap.add_argument("--pre", type=float, default=0.5,
                    help="seconds the orange highlight shows BEFORE the press")
    ap.add_argument("--settle", type=float, default=0.6,
                    help="the FLOOR: seconds to watch after every press, so a "
                         "human can see what happened")
    ap.add_argument("--settle-max", type=float, default=12.0,
                    help="the CEILING: how long to wait for the app to answer "
                         "messages again and for the desktop to stop changing "
                         "before moving on (a breach is logged as `stalled`)")
    ap.add_argument("--quiet", type=float, default=0.6,
                    help="the desktop must stop changing for this long before "
                         "an action counts as finished")
    ap.add_argument("--report-wait-after", type=float, default=2.0,
                    help="announce a wait in the banner and the log once it "
                         "passes this many seconds, so a stall is never silent")
    ap.add_argument("--launch-wait", type=float, default=40)
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--watch-log", default="")
    ap.add_argument("--beep", action="store_true")
    ap.add_argument("--no-highlight", action="store_true")
    ap.add_argument("--include-destructive", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--hands-off", type=float, default=5,
                    help="seconds of 'hands off' countdown before the first press")
    ap.add_argument("--menu-max", type=int, default=8,
                    help="items to press inside each opened menu")
    ap.add_argument("--watch-dir", default="",
                    help="semicolon-separated folders to watch for files the app "
                         "writes, so Save/Export can be judged by their effect")
    ap.add_argument("--linger", type=float, default=3.0,
                    help="seconds the finished banner stays on screen")
    ap.add_argument("--seed-text", default="",
                    help="type this into the app's first editable control before "
                         "sweeping, so Save/Copy/formatting act on real content")
    args = ap.parse_args()
    args.only = [o for o in args.only.split(",") if o]
    if args.out:
        Path(args.out).write_text("", encoding="utf-8")
    return Sweeper(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
