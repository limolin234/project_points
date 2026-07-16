# Project Points

Tiny project-local point graph for paper and research work. It stores small
knowledge points and manually maintained relations in plain JSONL.

It is designed to be copied directly into another project with no install step.

```text
project_points/
├── README.md
├── skill.md
├── requirements.txt
├── graph.py
├── nodes.jsonl
├── edges.jsonl
└── index/
    └── README.md
```

No package install, no MCP, no background hook, no embedding dependency.

## What It Does

Use it for small project-level knowledge that is too specific for generic
embedding search:

- paper ideas
- claim fragments
- source hints
- verification tasks
- decision points
- model assumptions
- rejected or caution notes
- manual relations between points

It supports:

- write points
- update points
- search points with lightweight BM25
- list by tag/kind/status/evidence
- link points with explicit relations
- inspect one point or its neighborhood
- derive exploration nodes from Git commits that change the point graph

## Installation / Copy-In

Copy the folder into a project:

```bash
cp -r project_points /path/to/target_project/
```

If the copied folder includes this template repository's Git metadata, remove
only the `.git` directory inside the copied `project_points/` folder. Do not
delete the host project's `.git`. The goal is only to prevent the copied
subfolder from becoming a nested Git repository:

```bash
rm -rf /path/to/target_project/project_points/.git
```

If you distribute `project_points` as a release archive, prefer an archive that
does not include `.git`; then this cleanup step is unnecessary.

Check that Python can run it:

```bash
python3 project_points/graph.py list
```

There are no external Python dependencies. `requirements.txt` is included only
as an installation marker for template workflows. After confirming there is
nothing to install, it can be deleted from the target project:

```bash
rm project_points/requirements.txt
```

Keep `skill.md` in the project long term. Its role is to tell agents how to use
this folder: active query/write, no automatic prompt injection, manual
relations, JSONL as source of truth.

If you want a blank copy, clear the data files:

```bash
: > project_points/nodes.jsonl
: > project_points/edges.jsonl
```

## Commands

Add a point:

```bash
python3 project_points/graph.py add "GlassBridge value depends on whether the glass interlayer offsets extra interface cost." \
  --kind decision_point \
  --tags glassbridge,cost,yield \
  --evidence idea \
  --source-hint "user discussion; Corning brochure to verify"
```

Search:

```bash
python3 project_points/graph.py search "glass interlayer cost"
```

Link two points:

```bash
python3 project_points/graph.py link P0001 P0002 --relation depends_on --note "cost closure depends on testing partition"
```

Inspect:

```bash
python3 project_points/graph.py node P0001
python3 project_points/graph.py neighborhood P0001
python3 project_points/graph.py list --tag glassbridge
python3 project_points/graph.py history
python3 project_points/graph.py exploration HEAD
```

Update:

```bash
python3 project_points/graph.py update P0001 --status pending --evidence E2/PENDING
```

## Data Model

`nodes.jsonl` stores points:

```json
{
  "id": "P0001",
  "kind": "decision_point",
  "text": "A short point.",
  "tags": ["glassbridge", "cost"],
  "status": "active",
  "evidence": "idea",
  "source_hint": "where this came from or what to check"
}
```

`edges.jsonl` stores manual relations:

```json
{
  "source": "P0001",
  "target": "P0002",
  "relation": "depends_on",
  "note": "why the relation exists"
}
```

## Git Explorations

When the folder is inside a Git worktree, each non-merge commit that changes
`nodes.jsonl` or `edges.jsonl` is exposed as one exploration. The changed
points, relations, and project files are derived from Git; they are not copied
back into JSONL.

`exploration_id` uses Git's stable patch identity, so an unchanged patch keeps
the same exploration ID after a normal rebase even though its commit hash and
parents change. Conflict resolution that changes the patch creates a new
exploration identity.

Git history is optional. The point graph commands still work when this folder
is copied without its host repository history. Git calls use one UTF-8 wrapper
and standard local Git commands. Keep the `project_points/` path stable after
history begins; moving it starts a new history view.

## Boundary

This is not a general memory system. It is for small, manually maintained,
project-specific point graphs. Embedding can be added later as a disposable
cache under `index/`, but JSONL remains the source of truth.

The intended scale is tens to hundreds of points. For larger document
collections, build a separate RAG/knowledge-base system instead of expanding
this folder into a hidden platform.

## Fallback File Layout

If the host project already has a file-management convention, follow that
project convention. If it does not, create extra material folders only when
needed, using these fixed names:

- `details/`: longer notes, worked analysis, or draft fragments that are too
  large for one point.
- `references/`: source lists, citation notes, excerpts, and verification
  records.
- `images/`: figures, screenshots, diagrams, and other image files.

These folders do not need to exist in a blank copy. Create them lazily when the
first real file is needed.

Do not put long prose, raw reference dumps, or image payloads into
`nodes.jsonl`. Add a short point and use `source_hint` or `note` to point to the
relevant file path.
