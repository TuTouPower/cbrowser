"""Explicit CloakBrowser Playwright launch helper with extension switch support (t104 / d055).

cloakbrowser 0.6.4 hardcodes ``IGNORE_DEFAULT_ARGS`` inside
``launch_persistent_context_async``, preventing callers from stripping Playwright's
``--disable-extensions`` switch for managed-extension or free-mode launches.
This module reuses CloakBrowser's binary/GeoIP/proxy/stealth arg helpers while
controlling ``ignore_default_args`` directly on Playwright's
``launch_persistent_context``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from cloakbrowser.browser import (
    IGNORE_DEFAULT_ARGS,
    _VIEWPORT_UNSET,
    _append_webrtc_exit_ip,
    _check_removed_kwargs,
    _drop_conflicting_viewport,
    _install_license_guard_async,
    _license_error,
    _maybe_warn_windows_fonts,
    _resolve_context_viewport,
    _resolve_proxy_config,
    _resolve_timezone,
    _resolve_webrtc_args,
    _warn_on_request_client_use,
    binary_supports_headless_no_viewport,
    binary_supports_maximized_window,
    build_args,
    build_launch_env,
    ensure_binary,
    maybe_resolve_geoip,
    mint_denial_file,
    persistent_seed_args,
    resolve_license_key,
    seed_widevine_hint,
)

LOGGER = logging.getLogger("cbrowser.runtime_agent.stealth_launch")

EXTENSION_IGNORE_DEFAULT_ARGS: tuple[str, ...] = (
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
)


def _build_launch_args_and_overrides(
    user_data_dir: str | os.PathLike[str],
    *,
    stealth_args: bool,
    resolved_args: list[str] | None,
    proxy_extra_args: list[str],
    timezone: str | None,
    locale: str | None,
    headless: bool,
    allow_extensions: bool,
    extension_paths: list[str] | None,
    viewport: Any,
    kwargs: dict[str, Any],
    license_key: str | None,
    browser_version: str | None,
    release_channel: str | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    effective_extensions = list(extension_paths) if (allow_extensions and extension_paths) else None
    chrome_args = build_args(
        stealth_args,
        (resolved_args or []) + proxy_extra_args,
        timezone=timezone,
        locale=locale,
        headless=headless,
        extension_paths=effective_extensions,
        start_maximized=(
            binary_supports_maximized_window(license_key, browser_version, release_channel)
            and viewport is _VIEWPORT_UNSET
            and "viewport" not in kwargs
            and "no_viewport" not in kwargs
        ),
    )
    _maybe_warn_windows_fonts(chrome_args)
    ignore_default_args = list(IGNORE_DEFAULT_ARGS)
    if allow_extensions:
        ignore_default_args.extend(EXTENSION_IGNORE_DEFAULT_ARGS)

    context_kwargs = dict(
        _resolve_context_viewport(
            viewport,
            headless,
            binary_supports_headless_no_viewport(
                license_key, browser_version, release_channel
            ),
        )
    )
    return chrome_args, ignore_default_args, context_kwargs


async def launch_stealth_persistent_context(
    user_data_dir: str | os.PathLike[str],
    *,
    headless: bool = False,
    proxy: str | dict[str, Any] | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: Any = _VIEWPORT_UNSET,
    locale: str | None = None,
    timezone: str | None = None,
    color_scheme: str | None = None,
    geoip: bool = False,
    allow_extensions: bool = False,
    extension_paths: list[str] | None = None,
    license_key: str | None = None,
    browser_version: str | None = None,
    release_channel: str | None = None,
    **kwargs: Any,
) -> Any:
    """Launch CloakBrowser persistently with explicit extension-mode flag control."""
    _check_removed_kwargs(kwargs)
    from playwright.async_api import async_playwright

    timezone = _resolve_timezone(timezone, kwargs)
    binary_path = await asyncio.to_thread(
        ensure_binary,
        license_key=license_key,
        browser_version=browser_version,
        release_channel=release_channel,
    )
    timezone, locale, exit_ip = await asyncio.to_thread(
        maybe_resolve_geoip, geoip, proxy, timezone, locale, args
    )
    proxy_kwargs, proxy_extra_args = _resolve_proxy_config(
        proxy, browser_version, license_key, release_channel
    )
    resolved_args = await asyncio.to_thread(_resolve_webrtc_args, args, proxy)
    resolved_args = _append_webrtc_exit_ip(resolved_args, exit_ip)
    resolved_args = persistent_seed_args(user_data_dir, stealth_args, resolved_args)

    chrome_args, ignore_default_args, context_kwargs = _build_launch_args_and_overrides(
        user_data_dir,
        stealth_args=stealth_args,
        resolved_args=resolved_args,
        proxy_extra_args=proxy_extra_args,
        timezone=timezone,
        locale=locale,
        headless=headless,
        allow_extensions=allow_extensions,
        extension_paths=extension_paths,
        viewport=viewport,
        kwargs=kwargs,
        license_key=license_key,
        browser_version=browser_version,
        release_channel=release_channel,
    )
    if user_agent:
        context_kwargs["user_agent"] = user_agent
    if color_scheme:
        context_kwargs["color_scheme"] = color_scheme
    context_kwargs.update(kwargs)
    _drop_conflicting_viewport(context_kwargs, kwargs)

    user_env = context_kwargs.pop("env", None)
    denial_path = mint_denial_file() if resolve_license_key(license_key) else None
    launch_env = build_launch_env(license_key, user_env=user_env, status_file=denial_path)
    if launch_env is not None:
        context_kwargs["env"] = launch_env

    seed_widevine_hint(user_data_dir, binary_path)

    pw = await async_playwright().start()
    try:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=os.fspath(user_data_dir),
            executable_path=binary_path,
            headless=headless,
            args=chrome_args,
            ignore_default_args=ignore_default_args,
            **proxy_kwargs,
            **context_kwargs,
        )
    except Exception as exc:
        lic = _license_error(exc)
        try:
            await pw.stop()
        except Exception as stop_exc:
            LOGGER.warning("Playwright cleanup after launch failure failed: %s", stop_exc)
        if lic is None:
            raise
        raise lic from exc

    original_close = context.close

    async def _close_with_cleanup(*, reason: str | None = None) -> None:
        try:
            if reason is None:
                await original_close()
            else:
                await original_close(reason=reason)
        finally:
            await pw.stop()

    context.close = _close_with_cleanup

    if proxy_extra_args:
        _warn_on_request_client_use(context._impl_obj)

    if denial_path:
        context._cloak_denial_path = denial_path
        _install_license_guard_async(context, denial_path)
        for pg in context.pages:
            _install_license_guard_async(pg, denial_path)

    return context
