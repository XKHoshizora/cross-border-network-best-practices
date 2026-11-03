# Repository guidance

Read [CLAUDE.md](CLAUDE.md) for the shared architecture and bilingual conventions; it applies to all agents working in this repository.

Keep helpers offline and dependency-free (Python 3.10+). Run `python3 -m unittest discover -s tests -v` and both helper `--self-test` commands after script changes. Keep README pairs aligned, route new operational references from `SKILL.md`, and distinguish version-specific observations from universal requirements. Never include deployment credentials in fixtures or commits.
