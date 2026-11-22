"""s029 spike: fixed 146.0.7680.177.3 free-mode entries, ID continuity & Bitwarden Passkey."""

from __future__ import annotations

import asyncio
import base64
import ctypes as c
import hashlib
import http.server
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cloakbrowser.browser import (
    _append_webrtc_exit_ip,
    _resolve_proxy_config,
    _resolve_webrtc_args,
    build_args,
    build_launch_env,
    maybe_resolve_geoip,
    persistent_seed_args,
    seed_widevine_hint,
)
from cloakbrowser.config import IGNORE_DEFAULT_ARGS
from playwright.async_api import async_playwright

from cbrowser.runtime_agent.event_storage import atomic_write_json
from cbrowser.runtime_agent.fontconfig import (
    FONT_SET_MOUNT_ROOT,
    prepare_profile_fontconfig,
    profile_font_dirs,
)
from cbrowser.runtime_agent.font_verification import verify_mounted_font_set
from cbrowser.runtime_agent.runner import BrowserRunner


BUILD = "146.0.7680.177.3"
WIDTH, HEIGHT = 1280, 800
ROOT = Path("/tmp/s029_probe")
EVIDENCE = Path("/evidence")
ASSETS = Path("/probe/assets")
FONT_SET_ID = os.environ["S029_FONT_SET_ID"]
HOST_PROXY = os.environ.get("S029_HOST_PROXY", "")


def capture_x11(runner: BrowserRunner, dest: Path) -> None:
    x11 = c.CDLL("libX11.so.6")
    cairo = c.CDLL("libcairo.so.2")
    ptr = c.c_void_p
    open_d = x11.XOpenDisplay
    open_d.restype = ptr
    open_d.argtypes = [c.c_char_p]
    root_w = x11.XDefaultRootWindow
    root_w.restype = c.c_ulong
    root_w.argtypes = [ptr]
    visual = x11.XDefaultVisual
    visual.restype = ptr
    visual.argtypes = [ptr, c.c_int]
    screen = x11.XDefaultScreen
    screen.restype = c.c_int
    screen.argtypes = [ptr]
    close_d = x11.XCloseDisplay
    close_d.restype = c.c_int
    close_d.argtypes = [ptr]
    mk_surf = cairo.cairo_xlib_surface_create
    mk_surf.restype = ptr
    mk_surf.argtypes = [ptr, c.c_ulong, ptr, c.c_int, c.c_int]
    wr_png = cairo.cairo_surface_write_to_png
    wr_png.restype = c.c_int
    wr_png.argtypes = [ptr, c.c_char_p]
    rm_surf = cairo.cairo_surface_destroy
    rm_surf.restype = None
    rm_surf.argtypes = [ptr]

    prev = os.environ.get("XAUTHORITY")
    os.environ["XAUTHORITY"] = str(runner.xauth_path)
    try:
        disp = open_d(runner.display.encode())
    finally:
        if prev is None:
            os.environ.pop("XAUTHORITY", None)
        else:
            os.environ["XAUTHORITY"] = prev
    if not disp:
        raise RuntimeError("XOpenDisplay failed")
    try:
        surf = mk_surf(disp, root_w(disp), visual(disp, screen(disp)), WIDTH, HEIGHT)
        try:
            wr_png(surf, os.fsencode(dest))
        finally:
            rm_surf(surf)
    finally:
        close_d(disp)


class RecordingHttpProxy:
    """Minimal CONNECT/HTTP recording proxy on 127.0.0.1."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self._srv: socket.socket | None = None
        self._stop = threading.Event()
        self.port = 0

    def start(self) -> int:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(32)
        self._srv.settimeout(0.2)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()
        return self.port

    def _loop(self) -> None:
        assert self._srv is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5.0)
            data = conn.recv(16384)
            first_line = data.split(b"\r\n", 1)[0].decode("latin1", "replace")
            self.requests.append(first_line)
            parts = first_line.split()
            if len(parts) < 2:
                return
            method, target = parts[0], parts[1]
            if method == "CONNECT":
                host, _, port_str = target.rpartition(":")
                if host in ("127.0.0.1", "localhost"):
                    up = socket.create_connection((host, int(port_str)), timeout=3.0)
                    conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    self._relay(conn, up)
                    return
                conn.sendall(b"HTTP/1.1 502 Blocked In Offline Probe\r\n\r\n")
            elif target.startswith("http://127.0.0.1:") or target.startswith("http://localhost:"):
                from urllib.parse import urlsplit
                u = urlsplit(target)
                host, port = u.hostname or "127.0.0.1", u.port or 80
                path_q = (u.path or "/") + (f"?{u.query}" if u.query else "")
                rest = data.split(b"\r\n", 1)[1] if b"\r\n" in data else b""
                rewritten = f"{method} {path_q} HTTP/1.1\r\n".encode("latin1") + rest
                up = socket.create_connection((host, port), timeout=3.0)
                up.sendall(rewritten)
                self._relay(conn, up)
            else:
                conn.sendall(b"HTTP/1.1 502 Blocked In Offline Probe\r\nContent-Length: 0\r\n\r\n")
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    @staticmethod
    def _relay(a: socket.socket, b: socket.socket) -> None:
        def pipe(src: socket.socket, dst: socket.socket) -> None:
            try:
                while True:
                    chunk = src.recv(4096)
                    if not chunk:
                        break
                    dst.sendall(chunk)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        t1 = threading.Thread(target=pipe, args=(a, b), daemon=True)
        t2 = threading.Thread(target=pipe, args=(b, a), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)
        try:
            b.close()
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        if self._srv is not None:
            self._srv.close()


class LocalTestWebServer:
    """Serves a plain HTML test page and a WebAuthn test harness over HTTP on localhost."""

    def __init__(self) -> None:
        self.port = 0
        self._httpd: http.server.ThreadingHTTPServer | None = None

    def start(self) -> int:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/webauthn":
                    body = """<!doctype html><html><head><meta charset="utf-8"><title>WebAuthn Probe</title></head>
<body>
<h1>WebAuthn Test</h1>
<button id="btn-create">Create Passkey</button>
<button id="btn-get">Get Passkey</button>
<pre id="out"></pre>
<script>
window.__runCreate = async () => {
  const challenge = new Uint8Array(32);
  crypto.getRandomValues(challenge);
  try {
    const res = await navigator.credentials.create({
      publicKey: {
        challenge,
        rp: { name: "Probe RP", id: location.hostname },
        user: { id: new Uint8Array([1,2,3,4]), name: "probe@example.com", displayName: "Probe User" },
        pubKeyCredParams: [{ alg: -7, type: "public-key" }],
        authenticatorSelection: { residentKey: "required", userVerification: "preferred" },
        timeout: 15000
      }
    });
    return { ok: true, id: res && res.id, type: res && res.type };
  } catch (e) {
    return { ok: false, name: e && e.name, message: String(e && e.message || e) };
  }
};
window.__runGet = async () => {
  const challenge = new Uint8Array(32);
  crypto.getRandomValues(challenge);
  try {
    const res = await navigator.credentials.get({
      publicKey: {
        challenge,
        rpId: location.hostname,
        userVerification: "preferred",
        timeout: 15000
      }
    });
    return { ok: true, id: res && res.id };
  } catch (e) {
    return { ok: false, name: e && e.name, message: String(e && e.message || e) };
  }
};
</script></body></html>""".encode()
                else:
                    body = b"<!doctype html><html><head><title>Ext Probe</title></head><body><h1>OK</h1></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self.port

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


class SpikeBrowserSession:
    """Runs Xvfb/Openbox/Pulse + Playwright Chromium identically to BrowserRunner, with configurable ignore_default_args."""

    def __init__(
        self,
        *,
        name: str,
        user_data_dir: Path,
        display: str = ":93",
        extension_paths: list[str] | None = None,
        suppress_disable_extensions: bool = False,
        suppress_disable_component_ext: bool = False,
        proxy_url: str | None = None,
    ) -> None:
        self.name = name
        self.run_dir = ROOT / "runs" / name
        shutil.rmtree(self.run_dir, ignore_errors=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir = user_data_dir
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.display = display
        self.extension_paths = extension_paths
        self.suppress_disable_extensions = suppress_disable_extensions
        self.suppress_disable_component_ext = suppress_disable_component_ext
        self.proxy_url = proxy_url

        os.environ["PULSE_RUNTIME_PATH"] = str(self.run_dir / "pulse")
        snap = self.run_dir / "snapshot.json"
        atomic_write_json(
            snap,
            {
                "id": f"snap_{name}",
                "profile_id": f"prof_{name}",
                "version": 1,
                "created_at": datetime.now().astimezone().isoformat(),
                "config": {
                    "name": name,
                    "locale": "en-US",
                    "color_scheme": "light",
                    "font_set_id": FONT_SET_ID,
                    "include_cjk_fonts": False,
                    "fingerprint_seed": 424242,
                    "screen_width": WIDTH,
                    "screen_height": HEIGHT,
                    "geoip": False,
                    "set_google_default": False,
                    "restore_session": False,
                },
            },
        )
        self.runner = BrowserRunner(
            profile_id=f"prof_{name}",
            runtime_instance_id=name,
            config_snapshot_path=snap,
            run_dir=self.run_dir,
            user_data_dir=self.user_data_dir,
            display=self.display,
            engine_build=BUILD,
        )
        self._pw = None
        self.context = None
        self.chrome_pid: int | None = None
        self.cmdline: list[str] = []

    async def start(self) -> None:
        self.runner.resolve_engine_binary()
        chrome_bin = Path(f"/data/engine-cache/chromium-{BUILD}/chrome")
        pulse_sock, pulse_cookie = self.runner.setup_pulse()
        self.runner.setup_display(WIDTH, HEIGHT)
        font_dirs = profile_font_dirs("windows", FONT_SET_ID)
        fontconfig_path = prepare_profile_fontconfig(
            self.run_dir, font_dirs, include_cjk_fonts=False, platform="windows"
        )
        assert fontconfig_path is not None
        verdict = await asyncio.to_thread(
            verify_mounted_font_set,
            mount_root=FONT_SET_MOUNT_ROOT,
            platform="windows",
            font_set_id=FONT_SET_ID,
            include_cjk_fonts=False,
            fontconfig_path=fontconfig_path,
        )
        assert verdict["status"] == "verified", verdict

        seed_widevine_hint(self.user_data_dir, str(chrome_bin))
        wrapper_path = self.run_dir / "chrome_wrapper.sh"
        pid_file = self.run_dir / "chrome.pid"
        wrapper_path.write_text(
            f'#!/bin/bash\n"{chrome_bin}" "$@" &\nCPID=$!\necho "$CPID" > "{pid_file}"\nwait $CPID\n',
            encoding="utf-8",
        )
        wrapper_path.chmod(0o755)
        browser_env = self.runner._browser_environment(
            pulse_sock, pulse_cookie, wrapper_path, fontconfig_path
        )

        extra_args: list[str] = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-position=0,0",
            f"--window-size={WIDTH},{HEIGHT}",
            "--force-device-scale-factor=1",
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
            "--autoplay-policy=no-user-gesture-required",
            "--fingerprint-platform=windows",
            "--fingerprint-noise=false",
            f"--fingerprint-screen-width={WIDTH}",
            f"--fingerprint-screen-height={HEIGHT}",
            "--disable-gtk-ime",
            "--fingerprint=424242",
        ]
        if self.proxy_url:
            extra_args.extend([
                "--disable-quic",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            ])

        prev_bin = os.environ.get("CLOAKBROWSER_BINARY_PATH")
        prev_cache = os.environ.get("CLOAKBROWSER_CACHE_DIR")
        os.environ["CLOAKBROWSER_BINARY_PATH"] = str(wrapper_path)
        os.environ["CLOAKBROWSER_CACHE_DIR"] = "/data/engine-cache"
        try:
            proxy_kwargs, proxy_extra_args = _resolve_proxy_config(self.proxy_url, BUILD, None, None)
            args = await asyncio.to_thread(_resolve_webrtc_args, extra_args, self.proxy_url)
            args = _append_webrtc_exit_ip(args, None)
            args = persistent_seed_args(self.user_data_dir, True, args)
            chrome_args = build_args(
                True,
                (args or []) + proxy_extra_args,
                timezone=None,
                locale="en-US",
                headless=False,
                extension_paths=self.extension_paths,
                start_maximized=False,
            )
            launch_env = build_launch_env(None, user_env=browser_env, status_file=None)
            ignore_args = list(IGNORE_DEFAULT_ARGS)
            if self.suppress_disable_extensions:
                ignore_args.append("--disable-extensions")
            if self.suppress_disable_component_ext:
                ignore_args.append("--disable-component-extensions-with-background-pages")

            self._pw = await async_playwright().start()
            self.context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=os.fspath(self.user_data_dir),
                executable_path=str(wrapper_path),
                headless=False,
                args=chrome_args,
                ignore_default_args=ignore_args,
                no_viewport=True,
                color_scheme="light",
                env=launch_env,
                **proxy_kwargs,
            )
        finally:
            if prev_bin is None:
                os.environ.pop("CLOAKBROWSER_BINARY_PATH", None)
            else:
                os.environ["CLOAKBROWSER_BINARY_PATH"] = prev_bin
            if prev_cache is None:
                os.environ.pop("CLOAKBROWSER_CACHE_DIR", None)
            else:
                os.environ["CLOAKBROWSER_CACHE_DIR"] = prev_cache
        for _ in range(50):
            if pid_file.exists() and pid_file.read_text().strip().isdigit():
                self.chrome_pid = int(pid_file.read_text().strip())
                break
            await asyncio.sleep(0.1)
        if self.chrome_pid:
            raw_cmd = Path(f"/proc/{self.chrome_pid}/cmdline").read_bytes()
            self.cmdline = [x for x in raw_cmd.decode("utf-8", "replace").split("\0") if x]

    async def stop(self) -> None:
        if self.context is not None:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        await self.runner.stop()


def copy_assets_to_tmp() -> dict[str, Path]:
    dst = ROOT / "mounts"
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    out = {}
    for folder in ("ext_with_key", "ext_no_key", "ext_free", "bitwarden_unpacked"):
        src = ASSETS / folder
        p1 = dst / "v1" / folder
        p2 = dst / "v2" / folder
        shutil.copytree(src, p1)
        shutil.copytree(src, p2)
        out[f"{folder}_v1"] = p1
        out[f"{folder}_v2"] = p2
    shutil.copy2(ASSETS / "bitwarden.crx", dst / "bitwarden.crx")
    shutil.copy2(ASSETS / "tiny_test.crx", dst / "tiny_test.crx")
    out["bitwarden_crx"] = dst / "bitwarden.crx"
    out["tiny_crx"] = dst / "tiny_test.crx"
    return out


async def inspect_extensions_page(page) -> dict[str, Any]:
    await page.goto("chrome://extensions", wait_until="domcontentloaded")
    await asyncio.sleep(0.8)
    return await page.evaluate(
        """() => {
  const mgr = document.querySelector('extensions-manager');
  if (!mgr || !mgr.shadowRoot) return { hasMgr: false, html: document.body.innerHTML.slice(0, 300) };
  const devToggle = mgr.shadowRoot.querySelector('extensions-toolbar')?.shadowRoot?.querySelector('cr-toggle#devMode');
  const itemList = mgr.shadowRoot.querySelector('extensions-item-list');
  const items = itemList && itemList.shadowRoot ? Array.from(itemList.shadowRoot.querySelectorAll('extensions-item')).map(el => ({
    id: el.getAttribute('id') || el.id,
    name: el.shadowRoot?.querySelector('#name')?.textContent?.trim(),
    version: el.shadowRoot?.querySelector('#version')?.textContent?.trim(),
  })) : [];
  return {
    hasMgr: true,
    devModeChecked: devToggle ? Boolean(devToggle.checked) : null,
    items,
  };
}"""
    )


async def test_spike1(paths: dict[str, Path], web_port: int) -> dict[str, Any]:
    results: dict[str, Any] = {}
    free_profile = ROOT / "profiles" / "free_profile"
    shutil.rmtree(free_profile, ignore_errors=True)

    # 1A: Default off state (--disable-extensions present, no load-extension)
    sess = SpikeBrowserSession(
        name="1a_off",
        user_data_dir=free_profile,
        display=":91",
        suppress_disable_extensions=False,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
        ext_state = await inspect_extensions_page(page)
        results["1a_off"] = {
            "has_disable_extensions_flag": "--disable-extensions" in sess.cmdline,
            "has_load_extension_flag": any(a.startswith("--load-extension") for a in sess.cmdline),
            "ext_page": ext_state,
            "service_workers": len(sess.context.service_workers),
        }
    finally:
        await sess.stop()

    # 1B-CWS: Test Candidate 1 (Chrome Web Store) in isolated proxy session
    cws_profile = ROOT / "profiles" / "cws_profile"
    shutil.rmtree(cws_profile, ignore_errors=True)
    cws_info: dict[str, Any] = {"skipped": not bool(HOST_PROXY)}
    if HOST_PROXY:
        sess = SpikeBrowserSession(
            name="1b_cws",
            user_data_dir=cws_profile,
            display=":91",
            suppress_disable_extensions=True,
            suppress_disable_component_ext=True,
            proxy_url=HOST_PROXY,
        )
        await sess.start()
        try:
            page = await sess.context.new_page()
            await page.goto(
                "https://chromewebstore.google.com/detail/bitwarden-password-manage/nngceckbapebfimnlniiiahkandclblb",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            await asyncio.sleep(3.5)
            cws_info = await page.evaluate(
                """() => {
  const txt = document.body ? document.body.innerText.slice(0, 1500) : '';
  const btns = Array.from(document.querySelectorAll('button')).map(b => ({
    text: (b.innerText || '').trim(),
    disabled: b.disabled,
    ariaDisabled: b.getAttribute('aria-disabled'),
  })).filter(b => /chrome|add|install|remove|扩展/i.test(b.text));
  return { url: location.href, hasSwitchToChrome: /Switch to Chrome/i.test(txt), buttons: btns, snippet: txt.slice(0, 500) };
}"""
            )
            capture_x11(sess.runner, EVIDENCE / "s1_cws.png")
        except Exception as exc:
            cws_info = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            await sess.stop()

    # 1B: Free mode without proxy (--disable-extensions removed) -> Candidate 2 (.crx) + Candidate 3 (Load unpacked)
    sess = SpikeBrowserSession(
        name="1b_free",
        user_data_dir=free_profile,
        display=":91",
        suppress_disable_extensions=True,
        suppress_disable_component_ext=True,
        proxy_url=None,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        ext_page_initial = await inspect_extensions_page(page)

        # Candidate 2: Local .crx file:// load AND DataTransfer drop on chrome://extensions (DevMode OFF & ON)
        crx_results: dict[str, Any] = {}
        for dev_mode in (False, True):
            await page.bring_to_front()
            await page.goto("chrome://extensions", wait_until="domcontentloaded")
            await asyncio.sleep(0.5)
            await page.evaluate(
                """(want) => {
  const mgr = document.querySelector('extensions-manager');
  const toggle = mgr.shadowRoot.querySelector('extensions-toolbar').shadowRoot.querySelector('cr-toggle#devMode');
  if (Boolean(toggle.checked) !== want) toggle.click();
}""",
                dev_mode,
            )
            await asyncio.sleep(0.4)
            nav_page = await sess.context.new_page()
            downloads: list[str] = []
            nav_page.on("download", lambda d: downloads.append(d.suggested_filename))
            nav_err = None
            try:
                await nav_page.goto(f"file://{paths['tiny_crx']}", timeout=5000)
            except Exception as exc:
                nav_err = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(0.8)
            await nav_page.close()
            await page.bring_to_front()
            after_nav = await inspect_extensions_page(page)

            # Try synthetic drag/drop onto chrome://extensions document using tiny_test.crx
            drop_res = await page.evaluate(
                """async (b64) => {
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const file = new File([raw], 'tiny_test.crx', { type: 'application/x-chrome-extension' });
  const dt = new DataTransfer();
  dt.items.add(file);
  document.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt }));
  document.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
  document.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  return true;
}""",
                base64.b64encode(paths["tiny_crx"].read_bytes()).decode(),
            )
            await asyncio.sleep(0.8)
            after_drop = await inspect_extensions_page(page)
            crx_results[f"dev_mode_{dev_mode}"] = {
                "file_nav_tiny_err": nav_err,
                "downloads": downloads,
                "after_tiny_nav": after_nav,
                "drop_res": drop_res,
                "after_drop": after_drop,
            }
        capture_x11(sess.runner, EVIDENCE / "s1_crx_drop.png")

        # Candidate 3: Developer Mode "Load unpacked" via GTK file chooser
        await page.bring_to_front()
        await page.goto("chrome://extensions", wait_until="domcontentloaded")
        await asyncio.sleep(0.5)
        await page.evaluate(
            """() => {
  const mgr = document.querySelector('extensions-manager');
  const toolbar = mgr.shadowRoot.querySelector('extensions-toolbar').shadowRoot;
  const toggle = toolbar.querySelector('cr-toggle#devMode');
  if (!toggle.checked) toggle.click();
}"""
        )
        await asyncio.sleep(0.5)
        btn_box = await page.evaluate(
            """() => {
  const mgr = document.querySelector('extensions-manager');
  const toolbar = mgr.shadowRoot.querySelector('extensions-toolbar').shadowRoot;
  const btn = toolbar.querySelector('#loadUnpacked');
  if (!btn) return null;
  const r = btn.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
}"""
        )
        unpacked_ok: dict[str, Any] = {"btn_box": btn_box}
        if btn_box and btn_box["w"] > 0:
            await page.bring_to_front()
            await page.mouse.click(btn_box["x"], btn_box["y"])
            await asyncio.sleep(1.2)
            xenv = dict(os.environ, DISPLAY=sess.display, XAUTHORITY=str(sess.runner.xauth_path))
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+l"], env=xenv, check=True)
            await asyncio.sleep(0.3)
            subprocess.run(["xdotool", "type", "--delay", "10", str(paths["ext_free_v1"])], env=xenv, check=True)
            await asyncio.sleep(0.3)
            subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"], env=xenv, check=True)
            await asyncio.sleep(1.0)
            after_first_enter = await inspect_extensions_page(page)
            if not after_first_enter.get("items"):
                # In GTK3 folder chooser, Return inside location bar navigates into folder; Alt+O presses Open!
                subprocess.run(["xdotool", "key", "--clearmodifiers", "alt+o"], env=xenv, check=True)
                await asyncio.sleep(1.0)
                after_first_enter = await inspect_extensions_page(page)
            await page.bring_to_front()
            capture_x11(sess.runner, EVIDENCE / "s1_load_unpacked_mgr.png")
            await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
            await asyncio.sleep(0.5)
            attr = await page.evaluate("document.documentElement.getAttribute('data-ext-free')")
            unpacked_ok.update({
                "after_load": after_first_enter,
                "content_script_attr": attr,
                "service_workers": [sw.url for sw in sess.context.service_workers],
            })
            capture_x11(sess.runner, EVIDENCE / "s1_load_unpacked.png")

        results["1b_free"] = {
            "has_disable_extensions_flag": "--disable-extensions" in sess.cmdline,
            "has_disable_component_flag": "--disable-component-extensions-with-background-pages" in sess.cmdline,
            "has_load_extension_flag": any(a.startswith("--load-extension") for a in sess.cmdline),
            "ext_page_initial": ext_page_initial,
            "candidate1_cws": cws_info,
            "candidate2_crx": crx_results,
            "candidate3_load_unpacked": unpacked_ok,
        }
    finally:
        await sess.stop()

    # 1C: Relaunch same free_profile WITHOUT --load-extension -> check free-mode persistence
    sess = SpikeBrowserSession(
        name="1c_free_persist",
        user_data_dir=free_profile,
        display=":91",
        suppress_disable_extensions=True,
        suppress_disable_component_ext=True,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        ext_state = await inspect_extensions_page(page)
        await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
        await asyncio.sleep(0.5)
        attr = await page.evaluate("document.documentElement.getAttribute('data-ext-free')")
        results["1c_free_persist"] = {
            "ext_page": ext_state,
            "content_script_attr": attr,
            "service_workers": [sw.url for sw in sess.context.service_workers],
        }
    finally:
        await sess.stop()

    # 1D: Toggle same free_profile BACK TO OFF (--disable-extensions restored)
    sess = SpikeBrowserSession(
        name="1d_cut_back_off",
        user_data_dir=free_profile,
        display=":91",
        suppress_disable_extensions=False,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        ext_state = await inspect_extensions_page(page)
        await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
        await asyncio.sleep(0.5)
        attr = await page.evaluate("document.documentElement.getAttribute('data-ext-free')")
        results["1d_cut_back_off"] = {
            "has_disable_extensions_flag": "--disable-extensions" in sess.cmdline,
            "ext_page": ext_state,
            "content_script_attr": attr,
            "service_workers": [sw.url for sw in sess.context.service_workers],
        }
    finally:
        await sess.stop()

    # 1E: Managed mode on SAME free_profile (--load-extension + --disable-extensions-except ONLY [ext_with_key, ext_no_key])
    sess = SpikeBrowserSession(
        name="1e_managed_refuses_free",
        user_data_dir=free_profile,
        display=":91",
        extension_paths=[str(paths["ext_with_key_v1"]), str(paths["ext_no_key_v1"])],
        suppress_disable_extensions=True,
        suppress_disable_component_ext=True,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        ext_state = await inspect_extensions_page(page)
        await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
        await asyncio.sleep(0.5)
        attrs = await page.evaluate(
            """() => ({
  keyed: document.documentElement.getAttribute('data-ext-keyed'),
  unkeyed: document.documentElement.getAttribute('data-ext-unkeyed'),
  free: document.documentElement.getAttribute('data-ext-free'),
})"""
        )
        results["1e_managed_refuses_free"] = {
            "ext_page": ext_state,
            "attrs": attrs,
            "service_workers": [sw.url for sw in sess.context.service_workers],
        }
    finally:
        await sess.stop()

    return results


async def test_spike2(paths: dict[str, Path], web_port: int) -> dict[str, Any]:
    results: dict[str, Any] = {}

    # 2A: chrome.runtime.id continuity & storage across path change: v1 -> v2
    uid_profile = ROOT / "profiles" / "uid_continuity"
    shutil.rmtree(uid_profile, ignore_errors=True)
    sess = SpikeBrowserSession(
        name="2a_paths_v1",
        user_data_dir=uid_profile,
        display=":92",
        extension_paths=[str(paths["ext_with_key_v1"]), str(paths["ext_no_key_v1"])],
        suppress_disable_extensions=True,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
        await asyncio.sleep(0.5)
        ids_v1 = await page.evaluate(
            """() => ({
  keyed: document.documentElement.getAttribute('data-ext-keyed'),
  unkeyed: document.documentElement.getAttribute('data-ext-unkeyed'),
})"""
        )
        # Write unique marker in chrome.storage.local via each extension's popup page
        stored_v1 = {}
        for k, eid in ids_v1.items():
            assert eid, ids_v1
            ep = await sess.context.new_page()
            await ep.goto(f"chrome-extension://{eid}/popup.html", wait_until="load")
            stored_v1[k] = await ep.evaluate(
                """async (tag) => {
  await chrome.storage.local.set({ probeToken: 'secret-' + tag });
  return await chrome.storage.local.get(null);
}""",
                k,
            )
            await ep.close()
        results["2a_v1"] = {"ids": ids_v1, "stored": stored_v1}
    finally:
        await sess.stop()

    # Relaunch SAME user_data_dir from paths v2
    sess = SpikeBrowserSession(
        name="2b_paths_v2",
        user_data_dir=uid_profile,
        display=":92",
        extension_paths=[str(paths["ext_with_key_v2"]), str(paths["ext_no_key_v2"])],
        suppress_disable_extensions=True,
    )
    await sess.start()
    try:
        page = await sess.context.new_page()
        await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="load")
        await asyncio.sleep(0.5)
        ids_v2 = await page.evaluate(
            """() => ({
  keyed: document.documentElement.getAttribute('data-ext-keyed'),
  unkeyed: document.documentElement.getAttribute('data-ext-unkeyed'),
})"""
        )
        read_v2 = {}
        for k, eid in ids_v2.items():
            assert eid, ids_v2
            ep = await sess.context.new_page()
            await ep.goto(f"chrome-extension://{eid}/popup.html", wait_until="load")
            read_v2[k] = await ep.evaluate("async () => await chrome.storage.local.get(null)")
            await ep.close()
        results["2b_v2"] = {
            "ids": ids_v2,
            "keyed_id_preserved": ids_v2["keyed"] == results["2a_v1"]["ids"]["keyed"],
            "unkeyed_id_changed": ids_v2["unkeyed"] != results["2a_v1"]["ids"]["unkeyed"],
            "read_after_move": read_v2,
        }
    finally:
        await sess.stop()

    # 2C: Official Bitwarden CRX (with extracted key) + local HTTP proxy + localhost WebAuthn page
    rec_proxy = RecordingHttpProxy()
    proxy_port = rec_proxy.start()
    bw_profile = ROOT / "profiles" / "bitwarden_profile"
    shutil.rmtree(bw_profile, ignore_errors=True)
    sess = SpikeBrowserSession(
        name="2c_bitwarden",
        user_data_dir=bw_profile,
        display=":93",
        extension_paths=[str(paths["bitwarden_unpacked_v1"]), str(paths["ext_with_key_v1"])],
        suppress_disable_extensions=True,
        suppress_disable_component_ext=True,
        proxy_url=f"http://127.0.0.1:{proxy_port}",
    )
    try:
        await sess.start()
        try:
            await asyncio.sleep(2.0)
            sw_urls = [sw.url for sw in sess.context.service_workers]
            bw_id = "nngceckbapebfimnlniiiahkandclblb"
            await asyncio.sleep(2.0)
            for p in list(sess.context.pages):
                if "bitwarden.com" in p.url:
                    await p.close()
            popup = await sess.context.new_page()
            await popup.goto(f"chrome-extension://{bw_id}/popup/index.html", wait_until="domcontentloaded")
            await asyncio.sleep(2.5)
            await popup.bring_to_front()
            popup_info = await popup.evaluate(
                """() => ({
  title: document.title,
  bodyLen: document.body ? document.body.innerText.length : 0,
  textSnippet: document.body ? document.body.innerText.slice(0, 600) : '',
})"""
            )
            capture_x11(sess.runner, EVIDENCE / "s2_bitwarden_popup.png")

            # Visit http://localhost:<web_port>/webauthn (where Bitwarden fido2-page-script.js hooks navigator.credentials!)
            page = await sess.context.new_page()
            await page.goto(f"http://localhost:{web_port}/webauthn", wait_until="load")
            await page.bring_to_front()
            await asyncio.sleep(1.5)
            # Check if Bitwarden replaced native navigator.credentials.create & ran multi-ext content script
            hook_check = await page.evaluate(
                """() => ({
  isSecureContext: window.isSecureContext,
  createSrc: String(navigator.credentials.create).slice(0, 120),
  getSrc: String(navigator.credentials.get).slice(0, 120),
  keyedExtAttr: document.documentElement.getAttribute('data-ext-keyed'),
})"""
            )
            # Trigger navigator.credentials.create() without logged-in Bitwarden vault to observe interception
            pages_before = [p.url for p in sess.context.pages]
            create_task = asyncio.create_task(page.evaluate("window.__runCreate()"))
            await asyncio.sleep(2.5)
            capture_x11(sess.runner, EVIDENCE / "s2_bitwarden_create.png")
            pages_after = [p.url for p in sess.context.pages]
            if not create_task.done():
                for p in list(sess.context.pages):
                    if p.url.startswith(f"chrome-extension://{bw_id}") and p != popup:
                        await p.close()
                try:
                    create_res = await asyncio.wait_for(create_task, timeout=3.0)
                except TimeoutError:
                    create_task.cancel()
                    try:
                        await create_task
                    except BaseException:
                        pass
                    create_res = {"intercepted_pending": True}
            else:
                create_res = await create_task

            results["2c_bitwarden"] = {
                "service_workers": sw_urls,
                "bitwarden_sw_active": any(bw_id in u for u in sw_urls),
                "popup_info": popup_info,
                "hook_check": hook_check,
                "pages_before_create": pages_before,
                "pages_during_create": pages_after,
                "create_res": create_res,
                "proxy_requests_seen": rec_proxy.requests[:30],
            }
        finally:
            await sess.stop()
    finally:
        rec_proxy.stop()

    return results


async def main() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    paths = copy_assets_to_tmp()
    web = LocalTestWebServer()
    web_port = web.start()
    try:
        out: dict[str, Any] = {}
        out["spike1"] = await test_spike1(paths, web_port)
        atomic_write_json(EVIDENCE / "results.json", out)
        # Skip spike1 if only validating spike2 fast? No, run full verification cleanly.
        out["spike2"] = await test_spike2(paths, web_port)
        atomic_write_json(EVIDENCE / "results.json", out)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    finally:
        web.stop()


if __name__ == "__main__":
    asyncio.run(main())
