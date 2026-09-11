#!/usr/bin/env python3
"""Token-aware rebrand sweep of the live GitHub issue + PR corpus (#338).

This is a *GitHub-metadata-only* sweep: it rewrites issue/PR **titles and
bodies** off the old "Agent Fabric SDK" brand to "Donkey Development Kit (DDK)".
It touches no repo files and no package code (those renames are owned by sibling
sub-issues of epic #343).

DEFAULT MODE IS DRY-RUN. Without ``--apply`` the script performs **zero** writes:
it enumerates the corpus, computes the rewrite for every object, and emits a
reviewable unified-diff report. ``--apply`` is the only path that mutates live
GitHub state, and it is sequenced *after* this script's PR is reviewed/merged and
*after* #327 (the org/repo rename) has landed, so the rewritten
``github.com/...`` URLs resolve.

Token map + retained-literal allowlist are kept in lockstep with the tree-wide
completeness gate ``scripts/check-rebrand.sh`` (#340): the same four retained
literals it masks out are masked here, so this sweep never rewrites a MuleSoft
product reference.

CLOSED-ITEM POLICY: closed issues/PRs are edited **in place** by default. GitHub
preserves full edit history on the object, so an in-place body rewrite is
non-destructive and keeps the corpus internally consistent (the alternative —
leaving closed items with stale ``agent_fabric``/old-URL content — is the
confusing trail this sweep exists to remove). Pass ``--skip-closed`` to restrict
the sweep to open items only.

Usage::

    # Dry-run (default): write the diff report, mutate nothing.
    python scripts/rebrand/sweep_issues.py

    # Hard-assert the live counts (fail loudly on a partial fetch).
    python scripts/rebrand/sweep_issues.py --expect-issues 192 --expect-prs 54

    # Apply — only after the PR merges and #327 has landed.
    python scripts/rebrand/sweep_issues.py --apply

Requires the ``gh`` CLI, authenticated against the repo below.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import unified_diff
from pathlib import Path

REPO = "Donkey-Development-Kit/donkey-development-kit"

# Rebrand meta-objects — EXCLUDED from the sweep by default. Their text
# intentionally contrasts the OLD brand with the NEW ("Rename Fabric* ->
# Donkey*", "replaces Agent Fabric SDK with Donkey Development Kit"), exactly
# like MIGRATION.md and spec/archive/** — sweeping them collapses "old -> new"
# into "new -> new" and erases (or fabricates) the historical record of a
# rename. Override with --sweep-rebrand-meta.
#
# Two generations of rename meta-objects are excluded:
#   1. This DDK rebrand: every sub-issue + the epic carries the `rebrand`
#      label; the implementation PR (#344) does not, so it is listed explicitly.
#   2. The EARLIER "MuleSoft Agent Fabric SDK" -> "Agent Fabric SDK" rebrand
#      (issue #156 + PR #159). These predate the `rebrand` label and record the
#      old->new dist/env map for THAT rename (`mulesoft-agent-fabric` ->
#      `agent-fabric`, `MULESOFT_*` -> `AGENT_FABRIC_*`); sweeping them invents
#      a `mulesoft-donkey-kit` that never shipped and misstates what #159 did.
REBRAND_LABEL = "rebrand"
EXCLUDE_PR_NUMBERS = {344, 159}     # 344: this DDK rebrand; 159: the earlier "to Agent Fabric SDK" rebrand
EXCLUDE_ISSUE_NUMBERS = {156}       # "Rebrand initiative to Agent Fabric SDK" — the earlier rename

# Where the dry-run report is written. Gitignored — it is a generated artifact,
# not committed source (see .gitignore).
DEFAULT_OUT = Path(__file__).resolve().parent / "sweep-report"

# The CLI subcommands (provisioning + simulator/scanner/a2a). Used to
# disambiguate the console-script invocation `agent-fabric <cmd>` (-> `donkey
# <cmd>`) from the PyPI dist name `agent-fabric` (-> `donkey-kit`), which share
# the same bare token. Bare `fabric <cmd>` is handled by the \bfabric\b rule;
# this list only rescues the *hyphenated* `agent-fabric <cmd>` form from being
# read as the dist name.
CLI_SUBCOMMANDS = (
    "validate", "plan", "apply", "drift", "lint",
    "generate", "status", "init", "publish", "verify",
    "mock", "scan", "dev", "serve", "expose", "doctor",
)

# --------------------------------------------------------------------------- #
# Retained MuleSoft product references — masked to a sentinel BEFORE any
# substitution runs, then restored verbatim at the end. This is the guard that
# must not regress: it mirrors the mask list in scripts/check-rebrand.sh.
#
# Order matters: the two hyphenated literals contain `agent-fabric`, so they
# must be masked before the `agent-fabric` -> `donkey-kit` substitution can
# corrupt them. "Agent Fabric SDK" (our old brand) is replaced BEFORE the bare
# "Agent Fabric" product phrase is masked, or the mask would eat its prefix.
# --------------------------------------------------------------------------- #
_S = "\x00"  # sentinel delimiter, cannot occur in GitHub text
MASKS: list[tuple[str, str]] = [
    ("mulesoft-anypoint-cli-agent-fabric-plugin", f"{_S}PLUGIN{_S}"),
    ("agent-fabric-transformation", f"{_S}MAVEN{_S}"),   # covers the bare + Maven-coord forms
    ("Agent Fabric", f"{_S}PRODUCT{_S}"),                # bare two-word product prose
]
UNMASKS: list[tuple[str, str]] = [
    (f"{_S}PLUGIN{_S}", "mulesoft-anypoint-cli-agent-fabric-plugin"),
    (f"{_S}MAVEN{_S}", "agent-fabric-transformation"),
    (f"{_S}PRODUCT{_S}", "Agent Fabric"),
]

# Ordered literal substitutions (applied in sequence; longer/more-specific first).
STR_SUBS: list[tuple[str, str]] = [
    # 1: our old brand -> new brand (BEFORE "Agent Fabric" is masked).
    ("Agent Fabric SDK", "Donkey Development Kit (DDK)"),
    # (masking happens here, between these two blocks — see rewrite())
    # 2: org / repo / Pages slugs (demos before base so the suffix is preserved).
    ("agent-fabric-sdk.github.io/agent-fabric-sdk", "donkey-development-kit.github.io/donkey-development-kit"),
    ("Agent-Fabric-SDK/agent-fabric-sdk-demos", "Donkey-Development-Kit/donkey-development-kit-demos"),
    ("Agent-Fabric-SDK/agent-fabric-sdk", "Donkey-Development-Kit/donkey-development-kit"),
    ("Agent-Fabric-SDK", "Donkey-Development-Kit"),
    ("agent-fabric-sdk-demos", "donkey-development-kit-demos"),
    ("agent-fabric-sdk", "donkey-development-kit"),
    # 3: PyPI dist install forms (explicit, so they map to the dist name donkey-kit).
    ("pip install agent-fabric", "pip install donkey-kit"),
    ("agent-fabric[", "donkey-kit["),
    # 4: identifiers / testing / simulator (specific before generic).
    ("agent_fabric_conformance", "donkey_kit_conformance"),
    ("--fabric-conformance", "--donkey-conformance"),
    ("x-fabric-simulator", "x-donkey-simulator"),
    ("agent_fabric", "donkey_kit"),
    ("AGENT_FABRIC_", "DONKEY_"),
    ("FABRIC_", "DONKEY_"),
    (".agent-fabric.toml", ".donkey-kit.toml"),
    ("fabric.lock", "donkey.lock"),
    # backticked bare CLI command -> new command name (a lone token is the CLI).
    ("`agent-fabric`", "`donkey`"),
    # remaining hyphenated form defaults to the PyPI dist name.
    ("agent-fabric", "donkey-kit"),
    # skill prefix / abbreviation.
    ("afdk-", "ddk-"),
    ("AFDK", "DDK"),
    ("afdk", "ddk"),
    # 5a: specific class names (before the bare \bFabric\b catch-all).
    ("FabricAsyncClient", "DonkeyAsyncClient"),
    ("FabricClient", "DonkeyClient"),
    ("FabricConfig", "DonkeyConfig"),
    ("FabricError", "DonkeyError"),
    ("FabricSpec", "DonkeySpec"),
]

# The console-script invocation `agent-fabric <subcommand>` -> `donkey <subcommand>`.
# Run BEFORE the generic `agent-fabric` -> `donkey-kit` literal above (handled in
# rewrite() by applying this regex first).
_CLI_INVOKE = re.compile(r"\bagent-fabric (" + "|".join(CLI_SUBCOMMANDS) + r")\b")

# 5b/5c: word-boundary class + instance/namespace renames. `\bfabric\b` catches
# `fabric.run()`, `fabric.py`, `[fabric]`, and the OTel `fabric.*` namespace,
# while the word boundary leaves "fabricated"/"fabrication" prose untouched
# (matching the gate's [Ff]abricat[a-z]* mask).
RE_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bFabric\b"), "Donkey"),
    (re.compile(r"\bfabric\b"), "donkey"),
]


def rewrite(text: str) -> str:
    """Apply the ordered token map to a single title or body string."""
    if not text:
        return text
    out = text
    # 1: our brand first, before masking the bare product phrase.
    out = out.replace("Agent Fabric SDK", "Donkey Development Kit (DDK)")
    # 2: mask retained product references.
    for old, sent in MASKS:
        out = out.replace(old, sent)
    # 3: CLI-invocation disambiguation before the generic agent-fabric literal.
    out = _CLI_INVOKE.sub(r"donkey \1", out)
    # 4: the remaining ordered literal substitutions (skip the brand entry at [0],
    #    already applied above).
    for old, new in STR_SUBS[1:]:
        out = out.replace(old, new)
    # 5: word-boundary class/instance/namespace renames.
    for rx, new in RE_SUBS:
        out = rx.sub(new, out)
    # 6: restore retained references.
    for sent, orig in UNMASKS:
        out = out.replace(sent, orig)
    return out


def gh_json(args: list[str]) -> list[dict]:
    """Run a `gh ... --json` command and parse the JSON array."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    )
    return json.loads(proc.stdout)


def fetch(kind: str, limit: int) -> list[dict]:
    """Enumerate all issues (kind='issue') or PRs (kind='pr'), both states.

    `gh issue list` excludes PRs by default, so the two calls do not overlap.
    Guards against silent truncation: if `gh` returns exactly `limit` rows the
    fetch may be incomplete, so we abort rather than sweep a partial set.
    """
    rows = gh_json([
        kind, "list", "--repo", REPO, "--state", "all",
        "--limit", str(limit),
        "--json", "number,title,body,url,state,labels",
    ])
    if len(rows) >= limit:
        sys.exit(
            f"ERROR: {kind} fetch returned {len(rows)} rows == --limit {limit}; "
            f"the corpus may be truncated. Re-run with a higher --limit."
        )
    return rows


def rate_limit() -> str:
    """Return a one-line summary of the REST core rate-limit budget."""
    try:
        proc = subprocess.run(
            ["gh", "api", "rate_limit", "--jq", ".resources.core"],
            capture_output=True, text=True, check=True,
        )
        core = json.loads(proc.stdout)
        return f"core: {core['remaining']}/{core['limit']} remaining"
    except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
        return "core: (unavailable)"


def diff_block(number: int, kind: str, field: str, before: str, after: str) -> str:
    """Unified diff for one changed field of one object."""
    lines = unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{kind}#{number} {field} (before)",
        tofile=f"{kind}#{number} {field} (after)",
        lineterm="",
    )
    return "\n".join(lines)


def apply_edit(kind: str, number: int, new_title: str, new_body: str) -> None:
    """Write the rewritten title/body back via `gh {issue,pr} edit`."""
    subprocess.run(
        ["gh", kind, "edit", str(number), "--repo", REPO,
         "--title", new_title, "--body", new_body],
        check=True, capture_output=True, text=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Write changes to live GitHub. Omit for a dry-run (default).")
    ap.add_argument("--limit", type=int, default=1000,
                    help="Per-list fetch ceiling; also the truncation guard (default 1000).")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="Directory for the dry-run diff report.")
    ap.add_argument("--expect-issues", type=int, default=None,
                    help="Assert the exact live issue count; exit non-zero on mismatch.")
    ap.add_argument("--expect-prs", type=int, default=None,
                    help="Assert the exact live PR count; exit non-zero on mismatch.")
    ap.add_argument("--skip-closed", action="store_true",
                    help="Sweep only open items (default: closed items edited in place).")
    ap.add_argument("--sweep-rebrand-meta", action="store_true",
                    help="Also sweep rebrand meta-issues/PRs (default: excluded — they "
                         "record the old->new map and would be corrupted).")
    ap.add_argument("--workers", type=int, default=8,
                    help="Parallel gh-edit workers used under --apply (default 8).")
    ap.add_argument("--only", default=None,
                    help="Comma-separated kind#number refs (e.g. 'issue#56,pr#160'); "
                         "under --apply, restrict writes to just these — a canary. "
                         "The dry-run report still covers the whole corpus.")
    args = ap.parse_args()

    only_set = {r.strip() for r in args.only.split(",")} if args.only else None

    print(f"[rebrand-sweep] repo={REPO}  mode={'APPLY' if args.apply else 'dry-run'}")
    print(f"[rebrand-sweep] rate limit before: {rate_limit()}")

    issues = fetch("issue", args.limit)
    prs = fetch("pr", args.limit)
    print(f"[rebrand-sweep] fetched {len(issues)} issues + {len(prs)} PRs "
          f"= {len(issues) + len(prs)} objects")

    # Live-count assertions (opt-in; not hardcoded to a stale total).
    if args.expect_issues is not None and len(issues) != args.expect_issues:
        sys.exit(f"ERROR: expected {args.expect_issues} issues, fetched {len(issues)}.")
    if args.expect_prs is not None and len(prs) != args.expect_prs:
        sys.exit(f"ERROR: expected {args.expect_prs} PRs, fetched {len(prs)}.")

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale per-object diffs from a prior run, so an object that is now
    # unchanged/excluded does not leave an orphan .diff misreading the report.
    for stale in out_dir.glob("*.diff"):
        stale.unlink()

    title_changed = body_changed = unchanged = 0
    fabric_titles: list[str] = []   # titles still containing bare "fabric"/"Fabric" after rewrite
    summary_rows: list[str] = []
    excluded_meta: list[str] = []
    edits: list[tuple[str, int, str, str]] = []   # (kind, number, new_title, new_body)

    for kind, rows in (("issue", issues), ("pr", prs)):
        for obj in rows:
            number = obj["number"]
            state = obj.get("state", "")
            if args.skip_closed and state.upper() != "OPEN":
                continue
            # Skip rebrand meta-objects unless explicitly overridden.
            labels = {lb.get("name", "") for lb in obj.get("labels", [])}
            is_meta = (
                REBRAND_LABEL in labels
                or (kind == "pr" and number in EXCLUDE_PR_NUMBERS)
                or (kind == "issue" and number in EXCLUDE_ISSUE_NUMBERS)
            )
            if is_meta and not args.sweep_rebrand_meta:
                excluded_meta.append(f"{kind}#{number}")
                continue
            title = obj.get("title") or ""
            body = obj.get("body") or ""
            new_title = rewrite(title)
            new_body = rewrite(body)

            t_diff = new_title != title
            b_diff = new_body != body
            if not (t_diff or b_diff):
                unchanged += 1
                continue

            title_changed += int(t_diff)
            body_changed += int(b_diff)

            # Flag titles that still carry a bare fabric/Fabric token after the
            # rewrite — these are the "descriptive prose about the renamed API"
            # cases the issue calls out for a human eyeball.
            if re.search(r"\b[Ff]abric\b", new_title):
                fabric_titles.append(f"{kind}#{number}: {new_title}")

            parts = [f"# {kind}#{number}  ({state})  {obj.get('url', '')}", ""]
            if t_diff:
                parts.append(diff_block(number, kind, "title", title, new_title))
                parts.append("")
            if b_diff:
                parts.append(diff_block(number, kind, "body", body, new_body))
            (out_dir / f"{kind}-{number}.diff").write_text(
                "\n".join(parts) + "\n", encoding="utf-8"
            )
            summary_rows.append(
                f"- {kind}#{number} ({state}): "
                f"{'title' if t_diff else ''}{'+body' if (t_diff and b_diff) else ('body' if b_diff else '')}"
            )
            edits.append((kind, number, new_title, new_body))

    # Apply (parallel) — only under --apply; a dry-run stops at the report.
    # --only narrows the write set to a canary subset (report still full).
    apply_edits = edits
    if only_set is not None:
        apply_edits = [e for e in edits if f"{e[0]}#{e[1]}" in only_set]
        missing = only_set - {f"{k}#{n}" for (k, n, _t, _b) in edits}
        if missing:
            sys.exit(f"ERROR: --only refs not in the changed set: {', '.join(sorted(missing))}")

    applied = 0
    if args.apply and apply_edits:
        scope = f" (--only: {', '.join(sorted(only_set))})" if only_set else ""
        print(f"[rebrand-sweep] applying {len(apply_edits)} edits with {args.workers} workers…{scope}")
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(apply_edit, k, n, t, b): f"{k}#{n}" for (k, n, t, b) in apply_edits
            }
            for fut in as_completed(futures):
                ref = futures[fut]
                try:
                    fut.result()
                    applied += 1
                except subprocess.CalledProcessError as exc:
                    errors.append(f"{ref}: {exc.stderr.strip() if exc.stderr else exc}")
        if errors:
            print(f"[rebrand-sweep] {len(errors)} edits FAILED:")
            for line in errors:
                print(f"  - {line}")

    # Write the summary.
    total_changed = len(summary_rows)
    summary = [
        "# Rebrand issue/PR sweep — dry-run report" if not args.apply
        else "# Rebrand issue/PR sweep — APPLIED",
        "",
        f"- Repo: `{REPO}`",
        f"- Corpus: {len(issues)} issues + {len(prs)} PRs = {len(issues) + len(prs)} objects",
        f"- Objects with changes: {total_changed}",
        f"- Titles changed: {title_changed}",
        f"- Bodies changed: {body_changed}",
        f"- Left untouched (no old-brand tokens): {unchanged}",
        f"- Rebrand meta-objects excluded (preserved verbatim): {len(excluded_meta)}",
    ]
    if args.apply:
        summary.append(f"- Objects edited on GitHub: {applied}")
    summary.append("")
    if excluded_meta:
        summary.append("## Rebrand meta-objects EXCLUDED (record the old->new map; "
                       "swept only with --sweep-rebrand-meta):")
        summary.append("  " + ", ".join(excluded_meta))
        summary.append("")
    if fabric_titles:
        summary.append("## Titles still containing a bare `fabric`/`Fabric` token "
                       "(human review — descriptive prose vs. the renamed API):")
        summary.extend(f"- {row}" for row in fabric_titles)
        summary.append("")
    summary.append("## Changed objects")
    summary.extend(summary_rows)
    (out_dir / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"[rebrand-sweep] changed: {total_changed}  "
          f"(titles={title_changed}, bodies={body_changed}), untouched: {unchanged}, "
          f"rebrand-meta excluded: {len(excluded_meta)}")
    if args.apply:
        print(f"[rebrand-sweep] applied {applied} edits to GitHub")
    print(f"[rebrand-sweep] report: {out_dir}/SUMMARY.md  (+ per-object .diff files)")
    print(f"[rebrand-sweep] rate limit after:  {rate_limit()}")
    if not args.apply:
        print("[rebrand-sweep] DRY-RUN: no GitHub writes performed. "
              "Review the report, then re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
