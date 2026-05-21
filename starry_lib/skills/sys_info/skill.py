#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       skill.py (sys_info)
# DESCRIPTION: Collect local system information
# SUMMARY: Uses psutil when available; falls back to
#          /proc reads and platform stdlib on bare Linux.
# NOTES: Available in plan and execution modes (read-only).
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    ahernandez86    Initial implementation
"""sys_info skill: CPU, memory, disk, network, OS info."""

from __future__ import annotations

import os
import platform
import socket
from typing import Any


_ALL_SECTIONS = ["cpu", "memory", "disk", "network", "os"]


async def execute(
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Return system info for the requested sections."""
    if not sections:
        sections = _ALL_SECTIONS
    result: dict[str, Any] = {}
    for section in sections:
        fn = _SECTION_FNS.get(section)
        if fn:
            result[section] = fn()
    return result


# ── section collectors ────────────────────────────────────


def _cpu() -> dict[str, Any]:
    try:
        import psutil  # type: ignore[import]
        freq = psutil.cpu_freq()
        return {
            "physical_cores": psutil.cpu_count(
                logical=False
            ),
            "logical_cores": psutil.cpu_count(
                logical=True
            ),
            "usage_percent": psutil.cpu_percent(
                interval=0.2
            ),
            "freq_mhz": round(
                freq.current, 1
            ) if freq else None,
        }
    except ImportError:
        pass
    # /proc fallback
    info: dict[str, Any] = {}
    try:
        with open("/proc/cpuinfo") as f:
            cores = sum(
                1 for l in f if l.startswith("processor")
            )
        info["logical_cores"] = cores
    except OSError:
        pass
    try:
        with open("/proc/loadavg") as f:
            loads = f.read().split()
        info["load_avg_1m"] = float(loads[0])
    except OSError:
        pass
    return info


def _memory() -> dict[str, Any]:
    try:
        import psutil  # type: ignore[import]
        vm = psutil.virtual_memory()
        return {
            "total_mb": vm.total // 2**20,
            "available_mb": vm.available // 2**20,
            "used_mb": vm.used // 2**20,
            "percent": vm.percent,
        }
    except ImportError:
        pass
    try:
        fields: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                fields[k.strip()] = int(
                    v.strip().split()[0]
                )
        return {
            "total_mb": fields.get(
                "MemTotal", 0
            ) // 1024,
            "available_mb": fields.get(
                "MemAvailable", 0
            ) // 1024,
            "used_mb": (
                fields.get("MemTotal", 0)
                - fields.get("MemAvailable", 0)
            ) // 1024,
        }
    except OSError:
        return {}


def _disk() -> list[dict[str, Any]]:
    try:
        import psutil  # type: ignore[import]
        partitions = []
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions.append({
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(
                        usage.total / 2**30, 1
                    ),
                    "used_gb": round(
                        usage.used / 2**30, 1
                    ),
                    "free_gb": round(
                        usage.free / 2**30, 1
                    ),
                    "percent": usage.percent,
                })
            except PermissionError:
                pass
        return partitions
    except ImportError:
        pass
    try:
        lines = os.popen("df -m /").read().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            return [{
                "mountpoint": parts[5],
                "total_gb": round(
                    int(parts[1]) / 1024, 1
                ),
                "used_gb": round(
                    int(parts[2]) / 1024, 1
                ),
                "free_gb": round(
                    int(parts[3]) / 1024, 1
                ),
            }]
    except Exception:
        pass
    return []


def _network() -> list[dict[str, Any]]:
    try:
        import psutil  # type: ignore[import]
        ifaces = []
        for name, addrs in psutil.net_if_addrs().items():
            iface: dict[str, Any] = {"name": name}
            for addr in addrs:
                import psutil as _ps
                AF_INET = _ps.AF_LINK if hasattr(
                    _ps, "AF_LINK"
                ) else None
                import socket as _s
                if addr.family == _s.AF_INET:
                    iface["ipv4"] = addr.address
                    iface["netmask"] = addr.netmask
                elif addr.family == _s.AF_INET6:
                    iface.setdefault(
                        "ipv6", []
                    ).append(addr.address)
            ifaces.append(iface)
        return ifaces
    except ImportError:
        pass
    ifaces: list[dict] = []
    try:
        with open("/proc/net/if_inet6") as f:
            pass
    except OSError:
        pass
    try:
        import subprocess
        out = subprocess.check_output(
            ["ip", "addr", "show"],
            text=True,
        )
        current: dict[str, Any] = {}
        for line in out.splitlines():
            line = line.strip()
            if line and line[0].isdigit():
                if current:
                    ifaces.append(current)
                name = line.split(":")[1].strip()
                current = {"name": name}
            elif line.startswith("inet "):
                current["ipv4"] = line.split()[1]
            elif line.startswith("inet6 "):
                current.setdefault(
                    "ipv6", []
                ).append(line.split()[1])
        if current:
            ifaces.append(current)
    except Exception:
        pass
    return ifaces


def _os_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
    }
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    info["distro"] = line.split(
                        "=", 1
                    )[1].strip().strip('"')
                    break
    except OSError:
        pass
    return info


_SECTION_FNS: dict[str, Any] = {
    "cpu": _cpu,
    "memory": _memory,
    "disk": _disk,
    "network": _network,
    "os": _os_info,
}
