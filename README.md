# Event Planning & Coordination

Build a reusable Skill that compares event options and produces consistent planning drafts.

## Run and review

The implemented skill produces nine evidence-linked snapshots and four local review drafts. From the repository root, use Python 3.10+ on Linux/WSL with a local POSIX filesystem:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r event-planning-coordination-brief/requirements.txt
.venv/bin/python -B event-planning-coordination-brief/scripts/run.py --through publication-validation --output-dir deliverables
```

The command requires outbound HTTPS to the disclosed sources. It archives a recognized existing run, retrieves fresh evidence and regenerates the drafts. Human approvals remain pending. See the [handoff and independent verification](HANDOFF.md), [command reference](event-planning-coordination-brief/references/command.md) and [recovery guide](event-planning-coordination-brief/references/recovery.md). The [implementation plan](PLAN.md) records stage completion and review status.

The original starter and interview requirements follow.

## Start

1. Read the [formal assignment](https://private-pecorino-70e.notion.site/Project-C-Event-Planning-Coordination-Brief-Learner-assignment-3da0b700541e813a8a91d0741d6ac96a?source=copy_link) for the work and acceptance requirements.
2. Create your own repository from [this starter](https://github.com/GitRollTraining/event-coordination) using **Fork**, then clone your copy and work there.

## Supplied files

| File | Purpose |
|---|---|
| `README.md` | Starting instructions and links. |
| `snapshot.schema.json` | Public snapshot contract; keep it unchanged. |

Create the Skill, implementation and outputs described in the formal assignment. This starter supplies no business workflow implementation.

## Before you work

**Interview rule.** You conduct the stakeholder interview yourself, and the questions are yours. Do not connect a coding agent or any other AI to the interview to run, script, or automate it. The interview transcript is assessed together with the code; a project whose interview was run by an agent is not scored.

- Export your interview as the original Work Sim Markdown, save one final complete file per session under `interviews/`, and commit and push it with your code. Do not rewrite the export. If the export is unavailable, contact the facilitator.

- Use an Agent Skills-capable coding environment. Choose and document your implementation runtime and dependencies; no runtime or install command is supplied here.
- Follow the [shared course guide for session capture](https://classroom.google.com/c/ODcyMjA4NTkwNDk2/m/ODc0NzI2NzQzMzQ2/details) and verify capture is active before implementation. Keep credentials out of the repository.
- Meet the [stakeholder](https://work-sim.catalyte.ai/s/project-c-event-coordination) to understand the work and relevant business sources. Read those online sources through their intended access route; an unavailable source is not permission to substitute repository data.
