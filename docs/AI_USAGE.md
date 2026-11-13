# AI usage

We used AI tools openly. All code was reviewed, tested and run by the team, and every number in the project comes from code in this repository that anyone can re-run.

| Tool | What for |
|---|---|
| **Claude** (Anthropic), via Claude Code | Pair-programming, refactoring, tests, code review, and drafting the docs. Each ticket was implemented, then reviewed by two separate review passes (coding standards; spec), and the findings were fixed before committing. The review notes are at the bottom of each ticket in `.scratch/space-apps-2026/issues/`. |
| **Matt Pocock's agent skills** (MIT, https://github.com/mattpocock/skills) | The engineering workflow: a design interview (grilling) that produced the glossary and ADRs, then the spec, tickets, TDD at fixed seams, and code review. |
| **Gemini** (Google) | Used in the prototype phase, before the event. |

What the AI did **not** decide alone:
- The scientific choices: the headline series, the risk label, the validation design and the activity gate.
- Anything that changed an approved decision. These were put to the team: see ADRs 0001–0007, and the proposed (not yet accepted) amendment in ADR 0006.

The changelog of what was built and when is in `docs/CHANGELOG_HACKATHON.md`.
