#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       skill.py (network_scan)
# DESCRIPTION: Scan a network target for live hosts/ports
# SUMMARY: Runs nmap when available; falls back to a
#          pure-Python TCP connect sweep otherwise.
# NOTES: Execution mode only — requires network access.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    bsdero    Initial implementation
"""network_scan skill: host and port discovery."""

from __future__ import annotations

import asyncio
import ipaddress
import shutil
import socket
from typing import Any


_DEFAULT_PORTS = "22,80,443,8080,8443,3306,5432,6379"
_DEFAULT_TIMEOUT = 5


async def execute(
    target: str,
    ports: str = _DEFAULT_PORTS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Scan target and return structured host/port data."""
    if shutil.which("nmap"):
        return await _nmap_scan(target, ports, timeout)
    return await _tcp_sweep(target, ports, timeout)


# ── nmap path ────────────────────────────────────────────


async def _nmap_scan(
    target: str,
    ports: str,
    timeout: int,
) -> dict[str, Any]:
    cmd = [
        "nmap", "-sV", "--open",
        "-p", ports,
        "--host-timeout", f"{timeout}s",
        "-oG", "-",
        target,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode not in (0, 1):
        return {
            "error": "nmap failed",
            "detail": stderr.decode().strip(),
        }
    return _parse_nmap_grepable(stdout.decode())


def _parse_nmap_grepable(output: str) -> dict[str, Any]:
    """Parse nmap -oG output into a structured dict."""
    hosts: list[dict] = []
    for line in output.splitlines():
        if not line.startswith("Host:"):
            continue
        parts = line.split("\t")
        ip_part = parts[0].split()[1]
        hostname = ""
        if "(" in parts[0]:
            hostname = parts[0].split("(")[1].rstrip(")")
        open_ports: list[dict] = []
        for part in parts[1:]:
            if not part.startswith("Ports:"):
                continue
            for entry in part[6:].split(","):
                entry = entry.strip()
                if "/open/" not in entry:
                    continue
                fields = entry.split("/")
                open_ports.append({
                    "port": int(fields[0]),
                    "protocol": fields[2],
                    "service": fields[4],
                    "version": fields[6] if len(
                        fields
                    ) > 6 else "",
                })
        hosts.append({
            "ip": ip_part,
            "hostname": hostname,
            "ports": open_ports,
        })
    return {"scanner": "nmap", "hosts": hosts}


# ── pure-Python fallback ──────────────────────────────────


async def _tcp_sweep(
    target: str,
    ports: str,
    timeout: int,
) -> dict[str, Any]:
    """TCP connect sweep — no external tools required."""
    targets = _expand_target(target)
    port_list = _parse_ports(ports)

    tasks = [
        _probe_host(ip, port_list, timeout)
        for ip in targets
    ]
    results = await asyncio.gather(*tasks)
    hosts = [r for r in results if r["ports"]]
    return {"scanner": "tcp_sweep", "hosts": hosts}


def _expand_target(target: str) -> list[str]:
    try:
        net = ipaddress.ip_network(target, strict=False)
        return [str(h) for h in net.hosts()]
    except ValueError:
        return [target]


def _parse_ports(ports: str) -> list[int]:
    result: list[int] = []
    for token in ports.split(","):
        token = token.strip()
        if "-" in token:
            lo, hi = token.split("-", 1)
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(int(token))
    return result


async def _probe_host(
    ip: str,
    ports: list[int],
    timeout: int,
) -> dict[str, Any]:
    open_ports: list[dict] = []
    for port in ports:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout,
            )
            writer.close()
            await writer.wait_closed()
            open_ports.append({"port": port})
        except (OSError, asyncio.TimeoutError):
            pass
    hostname = ""
    if open_ports:
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except OSError:
            pass
    return {"ip": ip, "hostname": hostname, "ports": open_ports}
