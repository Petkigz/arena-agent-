"""Network diagnostics — DNS lookup, port check, ping, traceroute, WHOIS.

Deterministic (stdlib socket/subprocess, no LLM). Every method returns a typed
`{"success": bool, ...}` and never raises; when a system utility is missing or
the network is unreachable, the call degrades to a clear error instead of
crashing — the thin model can relay the exact outcome.

Safety model (manifest authoritative): Level 0 (read-only, informational).
A single-port TCP check is service availability, not a scan.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger, audit_logger


class NetworkDiagnostics:
    # ── DNS ─────────────────────────────────────────────────────────────────
    @classmethod
    def resolve_dns(cls, host: str) -> Dict[str, Any]:
        """Resolve a hostname to IP addresses (IPv4 + IPv6)."""
        host = (host or "").strip()
        if not host:
            return {"success": False, "error": "A hostname is required."}
        try:
            infos = socket.getaddrinfo(host, None)
            ips = sorted({i[4][0] for i in infos})
            return {"success": True, "host": host, "addresses": ips, "count": len(ips)}
        except socket.gaierror as e:
            return {"success": False, "error": f"Could not resolve '{host}': {e}"}

    # ── port check ──────────────────────────────────────────────────────────
    @classmethod
    def check_port(cls, host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
        """Check whether a TCP port is open on a host (single connect attempt)."""
        host = (host or "").strip()
        if not host:
            return {"success": False, "error": "A host is required."}
        try:
            port = int(port)
        except (TypeError, ValueError):
            return {"success": False, "error": "port must be an integer."}
        if port < 1 or port > 65535:
            return {"success": False, "error": "port must be between 1 and 65535."}
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return {"success": True, "host": host, "port": port, "open": True}
        except (socket.timeout, OSError) as e:
            return {"success": True, "host": host, "port": port, "open": False, "reason": str(e)}

    # ── ping / traceroute (system utilities, best-effort) ──────────────────
    @classmethod
    def ping(cls, host: str, count: int = 4, timeout: float = 5.0) -> Dict[str, Any]:
        """Ping a host via the system `ping` utility; parse loss + latency."""
        host = (host or "").strip()
        if not host:
            return {"success": False, "error": "A host is required."}
        count = max(1, min(int(count), 20))
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            return {"success": False, "error": "timeout must be a number."}

        if sys.platform.startswith("win"):
            cmd = ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), host]
        else:
            cmd = ["ping", "-c", str(count), "-W", str(int(timeout)), host]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * count + 10)
        except FileNotFoundError:
            return {"success": False, "error": "The system 'ping' utility is not available."}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"ping timed out after {timeout * count + 10}s."}

        output = (proc.stdout or "") + (proc.stderr or "")
        stats = cls._parse_ping(output)
        return {
            "success": proc.returncode == 0,
            "host": host,
            "returncode": proc.returncode,
            "stats": stats,
            "output": output.strip()[:2000],
        }

    @classmethod
    def traceroute(cls, host: str, max_hops: int = 30) -> Dict[str, Any]:
        """Trace the route to a host via the system `traceroute`/`tracert` utility."""
        host = (host or "").strip()
        if not host:
            return {"success": False, "error": "A host is required."}
        max_hops = max(1, min(int(max_hops), 64))

        if sys.platform.startswith("win"):
            cmd = ["tracert", "-h", str(max_hops), host]
        else:
            cmd = ["traceroute", "-m", str(max_hops), host]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            return {"success": False, "error": "The system 'traceroute' utility is not available (try 'traceroute' or 'tracert')."}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "traceroute timed out."}

        output = (proc.stdout or "") + (proc.stderr or "")
        return {"success": proc.returncode == 0, "host": host, "output": output.strip()[:4000]}

    # ── WHOIS ───────────────────────────────────────────────────────────────
    @classmethod
    def whois(cls, domain: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Query WHOIS for a domain via the IANA referral, then the registry server."""
        domain = (domain or "").strip().lower()
        if not domain:
            return {"success": False, "error": "A domain is required."}
        if domain.startswith("http://") or domain.startswith("https://"):
            return {"success": False, "error": "Pass the bare domain, not a URL."}

        try:
            # 1. Ask IANA for the authoritative WHOIS server.
            iana = cls._whois_query("whois.iana.org", domain, timeout)
            if not iana:
                return {"success": False, "error": "Could not reach whois.iana.org."}
            m = re.search(r"refer:\s*(\S+)", iana, re.IGNORECASE)
            server = m.group(1) if m else "whois.verisign-grs.com"
            # 2. Query the registry.
            data = cls._whois_query(server, domain, timeout)
            if not data:
                return {"success": False, "error": f"Could not reach WHOIS server '{server}'."}
            audit_logger.info(f"WHOIS lookup for {domain} via {server}")
            return {"success": True, "domain": domain, "server": server, "output": data[:4000]}
        except Exception as e:
            app_logger.warning(f"WHOIS lookup failed for {domain}: {e}")
            return {"success": False, "error": f"WHOIS lookup failed: {e}"}

    @staticmethod
    def _whois_query(server: str, query: str, timeout: float) -> Optional[str]:
        try:
            with socket.create_connection((server, 43), timeout=timeout) as s:
                s.sendall((query + "\r\n").encode("utf-8"))
                chunks = []
                while True:
                    data = s.recv(4096)
                    if not data:
                        break
                    chunks.append(data.decode("utf-8", errors="replace"))
                return "".join(chunks)
        except OSError:
            return None

    # ── parser helpers ──────────────────────────────────────────────────────
    @classmethod
    def _parse_ping(cls, output: str) -> Dict[str, Any]:
        """Best-effort parse of ping output; returns empty dict if unparseable."""
        stats: Dict[str, Any] = {}
        m = re.search(r"(\d+(?:\.\d+)?)% packet loss", output)
        if m:
            stats["packet_loss_percent"] = float(m.group(1))
        m = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/[\d.]+ ms", output)
        if m:
            stats["min_ms"] = float(m.group(1))
            stats["avg_ms"] = float(m.group(2))
            stats["max_ms"] = float(m.group(3))
        m = re.search(r"(\d+)\s+received", output)
        if m:
            stats["received"] = int(m.group(1))
        return stats
