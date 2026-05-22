"""Tests for atlas.cli.commands.doctor (focused on #32 macOS hybrid).

The existing doctor checks (gpu, compose, container health, etc) don't
have unit tests yet — they're integration-shaped and mostly tested by
real CI runs. These tests cover the new check_metal_native() added in
#32 because:
  1. It's pure-logic + filesystem (no Docker, no slow network)
  2. The failure modes are exactly the ones a Mac user will hit
     (binary missing, not executable, not listening) and we want
     fast feedback when they regress
  3. The Linux + skip path matters too — the check must be a no-op
     for non-Mac users
"""

import os
import sys
import tempfile

import pytest

from atlas.cli.commands import doctor


def test_check_metal_native_skips_on_non_darwin(monkeypatch):
    """On Linux + Windows the metal hybrid path doesn't apply at all.
    The check must return `skip` so it shows up as a no-op in doctor
    output, not as a phantom warn for users who'll never use it."""
    monkeypatch.setattr(sys, "platform", "linux")
    result = doctor._check_metal_native()
    assert result.name == "metal-native"
    assert result.status == "skip"
    assert "macOS" in result.message


def test_check_metal_native_fail_when_binary_missing(monkeypatch, tmp_path):
    """The most common Mac failure mode: setup script was never run,
    so the binary doesn't exist at $HOME/.atlas/macos/bin/. Must point
    the user at the setup script in the detail field."""
    monkeypatch.setattr(sys, "platform", "darwin")
    # Repoint $HOME to an empty tmpdir so the expected binary path
    # definitely doesn't exist. This is more robust than mocking
    # os.path.isfile because the production code also calls os.access.
    monkeypatch.setenv("HOME", str(tmp_path))
    result = doctor._check_metal_native()
    assert result.status == "fail"
    assert "atlas-setup-macos.sh" in result.message
    # The detail should include the expected path so the user knows
    # WHERE the check looked.
    assert "/.atlas/macos/bin/llama-server-metal" in result.detail


def test_check_metal_native_fail_when_binary_not_executable(monkeypatch, tmp_path):
    """Less common but possible: the binary exists but lacks +x (e.g.
    the user copied it from a USB drive with vfat, or rsync'd it
    without --perms). The check should flag this distinctly from
    'binary missing' so the recovery action is clear (re-run setup)."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    # Create the binary path but without +x.
    bin_dir = tmp_path / ".atlas" / "macos" / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "llama-server-metal"
    binary.write_text("#!/bin/sh\necho ok\n")
    binary.chmod(0o644)  # no execute bit

    result = doctor._check_metal_native()
    assert result.status == "fail"
    assert "not executable" in result.message
    assert "--rebuild" in result.message


def test_check_metal_native_warn_when_port_not_listening(monkeypatch, tmp_path):
    """Setup ran cleanly but the user hasn't started the native
    llama-server yet. Warn (not fail) — the binary is fine, they just
    need to run the launcher. Distinct from 'binary missing' because
    the recovery is different (run the launcher, not the setup script)."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_dir = tmp_path / ".atlas" / "macos" / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "llama-server-metal"
    # Tiny shell script that exits 0 for --help so the executability
    # probe in check_metal_native passes. Real binary would be the
    # llama-server output but for testing we just need exit 0.
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)

    # Mock _run so the `nc -z localhost 8080` probe reports nothing
    # listening (non-zero exit). The binary --help probe must still
    # return 0 — so we discriminate by argv.
    def fake_run(argv, *args, **kwargs):
        if argv[:2] == ["nc", "-z"]:
            return (1, "", "")  # port not listening
        return (0, "", "")      # binary --help works
    monkeypatch.setattr(doctor, "_run", fake_run)

    result = doctor._check_metal_native()
    assert result.status == "warn"
    assert "nothing listening on :8080" in result.message
    assert "atlas-llama-macos.sh" in result.message


def test_check_metal_native_pass_when_everything_healthy(monkeypatch, tmp_path):
    """Happy path: binary exists, is executable, runs --help cleanly,
    and the port is listening. This is the steady-state Mac user
    experience after setup + launcher are both done."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_dir = tmp_path / ".atlas" / "macos" / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "llama-server-metal"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)

    # All shell calls succeed: --help returns 0, nc -z returns 0
    # (port is listening).
    monkeypatch.setattr(doctor, "_run",
                        lambda argv, *args, **kwargs: (0, "", ""))

    result = doctor._check_metal_native()
    assert result.status == "pass"
    assert "listening on :8080" in result.message


def test_check_metal_native_fail_when_binary_crashes(monkeypatch, tmp_path):
    """Edge: corrupt build — binary exists, is executable, but exits
    nonzero on --help (e.g. dynamic linker failure, missing dylib).
    Less common than the 'missing' case but happens after interrupted
    cmake builds. Detail should preserve stderr for debugging."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_dir = tmp_path / ".atlas" / "macos" / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "llama-server-metal"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)

    # --help exits nonzero — simulates a corrupt binary.
    monkeypatch.setattr(doctor, "_run",
                        lambda argv, *args, **kwargs: (127, "", "dyld: Library not loaded"))

    result = doctor._check_metal_native()
    assert result.status == "fail"
    assert "won't run" in result.message
    assert "--rebuild" in result.message
    # The dynamic linker error should land in the detail so the user
    # can paste it into an issue without needing to re-run by hand.
    assert "dyld" in result.detail
