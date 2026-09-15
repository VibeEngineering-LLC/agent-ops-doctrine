You are writing ONE complete Python module named `legacy.py` inside the package `doc_extract`.

OUTPUT RULES (critical):
- Output ONLY the Python source code. No markdown fences, no ``` , no explanation.
- The VERY FIRST line must be exactly: # -*- coding: utf-8 -*-
- Target Python 3.11+ on Windows. Real bodies. Keep under ~45 lines.

PURPOSE:
`doc_extract.legacy` holds the corpus-agnostic LibreOffice-headless conversion primitive relocated from
radon-library/scripts/deferred.py (`run_lo`). It converts one legacy office file to a target OOXML/PDF
format using a UNIQUE per-call profile and output dir (the proven anti-collision / anti-delegation
pattern), then polls for output-file size stabilization. NO corpus import, NO report logic, NO
extract/ocr calls: only the LibreOffice runner. Preserve EXACT logic (byte-compared against run_lo).

IMPORTS AND MODULE CONSTANTS (do exactly this):
- `import subprocess, time`; `from pathlib import Path`.
- Module-level LibreOffice path detection:
    `_LO = Path(r"C:\Program Files\LibreOffice\program")`
    `SOFFICE = _LO / "soffice.com" if (_LO / "soffice.com").exists() else _LO / "soffice.exe"`

FUNCTION TO IMPLEMENT (exact logic):

`run_libreoffice(src: Path, target: str, outdir_base: Path, idx: int, timeout: int = 180, soffice=None)`
   Returns a Path to the converted file, or None on failure.
   - if `soffice is None`: `soffice = SOFFICE`.
   - `prof = (outdir_base / f"prof_{idx}").as_uri()`.
   - `outdir = outdir_base / f"out_{idx}"`; `outdir.mkdir(parents=True, exist_ok=True)`.
   - `cmd = [str(soffice), "-env:UserInstallation=" + prof, "--headless", "--norestore", "--convert-to", target, "--outdir", str(outdir), str(src)]`.
   - try: `result = subprocess.run(cmd, capture_output=True, timeout=timeout)` except `(subprocess.TimeoutExpired, OSError): return None`.
   - `out_file = outdir / (src.stem + "." + target)`.
   - Poll for file stabilization: `last_size = -1`; for `_ in range(360)` (~180 seconds):
       if `out_file.exists()`: `size = out_file.stat().st_size`; if `size > 0 and size == last_size`: return `out_file`; `last_size = size`;
       `time.sleep(0.5)`.
   - return None.

Now output the complete legacy.py source, starting with the coding line.