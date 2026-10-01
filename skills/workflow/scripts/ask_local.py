import argparse, json, os, sys
sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vram_guard_reference import guarded_generate, wrap_untrusted, VramGuardFailure, GUARD_VERSION

VERSION = "1.0"
EXIT_OK, EXIT_USAGE, EXIT_EMPTY, EXIT_TRUNCATED, EXIT_NOT_JSON, EXIT_TOO_BIG, EXIT_GUARD, EXIT_BATCH_PARTIAL, EXIT_HTTP = 0, 2, 3, 4, 5, 6, 7, 8, 9
DEFAULT_MODEL = "qwen3.6:27b"        # overridden by env ASK_LOCAL_MODEL, then by --model
CHARS_PER_TOKEN = 2.0                # deliberately pessimistic for Cyrillic
MAX_CONSECUTIVE_FAILURES = 3         # batch aborts after this many records in a row failed with EXIT_GUARD/EXIT_HTTP

def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1

def build_prompt(template: str, data: str) -> str:
    return template.rstrip() + "\n\n" + wrap_untrusted(data, "DATA")

def check_fits(prompt: str, num_ctx: int, num_predict: int) -> None:
    need = estimate_tokens(prompt) + num_predict
    if need > num_ctx:
        raise ValueError(f"input needs ~{need} tokens (prompt+num_predict) but num_ctx={num_ctx}")

def call_one(model, prompt, *, fmt, num_ctx, num_predict, agent, project, priority, think, timeout_s) -> dict:
    # 1. check fits
    try:
        check_fits(prompt, num_ctx, num_predict)
    except ValueError as e:
        return {
            "ok": False,
            "exit": EXIT_TOO_BIG,
            "response": "",
            "parsed": None,
            "error": str(e),
            "raw": "",
            "tier": None
        }

    # 2. call guard
    try:
        r = guarded_generate(
            model, prompt, want_gpu=True, priority=priority, project=project, agent=agent,
            fmt=("json" if fmt == "json" else None), temperature=0.0, num_ctx=num_ctx, timeout_s=timeout_s,
            num_predict=num_predict, think=think
        )
    except VramGuardFailure as e:
        return {
            "ok": False,
            "exit": EXIT_GUARD,
            "response": "",
            "parsed": None,
            "error": f"vram_guard: {e}",
            "raw": "",
            "tier": "vram_guard"
        }
    except Exception as e:
        return {
            "ok": False,
            "exit": EXIT_HTTP,
            "response": "",
            "parsed": None,
            "error": f"{type(e).__name__}: {e}",
            "raw": "",
            "tier": "http"
        }

    # 3. extract response
    resp = (r.get("response") or "").strip()
    raw = resp
    meta = {k: r.get(k) for k in ("done", "done_reason", "eval_count", "prompt_eval_count", "total_duration", "load_duration", "eval_duration")}

    # 4. check done_reason
    if r.get("done_reason") != "stop":
        return {
            "ok": False,
            "exit": EXIT_TRUNCATED,
            "response": resp,
            "parsed": None,
            "error": f"done_reason={r.get('done_reason')!r}",
            "raw": raw,
            "tier": None,
            "meta": meta
        }

    # 5. check empty
    if not resp:
        err_msg = "empty response"
        if r.get("thinking"):
            err_msg += " (output went to thinking)"
        return {
            "ok": False,
            "exit": EXIT_EMPTY,
            "response": "",
            "parsed": None,
            "error": err_msg,
            "raw": raw,
            "tier": None,
            "meta": meta
        }

    # 6. parse json if needed
    parsed = None
    if fmt == "json":
        try:
            parsed = json.loads(resp)
        except json.JSONDecodeError as e:
            return {
                "ok": False,
                "exit": EXIT_NOT_JSON,
                "response": resp,
                "parsed": None,
                "error": f"not JSON: {e}",
                "raw": raw,
                "tier": None,
                "meta": meta
            }

    # 7. success
    return {
        "ok": True,
        "exit": EXIT_OK,
        "response": resp,
        "parsed": parsed,
        "error": None,
        "raw": raw,
        "tier": None
    }

def failure_json(model, res, source) -> str:
    return json.dumps({"ollama_failure": {"model": model, "error": res["error"], "tier": res.get("tier"), "file": source}}, ensure_ascii=False)

def read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()

def iter_records(args):
    if args.input:
        text = read_text(args.input)
        yield os.path.basename(args.input), text
    elif args.input_dir:
        files, ignored = [], []
        for fname in sorted(os.listdir(args.input_dir)):
            fpath = os.path.join(args.input_dir, fname)
            if not os.path.isfile(fpath):
                continue
            if fname.endswith(".txt") or fname.endswith(".md"):
                files.append((fname, fpath))
            else:
                ignored.append(fname)
        if ignored:
            print(f"ignored (not .txt/.md): {len(ignored)}: " + ", ".join(ignored), file=sys.stderr)
        for fname, fpath in files:
            text = read_text(fpath)
            yield fname, text
    elif args.jsonl:
        with open(args.jsonl, encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    raise ValueError(f"line {line_no}: invalid JSON")
                if "id" not in obj or "text" not in obj:
                    raise ValueError(f"line {line_no}: missing 'id' or 'text'")
                yield str(obj["id"]), str(obj["text"])

def done_ids(out_path: str) -> set:
    ids = set()
    if not os.path.exists(out_path):
        return ids
    try:
        with open(out_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("ok"):
                        ids.add(obj["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    except Exception:
        pass
    return ids

def run_single(args, template) -> int:
    try:
        record_id, text = next(iter_records(args))
    except StopIteration:
        print("no records found", file=sys.stderr)
        return EXIT_USAGE

    prompt = build_prompt(template, text)
    res = call_one(
        args.model, prompt,
        fmt=args.format, num_ctx=args.num_ctx, num_predict=args.num_predict,
        agent=args.agent, project=args.project, priority=args.priority,
        think=True if args.think else None, timeout_s=args.timeout
    )

    if not res["ok"]:
        if res["exit"] in (EXIT_GUARD, EXIT_HTTP):
            print(failure_json(args.model, res, record_id))
        
        if res["raw"]:
            rejected_path = args.out + ".rejected.txt"
            with open(rejected_path, "w", encoding="utf-8") as f:
                f.write(res["raw"])
        
        print(res["error"], file=sys.stderr)
        if res.get("meta"):
            print("meta: " + json.dumps(res["meta"]), file=sys.stderr)
        return res["exit"]

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(res["response"])
    
    print(f"ok: {record_id}", file=sys.stderr)
    return EXIT_OK

def run_batch(args, template) -> int:
    skip_ids = done_ids(args.out) if args.resume else set()
    mode = "a" if args.resume else "w"
    
    ok_count = 0
    fail_count = 0
    skip_count = 0
    consecutive_failures = 0

    with open(args.out, mode=mode, encoding="utf-8") as out_f:
        try:
            for record_id, text in iter_records(args):
                if record_id in skip_ids:
                    skip_count += 1
                    continue

                prompt = build_prompt(template, text)
                res = call_one(
                    args.model, prompt,
                    fmt=args.format, num_ctx=args.num_ctx, num_predict=args.num_predict,
                    agent=args.agent, project=args.project, priority=args.priority,
                    think=True if args.think else None, timeout_s=args.timeout
                )

                line_obj = {
                    "id": record_id,
                    "ok": res["ok"],
                    "exit": res["exit"],
                    "result": res["parsed"] if res["parsed"] is not None else (res["response"] if res["response"] else None),
                    "error": res["error"],
                    **({"meta": res["meta"]} if (not res["ok"] and res.get("meta")) else {})
                }
                out_f.write(json.dumps(line_obj, ensure_ascii=False) + "\n")
                out_f.flush()

                if res["ok"]:
                    ok_count += 1
                    consecutive_failures = 0
                else:
                    fail_count += 1
                    if res["exit"] in (EXIT_GUARD, EXIT_HTTP):
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            print("aborting: guard/http failing repeatedly", file=sys.stderr)
                            return EXIT_GUARD
                    else:
                        consecutive_failures = 0

        except ValueError as e:
            print(str(e), file=sys.stderr)
            return EXIT_USAGE

    print(f"ok={ok_count} failed={fail_count} skipped={skip_count}", file=sys.stderr)
    if ok_count == 0 and fail_count == 0 and skip_count == 0:
        print("empty batch: 0 records processed", file=sys.stderr)
        return EXIT_EMPTY
    if fail_count == 0:
        return EXIT_OK
    else:
        return EXIT_BATCH_PARTIAL

def main(argv=None) -> int:
    # Handle --version before parsing required args
    if argv is None:
        argv = sys.argv[1:]
    
    if "--version" in argv or "-v" in argv:
        print(f"ask_local {VERSION} guard {GUARD_VERSION}")
        return 0

    parser = argparse.ArgumentParser(description="Local LLM call for non-code tasks")
    parser.add_argument("--prompt", required=True, help="Path to trusted template file")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="Single input file")
    group.add_argument("--input-dir", help="Directory of input files")
    group.add_argument("--jsonl", help="JSONL input file")
    
    parser.add_argument("--out", required=True, help="Output file path")
    parser.add_argument("--model", default=os.environ.get("ASK_LOCAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--num-predict", type=int, default=4000)
    parser.add_argument("--agent", default="ask_local")
    parser.add_argument("--project", default="unknown")
    parser.add_argument("--priority", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--think", action="store_true", default=False)
    parser.add_argument("--resume", action="store_true", default=False)

    args = parser.parse_args(argv)

    # Validate prompt file
    if not os.path.exists(args.prompt):
        print(f"prompt file not found: {args.prompt}", file=sys.stderr)
        return EXIT_USAGE

    # Resume only meaningful for batch inputs
    if args.resume and args.input:
        pass # ignored as per spec, but we could warn. Spec says "ignored".

    template = read_text(args.prompt)
    
    try:
        if args.input:
            return run_single(args, template)
        else:
            return run_batch(args, template)
    except (ValueError, OSError) as e:  # bad jsonl line / unreadable or missing input -> usage error, not a traceback
        print(str(e), file=sys.stderr)
        return EXIT_USAGE

if __name__ == "__main__":
    sys.exit(main())
