# -*- coding: utf-8 -*-
import subprocess, time
from pathlib import Path

_LO = Path(r"C:\Program Files\LibreOffice\program")
SOFFICE = _LO / "soffice.com" if (_LO / "soffice.com").exists() else _LO / "soffice.exe"

def run_libreoffice(src: Path, target: str, outdir_base: Path, idx: int, timeout: int = 180, soffice=None):
    if soffice is None:
        soffice = SOFFICE
    prof = (outdir_base / f"prof_{idx}").as_uri()
    outdir = outdir_base / f"out_{idx}"
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [str(soffice), "-env:UserInstallation=" + prof, "--headless", "--norestore", "--convert-to", target, "--outdir", str(outdir), str(src)]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    out_file = outdir / (src.stem + "." + target)
    last_size = -1
    for _ in range(360):
        if out_file.exists():
            size = out_file.stat().st_size
            if size > 0 and size == last_size:
                return out_file
            last_size = size
        time.sleep(0.5)
    return None
