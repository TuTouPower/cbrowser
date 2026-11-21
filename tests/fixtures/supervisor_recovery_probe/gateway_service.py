"""Production Gateway harness for Supervisor integration and recovery tests.

The harness runs the real ``cbrowser.gateway.server.create_gateway_app`` and only
supplies a minimal fake API client for the remaining Gateway -> API call
(runtime state; viewer authorization is verified locally from API-minted
grants since t064 and needs no fake).
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import Any

import httpx
from aiohttp import web
from cbrowser.gateway.config import GatewayConfig
from cbrowser.gateway.server import create_gateway_app
from cbrowser.shared.viewer_grants import ViewerGrantAuthority
from cbrowser.supervisor.gate_identity import gate_labels
from docker.errors import NotFound

logger = logging.getLogger("cbrowser.fixtures.production_gateway")

_GATEWAY_RELAY = """
import asyncio
import sys

port = int(sys.argv[1])

async def forward(reader, writer):
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()

async def relay(reader, writer):
    upstream_writer = None
    tasks = []
    try:
        upstream, upstream_writer = await asyncio.open_connection('host.docker.internal', port)
        tasks = [asyncio.create_task(forward(reader, upstream_writer)),
                 asyncio.create_task(forward(upstream, writer))]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if upstream_writer is not None:
            upstream_writer.close()
        writer.close()

async def main():
    async with await asyncio.start_server(relay, '0.0.0.0', port) as server:
        await server.serve_forever()

asyncio.run(main())
"""


class ApiRuntimeLookup:
    """Reads the authoritative runtime binding from the real API subprocess."""

    def __init__(self, api_url: str, token_file: Path) -> None:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
            trust_env=False,
        )

    async def __call__(self, profile_id: str) -> dict[str, Any] | None:
        cursor: str | None = None
        try:
            while True:
                params = {"cursor": cursor} if cursor else None
                response = await self._client.get(
                    "/api/v1/internal/supervisor/state/snapshot",
                    params=params,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                snapshot = response.json()
                for item in snapshot.get("profiles") or []:
                    if item.get("profile_id") == profile_id:
                        return item
                cursor = snapshot.get("next_cursor")
                if not cursor:
                    return None
        except Exception as exc:  # noqa: BLE001 - transport/decode failure means unavailable
            logger.warning(
                "Runtime lookup failed for profile %s: %s",
                profile_id,
                type(exc).__name__,
            )
            return None

    async def close(self) -> None:
        await self._client.aclose()


class FakeGatewayApiClient:
    """Minimal fake for the Gateway -> API runtime-state surface."""

    def __init__(self, runtime_lookup: ApiRuntimeLookup | None = None) -> None:
        self.runtime_lookup = runtime_lookup
        self.profile_runtimes: dict[str, dict[str, Any]] = {}

    def set_profile_runtime(
        self,
        profile_id: str,
        runtime_instance_id: str,
        observed_state: str = "running",
        config_version: int = 1,
        desired_state: str = "running",
    ) -> None:
        self.profile_runtimes[profile_id] = {
            "profile_id": profile_id,
            "runtime_instance_id": runtime_instance_id,
            "config_version": config_version,
            "desired_state": desired_state,
            "observed_state": observed_state,
        }

    async def get_profile_runtime(self, profile_id: str) -> dict[str, Any] | None:
        if self.runtime_lookup is not None:
            return await self.runtime_lookup(profile_id)
        info = self.profile_runtimes.get(profile_id)
        return dict(info) if info is not None else None

    async def close(self) -> None:
        if self.runtime_lookup is not None:
            await self.runtime_lookup.close()


class ProductionGatewayService:
    """Runs the production Gateway application on localhost."""

    def __init__(
        self,
        port: int,
        agent_key_file: Path,
        gateway_token_file: Path,
        runtime_lookup: ApiRuntimeLookup | None = None,
        api_client: FakeGatewayApiClient | None = None,
        agent_heartbeat_timeout_sec: float = 30.0,
        viewer_grant_key_file: Path | None = None,
    ) -> None:
        self.port = port
        self.agent_key_file = Path(agent_key_file)
        self.gateway_token_file = Path(gateway_token_file)
        self.api = api_client or FakeGatewayApiClient(runtime_lookup=runtime_lookup)
        if viewer_grant_key_file is None:
            viewer_grant_key_file = Path(
                f"{self.gateway_token_file}.viewer_grant_key"
            )
            viewer_grant_key_file.write_text(
                secrets.token_urlsafe(32), encoding="utf-8"
            )
            viewer_grant_key_file.chmod(0o600)
        self.grant_authority = ViewerGrantAuthority(viewer_grant_key_file)

        # t054: the Gateway derives its Origin whitelist from the deploy
        # port; there is no network state directory to seed anymore.
        self.config = GatewayConfig(
            host="127.0.0.1",
            port=port,
            agent_key_file=self.agent_key_file,
            gateway_token_file=self.gateway_token_file,
            api_url="http://api.invalid",
            api_token_file=self.gateway_token_file,
            viewer_grant_key_file=viewer_grant_key_file,
            agent_heartbeat_timeout_sec=agent_heartbeat_timeout_sec,
        )
        self.app = create_gateway_app(self.config, api_client=self.api)
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.docker_relay = None

    @property
    def control_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def gateway_url(self) -> str:
        return f"ws://host.docker.internal:{self.port}"

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await self.site.start()

    async def attach_docker_relay(self, client, prefix: str) -> None:
        """Give the host-side Gateway fixture a fixed endpoint on each media bridge."""
        self.docker_relay = await asyncio.to_thread(
            client.containers.run,
            os.environ["CBROWSER_SUPERVISOR_TEST_IMAGE"],
            name=f"{prefix}-gateway-relay",
            entrypoint=["python3", "-c", _GATEWAY_RELAY, str(self.port)],
            detach=True,
            cap_drop=["ALL"],
            read_only=True,
            extra_hosts={"host.docker.internal": "host-gateway"},
            labels=gate_labels({
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": "gateway",
                "com.cbrowser.instance-id": os.environ["CBROWSER_INSTANCE_ID"],
            }),
        )

    async def stop(self) -> None:
        if self.docker_relay is not None:
            try:
                await asyncio.to_thread(self.docker_relay.remove, force=True)
            except NotFound:
                pass
            self.docker_relay = None
        await self.api.close()
        if self.site is not None:
            await self.site.stop()
            self.site = None
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def __aenter__(self) -> ProductionGatewayService:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
