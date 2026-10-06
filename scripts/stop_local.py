#!/usr/bin/env python3
"""Exit 0 once nothing listens on the given loopback ports, 1 if one still does.

The shared public-bar check starts the replay gateway and the explorer server
as child processes and stops them itself. This is the declared stop command: it
proves they are gone instead of assuming it.

    python3 scripts/stop_local.py 18157 18160
"""

from __future__ import annotations

import socket
import sys
import time


def listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main(ports: list[int], seconds: float = 8.0) -> int:
    deadline = time.monotonic() + seconds
    live = [port for port in ports if listening(port)]
    while live and time.monotonic() < deadline:
        time.sleep(0.2)
        live = [port for port in live if listening(port)]
    if live:
        print(f"still listening on 127.0.0.1: {live}", file=sys.stderr)
        return 1
    print(f"nothing listening on 127.0.0.1: {ports}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: stop_local.py PORT [PORT ...]")
    sys.exit(main([int(arg) for arg in sys.argv[1:]]))
