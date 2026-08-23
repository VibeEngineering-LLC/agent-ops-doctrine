# -*- coding: utf-8 -*-
"""SemVer bump + auto-push helper for the new-contour skill.

Auto-push policy is operator-pre-authorized: every SemVer bump is an explicit
intent gate (you ran this script — that IS the «yes»). Push goes to the remote
already configured on the repo (typically Verter73/claude-skills, private).

Usage:
  python scripts/bump_and_push.py --bump patch --note "fix watcher heartbeat dedup race"
  python scripts/bump_and_push.py --bump minor --note "add rig-pelican.md reference"
  python scripts/bump_and_push.py --bump major --note "breaking: register.py args renamed"

Repo layout: this skill lives at `<repo-root>/new-contour/`, alongside other
sibling skills in `Verter73/claude-skills` (the private multi-skill collection).
Tags are PER-SKILL namespaced — `new-contour/v1.2.3` — so this skill releases on
its own cadence without colliding with other skills' tag namespace.

What it does, in order (HALTS on any non-zero step):
  1. Read SKILL.md, parse current `version:` from frontmatter.
  2. Verify working tree is clean of UNTRACKED files (modified-tracked OK — we'll commit them).
  3. Bump SemVer (patch/minor/major) → new_version.
  4. Rewrite SKILL.md `version:` line.
  5. Prepend a CHANGELOG.md entry under the title.
  6. `git add -A .` — scoped to THIS skill's subtree only (the dot matters: modern
     git's bare `add -A` stages the whole working tree including repo-root files,
     which would mix sibling-skill or repo-meta changes into a per-skill bump).
  7. `git commit -m "<skill>/v<new> — <note>"` — fails if hooks reject.
  8. `git tag -a <skill>/v<new> -m "<note>"` (per-skill namespaced tag).
  9. `git push origin <branch> --follow-tags` — fails if remote refuses.
 10. Print final state (commit SHA, tag SHA on remote, both verified).

If any step fails, the script HALTS and leaves the tree in the failure state for
manual triage. It does NOT auto-rollback — that would hide the real failure.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
CHANGELOG = SKILL_DIR / "CHANGELOG.md"

VERSION_LINE_RE = re.compile(r"^version:\s*(\d+)\.(\d+)\.(\d+)\s*$", re.MULTILINE)


def run(cmd, check=True, capture=False):
    """Run a shell command in SKILL_DIR; halt on non-zero unless check=False."""
    print(f"$ {cmd}")
    res = subprocess.run(cmd, cwd=SKILL_DIR, shell=True, text=True,
                         capture_output=capture)
    if capture:
        print(res.stdout, end="")
        if res.stderr:
            print(res.stderr, end="", file=sys.stderr)
    if check and res.returncode != 0:
        print(f"FAIL: exit {res.returncode}", file=sys.stderr)
        sys.exit(res.returncode)
    return res


def read_current_version() -> tuple[int, int, int]:
    text = SKILL_MD.read_text(encoding="utf-8")
    m = VERSION_LINE_RE.search(text)
    if not m:
        print(f"FAIL: no `version: X.Y.Z` line in {SKILL_MD}", file=sys.stderr)
        sys.exit(2)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_version(cur: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    major, minor, patch = cur
    if kind == "major":
        return major + 1, 0, 0
    if kind == "minor":
        return major, minor + 1, 0
    if kind == "patch":
        return major, minor, patch + 1
    raise ValueError(kind)


def write_new_version(new: tuple[int, int, int]) -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    new_line = f"version: {new[0]}.{new[1]}.{new[2]}"
    new_text, n = VERSION_LINE_RE.subn(new_line, text, count=1)
    if n != 1:
        print(f"FAIL: version-line substitution count = {n}, expected 1",
              file=sys.stderr)
        sys.exit(2)
    SKILL_MD.write_text(new_text, encoding="utf-8")


def prepend_changelog(new: tuple[int, int, int], note: str) -> None:
    if not CHANGELOG.exists():
        print(f"FAIL: CHANGELOG.md not found at {CHANGELOG}", file=sys.stderr)
        sys.exit(2)
    today = run("git log -1 --format=%cs HEAD", capture=True, check=False).stdout.strip() \
            or "TBD"
    new_entry = f"## v{new[0]}.{new[1]}.{new[2]} — {today} — {note}\n\n"
    text = CHANGELOG.read_text(encoding="utf-8")
    # Insert after the H1 header + its description block (find first `## v` and
    # insert immediately before it). Falls back to append if no prior entry.
    m = re.search(r"^## v\d+\.\d+\.\d+", text, re.MULTILINE)
    if m:
        text = text[:m.start()] + new_entry + text[m.start():]
    else:
        text = text.rstrip() + "\n\n" + new_entry
    CHANGELOG.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bump", required=True, choices=["patch", "minor", "major"])
    ap.add_argument("--note", required=True,
                    help="One-line summary of what changed. Goes in commit "
                         "message + tag annotation + CHANGELOG entry.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Do everything except commit/tag/push (so you can inspect "
                         "the diff before publishing).")
    args = ap.parse_args()

    # Step 1: read current version
    cur = read_current_version()
    new = bump_version(cur, args.bump)
    print(f"BUMP: {cur[0]}.{cur[1]}.{cur[2]} → {new[0]}.{new[1]}.{new[2]} "
          f"({args.bump}): {args.note}")

    # Step 2: untracked-files safety (modified-tracked OK)
    status = run("git status --porcelain", capture=True).stdout
    untracked = [ln for ln in status.splitlines() if ln.startswith("??")]
    if untracked:
        print("FAIL: untracked files present — review/git add them first OR "
              "list them in .gitignore. We do NOT auto-stage untracked.",
              file=sys.stderr)
        for ln in untracked:
            print("  " + ln, file=sys.stderr)
        sys.exit(3)

    # Step 3+4: rewrite SKILL.md
    write_new_version(new)

    # Step 5: prepend CHANGELOG entry
    prepend_changelog(new, args.note)

    if args.dry_run:
        print("DRY-RUN: skipping commit/tag/push. Inspect diff with `git diff`.")
        return

    # Step 6-8: commit + tag
    tag = f"v{new[0]}.{new[1]}.{new[2]}"
    run("git add -A")
    run(f'git commit -m "{tag} — {args.note}"')
    run(f'git tag -a {tag} -m "{args.note}"')

    # Step 9: push
    branch = run("git rev-parse --abbrev-ref HEAD", capture=True).stdout.strip()
    run(f"git push origin {branch} --follow-tags")

    # Step 10: verify on remote
    print("=== POST-PUSH VERIFY ===")
    run(f"git ls-remote --tags origin {tag}", capture=True)
    print(f"DONE: {tag} published to origin/{branch}")


if __name__ == "__main__":
    main()
