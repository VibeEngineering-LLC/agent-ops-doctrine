"""Reusable Ollama codegen driver (workflow skill, IRON-MODE harness).
Claude authors the spec (.md); qwen3-coder:30b generates the code; this helper saves it.
Imports guarded_generate from the sibling vram_guard_reference.py (self-contained).
Usage: python gen_code.py <spec.md> <out.py> [num_predict=6000] [num_ctx=16384]"""
import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from vram_guard_reference import guarded_generate  # type: ignore
spec = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
out = pathlib.Path(sys.argv[2])
npred = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
nctx = int(sys.argv[4]) if len(sys.argv) > 4 else 16384
model = sys.argv[5] if len(sys.argv) > 5 else "qwen3-coder:30b"
resp = guarded_generate(model=model, prompt=spec, fmt=None, want_gpu=True,
    priority=50, max_wait_s=900, temperature=0, num_ctx=nctx, extra_options={"num_predict": npred})
text = resp.get("response", "") if isinstance(resp, dict) else str(resp)
t = text.strip()
if t.startswith("```"):
    t = t.split("\n", 1)[1] if "\n" in t else t
    if t.rstrip().endswith("```"): t = t.rstrip()[:-3]
out.write_text(t.strip() + "\n", encoding="utf-8")
print(f"[gen] {len(t)} chars -> {out} | {model} npred={npred}", file=sys.stderr)
