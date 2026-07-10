# Project Points Skill

Use this folder as a project-local, agent-maintained point graph.

## When To Use

Use `project_points/` when the task needs durable project-level context such as:

- paper ideas
- claim fragments
- source hints
- verification tasks
- design decisions
- model assumptions
- rejected or caution notes
- relationships between small knowledge points

This is for project/paper-scale knowledge, usually tens to hundreds of points.

## Rules

- Use `nodes.jsonl` and `edges.jsonl` as the source of truth.
- Do not auto-inject points into every answer.
- Query or write points only when they are relevant to the current task.
- Keep relations explicit and manually maintained.
- After copying this folder into another project, remove only the copied
  `project_points/.git` if it exists. Do not remove the host project's `.git`.
  The cleanup is only to prevent a nested Git repository inside the host
  project.
- Do not add required embedding dependencies.
- Treat `index/` as disposable cache space only.
- Keep points short enough for an agent to inspect directly.
- Preserve uncertainty in fields such as `evidence`, `status`, and `source_hint`.
- If the host project has no file-management convention, create fixed fallback
  folders only when needed: `details/` for long notes, `references/` for source
  and citation material, and `images/` for figures or screenshots.
- Do not put long prose, raw reference dumps, or image payloads into JSONL; add
  a short point and link to the fallback file path in `source_hint` or `note`.

## Commands

Search before writing when the point may already exist:

```bash
python3 project_points/graph.py search "query terms"
```

Add a point:

```bash
python3 project_points/graph.py add "point text" --kind idea --tags topic1,topic2 --evidence idea
```

Link two points:

```bash
python3 project_points/graph.py link P0001 P0002 --relation depends_on --note "short reason"
```

Inspect context:

```bash
python3 project_points/graph.py node P0001
python3 project_points/graph.py neighborhood P0001
python3 project_points/graph.py list --tag topic
```

## Writing Guidance

Prefer small, durable points:

```text
This claim depends on X; evidence is pending; verify with source Y.
```

Avoid dumping long notes, full papers, raw chat logs, or generated prose into
the graph. Store those elsewhere and add only a source hint or decision point.

When there is no better project-local place for that external material, create
`project_points/details/`, `project_points/references/`, or
`project_points/images/` lazily using the same fixed meanings as above.
