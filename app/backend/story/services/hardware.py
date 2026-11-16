"""Graphics card detection (v1.8) for the first-run assistant's model advice.

Only NVIDIA cards can be read reliably (nvidia-smi ships with their driver). Other cards: the assistant asks the player
to pick their video memory. Never fails: no card found is an empty list.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    if sys.platform == "win32":
        for p in (Path(r"C:\Windows\System32\nvidia-smi.exe"),
                  Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")):
            if p.is_file():
                return str(p)
    return None


def gpus() -> dict[str, Any]:
    exe = _nvidia_smi()
    if not exe:
        return {"gpus": [], "method": None}
    try:
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # no console window flashing
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=4, **flags).stdout
    except (OSError, subprocess.SubprocessError):
        return {"gpus": [], "method": None}
    found = []
    for line in out.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 2 and parts[1].replace(".", "").isdigit():
            found.append({"name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1)})
    return {"gpus": found, "method": "nvidia-smi" if found else None}
