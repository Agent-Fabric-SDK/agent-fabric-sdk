---
name: afdk-verification-discipline
description: Use when touching any Anypoint endpoint, header, class name, or kwarg in agent-fabric-sdk — before adding/removing a `_verify.blocked` guard or `Unverified` placeholder, flipping a `docs/verified-apis.md` row, or reviewing a PR that claims a surface is "verified". Enforces §0.3 "never invent an endpoint, header, or class name."
---

# Verification discipline (§0.3)

This is the signature workflow of this repo. Working instruction #2, stated in
`CLAUDE.md`, `docs/verified-apis.md`, and every relevant docstring:

> **Never invent an endpoint, header name, or class name.**

A fabricated endpoint that 404s in a customer sandbox destroys trust in the whole
package. The SDK's entire value proposition is that it consumes a *real* MuleSoft
Agent Fabric — so a guessed path, header, or constructor is not a bug, it is a
credibility failure. Everything below exists to make guessing structurally
impossible and to make un-guessing (verifying) a controlled, signed-off act.

**The one rule that governs everything here:** you may state a path, command,
flag, header, or class name only if you have *seen it* — in the repo, in a live
sandbox capture, or read from the official shipping client. If you have not seen
it, it is `UNVERIFIED` and it stays behind a guard. There is no fourth option.

Related runbooks: [[afdk-coding-conventions]] (layered architecture, where these
constants live), [[afdk-pr-review]] and [[afdk-pr-workflow]] (how this gates
review/merge), [[afdk-docs-authoring]] / [[afdk-docs-sync]] (keeping the
source-of-truth doc honest).

---

## The three moving parts

### 1. `core/_verify.py` — the enforcement mechanism

`python/src/agent_fabric/core/_verify.py` is the centralized home for every value
§0.3 says must be verified against a real Anypoint sandbox before it can be
trusted. **Nothing in this module is a verified fact by default.** Each surface is
handled one of three ways:

**(a) `_verify.blocked("…")` — no defensible placeholder exists.**

```python
def blocked(what: str) -> NotImplementedError:
    return NotImplementedError(f"blocked on verification: {what}")
```

Use this where we cannot even responsibly guess — e.g. the MCP Bridge
provisioning endpoint (§5), `fabric.tools.discover`, the provisioning
control-plane. The call site raises `_verify.blocked("…")`. **Do not replace
these with guesses.** Removing one is the last step of the UNBLOCK procedure
below, never a casual edit.

**(b) `Unverified(...)` placeholder constants — a documented best-guess.**

```python
@dataclass(frozen=True)
class Unverified:
    key: str
    placeholder: str
    doc_ref: str
    verified: bool = False

    def get(self) -> str:
        if not self.verified and self.key not in _warned:
            _warned.add(self.key)
            warnings.warn(..., UnverifiedValueWarning, stacklevel=2)
        return self.placeholder
```

- Reading it via `.get()` emits a **one-time** `UnverifiedValueWarning`
  (deduped through the module-level `_warned` set) that names the key, the
  placeholder, and the `doc_ref` row to check.
- The placeholder is a **default the user can and should override** via
  config/env — a customer can point it at the real value without waiting for us.
- Setting `verified=True` on the dataclass **flips the warning off**. You set
  that flag *only* after the value is confirmed against a real sandbox (or read
  from the official client) and its `docs/verified-apis.md` row is flipped.

Current examples in the file: `ATTRIBUTION_APP_HEADER` /
`ATTRIBUTION_BUSINESS_GROUP_HEADER` (still `verified=False`, §3 — the guessed
header names), and `OAUTH_TOKEN_PATH` (`verified=True`, `/accounts/api/v2/oauth2/token`,
confirmed `VERIFIED (plugin)` from static analysis of the shipping CLI, §12.1).

**(c) Confirmed constants — plain values, no `Unverified` wrapper.**

When a value is LIVE-verified it can graduate to a plain constant with a comment
citing the verifying source. Example: `LLM_PROXY_CLIENT_ID_HEADER = "client_id"`
/ `LLM_PROXY_CLIENT_SECRET_HEADER = "client_secret"` — the confirmed consumer-auth
header pair (§2/§3, LIVE 2026-08-28). Note the caveat next to `REGION_HOSTS`:
the dict has values but `REGION_HOSTS_VERIFIED = False` because the non-US
Hyperforce hosts are still unconfirmed — presence of a value is *not* the same as
verified.

### 2. `docs/verified-apis.md` — the single source of truth

This is the M0 deliverable and the worklist. Placeholder constants in `_verify.py`
point at rows here by `doc_ref`. Read the **header/legend** before asserting any
status. The status legend (verbatim):

| Status | Meaning |
|---|---|
| `VERIFIED (LIVE)` | observed from a real request against the deployed sandbox gateway |
| `VERIFIED (CLI)` | observed from a live `anypoint-cli-v4` run against the real sandbox |
| `VERIFIED (plugin)` | exact signature read from the official compiled client (authoritative, but a live request was **not** additionally replayed) |
| `VERIFIED (build)` | read from an artifact produced by `agent-network project build` |
| `VERIFIED-SHAPE-ONLY` | data shape confirmed from an Anypoint-adjacent source (A2D), **not** the direct contract; validates value types only, never a license to point real registries at it |
| `UNVERIFIED` | not yet confirmed; **its code guard stays in place** |

Every row carries **Verified value / Date / Source** columns. An `UNVERIFIED` row
has these blank (`—`). Key sections to know:

- **§2** — LLM proxy data plane (LIVE-verified: base URL shape with **no `/v1`**,
  the `client_id`/`client_secret` header pair, streaming, `/models` returns 404).
- **§3** — token attribution headers, the *highest-priority unknown*. The
  direct-proxy attribution unit is the `client_id` credential (LIVE); the
  bespoke request-header names in `_verify.py` remain `UNVERIFIED`/`build`-only.
- **§4** — the four LIVE-verified policy rejection shapes (the discriminator is
  the error `type` + headers, **not** the status code).
- **§8** — the eight framework constructor signatures, **all currently
  `UNVERIFIED`**. This is the critical path for M1 (see `docs/m1-completion-checklist.md`).
- **§12.8** — the **Unblocking guidance**, ordered by confidence: safe to unblock
  now behind a live smoke test (OAuth token path), design-ready after one live GET
  (Exchange read, API Manager list/describe/policy), and **do NOT unblock** (LLM
  data-plane §12.6, §3 token-attribution header — static analysis is insufficient).

`docs/unsupported-boundary.md` (§9.3) is the companion doc: every platform surface
the SDK calls, classified Documented-public / Documented-no-SLA / Undocumented.
Its "Undocumented surfaces" section **must stay empty**; anything landing there
needs a written justification and a named owner.

### 3. The verification harness (§8)

For framework constructor signatures specifically, verification is executable via
`python/scripts/verify_frameworks.py` (run from `python/`):

```bash
cd python
pip install -e ".[dev,llm,langgraph]"          # install the framework(s) you verify
python scripts/verify_frameworks.py            # offline signature check, all installed
python scripts/verify_frameworks.py --live     # + one real proxy round-trip
python scripts/verify_frameworks.py --emit-verified   # print §8 markdown rows to paste
```

- **Check A (signature, offline):** constructs the adapter's target class with
  the exact kwargs and `isinstance`-checks it against the class imported from its
  recorded §8 path — a renamed/re-exported class is caught. *Construction
  succeeding is the signature verification.*
- **Check B (`--live`):** one real completion through the sandbox proxy (needs the
  three `AGENT_FABRIC_LLM_PROXY_*` env vars). Only LangGraph's runtime call is
  exercised directly; the other adapters rely on the already-LIVE-verified shared
  proxy path (§2) rather than guessing an agent-loop method.

`--emit-verified` prints the §8 rows to paste, closing the loop into the doc. The
nightly matrix (`.github/workflows/nightly-matrix.yml`) runs this against latest
framework releases (§8.4 "floors, never ceilings").

---

## The UNBLOCK procedure (§0.3 / §12.8)

Confirming a surface and removing its guard is a **controlled, ordered, signed-off
act** — never a side effect of another change. Do the steps in this order:

1. **Confirm the value against ground truth.** For most surfaces that means a
   **real Anypoint sandbox** — a live request (`VERIFIED (LIVE)`), a live
   `anypoint-cli-v4` run (`VERIFIED (CLI)`), or a `project build` artifact
   (`VERIFIED (build)`). For framework signatures, run `verify_frameworks.py`
   green against the installed package. `VERIFIED (plugin)` (read from the
   official compiled client) is strong enough to *design against* but per §12.8
   still needs **one live smoke request** before its guard comes off.
2. **Fill the row + flip its status** in `docs/verified-apis.md`: change
   `UNVERIFIED` → the right `VERIFIED (…)` label and fill **Verified value / Date
   / Source**. If the SDK now calls that surface, add/update its classification
   in `docs/unsupported-boundary.md`.
3. **Set `verified=True`** in `core/_verify.py` for the corresponding
   `Unverified(...)` constant (or promote it to a plain constant with a
   source-citing comment). This is what stops the `UnverifiedValueWarning`.
4. **Get maintainer sign-off on scope (§12.8).** For `VERIFIED (plugin)` rows this
   explicitly means the one live smoke request has happened. Verification confirms
   the *fact*; the maintainer confirms it is in *scope* to rely on it now.
5. **Only then remove the guard** — the `_verify.blocked("…")` call or the
   `UNVERIFIED_*` fallback at the call site — and relax the adapter's inline
   `# verified: docs §N` note.

**Never skip step 1 to reach step 5.** Writing the code that assumes a fact does
not make the fact true (see the M1 checklist rule: "a box flips to ✅ only when the
fact is confirmed against the installed framework / real sandbox — not when the
code that assumes it is written"). Do NOT unblock §12.8 category 3 surfaces (LLM
data-plane, §3 token-attribution header) from static analysis alone.

Before touching any `§`-cited guard, read that section of
`agent-fabric-sdk-build-plan.md` (the authoritative spec at repo root) —
the constraints are deliberate, not accidental.

---

## How this intersects reviews and PRs

When authoring or reviewing (see [[afdk-pr-review]], [[afdk-pr-workflow]]),
treat these as blocking checks:

- **Any new endpoint / header / class name / kwarg** must trace to a
  `VERIFIED (…)` row in `docs/verified-apis.md`, or be behind an `Unverified(...)`
  placeholder (with `verified=False` and a `doc_ref`) or a `_verify.blocked(...)`
  guard. A literal path/header string with no such backing is a §0.3 violation —
  reject it.
- **A flipped `verified=True` or a removed guard** must be accompanied by the
  matching `docs/verified-apis.md` row change (Verified value / Date / Source) and
  evidence the UNBLOCK procedure ran (capture/fixture, harness output, or plugin
  citation) plus maintainer scope sign-off. A guard removal with no row flip is a
  red flag; so is a row flip with no `_verify.py` change.
- **New live captures** belong as fixtures (e.g. `tests/fixtures/anypoint/…`) and
  should be exercised by contract tests (e.g. `test_llm_proxy_contract.py`) — see
  [[afdk-testing]].
- **`docs/unsupported-boundary.md`** must never accumulate an undocumented
  surface without a written owner.
- Confirm the change didn't defeat the `base-only` CI job's purpose (no
  framework import leaked into `core/`) — that's a [[afdk-coding-conventions]]
  concern but it rides alongside verification changes.

---

## Quick reference

| You want to… | Do this |
|---|---|
| Add a value you have NOT confirmed | Wrap it in `Unverified(key, placeholder, doc_ref)` (`verified=False`) **or** raise `_verify.blocked("…")`; add its `UNVERIFIED` row to `docs/verified-apis.md` |
| Silence an `UnverifiedValueWarning` | You may only do so by *verifying* the value and setting `verified=True` — not by suppressing the warning |
| Override a placeholder as a user | Set it via config / env — placeholders are overridable defaults by design |
| Mark a framework signature verified | `verify_frameworks.py` green on the installed package → maintainer sign-off → flip the §8 row (`--emit-verified` prints it) |
| Remove a `blocked(...)` guard | Run the full 5-step UNBLOCK procedure; §12.8 category-3 surfaces cannot be unblocked from static analysis |

**Repo:** `Agent-Fabric-SDK/agent-fabric-sdk` · branches `develop` → `main`.
Files: `python/src/agent_fabric/core/_verify.py`, `docs/verified-apis.md`,
`docs/unsupported-boundary.md`, `docs/m1-completion-checklist.md`,
`python/scripts/verify_frameworks.py`, and the spec
`agent-fabric-sdk-build-plan.md`.
