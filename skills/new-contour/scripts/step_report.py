# -*- coding: utf-8 -*-
"""HL-4 — step reporting to the Censor.

Every meaningful step (unit of progress: 'starting X', 'X done with result Y',
'blocked on Z', 'irreversible decision needs operator') gets one of these. The
trail IS the contour's evidence pack — silent progress is unverifiable progress.

Usage:
  python step_report.py \
    --from tester \
    --step "install test APK + launch AtomFast app" \
    --status start \
    --action-class reversible \
    --body-file step.txt \
    [--in-reply-to <msg_id>] [--refs id1,id2,...]

Status values:
  start              — beginning the step
  done               — completed (body should include the fact trail)
  blocked            — stuck (body explains what's needed)
  decision-request   — irreversible action requires operator's own-channel «да»
                       (Censor cannot authorize irreversible; routes to operator)

action-class:
  read-only | reversible | irreversible
  irreversible → envelope's requires_operator flag is set automatically.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bus_lib import send

VALID_STATUS = {"start", "done", "blocked", "decision-request"}
VALID_ACTION_CLASS = {"read-only", "reversible", "irreversible"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True, help="Sender role (this contour)")
    ap.add_argument("--step", required=True, help="Short step description (subject line)")
    ap.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    ap.add_argument("--action-class", dest="action_class", required=True,
                    choices=sorted(VALID_ACTION_CLASS))
    ap.add_argument("--body-file", required=True,
                    help="Path to UTF-8 file with the step body. Must include: intent, fact "
                         "trail (file:line / adb output / device reading), delegation "
                         "provenance (subagent task-id OR Ollama helper used OR 'solo' "
                         "with reason).")
    ap.add_argument("--to", default="censor", help="Destination role (default: censor)")
    ap.add_argument("--in-reply-to", dest="in_reply_to", default=None)
    ap.add_argument("--refs", default="", help="Comma-separated reference ids/SHAs/URLs")
    args = ap.parse_args()

    body = Path(args.body_file).read_text(encoding="utf-8")
    if len(body.strip()) < 20:
        print("ERROR: step body too short. Include intent + fact trail + delegation "
              "provenance — silent progress is unverifiable progress (HL-4).",
              file=sys.stderr)
        sys.exit(2)

    refs = [r.strip() for r in args.refs.split(",") if r.strip()]

    subject = f"step[{args.status}]: {args.step}"

    msg_id, fname = send(
        frm=args.frm,
        to=args.to,
        etype="step_report",
        subject=subject,
        body=body,
        refs=refs,
        action_class=args.action_class,
        in_reply_to=args.in_reply_to,
    )

    print(f"SENT step_report id={msg_id} to={args.to} status={args.status} "
          f"action_class={args.action_class} file={fname}")
    if args.action_class == "irreversible" and args.status != "decision-request":
        print("WARN: action_class=irreversible but status is not decision-request — "
              "HL-2 says irreversible steps must NOT execute, only request decision "
              "from the operator in your OWN channel. Did you mean --status decision-request?",
              file=sys.stderr)


if __name__ == "__main__":
    main()
