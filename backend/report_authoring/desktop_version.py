"""Power BI Desktop version detection and compatibility mapping."""
from __future__ import annotations

import logging
import re
import subprocess
from functools import lru_cache

logger = logging.getLogger(__name__)

# Compatibility level history:
# 1200 = Pre-June 2019
# 1450 = June 2019 - Feb 2022
# 1470 = Mar 2022 - Aug 2022
# 1480 = Sep 2022 - Dec 2022
# 1550 = Jan 2023 - Jun 2023
# 1560 = Jul 2023 - Oct 2023
# 1565 = Nov 2023 - Feb 2024
# 1567 = Mar 2024 - Jun 2024
# 1570 = Jul 2024 - Sep 2024
# 1571 = Oct 2024 - Dec 2024
# 1572 = Jan 2025 - Mar 2025
# 1575 = Apr 2025 - Jun 2025
# 1600 = Jul 2025 - Jul 2026
# 1606 = Aug 2026+
#
# Mapping: version number -> minimum compatibility level
# Format: (major, minor, build, revision) -> level
_VERSION_LEVEL_MAP: list[tuple[tuple[int, ...], int]] = [
    ((2, 130, 0, 0), 1550),
    ((2, 135, 0, 0), 1560),
    ((2, 138, 0, 0), 1565),
    ((2, 140, 0, 0), 1567),
    ((2, 143, 0, 0), 1570),
    ((2, 144, 0, 0), 1571),
    ((2, 145, 0, 0), 1572),
    ((2, 148, 0, 0), 1575),
    ((2, 155, 0, 0), 1600),
    ((2, 157, 870, 0), 1606),
]

DEFAULT_COMPAT_LEVEL = 1606


def _parse_version(version_str: str) -> tuple[int, ...] | None:
    """Parse a version string like '2.157.879.0' into a tuple of ints."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?", version_str.strip())
    if not match:
        return None
    return tuple(int(g) for g in match.groups(default="0"))


def _level_for_version(version_tuple: tuple[int, ...]) -> int:
    """Map a version tuple to the correct compatibility level."""
    level = DEFAULT_COMPAT_LEVEL
    for min_ver, lvl in _VERSION_LEVEL_MAP:
        if version_tuple >= min_ver:
            level = lvl
    return level


def _detect_store_version() -> str | None:
    """Detect Power BI Desktop Store app version via PowerShell."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage *PowerBI* | Select-Object -ExpandProperty Version"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if re.match(r"\d+\.\d+", line):
                return line
    except Exception as exc:
        logger.debug("Store app detection failed: %s", exc)
    return None


def _detect_traditional_version() -> str | None:
    """Detect Power BI Desktop traditional installer version via registry."""
    # ``winreg`` is a Windows-only standard-library module.  Compatibility
    # generation is also used by CI and cloud-only workflows, where Desktop
    # is not installed, so a missing registry must simply mean "not found".
    try:
        import winreg
    except ImportError:
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        i = 0
        while True:
            try:
                subname = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subname)
                try:
                    display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                except FileNotFoundError:
                    i += 1
                    continue
                if "Power BI Desktop" not in str(display_name):
                    i += 1
                    continue
                try:
                    version, _ = winreg.QueryValueEx(subkey, "DisplayVersion")
                    winreg.CloseKey(subkey)
                    winreg.CloseKey(key)
                    return str(version)
                except FileNotFoundError:
                    i += 1
                    continue
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception as exc:
        logger.debug("Traditional installer detection failed: %s", exc)
    return None


@lru_cache(maxsize=1)
def detect_desktop_version() -> str | None:
    """Detect installed Power BI Desktop version (cached).

    Tries Store app first, then traditional installer.
    Returns version string like '2.157.879.0' or None.
    """
    version = _detect_store_version()
    if version:
        logger.info("Detected Power BI Desktop Store version: %s", version)
        return version
    version = _detect_traditional_version()
    if version:
        logger.info("Detected Power BI Desktop traditional version: %s", version)
        return version
    logger.warning("Could not detect Power BI Desktop version")
    return None


@lru_cache(maxsize=1)
def detect_compatibility_level() -> int:
    """Detect the correct compatibility level for the installed Desktop version.

    Returns the compatibility level integer (e.g. 1606).
    Falls back to DEFAULT_COMPAT_LEVEL if detection fails.
    """
    version_str = detect_desktop_version()
    if not version_str:
        logger.warning("Using default compatibility level %d", DEFAULT_COMPAT_LEVEL)
        return DEFAULT_COMPAT_LEVEL
    version_tuple = _parse_version(version_str)
    if not version_tuple:
        logger.warning("Could not parse version '%s', using default", version_str)
        return DEFAULT_COMPAT_LEVEL
    level = _level_for_version(version_tuple)
    logger.info("Compatibility level for v%s: %d", version_str, level)
    return level


def validate_compatibility_level(level: int) -> bool:
    """Check if a given compatibility level is compatible with installed Desktop."""
    installed = detect_compatibility_level()
    if level > installed:
        logger.error(
            "Model compatibility level %d exceeds installed Desktop level %d",
            level, installed,
        )
        return False
    return True
