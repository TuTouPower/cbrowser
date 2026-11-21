#!/usr/bin/env python3
"""p159 / t097 minimal OrbStack topology probe.

Reproduces the declared per-Profile media network (bridge + internal + explicit
subnet, Stream UDP mux published to host 127.0.0.1) with lightweight containers
and measures the reachability matrix the ADR claims. All resources are removed
in a finally block; names carry a dedicated probe prefix.
"""

import json
import socket
import subprocess
import sys
import time

PREFIX = "probe-s028"
IMAGE = "python:3.13-slim"
MEDIA = f"{PREFIX}-media"
OTHER = f"{PREFIX}-other"
UPLINK = f"{PREFIX}-uplink"
GATEWAY = f"{PREFIX}-gateway"
STREAM = f"{PREFIX}-stream"
PEER = f"{PREFIX}-peer"
SERVICE = f"{PREFIX}-svc"

MEDIA_SUBNET = "10.220.0.0/24"
OTHER_SUBNET = "10.221.0.0/24"
UPLINK_SUBNET = "10.222.0.0/24"
GW_IP = "10.220.0.10"
STREAM_IP = "10.220.0.20"
PEER_IP = "10.221.0.20"
SVC_IP = "10.222.0.20"
UDP_PORT = 30123
TCP_GW = 8005
TCP_OTHER = 9000


def run(args, *, check=True, capture=True, timeout=30):
    result = subprocess.run(
        args,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )
    return result


def d(*args, **kwargs):
    return run(["docker", *args], **kwargs)


def cleanup():
    for name in (STREAM, GATEWAY, PEER, SERVICE):
        d("rm", "-f", name, check=False, capture=False)
    for net in (MEDIA, OTHER, UPLINK):
        d("network", "rm", net, check=False, capture=False)


def tcp_probe(target, port, timeout=2):
    try:
        with socket.create_connection((target, port), timeout=timeout):
            return True
    except OSError:
        return False


def udp_loopback_probe():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        sock.sendto(b"ping", ("127.0.0.1", UDP_PORT))
        data, _ = sock.recvfrom(1024)
        return data.decode(errors="replace")
    except OSError as exc:
        return f"FAIL: {exc}"


def container_tcp(name, target, port):
    script = (
        "import socket;"
        f"s=socket.create_connection(('{target}',{port}),2);"
        "s.close();print('OK')"
    )
    result = d("exec", name, "python3", "-c", script, check=False)
    return result.stdout.strip() == "OK"


def main():
    results = {}
    cleanup()
    try:
        d("network", "create", "--driver", "bridge", "--internal",
          "--subnet", MEDIA_SUBNET, MEDIA)
        d("network", "create", "--driver", "bridge", "--internal",
          "--subnet", OTHER_SUBNET, OTHER)
        d("network", "create", "--driver", "bridge",
          "--subnet", UPLINK_SUBNET, UPLINK)

        d("run", "-d", "--name", GATEWAY, "--network", MEDIA,
          "--ip", GW_IP, IMAGE,
          "python3", "-m", "http.server", str(TCP_GW), "--bind", "0.0.0.0")
        d("run", "-d", "--name", PEER, "--network", OTHER,
          "--ip", PEER_IP, IMAGE,
          "python3", "-m", "http.server", str(TCP_OTHER), "--bind", "0.0.0.0")
        d("run", "-d", "--name", SERVICE, "--network", UPLINK,
          "--ip", SVC_IP, IMAGE,
          "python3", "-m", "http.server", str(TCP_OTHER), "--bind", "0.0.0.0")

        d("run", "-d", "--name", STREAM, "--network", MEDIA,
          "--ip", STREAM_IP, "-p", f"127.0.0.1:{UDP_PORT}:{UDP_PORT}/udp",
          IMAGE, "python3", "-c", "import time;time.sleep(3600)")
        d("cp", "docs/spikes/s028_t097_media_topology_orbstack/code/udp_echo.py",
          f"{STREAM}:/tmp/udp_echo.py")
        d("exec", "-d", STREAM, "python3", "/tmp/udp_echo.py")

        time.sleep(2)

        results["host_loopback_udp_published"] = udp_loopback_probe()
        results["gateway_same_net_tcp"] = container_tcp(STREAM, GW_IP, TCP_GW)
        results["other_profile_tcp"] = container_tcp(STREAM, PEER_IP, TCP_OTHER)
        results["host_or_lan_service_tcp"] = container_tcp(STREAM, SVC_IP, TCP_OTHER)
        results["public_tcp"] = container_tcp(STREAM, "1.1.1.1", 443)

        ipv6 = d("exec", STREAM, "cat", "/proc/net/if_inet6", check=False)
        results["ipv6_enabled"] = bool(ipv6.stdout.strip())
        results["ipv6_public_tcp"] = container_tcp(
            STREAM, "2606:4700:4700::1111", 443
        )

        media_inspect = d("network", "inspect", MEDIA)
        net = json.loads(media_inspect.stdout)[0]
        results["media_network"] = {
            "internal": net.get("Internal"),
            "driver": net.get("Driver"),
            "subnet": (net.get("IPAM") or {}).get("Config", [{}])[0].get("Subnet"),
        }
        stream_inspect = d("inspect", STREAM)
        info = json.loads(stream_inspect.stdout)[0]
        results["stream_ports"] = info.get("NetworkSettings", {}).get("Ports")
        results["stream_networks"] = list(
            (info.get("NetworkSettings") or {}).get("Networks", {}).keys()
        )
    finally:
        cleanup()

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
