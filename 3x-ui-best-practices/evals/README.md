# Evaluations

Scenario-based evaluations for the `3x-ui-best-practices` skill, following the
structure in the [Agent Skills best-practices guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#build-evaluations-first).

Each `*.json` file is one scenario:

```json
{
  "skills": ["3x-ui-best-practices"],
  "query": "the user request",
  "files": ["test-files/..."],
  "expected_behavior": ["observable behaviors a correct run should show"]
}
```

There is **no built-in runner** — these are a rubric. Run each `query` against
Claude with the skill loaded (attaching any `files`), then judge the transcript
against `expected_behavior`. Use them as a baseline when changing the skill:
behavior should not regress.

`expected_behavior` items target the skill's core contract — read-only first,
explicit confirmation before disruptive writes, nested JSON, placeholder
secrets, and explaining parameter choices — not exact wording.

## Scenarios

| File | Tests |
| --- | --- |
| `01-troubleshoot-connection.json` | Read-only diagnosis first; no disruptive calls without approval. |
| `02-design-vless-reality-inbound.json` | Correct REALITY inbound + parameter explanations + placeholders. |
| `03-install-and-harden.json` | Firewall + credential/path/HTTPS/2FA hardening; Bearer for automation. |
| `04-safe-upgrade-with-backup.json` | Backup before upgrade; record tag; verify after; restore is high-risk. |
| `05-validate-payload-before-write.json` | Validate a payload before POST; confirm before writing. |
