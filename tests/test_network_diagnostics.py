"""NetworkDiagnostics tests — DNS/port (local, deterministic) plus graceful
degradation for ping/traceroute/whois (system utilities / network may be absent)."""

import socket

from app.tools.network_diagnostics import NetworkDiagnostics


def test_resolve_localhost():
    res = NetworkDiagnostics.resolve_dns("localhost")
    assert res["success"] is True
    assert "127.0.0.1" in res["addresses"] or "::1" in res["addresses"]


def test_resolve_requires_host():
    assert NetworkDiagnostics.resolve_dns("")["success"] is False


def test_check_port_open():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        res = NetworkDiagnostics.check_port("127.0.0.1", port)
        assert res["success"] is True
        assert res["open"] is True
    finally:
        srv.close()


def test_check_port_closed():
    # Grab a port, close it, then verify it reports closed (connection refused).
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    res = NetworkDiagnostics.check_port("127.0.0.1", port)
    assert res["success"] is True
    assert res["open"] is False


def test_check_port_validation():
    assert NetworkDiagnostics.check_port("", 80)["success"] is False
    assert NetworkDiagnostics.check_port("127.0.0.1", 0)["success"] is False
    assert NetworkDiagnostics.check_port("127.0.0.1", 70000)["success"] is False
    assert NetworkDiagnostics.check_port("127.0.0.1", "abc")["success"] is False


def test_ping_requires_host():
    assert NetworkDiagnostics.ping("")["success"] is False


def test_ping_returns_typed_dict():
    # Loopback ping usually works even offline; if the utility is missing or
    # blocked it must still return a typed dict (never raise).
    res = NetworkDiagnostics.ping("127.0.0.1", count=1, timeout=2)
    assert isinstance(res, dict)
    assert "success" in res and "stats" in res


def test_traceroute_requires_host():
    assert NetworkDiagnostics.traceroute("")["success"] is False


def test_whois_requires_domain():
    assert NetworkDiagnostics.whois("")["success"] is False


def test_whois_rejects_url():
    assert NetworkDiagnostics.whois("https://example.com")["success"] is False


def test_whois_degrades_gracefully():
    # No network in sandbox → must return a typed dict, never raise.
    res = NetworkDiagnostics.whois("example.com", timeout=2)
    assert isinstance(res, dict)
    assert "success" in res


def test_parse_ping_linux():
    output = (
        "64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.05 ms\n"
        "--- 127.0.0.1 ping statistics ---\n"
        "4 packets transmitted, 4 received, 0% packet loss, time 3000ms\n"
        "rtt min/avg/max/mdev = 0.045/0.060/0.080/0.010 ms"
    )
    stats = NetworkDiagnostics._parse_ping(output)
    assert stats["packet_loss_percent"] == 0.0
    assert stats["received"] == 4
    assert stats["avg_ms"] == 0.060


def test_parse_ping_empty():
    assert NetworkDiagnostics._parse_ping("garbage") == {}
