"""Read-only inventory and equivalence mapping for retiring launch_args (t103).

Scans both ``profiles`` rows and historical ``profile_config_versions``
snapshots (flat and ``{"config": ..., "proxy_credential_revision": ...}``
wrapped) before any schema or row rewrite, classifying every argument into:

- ``冗余`` (redundant Playwright defaults, ``--disable-translate``, and per user
  ruling ``--disable-blink-features=AutomationControlled``),
- ``等价映射`` (``--mute-audio`` -> ``mute_audio=True``, or valid ``zh-CN`` /
  ``en-US`` language flags following CloakBrowser SDK precedence), or
- ``需裁决`` (unknown/unmapped flags, out-of-enum or multi-language values
  without an overriding explicit ``locale``, or corrupted payloads), which block
  the migration fail-before-write with zero business writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

RETIRED_PROFILE_KEYS: tuple[str, ...] = (
    "humanize",
    "human_preset",
    "auto_launch",
    "allow_3p_cookies",
    "transparent_proxy",
    "portable_cookies",
    "launch_args",
)

# Current Playwright 1.64.1 desktop default switches present in the removed
# launch_args whitelist (17/22). Note: folding ``--disable-extensions`` here
# rests on the current default baseline prior to t104 managed extension policy.
PLAYWRIGHT_DEFAULT_FLAGS: frozenset[str] = frozenset(
    {
        "--disable-background-networking",
        "--disable-backgrounding-occluded-windows",
        "--disable-client-side-phishing-detection",
        "--disable-component-extensions-with-background-pages",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-default-browser-check",
        "--no-first-run",
        "--password-store=basic",
        "--use-mock-keychain",
    }
)

# Verified redundant flags: Playwright already disables Translate via
# --disable-features and the fixed 146 binary has no --disable-translate flag;
# user ruling (t103 spike 2026-11-22) classifies AutomationControlled as
# redundant based on navigator.webdriver=false parity in fixed 146.
REDUNDANT_LAUNCH_ARGS: frozenset[str] = PLAYWRIGHT_DEFAULT_FLAGS | frozenset(
    {
        "--disable-translate",
        "--disable-blink-features=AutomationControlled",
    }
)

VALID_LOCALES: frozenset[str] = frozenset({"zh-CN", "en-US"})
_LOCALE_TAG = r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*"
_LANG_RE = re.compile(rf"^{_LOCALE_TAG}$")
_ACCEPT_LANG_RE = re.compile(rf"^{_LOCALE_TAG}(?:,{_LOCALE_TAG})*$")
_CONTROL_CHARS = re.compile(r"[\r\n\x00-\x1f]")

_SINGLE_ACCEPT_EQUIVALENTS: dict[tuple[str, ...], str] = {
    ("en-US",): "en-US",
    ("en-US", "en"): "en-US",
    ("zh-CN",): "zh-CN",
    ("zh-CN", "zh"): "zh-CN",
}


@dataclass(frozen=True)
class LaunchArgDisposition:
    """Classification of a single raw launch argument."""

    arg: str
    category: str  # "冗余" | "等价映射" | "需裁决"
    action: str
    reason: str


@dataclass(frozen=True)
class ProfileRowInventory:
    """Read-only inventory & planned migration result for a profiles row."""

    profile_id: str
    raw_launch_args: list[str] | None
    locale_before: str | None
    geoip: bool
    dispositions: tuple[LaunchArgDisposition, ...]
    resolved_locale: str | None
    resolved_mute_audio: bool
    blocking_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnapshotInventory:
    """Read-only inventory & planned migration result for a config snapshot."""

    row_id: str
    profile_id: str
    version: int
    wrapped: bool
    raw_launch_args: list[str] | None
    locale_before: str | None
    geoip: bool
    dispositions: tuple[LaunchArgDisposition, ...]
    resolved_locale: str | None
    resolved_mute_audio: bool
    blocking_reasons: tuple[str, ...] = ()


@dataclass
class DatabaseLaunchArgsInventory:
    """Complete pre-migration inventory across all current rows and snapshots."""

    profiles: list[ProfileRowInventory] = field(default_factory=list)
    snapshots: list[SnapshotInventory] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)

    @property
    def profile_by_id(self) -> dict[str, ProfileRowInventory]:
        return {entry.profile_id: entry for entry in self.profiles}

    @property
    def snapshot_by_id(self) -> dict[str, SnapshotInventory]:
        return {entry.row_id: entry for entry in self.snapshots}


def _parse_args_value(
    raw_value: Any, scope_label: str
) -> tuple[list[str] | None, str | None]:
    if raw_value is None:
        return [], None
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return [], None
        try:
            parsed = json.loads(raw_value)
        except ValueError:
            return None, f"{scope_label}: corrupt launch_args JSON"
    else:
        parsed = raw_value
    if not isinstance(parsed, list):
        return None, f"{scope_label}: launch_args must be a JSON array"
    cleaned: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            return None, f"{scope_label}: launch_args entry is not a string"
        arg = item.strip()
        if not arg or _CONTROL_CHARS.search(arg):
            return None, f"{scope_label}: launch_args entry contains invalid characters"
        cleaned.append(arg)
    return cleaned, None


def _equivalent_accept_locale(accept_lang_value: str) -> str | None:
    parts = tuple(part.strip() for part in accept_lang_value.split(",") if part.strip())
    return _SINGLE_ACCEPT_EQUIVALENTS.get(parts)


def _redundant_reason(arg: str) -> str:
    if arg == "--disable-extensions":
        return "playwright_default_baseline_before_t104"
    if arg == "--disable-blink-features=AutomationControlled":
        return "user_ruling_automation_controlled_redundant"
    return "playwright_default_or_builtin_disabled"


def _scan_raw_launch_args(
    args: list[str],
    scope_label: str,
    *,
    existing_mute_audio: bool,
) -> tuple[list[LaunchArgDisposition], bool, list[str], list[str], list[str]]:
    dispositions: list[LaunchArgDisposition] = []
    mute_audio = bool(existing_mute_audio)
    lang_values: list[str] = []
    accept_lang_values: list[str] = []
    blocking: list[str] = []

    for arg in args:
        if arg == "--mute-audio":
            mute_audio = True
            dispositions.append(
                LaunchArgDisposition(
                    arg=arg,
                    category="等价映射",
                    action="migrate_to_mute_audio",
                    reason="mapped --mute-audio to mute_audio=True",
                )
            )
            continue
        if arg in REDUNDANT_LAUNCH_ARGS:
            dispositions.append(
                LaunchArgDisposition(
                    arg=arg,
                    category="冗余",
                    action="drop_redundant",
                    reason=_redundant_reason(arg),
                )
            )
            continue

        name, sep, value = arg.partition("=")
        if sep and name == "--lang" and _LANG_RE.fullmatch(value):
            lang_values.append(value)
            continue
        if sep and name == "--accept-lang" and _ACCEPT_LANG_RE.fullmatch(value):
            accept_lang_values.append(value)
            continue

        reason = f"unsupported or unmapped launch argument {arg!r}"
        dispositions.append(
            LaunchArgDisposition(
                arg=arg,
                category="需裁决",
                action="block_migration",
                reason=reason,
            )
        )
        blocking.append(f"{scope_label}: {reason}")

    return dispositions, mute_audio, lang_values, accept_lang_values, blocking


def _resolve_with_explicit_locale(
    lang_values: list[str],
    accept_lang_values: list[str],
) -> list[LaunchArgDisposition]:
    dispositions = [
        LaunchArgDisposition(
            arg=f"--lang={val}",
            category="等价映射",
            action="keep_explicit_locale",
            reason="shadowed_by_explicit_locale",
        )
        for val in lang_values
    ]
    dispositions.extend(
        LaunchArgDisposition(
            arg=f"--accept-lang={val}",
            category="等价映射",
            action="keep_explicit_locale",
            reason="shadowed_by_explicit_locale",
        )
        for val in accept_lang_values
    )
    return dispositions


def _resolve_accept_lang_series(
    accept_lang_values: list[str],
    scope_label: str,
) -> tuple[list[LaunchArgDisposition], str | None, list[str]]:
    dispositions: list[LaunchArgDisposition] = []
    accept_candidate: str | None = None
    blocking: list[str] = []

    for idx, val in enumerate(accept_lang_values):
        if idx < len(accept_lang_values) - 1:
            dispositions.append(
                LaunchArgDisposition(
                    arg=f"--accept-lang={val}",
                    category="等价映射",
                    action="shadowed_same_key_last_wins",
                    reason="overwritten_by_last_accept_lang_arg",
                )
            )
            continue

        eq = _equivalent_accept_locale(val)
        if eq is not None:
            accept_candidate = eq
            dispositions.append(
                LaunchArgDisposition(
                    arg=f"--accept-lang={val}",
                    category="等价映射",
                    action="promote_accept_lang_to_locale",
                    reason="single_language_accept_lang_equivalent",
                )
            )
        else:
            reason = f"--accept-lang={val!r} is multi-language or outside closed locale enum"
            dispositions.append(
                LaunchArgDisposition(
                    arg=f"--accept-lang={val}",
                    category="需裁决",
                    action="block_migration",
                    reason=reason,
                )
            )
            blocking.append(f"{scope_label}: {reason}")

    return dispositions, accept_candidate, blocking


def _resolve_lang_last_wins(
    lang_values: list[str],
    scope_label: str,
) -> tuple[list[LaunchArgDisposition], str | None, list[str]]:
    dispositions: list[LaunchArgDisposition] = []
    lang_candidate: str | None = None
    blocking: list[str] = []

    for idx, val in enumerate(lang_values):
        if idx < len(lang_values) - 1:
            dispositions.append(
                LaunchArgDisposition(
                    arg=f"--lang={val}",
                    category="等价映射",
                    action="shadowed_same_key_last_wins",
                    reason="overwritten_by_last_lang_arg",
                )
            )
            continue

        if val in VALID_LOCALES:
            lang_candidate = val
            dispositions.append(
                LaunchArgDisposition(
                    arg=f"--lang={val}",
                    category="等价映射",
                    action="promote_last_to_locale",
                    reason="same_key_last_lang_equivalent_to_locale",
                )
            )
        else:
            reason = f"last --lang={val!r} is outside closed locale enum zh-CN/en-US"
            dispositions.append(
                LaunchArgDisposition(
                    arg=f"--lang={val}",
                    category="需裁决",
                    action="block_migration",
                    reason=reason,
                )
            )
            blocking.append(f"{scope_label}: {reason}")

    return dispositions, lang_candidate, blocking


def _relabel_conflict_dispositions(
    dispositions: list[LaunchArgDisposition],
    reason: str,
) -> list[LaunchArgDisposition]:
    promoted_actions = frozenset(
        {
            "promote_first_to_locale",
            "promote_last_to_locale",
            "promote_accept_lang_to_locale",
        }
    )
    return [
        LaunchArgDisposition(
            arg=d.arg,
            category="需裁决",
            action="block_migration",
            reason=reason,
        )
        if d.action in promoted_actions
        else d
        for d in dispositions
    ]


def _resolve_geoip_out_of_enum_lang(
    lang_values: list[str],
    accept_lang_values: list[str],
    scope_label: str,
) -> tuple[list[LaunchArgDisposition], str | None, list[str]]:
    promoted = lang_values[0]
    dispositions = [
        LaunchArgDisposition(
            arg=f"--lang={val}",
            category="需裁决" if idx == 0 else "等价映射",
            action="block_migration" if idx == 0 else "drop_shadowed",
            reason=(
                f"geoip promotes first --lang={val!r} outside closed locale enum"
                if idx == 0
                else "shadowed_after_first_geoip_lang"
            ),
        )
        for idx, val in enumerate(lang_values)
    ]
    dispositions.extend(
        LaunchArgDisposition(
            arg=f"--accept-lang={val}",
            category="需裁决",
            action="block_migration",
            reason="present_with_unresolvable_geoip_lang",
        )
        for val in accept_lang_values
    )
    return (
        dispositions,
        None,
        [f"{scope_label}: geoip-promoted --lang={promoted!r} is outside zh-CN/en-US"],
    )


def _resolve_with_geoip(
    lang_values: list[str],
    accept_lang_values: list[str],
    scope_label: str,
) -> tuple[list[LaunchArgDisposition], str | None, list[str]]:
    # If only --accept-lang is passed while locale=None and geoip=True,
    # CloakBrowser keeps --accept-lang untouched; promote valid single-language
    # equivalents cleanly or block unmapped/multi-language values for adjudication.
    if not lang_values:
        return _resolve_accept_lang_series(accept_lang_values, scope_label)

    promoted = lang_values[0]
    if promoted not in VALID_LOCALES:
        return _resolve_geoip_out_of_enum_lang(
            lang_values, accept_lang_values, scope_label
        )

    dispositions = [
        LaunchArgDisposition(
            arg=f"--lang={val}",
            category="等价映射",
            action=(
                "promote_first_to_locale"
                if idx == 0
                else "shadowed_by_first_geoip_lang"
            ),
            reason=(
                "geoip_promotes_first_matching_lang"
                if idx == 0
                else "ignored_after_first_geoip_lang"
            ),
        )
        for idx, val in enumerate(lang_values)
    ]
    acc_disps, acc_candidate, acc_blocking = _resolve_accept_lang_series(
        accept_lang_values, scope_label
    )
    dispositions.extend(acc_disps)
    blocking = list(acc_blocking)
    if acc_candidate is not None and acc_candidate != promoted:
        conflict_reason = (
            f"conflicting geoip-promoted --lang={promoted} and --accept-lang equivalence {acc_candidate}"
        )
        dispositions = _relabel_conflict_dispositions(dispositions, conflict_reason)
        blocking.append(f"{scope_label}: {conflict_reason}")
        return dispositions, None, blocking
    if blocking:
        return dispositions, None, blocking
    return dispositions, promoted, []


def _resolve_without_geoip(
    lang_values: list[str],
    accept_lang_values: list[str],
    scope_label: str,
) -> tuple[list[LaunchArgDisposition], str | None, list[str]]:
    lang_disps, lang_candidate, lang_blocking = _resolve_lang_last_wins(
        lang_values, scope_label
    )
    acc_disps, accept_candidate, acc_blocking = _resolve_accept_lang_series(
        accept_lang_values, scope_label
    )
    dispositions = lang_disps + acc_disps
    blocking = lang_blocking + acc_blocking

    if lang_candidate and accept_candidate and lang_candidate != accept_candidate:
        conflict_reason = (
            f"conflicting --lang={lang_candidate} and --accept-lang equivalence {accept_candidate}"
        )
        dispositions = _relabel_conflict_dispositions(dispositions, conflict_reason)
        blocking.append(f"{scope_label}: {conflict_reason}")
        return dispositions, None, blocking

    if blocking:
        return dispositions, None, blocking

    resolved = accept_candidate if accept_candidate is not None else lang_candidate
    return dispositions, resolved, []


def _classify_launch_args_with_parsed(
    scope_label: str,
    *,
    locale: Any,
    geoip: Any,
    raw_launch_args: Any,
    existing_mute_audio: bool = False,
) -> tuple[list[str] | None, list[LaunchArgDisposition], str | None, bool, list[str]]:
    """Parse and classify raw launch_args using CloakBrowser SDK precedence rules."""
    if locale is not None and (not isinstance(locale, str) or locale not in VALID_LOCALES):
        return (
            None,
            [],
            None,
            existing_mute_audio,
            [f"{scope_label}: unsupported existing locale {locale!r}"],
        )

    args, parse_err = _parse_args_value(raw_launch_args, scope_label)
    if parse_err is not None or args is None:
        return (
            None,
            [],
            locale,
            existing_mute_audio,
            [parse_err or f"{scope_label}: invalid launch_args"],
        )

    dispositions, mute_audio, lang_values, accept_lang_values, blocking = (
        _scan_raw_launch_args(
            args,
            scope_label,
            existing_mute_audio=existing_mute_audio,
        )
    )
    geoip_enabled = bool(geoip) if geoip is not None else True

    if locale is not None:
        dispositions.extend(_resolve_with_explicit_locale(lang_values, accept_lang_values))
        resolved_locale: str | None = locale
    elif geoip_enabled:
        lang_disps, resolved_locale, lang_block = _resolve_with_geoip(
            lang_values, accept_lang_values, scope_label
        )
        dispositions.extend(lang_disps)
        blocking.extend(lang_block)
    else:
        lang_disps, resolved_locale, lang_block = _resolve_without_geoip(
            lang_values, accept_lang_values, scope_label
        )
        dispositions.extend(lang_disps)
        blocking.extend(lang_block)

    return args, dispositions, resolved_locale, mute_audio, blocking


def classify_launch_args_entry(
    scope_label: str,
    *,
    locale: Any,
    geoip: Any,
    raw_launch_args: Any,
    existing_mute_audio: bool = False,
) -> tuple[list[LaunchArgDisposition], str | None, bool, list[str]]:
    """Classify raw launch_args according to CloakBrowser SDK runtime rules."""
    _, dispositions, resolved_locale, mute_audio, blocking = (
        _classify_launch_args_with_parsed(
            scope_label,
            locale=locale,
            geoip=geoip,
            raw_launch_args=raw_launch_args,
            existing_mute_audio=existing_mute_audio,
        )
    )
    return dispositions, resolved_locale, mute_audio, blocking


def _unpack_raw_snapshot(
    raw: Any, row_id: str, profile_id: str, version: int
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, bool, str | None]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return (
            None,
            None,
            False,
            f"snapshot {row_id} (profile {profile_id} v{version}): corrupt snapshot JSON",
        )
    if not isinstance(data, dict):
        return (
            None,
            None,
            False,
            f"snapshot {row_id} (profile {profile_id} v{version}): snapshot JSON is not an object",
        )
    if "config" in data:
        cfg = data["config"]
        if not isinstance(cfg, dict):
            return (
                None,
                None,
                True,
                f"snapshot {row_id} (profile {profile_id} v{version}): nested config is not an object",
            )
        return data, cfg, True, None
    return data, data, False, None


def _exec_sql(conn: Any, sql: str, params: dict[str, Any] | None = None) -> Any:
    """Execute SQL cleanly across SQLAlchemy Connection and raw sqlite3 Connection."""
    if hasattr(conn, "dialect"):
        stmt = sa.text(sql)
        return conn.execute(stmt, params) if params is not None else conn.execute(stmt)
    return conn.execute(sql, params) if params is not None else conn.execute(sql)


def audit_launch_args_database(conn: Any) -> DatabaseLaunchArgsInventory:
    """Perform read-only inventory of profiles and historical snapshots."""
    inventory = DatabaseLaunchArgsInventory()

    profile_rows = _exec_sql(
        conn, "SELECT id, locale, geoip, launch_args FROM profiles ORDER BY id"
    ).fetchall()
    for profile_id, locale, geoip, raw_la in profile_rows:
        scope = f"profile {profile_id}"
        parsed_raw, dispositions, resolved_locale, resolved_mute, blocking = (
            _classify_launch_args_with_parsed(
                scope,
                locale=locale,
                geoip=geoip,
                raw_launch_args=raw_la,
            )
        )
        inventory.profiles.append(
            ProfileRowInventory(
                profile_id=profile_id,
                raw_launch_args=parsed_raw,
                locale_before=locale,
                geoip=bool(geoip),
                dispositions=tuple(dispositions),
                resolved_locale=resolved_locale,
                resolved_mute_audio=resolved_mute,
                blocking_reasons=tuple(blocking),
            )
        )
        inventory.blocking_errors.extend(blocking)

    snapshot_rows = _exec_sql(
        conn,
        "SELECT id, profile_id, version, snapshot "
        "FROM profile_config_versions ORDER BY profile_id, version",
    ).fetchall()
    for row_id, profile_id, version, raw_snap in snapshot_rows:
        scope = f"snapshot {row_id} (profile {profile_id} v{version})"
        _outer, cfg, wrapped, err = _unpack_raw_snapshot(
            raw_snap, row_id, profile_id, version
        )
        if err is not None or cfg is None:
            blocking = [err or f"{scope}: invalid snapshot"]
            inventory.snapshots.append(
                SnapshotInventory(
                    row_id=row_id,
                    profile_id=profile_id,
                    version=version,
                    wrapped=wrapped,
                    raw_launch_args=None,
                    locale_before=None,
                    geoip=True,
                    dispositions=(),
                    resolved_locale=None,
                    resolved_mute_audio=False,
                    blocking_reasons=tuple(blocking),
                )
            )
            inventory.blocking_errors.extend(blocking)
            continue

        parsed_raw, dispositions, resolved_locale, resolved_mute, blocking = (
            _classify_launch_args_with_parsed(
                scope,
                locale=cfg.get("locale"),
                geoip=cfg.get("geoip", True),
                raw_launch_args=cfg.get("launch_args"),
                existing_mute_audio=bool(cfg.get("mute_audio", False)),
            )
        )
        inventory.snapshots.append(
            SnapshotInventory(
                row_id=row_id,
                profile_id=profile_id,
                version=version,
                wrapped=wrapped,
                raw_launch_args=parsed_raw,
                locale_before=cfg.get("locale"),
                geoip=bool(cfg.get("geoip", True)),
                dispositions=tuple(dispositions),
                resolved_locale=resolved_locale,
                resolved_mute_audio=resolved_mute,
                blocking_reasons=tuple(blocking),
            )
        )
        inventory.blocking_errors.extend(blocking)

    return inventory


def transform_migrated_config_dict(
    cfg: dict[str, Any], *, scope_label: str = "config"
) -> tuple[dict[str, Any], list[str]]:
    """Transform a snapshot config dict idempotently to the post-t103 schema."""
    _, resolved_locale, resolved_mute, blocking = classify_launch_args_entry(
        scope_label,
        locale=cfg.get("locale"),
        geoip=cfg.get("geoip", True),
        raw_launch_args=cfg.get("launch_args"),
        existing_mute_audio=bool(cfg.get("mute_audio", False)),
    )
    if blocking:
        return dict(cfg), blocking

    rewritten = dict(cfg)
    for key in RETIRED_PROFILE_KEYS:
        rewritten.pop(key, None)
    rewritten["mute_audio"] = resolved_mute
    if "locale" in rewritten or resolved_locale is not None:
        rewritten["locale"] = resolved_locale
    return rewritten, []


def apply_launch_args_profile_updates(
    conn: Any, inventory: DatabaseLaunchArgsInventory
) -> None:
    """Apply resolved mute_audio and locale updates onto profiles rows."""
    for entry in inventory.profiles:
        if entry.resolved_mute_audio or entry.resolved_locale != entry.locale_before:
            _exec_sql(
                conn,
                "UPDATE profiles SET mute_audio = :mute, locale = :locale "
                "WHERE id = :pid",
                {
                    "mute": int(entry.resolved_mute_audio),
                    "locale": entry.resolved_locale,
                    "pid": entry.profile_id,
                },
            )


def rewrite_profile_snapshots_for_launch_args(conn: Any) -> None:
    """Rewrite flat and wrapped profile_config_versions snapshots atomically."""
    snap_rows = _exec_sql(
        conn, "SELECT id, profile_id, version, snapshot FROM profile_config_versions"
    ).fetchall()
    for row_id, profile_id, version, raw in snap_rows:
        outer, cfg, wrapped, err = _unpack_raw_snapshot(raw, row_id, profile_id, version)
        if err is not None or outer is None or cfg is None:
            raise RuntimeError(err or f"Corrupt snapshot {row_id}")
        migrated_cfg, blocking = transform_migrated_config_dict(
            cfg, scope_label=f"snapshot {row_id} (profile {profile_id} v{version})"
        )
        if blocking:
            raise RuntimeError("; ".join(blocking))
        if wrapped:
            for outer_key in RETIRED_PROFILE_KEYS:
                outer.pop(outer_key, None)
            outer["config"] = migrated_cfg
            new_payload: Any = outer
        else:
            new_payload = migrated_cfg

        rewritten = json.dumps(new_payload, ensure_ascii=False)
        if rewritten != raw:
            _exec_sql(
                conn,
                "UPDATE profile_config_versions SET snapshot = :snapshot "
                "WHERE id = :row_id",
                {"snapshot": rewritten, "row_id": row_id},
            )
