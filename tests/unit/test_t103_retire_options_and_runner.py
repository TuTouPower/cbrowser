"""t103 AC-001 / AC-002 / AC-005 unit contracts: removed fields, mute_audio, runner args."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from cbrowser.adapters.database.models import ProfileModel
from cbrowser.adapters.database.repository import (
    CONFIG_VERSION_FIELDS,
    INSTANT_FIELDS,
    METADATA_FIELDS,
)
from cbrowser.domain.models import (
    ProfileConfig,
    ProfileCreateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from cbrowser.fingerprint_verification.probe_collector import sanitize_config_summary
from cbrowser.runtime_agent.runner import BrowserRunner

REMOVED_FIELDS = (
    "humanize",
    "human_preset",
    "auto_launch",
    "allow_3p_cookies",
    "transparent_proxy",
    "portable_cookies",
    "launch_args",
)


def test_removed_fields_absent_across_orm_domain_classification_and_probe() -> None:
    orm_cols = set(ProfileModel.__table__.columns.keys())
    for field in REMOVED_FIELDS:
        assert field not in orm_cols, field
        assert field not in ProfileConfig.model_fields, field
        assert field not in ProfileCreateRequest.model_fields, field
        assert field not in ProfileUpdateRequest.model_fields, field
        assert field not in ProfileResponse.model_fields, field
        assert field not in CONFIG_VERSION_FIELDS, field
        assert field not in METADATA_FIELDS, field
        assert field not in INSTANT_FIELDS, field

    assert "mute_audio" in orm_cols
    assert "mute_audio" in CONFIG_VERSION_FIELDS
    default_cfg = ProfileConfig(name="Default")
    default_req = ProfileCreateRequest(name="Default")
    assert default_cfg.locale is None
    assert default_req.locale == "en-US"
    for model in (default_cfg, default_req):
        assert model.mute_audio is False
        assert model.clipboard_sync is True
        assert model.set_google_default is True
        assert model.restore_session is True
        assert model.capture_preview is True
        assert model.geoip is True
        assert model.timezone is None
        assert model.screen_width == 1920
        assert model.screen_height == 1080
        assert model.color_scheme == "light"
        assert model.extension_paths == []

    summary = sanitize_config_summary(ProfileConfig(name="Probe", mute_audio=True))
    for field in REMOVED_FIELDS:
        assert field not in summary
    assert summary["mute_audio"] is True

    # Legacy snapshot payloads carrying removed keys fail strict ProfileConfig validation
    for field in REMOVED_FIELDS:
        with pytest.raises(ValidationError):
            ProfileConfig(name="Bad", **{field: None if field != "launch_args" else []})


def test_launch_args_module_retired() -> None:
    import importlib.util

    assert importlib.util.find_spec("cbrowser.launch_args") is None


@pytest.mark.asyncio
async def test_runner_injects_mute_audio_and_restore_session_without_dead_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_calls: list[dict] = []

    async def fake_launch(**kwargs):
        captured_calls.append(kwargs)
        pid_file = Path(kwargs["user_data_dir"]).parent / "run" / "chrome.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("99999", encoding="utf-8")
        return SimpleNamespace(pages=[], new_page=AsyncMock())

    monkeypatch.setattr("cbrowser.runtime_agent.runner.launch_persistent_context_async", fake_launch)
    monkeypatch.setattr("cbrowser.runtime_agent.runner.seed_widevine_hint", lambda *_a, **_kw: None)
    monkeypatch.setattr("cbrowser.runtime_agent.runner.profile_font_dirs", lambda *_a, **_kw: [tmp_path / "f"])
    monkeypatch.setattr("cbrowser.runtime_agent.runner.prepare_profile_fontconfig", lambda *_a, **_kw: tmp_path / "fonts.conf")
    monkeypatch.setattr("cbrowser.runtime_agent.runner.verify_mounted_font_set", lambda **_kw: {"status": "verified"})

    for idx, (mute, restore) in enumerate([(True, True), (False, False)]):
        run_root = tmp_path / f"case_{idx}"
        (run_root / "fonts").mkdir(parents=True, exist_ok=True)
        snap = run_root / "snapshot.json"
        snap.write_text(
            json.dumps(
                {
                    "id": f"s{idx}",
                    "profile_id": "prof1",
                    "version": 1,
                    "config": {
                        "name": "RunTest",
                        "fingerprint_platform": "windows",
                        "font_set_id": "a" * 64,
                        "geoip": False,
                        "locale": "en-US",
                        "mute_audio": mute,
                        "restore_session": restore,
                        "set_google_default": False,
                        "extension_paths": ["/opt/ext1"] if idx == 0 else [],
                    },
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        runner = BrowserRunner(
            "prof1",
            f"inst_{idx}",
            snap,
            run_root / "run",
            run_root / "profile",
            events_dir=run_root / "events",
            engine_cache_dir=run_root / "engine",
        )
        chrome_bin = run_root / "engine" / "chrome"
        chrome_bin.parent.mkdir(parents=True, exist_ok=True)
        chrome_bin.write_text("", encoding="utf-8")
        monkeypatch.setattr(runner, "resolve_engine_binary", lambda cb=chrome_bin: cb)
        monkeypatch.setattr(runner, "setup_pulse", lambda rr=run_root: (rr / "pulse.sock", rr / "pulse.cookie"))
        monkeypatch.setattr(runner, "setup_display", lambda *_a, **_kw: None)
        (run_root / "run").mkdir(parents=True, exist_ok=True)
        (run_root / "run" / "chrome.pid").write_text("99999", encoding="utf-8")
        (run_root / "profile").mkdir(parents=True, exist_ok=True)
        (run_root / "profile" / "DevToolsActivePort").write_text("9222\n/devtools/browser/x\n", encoding="utf-8")
        monkeypatch.setattr(runner, "_resolve_browser_version", AsyncMock(return_value=("Chrome/146", "UA")))
        monkeypatch.setattr(runner, "_apply_native_color_scheme", lambda *_a, **_kw: None)
        monkeypatch.setattr(runner, "_configure_window", AsyncMock())

        class _FakeUrlopenResp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self) -> bytes:
                return b'{"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/x"}'

        monkeypatch.setattr("cbrowser.runtime_agent.runner.urllib.request.urlopen", lambda *_a, **_kw: _FakeUrlopenResp())
        monkeypatch.setattr(
            "cbrowser.runtime_agent.runner.CdpGuard",
            lambda _port: SimpleNamespace(start=AsyncMock(return_value=19222)),
        )
        monkeypatch.setattr("cbrowser.runtime_agent.runner.run_search_defaults_initialization", AsyncMock(return_value="disabled"))
        monkeypatch.setattr("cbrowser.runtime_agent.runner.asyncio.create_task", lambda coro: (coro.close() or None) if hasattr(coro, "close") else None)

        await runner.start()

    assert len(captured_calls) == 2
    on_call, off_call = captured_calls
    for call in captured_calls:
        assert "humanize" not in call
        assert "human_preset" not in call
        args = call["args"]
        assert "--fingerprint-allow-3p-cookies" not in args
        assert "--fingerprint-transparent-proxy" not in args
        assert "--fingerprint-portable-cookies" not in args

    assert "--mute-audio" in on_call["args"]
    assert "--restore-last-session" in on_call["args"]
    assert on_call["extension_paths"] == ["/opt/ext1"]

    assert "--mute-audio" not in off_call["args"]
    assert "--restore-last-session" not in off_call["args"]
    assert off_call["extension_paths"] is None
