# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is a **content repository**, not a software project. It packages cross-border-networking / censorship-circumvention knowledge as **AI Agent Skills** — directories of Markdown + YAML that an agent reads in order to install, configure, and troubleshoot tools for ordinary (non-specialist) users. There is no build system, no test runner, no linter, and no application code. **The documentation is the deliverable.**

Currently the only Skill is `3x-ui-best-practices/` (for the [3X-UI](https://github.com/MHSanaei/3x-ui) Xray panel). The root `README.md` lists planned future Skills (`xray-core`, `sing-box`, `mihomo-clash`, `vps-network-hardening`, etc.), each of which would become a sibling directory with the same layout.

## Commands

There is nothing to build or run. The only relevant tooling is `git` plus two manual checks tied to the conventions below:

- Bilingual drift: `wc -l **/README*.md` — an EN file and its `*.zh_CN.md` counterpart should stay close.
- Secret scan before committing: grep the diff for real tokens, UUIDs, Reality private keys, `subId`s, and panel URLs (see redaction rule below).

## Skill Architecture (progressive disclosure)

Each Skill is a self-contained directory built as layers, so an agent reads only what a task needs. For `3x-ui-best-practices/`:

- `SKILL.md` — **the entrypoint.** YAML frontmatter (`name` + `description`) followed by concise agent behavior: operating rules, workflows (discovery / fresh install / troubleshooting), and configuration defaults. Kept deliberately short.
- `references/api-and-config-reference.md` — long-form, precise field tables, endpoint risk classes, troubleshooting matrix, and example payloads. The detail layer.
- `README.md` / `README.zh_CN.md` — human-facing documentation with Mermaid diagrams and copy-pasteable examples (English + Simplified Chinese).
- `agents/` — optional per-platform interface descriptors (e.g. `openai.yaml`: display name, short description, default prompt). Not behavior; just integration metadata.

The bottom of `SKILL.md` has an explicit routing block ("Read `references/…` when you need X; read `README.md` when the user wants Y"). **That routing is the contract.** When you add content, decide which layer it belongs in and keep the routing accurate. Don't copy reference tables up into `SKILL.md` — link down to them.

Two properties drive Skill behavior and must stay correct:

1. **The frontmatter `description` is the activation trigger.** It is intentionally keyword-dense (protocol names, error symptoms, action verbs) so the runtime knows when to load the Skill. If you change a Skill's scope, keep its keyword list aligned with what it actually covers.
2. **Content is evidence-grounded, not invented.** The references record real, observed quirks — e.g. Bearer auth only works reliably on `/panel/api/*`, and a live OpenAPI may advertise global security that `/panel/setting/*` routes don't actually honor. Preserve these empirical caveats; do not replace an observed limitation with an optimistic assumption.

## Content Conventions (nothing automated enforces these)

- **Bilingual parity.** Every `README.md` has a `README.zh_CN.md` that must stay in lockstep — same structure, sections, and examples (the `3x-ui-best-practices` pair is currently line-for-line parallel). Edit both in the same change.
- **Redaction is mandatory.** Examples use placeholders only: `example.com`, `replace-with-*`, `00000000-0000-0000-0000-000000000000`. Never commit real API tokens, Reality private keys, client UUID/password/auth values, `subId`s, subscription URLs, or panel URLs containing secrets.
- **Operations are classified by risk, and the docs must preserve that taxonomy.** Read-only diagnostics first; then routine writes; then high-risk operations (delete, traffic reset, Xray restart/stop, panel update, DB import/restore, regenerating live TLS/Reality secrets) that require explicit user approval. When documenting a new endpoint or command, place it in the correct risk class — this safety model is the substance of the content, not decoration.
- **Use modern nested JSON** for `settings` / `streamSettings` / `sniffing` in examples. Legacy JSON-encoded strings still work but are not the documented shape.

## Adding a New Skill

Mirror the `3x-ui-best-practices/` layout: a lowercase-hyphenated directory containing a concise `SKILL.md` (with a keyword-rich `description`), `README.md`, `README.zh_CN.md`, and `references/` for long material; add `agents/` only if you ship platform descriptors. Then register the Skill in the "Current Skills" section of **both** root `README.md` and `README.zh_CN.md`. Keep `SKILL.md` focused on agent behavior, boundaries, and checklists; put long tables and full examples in `references/`; use diagrams only when they aid understanding.
