"""Install one atomic, daemon-side egress ACL for an owned media bridge."""

from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

BRIDGE_OPTION = "com.docker.network.bridge.name"
BRIDGE_FILTER = Path("/proc/sys/net/bridge/bridge-nf-call-iptables")
STREAM_SYSCTLS = {
    "net.ipv6.conf.all.disable_ipv6": "1",
    "net.ipv6.conf.default.disable_ipv6": "1",
}


def bridge_name(identity: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{13}", identity):
        raise ValueError("Invalid media bridge identity")
    return "cm" + identity


def table_name(bridge: str) -> str:
    if not re.fullmatch(r"cm[a-f0-9]{13}", bridge):
        raise ValueError("Invalid media bridge name")
    return "cbmedia_" + bridge


def rule_set(bridge: str, stream: str, gateway: str, signal_port: int, mux_port: int) -> str:
    table = table_name(bridge)
    stream = str(ipaddress.IPv4Address(stream))
    gateway = str(ipaddress.IPv4Address(gateway))
    if stream == gateway or not (1 <= signal_port <= 65535 and 1 <= mux_port <= 65535):
        raise ValueError("Invalid media ACL endpoints")
    return f"""destroy table inet {table}
table inet {table} {{
    chain stream_egress {{
        ip daddr {gateway} tcp dport {signal_port} accept
        udp sport {mux_port} ct state established ct direction reply accept
        drop
    }}
    chain input {{
        type filter hook input priority -5; policy accept;
        iifname "{bridge}" ip saddr {stream} jump stream_egress
    }}
    chain forward {{
        type filter hook forward priority -5; policy accept;
        iifname "{bridge}" ip saddr {stream} jump stream_egress
    }}
}}
"""


def main() -> None:
    action, bridge, *args = sys.argv[1:]
    if action == "apply":
        if BRIDGE_FILTER.read_text().strip() != "1":
            raise RuntimeError("Media ACL requires bridge IPv4 netfilter")
        stream, gateway, signal_port, mux_port = args
        rules = rule_set(bridge, stream, gateway, int(signal_port), int(mux_port))
    elif action == "remove" and not args:
        rules = f"destroy table inet {table_name(bridge)}\n"
    else:
        raise ValueError("Invalid media ACL command")
    subprocess.run(["nft", "-f", "-"], input=rules, text=True, check=True, timeout=8)


if __name__ == "__main__":
    main()
