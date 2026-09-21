"""TTS bench: drive the crew's four modules with real devices and real speech.

Version 2, after the first one failed a human test. Kris: "No audio ever played,
there was no way to trigger audio... if I dont know how it will work when I use
the program or no sound is produced during a test of computer speech, this isnt
the most effective way to test for Human UX."

Three measured defects caused that, all fixed here:

1. **The window froze.** `SpVoice.Speak()` is synchronous and was called on the UI
   thread. On this machine one utterance took 9.17s on the stereo endpoint and
   109s on the hands-free one, so tkinter sat dead while nothing came out. Speech
   now runs on a worker thread with its own COM apartment, and a watchdog reports
   a device that does not answer instead of waiting for it.
2. **There was no way to just speak.** Audio needed type -> queue -> speak the
   queue. There is now a SPEAK THIS NOW button, and a test button per device.
3. **Silence looked identical to failure.** Every step is logged with its elapsed
   time, the engine is checked out loud at startup, and "prove audio" renders the
   speech to a WAV and reports the peak amplitude - so if the headset is silent for
   an operating-system reason, you can still see the engine working.

Measured on Kris's M98 headset, and it matters for VtoT itself: the two endpoints
of one Bluetooth headset fight over the profile. Alternating between them wedges
the device (stereo blocked for 25s and then returned a COM error). So the bench
picks ONE endpoint per session and warns before switching.

    python crew/runners/tts_bench.py
    python crew/runners/tts_bench.py --workspace <dir>
"""

from __future__ import annotations

import argparse
import queue as queuelib
import sys
import threading
import time
import traceback
from pathlib import Path

TEST_COLOR = "#FF7900"          # Kris: orange marks a test action, nothing else
BG = "#161A20"
PANEL = "#0E1116"
FG = "#E8EAED"
DIM = "#9AA4B2"
OK = "#5BD675"
BAD = "#FF6B6B"
WARN = "#FFC857"
SPEAK_TIMEOUT = 20.0            # a device that takes longer is reported, not waited on
# SAPI speak flags. Async is what makes a stop button possible at all: a
# synchronous Speak() holds the worker inside Windows with no way to interrupt it.
SVSF_ASYNC = 1
SVSF_PURGE = 2
POLL_MS = 100                   # how often the worker checks for a stop request


def load_modules(workspace: Path):
    """Import the crew's modules, reporting failures instead of crashing."""
    sys.path.insert(0, str(workspace))
    loaded, failed = {}, {}
    for name in ("devices", "verbalize", "chattiness", "speech_queue", "profiles"):
        try:
            loaded[name] = __import__(name)
        except Exception as exc:                            # noqa: BLE001
            failed[name] = f"{type(exc).__name__}: {exc}"
    return loaded, failed


class SpeechWorker(threading.Thread):
    """Windows speech on its own thread, so a slow device can never freeze the UI.

    Each job is (kind, text, device_index, volume). Results go back as dicts the
    UI polls: every job reports how long the device took, or that it never
    answered.
    """

    def __init__(self, results: queuelib.Queue):
        super().__init__(daemon=True)
        self.jobs: queuelib.Queue = queuelib.Queue()
        self.results = results
        self.stop_now = threading.Event()   # set by the UI, read between polls
        self.voice = None
        self.tokens = None
        self.error = ""

    # -- the thread ---------------------------------------------------------------
    def run(self) -> None:
        # The import lives inside the try: on Kris's first launch comtypes was
        # missing and the thread died with a console traceback while the window
        # sat there looking fine.
        try:
            import comtypes
            import comtypes.client as cc
            comtypes.CoInitialize()
            self.voice = cc.CreateObject("SAPI.SpVoice")
            self.tokens = self.voice.GetAudioOutputs()
            self.results.put({"event": "engine_ready",
                              "devices": self._devices()})
        except Exception as exc:                            # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            self.results.put({"event": "engine_failed", "detail": self.error,
                              "python": sys.executable})
            return
        while True:
            job = self.jobs.get()
            if job is None:
                break
            try:
                self._do(job)
            except Exception as exc:                        # noqa: BLE001
                self.results.put({"event": "error", "id": job.get("id"),
                                  "detail": f"{type(exc).__name__}: {exc}"})
        comtypes.CoUninitialize()

    def _devices(self):
        out = []
        for i in range(self.tokens.Count):
            try:
                out.append({"index": i, "name": self.tokens.Item(i).GetDescription()})
            except Exception:                               # noqa: BLE001
                out.append({"index": i, "name": f"(unreadable device {i})"})
        return out

    def _do(self, job: dict) -> None:
        kind = job["kind"]
        if kind == "speak":
            self._speak(job)
        elif kind == "render":
            self._render(job)

    def _speak(self, job: dict) -> None:
        """Speak asynchronously and poll, so a stop request can cut in mid-word."""
        index, text = job["index"], job["text"]
        self.results.put({"event": "speaking", "id": job.get("id"), "text": text,
                          "device": job.get("device", "")})
        t0 = time.time()
        if 0 <= index < self.tokens.Count:
            self.voice.AudioOutput = self.tokens.Item(index)
        self.voice.Volume = int(job.get("volume", 45))
        self.stop_now.clear()
        self.voice.Speak(text, SVSF_ASYNC)
        while True:
            if self.stop_now.is_set():
                # Discard whatever Windows still holds: this is what silences the
                # voice in the middle of a sentence.
                self.voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                self.stop_now.clear()
                self.results.put({"event": "stopped", "id": job.get("id"),
                                  "seconds": round(time.time() - t0, 2),
                                  "text": text})
                return
            if self.voice.WaitUntilDone(POLL_MS):
                break
        self.results.put({"event": "spoken", "id": job.get("id"),
                          "seconds": round(time.time() - t0, 2), "text": text})

    def request_stop(self) -> None:
        """Called from the UI thread: only sets a flag, never touches COM."""
        self.stop_now.set()

    def drop_queued(self) -> int:
        """Throw away jobs not yet started. The one being spoken is stopped by
        request_stop; these never begin."""
        dropped = 0
        while True:
            try:
                self.jobs.get_nowait()
                dropped += 1
            except queuelib.Empty:
                return dropped

    def _render(self, job: dict) -> None:
        """Speak into a WAV and report the peak amplitude: proof the engine makes
        audio even when a device is silent for reasons outside our control."""
        import struct
        import tempfile
        import wave

        import comtypes.client as cc
        out = Path(tempfile.gettempdir()) / "tts_bench_proof.wav"
        stream = cc.CreateObject("SAPI.SpFileStream")
        fmt = cc.CreateObject("SAPI.SpAudioFormat")
        fmt.Type = 22                       # 16kHz 16-bit mono
        stream.Format = fmt
        stream.Open(str(out), 3, False)
        self.voice.AudioOutputStream = stream
        try:
            self.voice.Speak(job["text"])
        finally:
            stream.Close()
            self.voice.AudioOutputStream = None
        with wave.open(str(out), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            count = handle.getnframes()
        samples = struct.unpack(f"<{len(frames) // 2}h", frames) if frames else ()
        peak = max((abs(s) for s in samples), default=0)
        self.results.put({"event": "rendered", "frames": count, "peak": peak,
                          "path": str(out), "seconds": round(count / 16000, 2)})

    # -- the UI side --------------------------------------------------------------
    def submit(self, **job) -> None:
        self.jobs.put(job)


class Bench:
    def __init__(self, workspace: Path):
        import tkinter as tk

        self.tk = tk
        self.workspace = workspace
        self.mods, self.failed = load_modules(workspace)
        self.results: queuelib.Queue = queuelib.Queue()
        self.worker = SpeechWorker(self.results)
        self.devices: list = []
        self.session_device = None      # locked once chosen: switching wedges BT
        self.pending_jobs = {}
        self.primed = None
        self.wedged = False
        self.job_seq = 0
        self.queue = None
        # The device memory, kept in a file beside the bench so it survives a
        # restart - which is the whole point of remembering anything.
        self.profiles_file = workspace.parent / "bench_profiles.json"
        self.profiles: list = self.load_profiles()
        self._reconnect_tries: dict = {}

        self.root = tk.Tk()
        self.root.title("TTS bench - the crew's modules, live")
        self.root.configure(bg=BG)
        self.root.geometry("1040x860")
        self._build()
        self.worker.start()
        self.root.after(80, self.drain)

    # -- widgets ------------------------------------------------------------------
    def _label(self, parent, text, **kw):
        opts = {"bg": BG, "fg": FG, "font": ("Segoe UI", 10)}
        opts.update(kw)
        return self.tk.Label(parent, text=text, **opts)

    def _panel(self, title: str):
        f = self.tk.LabelFrame(self.root, text=title, bg=BG, fg=TEST_COLOR,
                               font=("Segoe UI", 10, "bold"), bd=1,
                               labelanchor="nw", padx=8, pady=6)
        f.pack(fill="x", padx=10, pady=4)
        return f

    def _mono(self, parent, height: int):
        box = self.tk.Text(parent, height=height, bg=PANEL, fg=FG,
                           insertbackground=FG, font=("Consolas", 10),
                           relief="flat", wrap="none")
        box.pack(fill="x", pady=(4, 0))
        return box

    def _button(self, parent, text, cmd, big=False):
        b = self.tk.Button(parent, text=text, command=cmd, relief="flat",
                           bg=TEST_COLOR if big else "#22303C",
                           fg="#101318" if big else FG,
                           activebackground="#FFA24D" if big else "#2E4152",
                           font=("Segoe UI", 12, "bold") if big
                           else ("Segoe UI", 9), padx=12 if big else 8,
                           pady=8 if big else 2)
        b.pack(side="left", padx=(0, 8))
        return b

    def _build(self):
        head = self.tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=10, pady=(10, 0))
        self._label(head, "Every decision below is the crew's code deciding. The "
                          "window, the thread and the speech call are Claude's.",
                    font=("Segoe UI", 9, "italic"), fg=DIM).pack(anchor="w")
        self._label(head, f"modules: {workspace_label(self.workspace)}",
                    font=("Consolas", 8), fg=DIM).pack(anchor="w")
        for name, why in self.failed.items():
            self._label(head, f"{name} did not load: {why}", fg=BAD).pack(anchor="w")

        # --- the thing that was missing: an obvious way to make sound -----------
        act = self._panel("say something (start here)")
        self.text_in = self.tk.Entry(act, bg=PANEL, fg=FG, insertbackground=FG,
                                     font=("Consolas", 12), relief="flat")
        self.text_in.insert(0, "Don't stop, Kris - line two... (see notes)")
        self.text_in.pack(fill="x", pady=(2, 8))
        self.text_in.bind("<KeyRelease>", lambda _e: self.refresh_verbalize())
        row = self.tk.Frame(act, bg=BG)
        row.pack(fill="x")
        self._button(row, "SPEAK THIS NOW", self.speak_now, big=True)
        self._button(row, "check the engine out loud", self.self_check)
        self._button(row, "prove audio is produced", self.prove_audio)
        self._button(row, "run the whole demo", self.run_demo)
        self._button(row, "STOP SPEAKING", self.stop_speaking, big=True)
        self._button(row, "restart the speech engine", self.restart_engine)
        self.speaking = self._label(act, "", fg=WARN, font=("Segoe UI", 10, "bold"))
        self.speaking.pack(anchor="w", pady=(6, 0))

        dev = self._panel("devices.py (Hoss) - which endpoint, and at what volume")
        row = self.tk.Frame(dev, bg=BG)
        row.pack(fill="x")
        self.mic_live = self.tk.BooleanVar(value=False)
        self.allow_speakers = self.tk.BooleanVar(value=False)
        for text, var in (("microphone is live (dictating)", self.mic_live),
                          ("allow speakers this session", self.allow_speakers)):
            self.tk.Checkbutton(row, text=text, variable=var, bg=BG, fg=FG,
                                selectcolor=PANEL, activebackground=BG,
                                activeforeground=TEST_COLOR,
                                command=self.refresh_devices).pack(side="left",
                                                                   padx=(0, 16))
        self.volume = self.tk.IntVar(value=45)
        self.tk.Scale(row, from_=0, to=120, orient="horizontal",
                      variable=self.volume, bg=BG, fg=FG, troughcolor=PANEL,
                      highlightthickness=0, length=200, label="volume asked for",
                      command=lambda _v: self.refresh_devices()).pack(side="left")
        self.volume_note = self._label(row, "", fg=DIM)
        self.volume_note.pack(side="left", padx=8)
        pick = self.tk.Frame(dev, bg=BG)
        pick.pack(fill="x", pady=(6, 0))
        self._label(pick, "speak through:", fg=DIM).pack(side="left", padx=(0, 8))
        self.override = self.tk.IntVar(value=-1)
        self.override_row = self.tk.Frame(pick, bg=BG)
        self.override_row.pack(side="left")
        self.device_rows = self.tk.Frame(dev, bg=BG)
        self.device_rows.pack(fill="x", pady=(6, 0))
        self.devices_box = self._mono(dev, 5)

        v = self._panel("verbalize.py (Qwen) - what the voice actually says")
        self.verbalize_box = self._mono(v, 6)

        c = self._panel("chattiness.py (Nemotron) - what gets mentioned at all")
        row = self.tk.Frame(c, bg=BG)
        row.pack(fill="x")
        self.level = self.tk.StringVar(value="normal")
        for level in ("off", "brief", "normal", "full", "verbatim"):
            self.tk.Radiobutton(row, text=level, value=level, variable=self.level,
                                bg=BG, fg=FG, selectcolor=PANEL,
                                activebackground=BG, activeforeground=TEST_COLOR,
                                command=self.on_level_change).pack(side="left",
                                                                    padx=(0, 10))
        self.chattiness_box = self._mono(c, 6)

        q = self._panel("speech_queue.py (Barry) - order, alerts, and stopping")
        row = self.tk.Frame(q, bg=BG)
        row.pack(fill="x")
        for text, cmd in (("queue as normal", lambda: self.enqueue("normal")),
                          ("queue as ALERT", lambda: self.enqueue("alert")),
                          ("speak the queue", self.speak_queue),
                          ("cancel current", self.cancel_current),
                          ("cancel all", self.cancel_all)):
            self._button(row, text, cmd)
        self.queue_box = self._mono(q, 5)

        pr = self._panel("profiles.py (Qwen) - the headsets it remembers")
        row = self.tk.Frame(pr, bg=BG)
        row.pack(fill="x")
        self._label(row, "these survive closing the bench:", fg=DIM).pack(
            side="left", padx=(0, 10))
        for text, cmd in (("remember the chosen device", self.remember_chosen),
                          ("speak with its own volume", self.speak_with_profile),
                          ("forget it", self.forget_chosen),
                          ("what would reconnect", self.show_reconnect)):
            self._button(row, text, cmd)
        self.profile_rows = self.tk.Frame(pr, bg=BG)
        self.profile_rows.pack(fill="x", pady=(6, 0))
        self.profiles_box = self._mono(pr, 5)

        log = self._panel("what actually happened (with timings)")
        self.log_box = self._mono(log, 8)

        self.refresh_verbalize()
        self.refresh_chattiness()
        self.refresh_queue()
        self.refresh_profiles()
        self.log("bench starting; waiting for the Windows speech engine")

    # -- the device memory ---------------------------------------------------------
    def load_profiles(self) -> list:
        mod = self.mods.get("profiles")
        if mod is None or not self.profiles_file.is_file():
            return []
        try:
            return mod.load(self.profiles_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def save_profiles(self) -> None:
        mod = self.mods.get("profiles")
        if mod is None:
            return
        try:
            self.profiles_file.write_text(mod.dump(self.profiles), encoding="utf-8")
        except OSError as exc:
            self.log(f"could not save the profiles: {exc}", BAD)

    def refresh_profiles(self) -> None:
        """Redraw the remembered devices, each with its own volumes and lock."""
        mod = self.mods.get("profiles")
        for child in self.profile_rows.winfo_children():
            child.destroy()
        self.profiles_box.delete("1.0", "end")
        if mod is None:
            self.profiles_box.insert("end", "profiles.py did not load")
            return
        present = {d["name"] for d in self.devices}
        known = mod.known(self.profiles)
        if not known:
            self.profiles_box.insert(
                "end", "nothing remembered yet.\n\nPick a device above, press "
                "SPEAK THIS NOW so it is the one that spoke, then press "
                "'remember the chosen device'.")
            return
        for profile in known:
            row = self.tk.Frame(self.profile_rows, bg=BG)
            row.pack(fill="x", pady=1)
            here = profile["name"] in present
            self._label(row, ("here  " if here else "away  ") + profile["name"],
                        fg=OK if here else DIM,
                        font=("Consolas", 9)).pack(side="left")
            for purpose in ("speech", "alert"):
                var = self.tk.IntVar(value=mod.volume_for(profile, purpose))
                scale = self.tk.Scale(
                    row, from_=0, to=100, orient="horizontal", variable=var,
                    bg=BG, fg=FG, troughcolor=PANEL, highlightthickness=0,
                    length=130, label=purpose, font=("Segoe UI", 7),
                    state="disabled" if profile["locked"] else "normal",
                    command=lambda value, n=profile["name"], p=purpose:
                    self.set_profile_volume(n, p, value))
                scale.pack(side="left", padx=(8, 0))
            locked = self.tk.BooleanVar(value=bool(profile["locked"]))
            self.tk.Checkbutton(
                row, text="locked", variable=locked, bg=BG, fg=WARN,
                selectcolor=PANEL, activebackground=BG,
                activeforeground=TEST_COLOR, font=("Segoe UI", 8),
                command=lambda n=profile["name"], v=locked:
                self.lock_profile(n, v.get())).pack(side="left", padx=8)
        lines = [f"{p['name']}  {p['kind']}/{p['link']}  "
                 f"speech={mod.volume_for(p, 'speech')} "
                 f"alert={mod.volume_for(p, 'alert')}"
                 f"{'  LOCKED' if p['locked'] else ''}" for p in known]
        away = [p["name"] for p in mod.missing(self.profiles, self.devices)]
        if away:
            lines.append("")
            lines.append(f"not connected right now: {', '.join(away)}")
        lines.append(f"saved in {self.profiles_file}")
        self.profiles_box.insert("end", chr(10).join(lines))

    def remember_chosen(self) -> None:
        mod = self.mods.get("profiles")
        chosen = self.chosen()
        if mod is None or not chosen:
            self.log("nothing to remember: no device chosen", WARN)
            return
        self.profiles = mod.remember(self.profiles, chosen["name"], now=time.time())
        self.save_profiles()
        self.refresh_profiles()
        self.log(f"remembered {chosen['name']} - it now has its own volumes", OK)

    def forget_chosen(self) -> None:
        mod = self.mods.get("profiles")
        chosen = self.chosen()
        if mod is None or not chosen:
            return
        before = len(self.profiles)
        self.profiles = [p for p in self.profiles
                         if p.get("name") != chosen["name"]]
        if len(self.profiles) == before:
            self.log(f"{chosen['name']} was not remembered anyway", DIM)
            return
        self.save_profiles()
        self.refresh_profiles()
        self.log(f"forgot {chosen['name']}", DIM)

    def set_profile_volume(self, name: str, purpose: str, value) -> None:
        """Move one device's own volume - refused when the profile is locked."""
        mod = self.mods.get("profiles")
        if mod is None:
            return
        current = mod.find(self.profiles, name)
        if current is None:
            return
        updated = mod.set_volume(current, purpose, int(float(value)))
        if updated["volumes"] == current["volumes"]:
            return
        self.profiles = [updated if p.get("name") == name else p
                         for p in self.profiles]
        self.save_profiles()

    def lock_profile(self, name: str, locked: bool) -> None:
        mod = self.mods.get("profiles")
        if mod is None:
            return
        current = mod.find(self.profiles, name)
        if current is None:
            return
        self.profiles = [mod.set_lock(current, locked) if p.get("name") == name
                         else p for p in self.profiles]
        self.save_profiles()
        self.refresh_profiles()
        detail = ("its volumes now refuse every change" if locked
                  else "its volumes can move again")
        self.log(f"{name} is {'locked' if locked else 'unlocked'}: {detail}",
                 WARN if locked else OK)

    def speak_with_profile(self) -> None:
        """Speak through the chosen device at ITS volume, not the slider's.

        This is the difference a profile makes, and it has to be audible: a
        remembered headset set to 20 must sound quieter than the same sentence at
        the slider's 45.
        """
        mod = self.mods.get("profiles")
        chosen = self.chosen()
        if mod is None or not chosen:
            self.log("choose a device first", WARN)
            return
        profile = mod.find(self.profiles, chosen["name"])
        if profile is None:
            self.log(f"{chosen['name']} is not remembered yet - press 'remember "
                     f"the chosen device' first", WARN)
            return
        purpose = "alert" if self.level.get() == "verbatim" else "speech"
        volume = mod.volume_for(profile, purpose)
        text = self.text_in.get("1.0", "end").strip() or (
            f"This is {chosen['name']} at its own {purpose} volume, {volume}.")
        self.log(f"speaking at the profile's {purpose} volume {volume} "
                 f"(the slider says {self.volume.get()})", TEST_COLOR)
        self.speak_on(chosen["index"], chosen["name"], text, volume=volume)

    def show_reconnect(self) -> None:
        """What the app would do about a paired headset that is not here."""
        mod = self.mods.get("profiles")
        if mod is None:
            return
        away = mod.missing(self.profiles, self.devices)
        if not away:
            self.log("every remembered device is connected - nothing to reconnect",
                     OK)
            return
        now = time.time()
        for profile in away:
            plan = mod.reconnect_plan(profile, self.devices, now=now,
                                      last_attempt=self._reconnect_tries.get(
                                          profile["name"], 0.0))
            if plan["should_try"]:
                self._reconnect_tries[profile["name"]] = now
                self.log(f"WOULD ASK WINDOWS to reconnect {plan['name']} "
                         f"({plan['reason']})", TEST_COLOR)
            else:
                self.log(f"would NOT try {plan['name']}: {plan['reason']}"
                         + (f", {plan['wait_s']}s to wait" if plan["wait_s"]
                            else ""), DIM)

    # -- logging ------------------------------------------------------------------
    def log(self, text: str, colour: str = FG) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"{stamp}  {text}\n")
        self.log_box.see("end")
        if colour != FG:
            start = self.log_box.index("end-2l")
            tag = f"c{self.log_box.index('end')}"
            self.log_box.tag_add(tag, start, f"{start} lineend")
            self.log_box.tag_config(tag, foreground=colour)

    # -- devices ------------------------------------------------------------------
    def policy(self):
        d = self.mods.get("devices")
        if not d:
            return None
        return d.Policy(allow_speakers_this_session=self.allow_speakers.get(),
                        prefer_hands_free_while_live=True)

    def decision(self):
        d = self.mods.get("devices")
        if not d:
            return None
        return d.choose(self.devices, mic_live=self.mic_live.get(),
                        policy=self.policy())

    def refresh_devices(self, *_):
        if hasattr(self, "profile_rows"):
            self.root.after_idle(self.refresh_profiles)
        d = self.mods.get("devices")
        box = self.devices_box
        box.delete("1.0", "end")
        if not d:
            box.insert("end", "devices.py did not load")
            return
        asked = self.volume.get()
        allowed = d.clamp_volume(asked)
        self.volume_note.config(
            text=f"clamp_volume({asked}) = {allowed}"
                 + ("  (capped at your 65 ceiling)" if allowed != asked else ""),
            fg=WARN if allowed != asked else DIM)
        for dev in self.devices:
            box.insert("end", f"  [{dev['index']}] {dev['name']}"
                              f"   -> {d.classify(dev['name'])}\n")
        if not self.devices:
            box.insert("end", "  (no devices yet - the engine is still starting)\n")
        result = self.decision()
        if result:
            chosen = result["device"]["name"] if result["device"] else "NOTHING"
            box.insert("end", f"\n  choose() -> {chosen}\n  speak={result['speak']}"
                              f"   fallback tone={result['play_fallback_tone']}\n"
                              f"  reason: {result['reason']}\n")
            if (result["device"] and self.session_device is not None
                    and result["device"]["index"] != self.session_device):
                box.insert("end", "\n  WARNING: this would switch endpoint "
                                  "mid-session. Measured on this headset: "
                                  "alternating endpoints wedges it (25s block, "
                                  "then a COM error). The bench keeps speaking on "
                                  f"device {self.session_device}.\n")

    def build_override_choice(self):
        """Kris's headset has ONE speaker and ONE microphone: its "Stereo"
        endpoint is firmware copied from a two-ear headset. He chose hands-free,
        so that is what the bench defaults to - the policy's own preference is
        still shown, and still selectable, so the two can be compared."""
        for child in self.override_row.winfo_children():
            child.destroy()
        self.tk.Radiobutton(self.override_row, text="the policy's choice",
                            value=-1, variable=self.override, bg=BG, fg=FG,
                            selectcolor=PANEL, activebackground=BG,
                            activeforeground=TEST_COLOR,
                            command=self.refresh_devices).pack(side="left",
                                                               padx=(0, 10))
        working = None
        for dev in self.devices:
            low = dev["name"].lower()
            warn = ""
            if "hands-free" in low or "hands free" in low:
                # Measured: speaks once, then the second utterance never returns.
                warn = " (wedges after one)"
            if "stereo" in low:
                working = dev["index"]
            short = dev["name"].split("(")[0].strip()[:16]
            self.tk.Radiobutton(self.override_row,
                                text=f"[{dev['index']}] {short}{warn}",
                                value=dev["index"], variable=self.override, bg=BG,
                                fg=BAD if warn else FG, selectcolor=PANEL,
                                activebackground=BG, activeforeground=TEST_COLOR,
                                command=self.refresh_devices).pack(side="left",
                                                                    padx=(0, 10))
        if working is not None:
            self.override.set(working)

    def chosen(self):
        """(index, name) actually used: the override when set, else the policy."""
        forced = self.override.get()
        for dev in self.devices:
            if dev["index"] == forced:
                return dev["index"], dev["name"]
        result = self.decision()
        if result and result["device"]:
            return result["device"]["index"], result["device"]["name"]
        return -1, ""

    def build_device_buttons(self):
        for child in self.device_rows.winfo_children():
            child.destroy()
        self._label(self.device_rows, "test one device directly:",
                    fg=DIM).pack(side="left", padx=(0, 8))
        for dev in self.devices:
            short = dev["name"].split("(")[0].strip()[:18]
            self.tk.Button(self.device_rows, text=f"[{dev['index']}] {short}",
                           command=lambda i=dev["index"], n=dev["name"]:
                               self.speak_on(i, n, "This is device "
                                             f"{i}. One two three."),
                           bg="#22303C", fg=FG, relief="flat",
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))

    # -- speaking -----------------------------------------------------------------
    def prime(self, index: int = -1) -> None:
        """Open the endpoint at volume 0 before the human presses anything.

        Measured here: the first utterance on a cold Bluetooth endpoint costs
        about 3.7 extra seconds while Windows switches profile, and the start of
        the sentence is swallowed. Priming pays that cost where nobody is waiting.
        """
        if index < 0:
            index = self.chosen()[0]
            if index < 0:
                return
        self.primed = index
        self.log(f"waking device [{index}] quietly, so your first press is not the "
                 f"one that waits for Bluetooth", DIM)
        self.worker.submit(kind="speak", id=None, index=index, text="ready",
                           volume=0, device="(priming, silent)")

    def speak_on(self, index: int, name: str, text: str,
                 volume: int | None = None) -> None:
        """Speak on one endpoint. `volume` overrides the slider - that is how a
        remembered device speaks at its own volume rather than the bench's."""
        if self.wedged:
            self.log("the speech engine is stuck on the last utterance; press "
                     "'restart the speech engine' first", WARN)
            return
        d = self.mods.get("devices")
        asked = self.volume.get() if volume is None else volume
        volume = d.clamp_volume(asked) if d else asked
        if self.primed != index:
            self.prime(index)
        self.job_seq += 1
        job_id = self.job_seq
        self.pending_jobs[job_id] = {"started": time.time(), "name": name,
                                     "text": text}
        self.session_device = index
        self.speaking.config(text=f"speaking on {name} ... (a cold Bluetooth "
                                  f"endpoint can take several seconds)", fg=WARN)
        self.log(f"-> speak on [{index}] {name} at volume {volume}: {text!r}")
        self.worker.submit(kind="speak", id=job_id, index=index, text=text,
                           volume=volume, device=name)
        self.root.after(int(SPEAK_TIMEOUT * 1000), lambda: self.watchdog(job_id))

    def watchdog(self, job_id: int) -> None:
        job = self.pending_jobs.get(job_id)
        if not job:
            return
        waited = time.time() - job["started"]
        self.log(f"!! {job['name']} has not answered in {waited:.0f}s, so the "
                 f"speech engine is stuck inside Windows and nothing else can be "
                 f"spoken until it is restarted.", BAD)
        self.log("   measured on this headset: the Hands-Free endpoint speaks "
                 "ONCE and then never returns. The Stereo endpoint answers in "
                 "1.72s every time.", DIM)
        self.log("   press 'restart the speech engine', then pick a different "
                 "endpoint above.", WARN)
        self.speaking.config(text=f"{job['name']} is not responding "
                                 f"({waited:.0f}s) - restart the engine", fg=BAD)
        self.pending_jobs.pop(job_id, None)
        self.wedges = getattr(self, "wedges", 0) + 1
        if self.wedges > 1:
            self.log("   this is the second time. A Bluetooth headset has ONE "
                     "radio and carries ONE profile at a time, so a stuck "
                     "hands-free stream holds the device even for the endpoint "
                     "that works. Turn the headset off and on again, then restart "
                     "the engine.", BAD)
        self.wedged = True

    def stop_speaking(self) -> int:
        """Silence the voice now and drop anything queued behind it."""
        dropped = self.worker.drop_queued()
        self.worker.request_stop()
        self.pending_jobs.clear()
        self.log("stop: purging the current utterance"
                 + (f" and dropping {dropped} queued after it" if dropped else ""),
                 TEST_COLOR)
        self.speaking.config(text="stopped", fg=WARN)
        return dropped

    def restart_engine(self) -> None:
        """Abandon a wedged engine and start a fresh one.

        A COM call blocked inside a Bluetooth driver cannot be cancelled or
        killed from Python, so the old worker thread is left where it is (it is a
        daemon, and it dies with the process) and a new one takes over. That is
        the honest way to recover: say what was abandoned rather than pretend it
        was stopped.
        """
        if self.pending_jobs:
            self.log(f"abandoning {len(self.pending_jobs)} stuck job(s) - the old "
                     f"engine thread is still blocked inside Windows and will be "
                     f"left to die with this window", WARN)
        self.pending_jobs.clear()
        self.primed = None
        self.wedged = False
        self.results = queuelib.Queue()
        self.worker = SpeechWorker(self.results)
        self.manual_restart = True
        self.worker.start()
        self.log("started a fresh speech engine", TEST_COLOR)

    def speak_now(self):
        text = self.text_in.get().strip()
        if not text:
            self.log("nothing to say: the box is empty", WARN)
            return
        v = self.mods.get("verbalize")
        level = self.level.get()
        spoken = v.verbalize(text, level) if v else text
        if not spoken:
            self.log(f"verbalize.py returns nothing at level {level!r}, so there "
                     f"is nothing to say. That is the module working: switch the "
                     f"level above.", WARN)
            return
        result = self.decision()
        if not result or not result["speak"]:
            why = result["reason"] if result else "devices.py did not load"
            self.log(f"devices.py says speech is OFF: {why}. A real VtoT would "
                     f"play one tone here and stay silent.", WARN)
            return
        index, name = self.chosen()
        if index < 0:
            self.log("no device to speak through", BAD)
            return
        self.log(f"level {level}: {text!r} -> {spoken!r}")
        self.speak_on(index, name, spoken)

    def self_check(self):
        if not self.devices:
            self.log("the engine has not reported any devices yet", WARN)
            return
        index, name = self.chosen()
        if index < 0:
            index, name = self.devices[0]["index"], self.devices[0]["name"]
        self.log("engine check: you should hear a short sentence now", TEST_COLOR)
        self.speak_on(index, name, "Bench ready. If you can hear this, the crew's "
                                   "device policy and the speech engine are both "
                                   "working.")

    def prove_audio(self):
        self.log("rendering speech to a WAV file to prove the engine produces "
                 "audio, whatever the device does", TEST_COLOR)
        self.worker.submit(kind="render",
                           text="This is rendered proof that speech is produced.")

    def run_demo(self):
        """Walk every module and speak at each step, so a human sees the whole
        feature rather than four panels of parts."""
        d, v = self.mods.get("devices"), self.mods.get("verbalize")
        if not (d and v):
            self.log("the demo needs devices.py and verbalize.py", BAD)
            return
        result = self.decision()
        if not result or not result["speak"]:
            self.log(f"the demo cannot speak: {result['reason'] if result else '?'}",
                     WARN)
            return
        index, name = self.chosen()
        if index < 0:
            self.log("no device to speak through", BAD)
            return
        self.log("=== demo: four modules, one feature ===", TEST_COLOR)
        self.log(f"1. devices.py chose {name} because {result['reason']}")
        lines = [("normal", "Heading two applied."),
                 ("verbatim", "Don't stop, Kris - line two...")]
        for level, text in lines:
            said = v.verbalize(text, level)
            self.log(f"2. verbalize.py at {level}: {text!r} -> {said!r}")
            self.speak_on(index, name, said)
        self.log("3. queue an alert behind a long line and watch it overtake")
        sq = self.mods.get("speech_queue")
        if sq:
            self.queue = sq.SpeechQueue(level="normal")
            self.queue.enqueue("This is a long read back that you would not want "
                               "to wait for.")
            self.queue.enqueue("Headset lost.", "alert")
            self.refresh_queue()
            self.log("   queue order is now: "
                     + ", ".join(f"#{u.id} {u.priority}" for u in self.queue.pending))
            self.speak_queue()

    # -- panels -------------------------------------------------------------------
    def refresh_verbalize(self, *_):
        v = self.mods.get("verbalize")
        box = self.verbalize_box
        box.delete("1.0", "end")
        if not v:
            box.insert("end", "verbalize.py did not load")
            return
        text = self.text_in.get()
        for level in v.LEVELS:
            box.insert("end", f"  {level:9s} -> {v.verbalize(text, level)!r}\n")

    def refresh_chattiness(self, *_):
        c = self.mods.get("chattiness")
        box = self.chattiness_box
        box.delete("1.0", "end")
        if not c:
            box.insert("end", "chattiness.py did not load")
            return
        payloads = {"error": {"message": "microphone lost"},
                    "mode_change": {"mode": "command"},
                    "read_back": {"text": "the quick brown fox"},
                    "command_applied": {"command": "heading two"},
                    "block_created": {"block": "bullet list"},
                    "dictation_word": {"word": "Kris"},
                    "edit_applied": {"what": "color", "to": "colour"},
                    "punctuation": {"name": "comma"},
                    "whitespace": {"name": "line break"}}
        level = self.level.get()
        for event in c.EVENTS:
            mark = "SPEAKS  " if c.should_speak(event, level) else "silent  "
            box.insert("end", f"  {mark}{event:16s} "
                              f"{c.describe(event, payloads[event])!r}\n")

    def on_level_change(self):
        self.queue = None
        self.refresh_chattiness()
        self.refresh_verbalize()
        self.refresh_queue()

    def ensure_queue(self):
        sq = self.mods.get("speech_queue")
        if not sq:
            return None
        if self.queue is None:
            self.queue = sq.SpeechQueue(level=self.level.get())
        return self.queue

    def enqueue(self, priority: str):
        q = self.ensure_queue()
        if q is None:
            self.log("speech_queue.py did not load", BAD)
            return
        utt = q.enqueue(self.text_in.get(), priority)
        if utt is None:
            self.log(f"nothing queued: verbalize.py gives empty text at level "
                     f"{self.level.get()!r}", WARN)
        else:
            self.log(f"queued #{utt.id} as {priority}: {utt.text!r}")
        self.refresh_queue()

    def refresh_queue(self):
        box = self.queue_box
        box.delete("1.0", "end")
        q = self.queue
        if q is None:
            box.insert("end", "  (empty - a queue is built at the level chosen "
                              "above)\n")
            return
        box.insert("end", f"  current: {q.current.text!r}\n" if q.current
                   else "  current: nothing\n")
        for utt in q.pending:
            box.insert("end", f"  #{utt.id} {utt.priority:6s} {utt.text!r}\n")
        box.insert("end", f"\n  dropped={q.dropped}  cancelled={q.cancelled}\n")

    def speak_queue(self):
        q = self.queue
        if q is None or not q.pending:
            self.log("nothing queued to speak - use 'queue as normal' first, or "
                     "just press SPEAK THIS NOW", WARN)
            return
        result = self.decision()
        if not result or not result["speak"]:
            self.log(f"devices.py says speech is OFF: "
                     f"{result['reason'] if result else '?'}", WARN)
            return
        index, name = self.chosen()
        if index < 0:
            self.log("no device to speak through", BAD)
            return
        # The worker speaks these one at a time, in order, and a stop drops the
        # rest - which is what makes "cancel all" mean something while talking.
        count = 0
        while q.pending:
            utt = q.next_utterance()
            if utt is None:
                break
            self.speak_on(index, name, utt.text)
            count += 1
        self.log(f"handed {count} utterance(s) to the engine, in queue order")
        self.refresh_queue()

    def cancel_current(self):
        """The queue's own cancel, plus the audio - Kris: "cancel of queued items
        did not cancel the ones being spoken"."""
        self.stop_speaking()
        if self.queue is None:
            return
        self.log(f"cancel_current() -> {self.queue.cancel_current()}")
        self.refresh_queue()

    def cancel_all(self):
        self.stop_speaking()
        if self.queue is None:
            return
        self.log(f"cancel_all() cleared {self.queue.cancel_all()} queued "
                 f"utterance(s), and the voice was silenced")
        self.refresh_queue()

    # -- results from the worker --------------------------------------------------
    def drain(self):
        try:
            while True:
                msg = self.results.get_nowait()
                self.handle(msg)
        except queuelib.Empty:
            pass
        self.root.after(80, self.drain)

    def handle(self, msg: dict):
        event = msg.get("event")
        if event == "engine_ready":
            self.devices = msg["devices"]
            self.build_override_choice()
            self.build_device_buttons()
            self.refresh_devices()
            self.log(f"speech engine ready, {len(self.devices)} output device(s) "
                     f"visible", OK)
            self.prime()
            if getattr(self, "manual_restart", False):
                self.manual_restart = False
                self.log("engine replaced; press SPEAK THIS NOW when ready",
                         TEST_COLOR)
                return
            self.log("press SPEAK THIS NOW, or 'check the engine out loud'",
                     TEST_COLOR)
            self.self_check()
        elif event == "engine_failed":
            self.log(f"the Windows speech engine did not start: {msg['detail']}",
                     BAD)
            self.log(f"   this interpreter: {msg.get('python', sys.executable)}",
                     DIM)
            self.log("   if that says comtypes is missing, close this and run "
                     "Launch TTS bench.bat, which finds the right Python", WARN)
        elif event == "speaking":
            self.speaking.config(text=f"speaking on {msg.get('device', '')} ...",
                                 fg=WARN)
        elif event == "spoken":
            self.pending_jobs.pop(msg.get("id"), None)
            if msg.get("id") is None:          # a silent priming utterance
                self.log(f"   device awake ({msg['seconds']}s, silent)", DIM)
                return
            self.log(f"<- spoke in {msg['seconds']}s: {msg['text']!r}", OK)
            self.speaking.config(text=f"last utterance took {msg['seconds']}s",
                                 fg=OK)
        elif event == "stopped":
            self.pending_jobs.pop(msg.get("id"), None)
            self.log(f"<- stopped after {msg['seconds']}s (mid-utterance): "
                     f"{msg['text']!r}", WARN)
            self.speaking.config(text=f"stopped after {msg['seconds']}s", fg=WARN)
        elif event == "rendered":
            self.log(f"rendered {msg['frames']} frames "
                     f"({msg['seconds']}s of audio), peak amplitude "
                     f"{msg['peak']}/32767 -> "
                     + ("the engine IS producing audible speech"
                        if msg["peak"] > 500 else
                        "SILENT: the engine produced no sound"),
                     OK if msg["peak"] > 500 else BAD)
            self.log(f"   proof file: {msg['path']}", DIM)
        elif event == "error":
            self.pending_jobs.pop(msg.get("id"), None)
            self.log(f"speech error: {msg['detail']}", BAD)
            self.speaking.config(text="speech failed - see the log", fg=BAD)

    def run(self):
        self.root.mainloop()


def workspace_label(path: Path) -> str:
    return str(path)


def find_interpreter() -> str:
    """An interpreter on this machine that can actually talk to Windows speech.

    Kris launched the bench with `python`, which on his PATH is a uv-managed 3.11
    with no comtypes; the working one is 3.14. Rather than tell a tester to hunt
    for the right python, the bench finds one.
    """
    import glob
    import subprocess

    candidates = [
        r"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe",
    ]
    candidates += sorted(glob.glob(
        str(Path.home() / "AppData/Local/Programs/Python/Python3*/python.exe")),
        reverse=True)
    for exe in candidates:
        if not Path(exe).is_file() or Path(exe) == Path(sys.executable):
            continue
        try:
            ok = subprocess.run([exe, "-c", "import comtypes, tkinter"],
                                capture_output=True, timeout=30).returncode == 0
        except Exception:                                   # noqa: BLE001
            continue
        if ok:
            return exe
    return ""


def ensure_interpreter() -> None:
    """Re-run under an interpreter that has comtypes, once, and say so."""
    import importlib.util
    import os
    import subprocess

    if importlib.util.find_spec("comtypes") or os.environ.get("TTS_BENCH_REEXEC"):
        return
    exe = find_interpreter()
    if not exe:
        print("[bench] this Python has no comtypes, and no other Python on this "
              "machine does either.\n"
              "        Install it with:  py -3.14 -m pip install comtypes\n"
              "        The window will still open, without speech.", flush=True)
        return
    print(f"[bench] {sys.executable}\n"
          f"        has no comtypes, so it cannot reach Windows speech.\n"
          f"[bench] re-running under {exe}", flush=True)
    os.environ["TTS_BENCH_REEXEC"] = "1"
    raise SystemExit(subprocess.call([exe, str(Path(__file__).resolve()),
                                      *sys.argv[1:]]))


def main(argv=None) -> int:
    ensure_interpreter()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="")
    args = ap.parse_args(argv)
    if args.workspace:
        workspace = Path(args.workspace).resolve()
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from crew.config import load_config
        workspace = Path(load_config().state_home) / "outbox" / "workspace"
    if not workspace.is_dir():
        print(f"no modules at {workspace}")
        return 2
    print(f"[bench] loading the crew's modules from {workspace}", flush=True)
    try:
        Bench(workspace).run()
    except Exception:                                       # noqa: BLE001
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
