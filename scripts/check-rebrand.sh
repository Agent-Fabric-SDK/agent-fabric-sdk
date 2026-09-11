#!/usr/bin/env bash
#
# Rebrand completeness gate (#340, plan S14).
#
# Fails CI if any DDK-owned identifier still carries the old "Agent Fabric SDK"
# branding. The rebrand map lives in MIGRATION.md; this script is its enforcer.
#
# What it flags: the *slug / identifier* forms that were ours —
#   agent-fabric / agent_fabric, AGENT_FABRIC_*, FABRIC_*, x-fabric,
#   the OTel `fabric.*` namespace, the `Fabric*` class names, the `afdk`/`AFDK`
#   skill prefix, and the `Agent-Fabric-SDK` org slug.
#
# What it deliberately does NOT flag: the bare two-word product phrase
#   "Agent Fabric" (MuleSoft's product, which DDK consumes), the upstream
#   literals `agent-fabric-transformation` and
#   `mulesoft-anypoint-cli-agent-fabric-plugin`, and prose "fabricated" /
#   "fabrication". These are masked out before matching, so a line that mixes a
#   legitimate reference with a real leftover still fails.
#
# Case-sensitive by design: the lowercase `fabric.` / `agent-fabric` forms are
# ours; a sentence-final "…Agent Fabric." (capital F) is the product and passes.
#
# Run from the repo root:  bash scripts/check-rebrand.sh
set -uo pipefail

# Forbidden identifier forms (extended regex, case-sensitive).
PATTERN='agent[-_]fabric|AGENT_FABRIC|FABRIC_|x-fabric|fabric\.|afdk|AFDK|Fabric|Agent-Fabric-SDK'

# Retained literals — masked to empty before re-matching so they never trip it.
mask() {
  sed -E \
    -e 's/Agent Fabric//g' \
    -e 's/agent-fabric-transformation//g' \
    -e 's/mulesoft-anypoint-cli-agent-fabric-plugin//g' \
    -e 's/[Ff]abricat[a-z]*//g'
}

violations=""
while IFS= read -r line; do
  masked=$(printf '%s' "$line" | mask)
  if printf '%s' "$masked" | grep -qE "$PATTERN"; then
    violations+="$line"$'\n'
  fi
done < <(
  git grep -nI -E "$PATTERN" -- \
    ':(exclude)spec/archive/**' \
    ':(exclude)MIGRATION.md' \
    ':(exclude)scripts/check-rebrand.sh' \
    ':(exclude)scripts/rebrand/**' \
    ':(exclude).github/workflows/rebrand-completeness.yml' \
    ':(exclude)website/package-lock.json'
)

if [ -n "$violations" ]; then
  printf '::error::Rebrand completeness gate FAILED — old Agent-Fabric-SDK branding remains:\n'
  printf '%s' "$violations"
  printf '\nSee MIGRATION.md for the rebrand map. If a hit is a legitimate MuleSoft\n'
  printf 'product reference, it belongs in the mask list in scripts/check-rebrand.sh.\n'
  exit 1
fi

printf 'Rebrand completeness gate passed: no stray Agent-Fabric-SDK branding.\n'
