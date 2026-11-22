"""t099: the bound Profile color scheme drives the native shell theme.

Spike s027 verified on the pinned engine that Chromium reads
``browser.theme.color_scheme2`` (1 = light, 2 = dark) from the
Profile's ``Preferences`` at launch, and that
``extensions.theme.system_theme`` must be 0 so a GTK system theme
cannot override the built-in theme. BrowserRunner merges both keys
into the Profile's Preferences before every launch, alongside the
existing web-preference pass-through of the same bound value.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.runtime_agent.runner import BrowserRunner


def _runner(tmp_path: Path, color_scheme: str = "dark") -> BrowserRunner:
    snapshot = ConfigVersionSnapshot(
        id="snap_t099",
        profile_id="p1",
        version=1,
        config=ProfileConfig(
            name="Profile One", color_scheme=color_scheme
        ).model_dump(),
        created_at="2026-11-21T00:00:00Z",
    )
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot.model_dump()), encoding="utf-8"
    )
    return BrowserRunner(
        profile_id="p1",
        runtime_instance_id="i1",
        config_snapshot_path=snapshot_path,
        run_dir=tmp_path / "run",
        user_data_dir=tmp_path / "user_data",
    )


def _preferences(runner: BrowserRunner) -> dict:
    path = runner.user_data_dir / "Default" / "Preferences"
    return json.loads(path.read_text(encoding="utf-8"))


def test_dark_scheme_writes_native_dark_and_builtin_theme(tmp_path):
    runner = _runner(tmp_path, "dark")
    runner._apply_native_color_scheme(
        runner.profile_config.color_scheme
    )
    preferences = _preferences(runner)
    assert preferences["browser"]["theme"]["color_scheme2"] == 2
    assert preferences["extensions"]["theme"]["system_theme"] == 0


def test_light_scheme_writes_native_light(tmp_path):
    runner = _runner(tmp_path, "light")
    runner._apply_native_color_scheme(
        runner.profile_config.color_scheme
    )
    preferences = _preferences(runner)
    assert preferences["browser"]["theme"]["color_scheme2"] == 1
    assert preferences["extensions"]["theme"]["system_theme"] == 0


def test_existing_preferences_are_preserved_and_scheme_switches(tmp_path):
    runner = _runner(tmp_path, "dark")
    path = runner.user_data_dir / "Default" / "Preferences"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "browser": {"window": {"placement": {"left": 10}}},
                "profile": {"name": "Person 1"},
            }
        ),
        encoding="utf-8",
    )
    runner._apply_native_color_scheme("dark")
    runner._apply_native_color_scheme("light")
    preferences = _preferences(runner)
    assert preferences["browser"]["theme"]["color_scheme2"] == 1
    assert preferences["browser"]["window"]["placement"]["left"] == 10
    assert preferences["profile"]["name"] == "Person 1"


def test_malformed_preferences_start_from_an_empty_document(tmp_path):
    runner = _runner(tmp_path, "dark")
    path = runner.user_data_dir / "Default" / "Preferences"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    runner._apply_native_color_scheme("dark")
    preferences = _preferences(runner)
    assert preferences["browser"]["theme"]["color_scheme2"] == 2

    path.write_text(
        json.dumps({"browser": "not-a-section"}), encoding="utf-8"
    )
    runner._apply_native_color_scheme("light")
    preferences = _preferences(runner)
    assert preferences["browser"]["theme"]["color_scheme2"] == 1
    assert preferences["extensions"]["theme"]["system_theme"] == 0


@pytest.mark.asyncio
async def test_start_writes_native_scheme_before_launch(tmp_path, monkeypatch):
    # Review t099_gen_f001: the Preferences write must happen inside
    # start(), before the persistent context launches, and from the
    # same bound value that reaches the web preference. The launch
    # seam is stubbed (font verification stubbed at the same seams
    # the egress/font suites use; the real verification has its own
    # suites) and reads the Preferences file at launch time.
    import os
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import cbrowser.runtime_agent.runner as runner_mod

    run_dir = tmp_path / "run"
    user_dir = tmp_path / "profile"
    run_dir.mkdir()
    user_dir.mkdir()
    snap_path = run_dir / "snapshot.json"
    cfg = ProfileConfig(name="p1", color_scheme="dark", geoip=False)
    snap = ConfigVersionSnapshot(
        id="snap_1",
        profile_id="prof_1",
        version=1,
        config=cfg.model_dump(),
        proxy_credential_revision=None,
        created_at="2026-11-21T00:00:00+00:00",
    )
    snap_path.write_text(snap.model_dump_json(), encoding="utf-8")
    runner = runner_mod.BrowserRunner(
        profile_id="prof_1",
        runtime_instance_id="inst_1",
        config_snapshot_path=snap_path,
        run_dir=run_dir,
        user_data_dir=user_dir,
        engine_build="146.0.7680.177.3",
    )
    wrapper = tmp_path / "chrome-wrapper"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runner, "resolve_engine_binary", lambda: wrapper)
    monkeypatch.setattr(
        runner, "setup_pulse", lambda: (run_dir / "pulse.sock", run_dir / "cookie")
    )
    monkeypatch.setattr(
        runner, "setup_display", lambda width, height: run_dir / "Xauth"
    )
    monkeypatch.setattr(
        runner,
        "_resolve_browser_version",
        AsyncMock(return_value=("Chrome/146", "UA")),
    )
    monkeypatch.setattr(runner, "_configure_window", AsyncMock())
    monkeypatch.setattr(
        runner_mod,
        "prepare_profile_fontconfig",
        lambda *_a, **_k: run_dir / "fonts.conf",
    )
    monkeypatch.setattr(
        runner_mod,
        "verify_mounted_font_set",
        lambda **_k: {"status": "verified", "failures": []},
    )
    monkeypatch.setattr(
        runner_mod,
        "run_search_defaults_initialization",
        AsyncMock(return_value=SimpleNamespace(state="applied", error_kind=None)),
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/1"}
            ).encode("utf-8")

    monkeypatch.setattr(
        runner_mod.urllib.request, "urlopen", lambda *_a, **_k: _Resp()
    )
    guard = SimpleNamespace(start=AsyncMock(return_value=9333), close=AsyncMock())
    monkeypatch.setattr(runner_mod, "CdpGuard", lambda *_a, **_k: guard)

    captured: dict = {}

    class _FakeContext:
        pages: list = []

        async def close(self) -> None:
            return None

    async def fake_launch(**kwargs):
        captured.update(kwargs)
        preferences_path = user_dir / "Default" / "Preferences"
        captured["preferences_at_launch"] = json.loads(
            preferences_path.read_text(encoding="utf-8")
        )
        (run_dir / "chrome.pid").write_text(str(os.getpid()), encoding="utf-8")
        (user_dir / "DevToolsActivePort").write_text(
            "9222\n/devtools/browser/1\n", encoding="utf-8"
        )
        return _FakeContext()

    monkeypatch.setattr(
        runner_mod, "launch_stealth_persistent_context", fake_launch
    )

    await runner.start()
    try:
        at_launch = captured["preferences_at_launch"]
        assert at_launch["browser"]["theme"]["color_scheme2"] == 2
        assert at_launch["extensions"]["theme"]["system_theme"] == 0
        # Same bound value reaches the web preference.
        assert captured["color_scheme"] == "dark"
    finally:
        await runner.stop()
