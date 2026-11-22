"""s029 Bitwarden Passkey end-to-end probe on fixed 146.0.7680.177.3 + Proxy + Vaultwarden."""

from __future__ import annotations

import asyncio
import base64
import ctypes as c
import hashlib
import http.client
import http.server
import json
import os
import shutil
import socket
import ssl
import struct
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cloakbrowser.browser import (
    _append_webrtc_exit_ip,
    _resolve_proxy_config,
    _resolve_webrtc_args,
    build_args,
    build_launch_env,
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
ROOT = Path("/tmp/s029_bw_probe")
EVIDENCE = Path("/evidence")
ASSETS = Path("/probe/assets")
FONT_SET_ID = os.environ["S029_FONT_SET_ID"]
VAULTWARDEN_HOST = os.environ.get("VAULTWARDEN_HOST", "s029-vaultwarden")
VAULTWARDEN_PORT = int(os.environ.get("VAULTWARDEN_PORT", "80"))
TLS_PORT = 8443
BW_ID = "nngceckbapebfimnlniiiahkandclblb"


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
        return
    try:
        surf = mk_surf(disp, root_w(disp), visual(disp, screen(disp)), WIDTH, HEIGHT)
        try:
            wr_png(surf, os.fsencode(dest))
        finally:
            rm_surf(surf)
    finally:
        close_d(disp)


class RecordingConnectProxy:
    """HTTP CONNECT proxy routing only *.s029.local:8443 to local TLS router."""

    def __init__(self, tls_port: int) -> None:
        self.tls_port = tls_port
        self.connect_targets: list[str] = []
        self._srv: socket.socket | None = None
        self._stop = threading.Event()
        self.port = 0

    def start(self) -> int:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(64)
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
            conn.settimeout(30.0)
            data = conn.recv(8192)
            first = data.split(b"\r\n", 1)[0].decode("latin1", "replace")
            parts = first.split()
            if len(parts) < 2:
                return
            method, target = parts[0], parts[1]
            if method == "CONNECT":
                self.connect_targets.append(target)
                host, _, port_str = target.rpartition(":")
                if host in ("vault.s029.local", "rp.s029.local") and int(port_str) == self.tls_port:
                    up = socket.create_connection(("127.0.0.1", self.tls_port), timeout=5.0)
                    conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    self._relay(conn, up)
                    return
                conn.sendall(b"HTTP/1.1 502 Blocked Non-Lab Destination\r\n\r\n")
            else:
                self.connect_targets.append(f"HTTP:{target}")
                conn.sendall(b"HTTP/1.1 502 Blocked\r\nContent-Length: 0\r\n\r\n")
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
                    chunk = src.recv(16384)
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
        t1.join()
        t2.join()
        try:
            b.close()
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        if self._srv is not None:
            self._srv.close()


class LocalTlsRouter:
    """Single HTTPS server routing vault.s029.local -> Vaultwarden and rp.s029.local -> WebAuthn RP."""

    def __init__(self, cert: Path, key: Path) -> None:
        self.cert = cert
        self.key = key
        self.httpd: http.server.ThreadingHTTPServer | None = None
        self.created_credentials: list[dict[str, Any]] = []
        self.asserted_credentials: list[dict[str, Any]] = []
        self.vault_requests: list[str] = []

    def start(self, port: int = TLS_PORT) -> None:
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _handle_any(self) -> None:
                host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length) if length > 0 else b""
                if host == "vault.s029.local":
                    outer.vault_requests.append(f"{self.command} {self.path}")
                    conn = http.client.HTTPConnection(VAULTWARDEN_HOST, VAULTWARDEN_PORT, timeout=15)
                    fwd_headers = {
                        k: v for k, v in self.headers.items()
                        if k.lower() not in ("host", "connection", "proxy-connection", "transfer-encoding")
                    }
                    fwd_headers["Host"] = self.headers.get("Host") or f"vault.s029.local:{port}"
                    fwd_headers["X-Forwarded-Proto"] = "https"
                    fwd_headers["X-Forwarded-Host"] = fwd_headers["Host"]
                    conn.request(self.command, self.path, body=body if length > 0 else None, headers=fwd_headers)
                    resp = conn.getresponse()
                    raw = resp.read()
                    self.send_response(resp.status, resp.reason)
                    for hk, hv in resp.getheaders():
                        if hk.lower() in ("transfer-encoding", "connection", "content-length"):
                            continue
                        self.send_header(hk, hv)
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if raw:
                        self.wfile.write(raw)
                    conn.close()
                    return

                if host == "rp.s029.local":
                    if self.command == "POST" and self.path == "/api/verify":
                        payload = json.loads(body.decode("utf-8"))
                        if payload.get("kind") == "create":
                            outer.created_credentials.append(payload)
                        elif payload.get("kind") == "get":
                            outer.asserted_credentials.append(payload)
                        out = json.dumps({"ok": True}).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(out)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(out)
                        return

                    html = """<!doctype html><html><head><meta charset="utf-8"><title>Passkey RP</title></head>
<body>
<h1>Passkey RP (rp.s029.local)</h1>
<button id="create-btn" onclick="runCreate()">Create Passkey</button>
<button id="get-btn" onclick="runGet()">Sign in with Passkey</button>
<pre id="status">ready</pre>
<script>
const b64u = (buf) => {
  const bytes = new Uint8Array(buf);
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
};
window.lastCreateResult = null;
window.lastGetResult = null;
async function runCreate() {
  const challenge = new Uint8Array(32);
  crypto.getRandomValues(challenge);
  const userId = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
  try {
    const cred = await navigator.credentials.create({
      publicKey: {
        challenge,
        rp: { name: "S029 Test RP", id: "rp.s029.local" },
        user: { id: userId, name: "s029@example.com", displayName: "S029 Tester" },
        pubKeyCredParams: [{ alg: -7, type: "public-key" }, { alg: -257, type: "public-key" }],
        authenticatorSelection: { residentKey: "required", requireResidentKey: true, userVerification: "preferred" },
        timeout: 60000
      }
    });
    const out = {
      ok: true,
      id: cred.id,
      rawId: b64u(cred.rawId),
      type: cred.type,
      clientDataJSON: new TextDecoder().decode(cred.response.clientDataJSON),
      attestationLen: cred.response.attestationObject.byteLength,
    };
    window.lastCreateResult = out;
    document.getElementById('status').textContent = JSON.stringify(out, null, 2);
    await fetch('/api/verify', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({kind: 'create', ...out}) });
    return out;
  } catch (e) {
    const out = { ok: false, name: e && e.name, message: String(e && e.message || e) };
    window.lastCreateResult = out;
    document.getElementById('status').textContent = JSON.stringify(out, null, 2);
    return out;
  }
}
async function runGet() {
  const challenge = new Uint8Array(32);
  crypto.getRandomValues(challenge);
  try {
    const assertion = await navigator.credentials.get({
      publicKey: {
        challenge,
        rpId: "rp.s029.local",
        userVerification: "preferred",
        timeout: 60000
      }
    });
    const out = {
      ok: true,
      id: assertion.id,
      rawId: b64u(assertion.rawId),
      clientDataJSON: new TextDecoder().decode(assertion.response.clientDataJSON),
      authDataLen: assertion.response.authenticatorData.byteLength,
      sigLen: assertion.response.signature.byteLength,
      userHandle: assertion.response.userHandle ? b64u(assertion.response.userHandle) : null,
    };
    window.lastGetResult = out;
    document.getElementById('status').textContent = JSON.stringify(out, null, 2);
    await fetch('/api/verify', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({kind: 'get', ...out}) });
    return out;
  } catch (e) {
    const out = { ok: false, name: e && e.name, message: String(e && e.message || e) };
    window.lastGetResult = out;
    document.getElementById('status').textContent = JSON.stringify(out, null, 2);
    return out;
  }
}
</script></body></html>""".encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(html)
                    return

                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()

            do_GET = _handle_any
            do_POST = _handle_any
            do_PUT = _handle_any
            do_DELETE = _handle_any
            do_OPTIONS = _handle_any
            do_HEAD = _handle_any

            def log_message(self, *args: object) -> None:
                return

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(self.cert), keyfile=str(self.key))
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


async def main() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    bw_mount = ROOT / "bw_ext"
    shutil.copytree(ASSETS / "bitwarden_unpacked", bw_mount)
    spki = (ASSETS / "tls_spki.txt").read_text().strip()

    tls_router = LocalTlsRouter(ASSETS / "tls_cert.pem", ASSETS / "tls_key.pem")
    tls_router.start(TLS_PORT)
    proxy = RecordingConnectProxy(TLS_PORT)
    proxy_port = proxy.start()

    run_dir = ROOT / "run"
    user_data_dir = ROOT / "profile"
    run_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PULSE_RUNTIME_PATH"] = str(run_dir / "pulse")
    snap = run_dir / "snapshot.json"
    atomic_write_json(
        snap,
        {
            "id": "snap_bw",
            "profile_id": "prof_bw",
            "version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "config": {
                "name": "bw_passkey",
                "locale": "en-US",
                "color_scheme": "light",
                "font_set_id": FONT_SET_ID,
                "include_cjk_fonts": False,
                "fingerprint_seed": 778899,
                "screen_width": WIDTH,
                "screen_height": HEIGHT,
                "geoip": False,
                "set_google_default": False,
                "restore_session": False,
            },
        },
    )
    runner = BrowserRunner(
        profile_id="prof_bw",
        runtime_instance_id="bw1",
        config_snapshot_path=snap,
        run_dir=run_dir,
        user_data_dir=user_data_dir,
        display=":95",
        engine_build=BUILD,
    )
    runner.resolve_engine_binary()
    chrome_bin = Path(f"/data/engine-cache/chromium-{BUILD}/chrome")
    pulse_sock, pulse_cookie = runner.setup_pulse()
    runner.setup_display(WIDTH, HEIGHT)
    font_dirs = profile_font_dirs("windows", FONT_SET_ID)
    fc = prepare_profile_fontconfig(run_dir, font_dirs, include_cjk_fonts=False, platform="windows")
    assert fc is not None
    assert verify_mounted_font_set(
        mount_root=FONT_SET_MOUNT_ROOT, platform="windows", font_set_id=FONT_SET_ID,
        include_cjk_fonts=False, fontconfig_path=fc
    )["status"] == "verified"

    seed_widevine_hint(user_data_dir, str(chrome_bin))
    wrapper_path = run_dir / "chrome_wrapper.sh"
    pid_file = run_dir / "chrome.pid"
    wrapper_path.write_text(
        f'#!/bin/bash\n"{chrome_bin}" "$@" &\nCPID=$!\necho "$CPID" > "{pid_file}"\nwait $CPID\n',
        encoding="utf-8",
    )
    wrapper_path.chmod(0o755)
    browser_env = runner._browser_environment(pulse_sock, pulse_cookie, wrapper_path, fc)

    proxy_url = f"http://127.0.0.1:{proxy_port}"
    extra_args = [
        "--no-sandbox", "--disable-dev-shm-usage", "--window-position=0,0",
        f"--window-size={WIDTH},{HEIGHT}", "--force-device-scale-factor=1",
        "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
        "--autoplay-policy=no-user-gesture-required", "--fingerprint-platform=windows",
        "--fingerprint-noise=false", f"--fingerprint-screen-width={WIDTH}",
        f"--fingerprint-screen-height={HEIGHT}", "--disable-gtk-ime",
        "--fingerprint=778899", "--disable-quic",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        f"--ignore-certificate-errors-spki-list={spki}",
    ]
    os.environ["CLOAKBROWSER_BINARY_PATH"] = str(wrapper_path)
    os.environ["CLOAKBROWSER_CACHE_DIR"] = "/data/engine-cache"
    try:
        proxy_kwargs, proxy_extra = _resolve_proxy_config(proxy_url, BUILD, None, None)
        args = await asyncio.to_thread(_resolve_webrtc_args, extra_args, proxy_url)
        args = _append_webrtc_exit_ip(args, None)
        args = persistent_seed_args(user_data_dir, True, args)
        chrome_args = build_args(
            True, (args or []) + proxy_extra, timezone=None, locale="en-US",
            headless=False, extension_paths=[str(bw_mount)], start_maximized=False,
        )
        launch_env = build_launch_env(None, user_env=browser_env, status_file=None)
        ignore_args = list(IGNORE_DEFAULT_ARGS) + ["--disable-extensions", "--disable-component-extensions-with-background-pages"]

        pw = await async_playwright().start()
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=os.fspath(user_data_dir), executable_path=str(wrapper_path),
            headless=False, args=chrome_args, ignore_default_args=ignore_args,
            no_viewport=True, color_scheme="light", env=launch_env, **proxy_kwargs,
        )
    finally:
        os.environ.pop("CLOAKBROWSER_BINARY_PATH", None)
        os.environ.pop("CLOAKBROWSER_CACHE_DIR", None)

    out: dict[str, Any] = {}
    try:
        await asyncio.sleep(2.5)
        for p in list(ctx.pages):
            if "bitwarden.com" in p.url:
                await p.close()

        # Step 1: Register an account via Vaultwarden Web Vault over HTTPS via proxy
        vw = await ctx.new_page()
        await vw.goto(f"https://vault.s029.local:{TLS_PORT}/#/register", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2.5)
        await vw.bring_to_front()
        capture_x11(runner, EVIDENCE / "bw_01_vw_register.png")

        # Try registering account in Vaultwarden Web UI or inspect form fields
        vw_info = await vw.evaluate("""() => ({
  url: location.href,
  title: document.title,
  inputs: Array.from(document.querySelectorAll('input')).map(i => ({type: i.type, name: i.name, id: i.id, formcontrol: i.getAttribute('formcontrolname'), placeholder: i.placeholder})),
  buttons: Array.from(document.querySelectorAll('button')).map(b => (b.innerText || '').trim()),
  text: (document.body?.innerText || '').slice(0, 600),
})""")
        out["vw_register_page"] = vw_info

        # Fill Vaultwarden registration form: step 1 or full form
        # Vaultwarden new web vault uses 2-step or single-page registration; let's handle dynamically
        email = "s029-test@example.com"
        master_pw = "CorrectHorseBatteryStaple!2026"
        if await vw.locator('input[type="email"]').count() > 0:
            await vw.locator('input[type="email"]').first.fill(email)
            # Check if name input exists right away or after Continue
            if await vw.locator('button:has-text("Continue")').count() > 0:
                await vw.locator('button:has-text("Continue")').first.click()
                await asyncio.sleep(1.5)
            pws = vw.locator('input[type="password"]')
            pw_cnt = await pws.count()
            if pw_cnt == 0:
                # Try clicking checkbox or submit
                for _ in range(3):
                    await asyncio.sleep(0.5)
                    pw_cnt = await pws.count()
                    if pw_cnt > 0:
                        break
            for idx in range(min(pw_cnt, 2)):
                await pws.nth(idx).fill(master_pw)
            # Uncheck "Check known data breaches for this password" (offline proxy blocks HIBP api.pwnedpasswords.com)
            cbs = vw.locator('input[type="checkbox"]')
            for idx in range(await cbs.count()):
                if await cbs.nth(idx).is_checked():
                    await cbs.nth(idx).uncheck()
            for btn_sel in ('button:has-text("Create account")', 'button[type="submit"]'):
                if await vw.locator(btn_sel).count() > 0:
                    await vw.locator(btn_sel).first.click()
                    break
            await asyncio.sleep(3.5)
        capture_x11(runner, EVIDENCE / "bw_02_vw_after_reg.png")
        out["vw_after_reg_url"] = vw.url
        out["vw_after_reg_text"] = await vw.evaluate("document.body?.innerText?.slice(0, 400) || ''")

        # Step 2: Open Bitwarden Extension Popup and configure Self-hosted URL -> Log in
        pop = await ctx.new_page()
        await pop.goto(f"chrome-extension://{BW_ID}/popup/index.html", wait_until="domcontentloaded")
        await asyncio.sleep(2.5)
        await pop.bring_to_front()
        capture_x11(runner, EVIDENCE / "bw_03_ext_carousel.png")

        # Click Log in button
        if await pop.locator('a:has-text("Log in"), button:has-text("Log in")').count() > 0:
            await pop.locator('a:has-text("Log in"), button:has-text("Log in")').first.click()
            await asyncio.sleep(1.5)
        await pop.bring_to_front()
        capture_x11(runner, EVIDENCE / "bw_04_ext_login_screen.png")
        out["ext_login_snippet"] = await pop.evaluate("document.body?.innerText?.slice(0, 600) || ''")

        # Select Self-hosted server environment (button/select "bitwarden.com" -> Self-hosted)
        if await pop.locator('button:has-text("bitwarden.com"), a:has-text("bitwarden.com")').count() > 0:
            await pop.locator('button:has-text("bitwarden.com"), a:has-text("bitwarden.com")').first.click()
            await asyncio.sleep(1.0)
        capture_x11(runner, EVIDENCE / "bw_05_env_dropdown.png")
        if await pop.locator('text=Self-hosted').count() > 0:
            await pop.locator('text=Self-hosted').first.click()
            await asyncio.sleep(1.0)
        capture_x11(runner, EVIDENCE / "bw_06_self_hosted_dialog.png")

        # Fill Self-hosted Server URL inside CDK modal overlay!
        server_url = f"https://vault.s029.local:{TLS_PORT}"
        dlg = pop.locator(".cdk-overlay-container")
        await dlg.locator("input").first.fill(server_url)
        await dlg.locator('button:has-text("Save")').first.click()
        await asyncio.sleep(1.2)

        # Log in with email -> Continue -> master password
        await pop.locator('input[type="email"], input[formcontrolname="email"]').first.fill(email)
        await pop.locator('button:has-text("Continue")').first.click()
        await asyncio.sleep(1.5)
        await pop.locator('input[type="password"]').first.fill(master_pw)
        await pop.locator('button[type="submit"]:visible, button:has-text("Log in with master password"):visible').first.click()
        await asyncio.sleep(4.0)

        await pop.bring_to_front()
        capture_x11(runner, EVIDENCE / "bw_07_ext_logged_in.png")
        out["ext_after_login_url"] = pop.url
        out["ext_after_login_text"] = await pop.evaluate("document.body?.innerText?.slice(0, 600) || ''")

        # Step 3: Navigate to RP WebAuthn page and test navigator.credentials.create & get!
        rp = await ctx.new_page()
        await rp.goto(f"https://rp.s029.local:{TLS_PORT}/webauthn", wait_until="load")
        await rp.bring_to_front()
        await asyncio.sleep(1.5)
        out["rp_hook_check"] = await rp.evaluate("""() => ({
  isSecureContext: window.isSecureContext,
  createFn: String(navigator.credentials.create).slice(0, 120),
  getFn: String(navigator.credentials.get).slice(0, 120),
})""")

        async def _interact_bitwarden_fido(kind: str) -> dict[str, Any]:
            info: dict[str, Any] = {"pages": [p.url for p in ctx.pages], "frames": [f.url for f in rp.frames]}
            for target in [*list(ctx.pages), *list(rp.frames)]:
                url = target.url
                if url.startswith(f"chrome-extension://{BW_ID}") and target != pop:
                    info["matched_url"] = url
                    try:
                        info["text"] = await target.evaluate("document.body?.innerText?.slice(0, 600) || ''")
                    except Exception:
                        pass
                    btn_order = (
                        ("Save passkey as new login", "Save passkey", "Save", "Confirm")
                        if kind == "create"
                        else ("s029@example.com", "S029 Test RP", "Confirm", "Sign in", "Use passkey")
                    )
                    for btxt in btn_order:
                        try:
                            loc = target.locator(f'button:has-text("{btxt}"), [role="button"]:has-text("{btxt}"), a:has-text("{btxt}")')
                            if await loc.count() > 0:
                                info.setdefault("clicked", []).append(btxt)
                                await loc.first.click()
                                await asyncio.sleep(1.5)
                                break
                        except Exception:
                            break
                    break
            return info

        # Trigger Create Passkey and watch Bitwarden popup/overlay!
        await rp.click("#create-btn")
        await asyncio.sleep(3.0)
        capture_x11(runner, EVIDENCE / "bw_08_passkey_create_prompt.png")
        out["fido2_create_ui"] = await _interact_bitwarden_fido("create")
        await asyncio.sleep(3.0)
        await rp.bring_to_front()
        out["rp_create_result"] = await rp.evaluate("window.lastCreateResult")
        capture_x11(runner, EVIDENCE / "bw_09_after_create.png")

        # Trigger Get Passkey!
        await rp.click("#get-btn")
        await asyncio.sleep(3.0)
        capture_x11(runner, EVIDENCE / "bw_10_passkey_get_prompt.png")
        out["fido2_get_ui"] = await _interact_bitwarden_fido("get")
        await asyncio.sleep(3.0)
        await rp.bring_to_front()
        out["rp_get_result"] = await rp.evaluate("window.lastGetResult")
        capture_x11(runner, EVIDENCE / "bw_11_after_get.png")

        out["proxy_connect_targets"] = proxy.connect_targets[:50]
        out["vault_requests"] = tls_router.vault_requests[:50]
        out["rp_verified_create"] = tls_router.created_credentials
        out["rp_verified_get"] = tls_router.asserted_credentials
        print(json.dumps(out, indent=2, ensure_ascii=False))
    finally:
        out["proxy_connect_targets"] = proxy.connect_targets[:50]
        out["vault_requests"] = tls_router.vault_requests[:50]
        atomic_write_json(EVIDENCE / "bw_results.json", out)
        await ctx.close()
        await pw.stop()
        await runner.stop()
        proxy.stop()
        tls_router.stop()


if __name__ == "__main__":
    asyncio.run(main())
