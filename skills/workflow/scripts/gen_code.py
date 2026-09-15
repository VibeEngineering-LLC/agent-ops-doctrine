"""Reusable Ollama codegen driver (workflow skill, IRON-MODE harness).
Claude authors the spec (.md); qwen3-coder:30b generates the code; this helper saves it.
Imports guarded_generate from the sibling vram_guard_reference.py (self-contained).
Usage: python gen_code.py <spec.md> <out.py> [num_predict=16000] [num_ctx=32768]
v1.1 (2026-08-23, P-002): defaults raised (6000 tokens truncated 400-line files
mid-function) and truncated output now FAILS loudly instead of being saved silently.
v1.2 (2026-09-14, надзорный 30.08 + моделирование:W-100): empty `response` -> exit 3 (names the
`thinking` field if present); for a `.py` target a non-Python answer (prose, markdown
report) -> ast.parse fails -> exit 4. In every failure case nothing is written.
v1.3 (2026-09-14, моделирование:W-105): on exit 2/3/4 the rejected answer is kept as
`<target>.rejected.txt` (path printed) so the cause can be read without re-generating;
ast.parse SyntaxWarnings (invalid escapes — errors in future Python) printed per line."""
import ast, sys, pathlib, warnings

def _reject(code: int, msg: str, body: str) -> None:
    rej = out.with_name(out.name + ".rejected.txt")
    rej.write_text(body, encoding="utf-8")
    print(f"[gen] ABORT: {msg} Target not written; rejected answer: {rej}", file=sys.stderr)
    sys.exit(code)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from vram_guard_reference import guarded_generate  # type: ignore
spec = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
out = pathlib.Path(sys.argv[2])
npred = int(sys.argv[3]) if len(sys.argv) > 3 else 16000
nctx = int(sys.argv[4]) if len(sys.argv) > 4 else 32768
model = sys.argv[5] if len(sys.argv) > 5 else "qwen3-coder:30b"
resp = guarded_generate(model=model, prompt=spec, fmt=None, want_gpu=True,
    priority=50, max_wait_s=900, temperature=0, num_ctx=nctx, extra_options={"num_predict": npred})
text = resp.get("response", "") if isinstance(resp, dict) else str(resp)
reason = resp.get("done_reason") if isinstance(resp, dict) else None
if reason and reason != "stop":
    _reject(2, f"truncated (done_reason={reason!r}, eval_count={resp.get('eval_count')}, "
               f"npred={npred}). Raise num_predict or split the spec.", text)
t = text.strip()
if t.startswith("```"):
    t = t.split("\n", 1)[1] if "\n" in t else t
    if t.rstrip().endswith("```"): t = t.rstrip()[:-3]
if not t.strip():
    hint = " Output went to `thinking` — use think=False or a non-thinking model." if isinstance(resp, dict) and resp.get("thinking") else ""
    _reject(3, f"empty response (keys={sorted(resp) if isinstance(resp, dict) else type(resp).__name__}).{hint}",
            (resp.get("thinking") or "") if isinstance(resp, dict) else str(resp))
if out.suffix == ".py":
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ast.parse(t)
        except SyntaxError as e:
            head = "\n".join(t.strip().splitlines()[:3])
            _reject(4, f"not valid Python ({e.msg}, line {e.lineno}). Head:\n{head}\n", t)
    for w in caught:
        print(f"[gen] WARNING: {w.category.__name__} line {w.lineno}: {w.message}", file=sys.stderr)
out.write_text(t.strip() + "\n", encoding="utf-8")
print(f"[gen] {len(t)} chars -> {out} | {model} npred={npred}", file=sys.stderr)
