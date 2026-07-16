#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NODES = ROOT / "nodes.jsonl"
EDGES = ROOT / "edges.jsonl"
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def nodes() -> list[dict]:
    return read_jsonl(NODES)


def edges() -> list[dict]:
    return read_jsonl(EDGES)


def save_nodes(rows: list[dict]) -> None:
    write_jsonl(NODES, rows)


def save_edges(rows: list[dict]) -> None:
    write_jsonl(EDGES, rows)


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def parse_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return number


def next_id(rows: list[dict]) -> str:
    max_id = 0
    for row in rows:
        node_id = str(row.get("id", ""))
        if node_id.startswith("P") and node_id[1:].isdigit():
            max_id = max(max_id, int(node_id[1:]))
    return f"P{max_id + 1:04d}"


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def node_blob(node: dict) -> str:
    parts = [
        node.get("id", ""),
        node.get("kind", ""),
        node.get("text", ""),
        node.get("status", ""),
        node.get("evidence", ""),
        node.get("source_hint", ""),
        node.get("note", ""),
    ]
    parts.extend(node.get("tags", []) or [])
    props = node.get("properties", {}) or {}
    parts.extend(str(v) for v in props.values() if v)
    return "\n".join(parts)


def compact_node(node: dict) -> dict:
    keys = ["id", "kind", "text", "tags", "status", "evidence", "source_hint", "note"]
    return {key: node[key] for key in keys if key in node and node[key] not in ("", [], None)}


def add(args: argparse.Namespace) -> None:
    rows = nodes()
    node = {
        "id": next_id(rows),
        "kind": args.kind,
        "text": args.text,
        "tags": parse_tags(args.tags),
        "status": args.status,
        "evidence": args.evidence,
        "source_hint": args.source_hint,
        "note": args.note,
        "properties": {},
    }
    rows.append(node)
    save_nodes(rows)
    print_json(compact_node(node))


def get_node_or_die(node_id: str, rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else nodes()
    for row in rows:
        if row.get("id") == node_id:
            return row
    raise SystemExit(f"Unknown node: {node_id}")


def show_node(args: argparse.Namespace) -> None:
    print_json(get_node_or_die(args.node_id))


def list_nodes(args: argparse.Namespace) -> None:
    out = []
    for row in nodes():
        if args.tag and args.tag not in (row.get("tags") or []):
            continue
        if args.kind and row.get("kind") != args.kind:
            continue
        if args.status and row.get("status") != args.status:
            continue
        if args.evidence and row.get("evidence") != args.evidence:
            continue
        out.append(compact_node(row))
    print_json(out[: args.limit])


def link(args: argparse.Namespace) -> None:
    node_rows = nodes()
    get_node_or_die(args.source, node_rows)
    get_node_or_die(args.target, node_rows)
    edge_rows = edges()
    edge = {
        "source": args.source,
        "target": args.target,
        "relation": args.relation,
        "note": args.note,
    }
    clean_rows = [
        {key: value for key, value in row.items() if key not in {"created_at", "updated_at"}}
        for row in edge_rows
    ]
    if edge in clean_rows:
        print_json(edge)
        return
    edge_rows.append(edge)
    save_edges(edge_rows)
    print_json(edge)


def neighborhood(args: argparse.Namespace) -> None:
    node_rows = nodes()
    by_id = {row["id"]: row for row in node_rows}
    node = get_node_or_die(args.node_id, node_rows)
    related = []
    for edge in edges():
        if edge.get("source") == args.node_id or edge.get("target") == args.node_id:
            other_id = edge["target"] if edge["source"] == args.node_id else edge["source"]
            related.append({
                "edge": edge,
                "other": compact_node(by_id.get(other_id, {"id": other_id, "text": ""})),
            })
    print_json({"node": compact_node(node), "related": related})


def bm25(query: str, rows: list[dict]) -> list[dict]:
    q_terms = tokenize(query)
    if not q_terms:
        return []
    docs = [(row, tokenize(node_blob(row))) for row in rows]
    avgdl = sum(len(terms) for _, terms in docs) / max(len(docs), 1)
    df: dict[str, int] = defaultdict(int)
    for _, terms in docs:
        for term in set(terms):
            df[term] += 1
    n = len(docs)
    out = []
    for row, terms in docs:
        tf = Counter(terms)
        dl = len(terms) or 1
        score = 0.0
        for term in q_terms:
            if tf[term] == 0:
                continue
            idf = math.log(1.0 + (n - df[term] + 0.5) / (df[term] + 0.5))
            denom = tf[term] + 1.5 * (1.0 - 0.75 + 0.75 * dl / max(avgdl, 1e-9))
            score += idf * (tf[term] * 2.5) / denom
        if score:
            item = compact_node(row)
            item["score"] = score
            out.append(item)
    return sorted(out, key=lambda item: (-item["score"], item["id"]))


def search(args: argparse.Namespace) -> None:
    print_json(bm25(args.query, nodes())[: args.limit])


def update(args: argparse.Namespace) -> None:
    rows = nodes()
    node = get_node_or_die(args.node_id, rows)
    if args.text is not None:
        node["text"] = args.text
    if args.kind is not None:
        node["kind"] = args.kind
    if args.tags is not None:
        node["tags"] = parse_tags(args.tags)
    if args.status is not None:
        node["status"] = args.status
    if args.evidence is not None:
        node["evidence"] = args.evidence
    if args.source_hint is not None:
        node["source_hint"] = args.source_hint
    if args.note is not None:
        node["note"] = args.note
    save_nodes(rows)
    print_json(compact_node(node))


def run_git(args: list[str], input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "-c",
                "i18n.logOutputEncoding=utf-8",
                "-C",
                str(ROOT),
                *args,
            ],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise SystemExit(f"Git exploration history is unavailable: cannot run git: {exc}") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise SystemExit(f"Git exploration history is unavailable: {detail}")
    return result


def git_paths() -> tuple[Path, str, str]:
    result = run_git(["rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        raise SystemExit("Git exploration history is unavailable: project_points is not inside a Git worktree")
    repo_root = Path(result.stdout.strip()).resolve()
    try:
        node_path = NODES.relative_to(repo_root).as_posix()
        edge_path = EDGES.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise SystemExit("Git exploration history is unavailable: point files are outside the Git worktree") from exc
    return repo_root, node_path, edge_path


def jsonl_from_revision(commit: str | None, path: str | None) -> list[dict]:
    if commit is None or path is None:
        return []
    result = run_git(["show", f"{commit}:{path}"], check=False)
    if result.returncode != 0:
        return []
    try:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSONL in {path} at {commit}: {exc}") from exc


def rows_by_id(rows: list[dict], path: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        row = {key: value for key, value in row.items() if key not in {"created_at", "updated_at"}}
        row_id = str(row.get("id", ""))
        if not row_id:
            raise SystemExit(f"Point without id in {path}")
        if row_id in out:
            raise SystemExit(f"Duplicate point id {row_id} in {path}")
        out[row_id] = row
    return out


def relation_changes(before: list[dict], after: list[dict]) -> tuple[list[dict], list[dict]]:
    def counted(rows: list[dict]) -> Counter[str]:
        clean_rows = [
            {key: value for key, value in row.items() if key not in {"created_at", "updated_at"}}
            for row in rows
        ]
        return Counter(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in clean_rows)

    old = counted(before)
    new = counted(after)
    added = [json.loads(key) for key in sorted(new) for _ in range(max(new[key] - old[key], 0))]
    removed = [json.loads(key) for key in sorted(old) for _ in range(max(old[key] - new[key], 0))]
    return added, removed


def stable_patch_id(commit: str, parent: str | None) -> str:
    if parent:
        patch = run_git(["diff", "--binary", "--full-index", parent, commit]).stdout
    else:
        patch = run_git(["show", "--root", "--pretty=format:", "--binary", "--full-index", commit]).stdout
    result = run_git(["patch-id", "--stable"], input_text=patch, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.split()[0]
    raise SystemExit("Git exploration history is unavailable: cannot calculate stable patch identity")


def exploration_data(revision: str) -> dict:
    _, node_path, edge_path = git_paths()
    commit = run_git(["rev-parse", "--verify", f"{revision}^{{commit}}"]).stdout.strip()
    metadata = run_git(["show", "-s", "--format=%P%x00%s", commit]).stdout.rstrip("\n").split("\x00")
    parents = metadata[0].split() if metadata and metadata[0] else []
    parent = parents[0] if parents else None

    before_nodes = rows_by_id(jsonl_from_revision(parent, node_path), node_path)
    after_nodes = rows_by_id(jsonl_from_revision(commit, node_path), node_path)
    added = sorted(after_nodes.keys() - before_nodes.keys())
    removed = sorted(before_nodes.keys() - after_nodes.keys())
    updated = sorted(key for key in after_nodes.keys() & before_nodes.keys() if after_nodes[key] != before_nodes[key])

    added_relations, removed_relations = relation_changes(
        jsonl_from_revision(parent, edge_path),
        jsonl_from_revision(commit, edge_path),
    )
    point_ids = set(added + updated + removed)
    for edge in added_relations + removed_relations:
        point_ids.update(str(edge.get(key, "")) for key in ("source", "target") if edge.get(key))

    changes = {
        "points": {"added": added, "updated": updated, "removed": removed},
        "relations": {"added": added_relations, "removed": removed_relations},
    }
    patch_id = stable_patch_id(commit, parent)
    return {
        "exploration_id": f"E{patch_id[:12]}",
        "commit": commit,
        "parents": parents,
        "summary": metadata[1],
        "point_ids": sorted(point_ids),
        "changes": changes,
    }


def exploration(args: argparse.Namespace) -> None:
    item = exploration_data(args.revision)
    if len(item["parents"]) > 1:
        raise SystemExit("Merge commits do not define explorations; inspect a non-merge commit")
    if not item["point_ids"]:
        raise SystemExit("The revision does not change any point or relation")
    print_json(item)


def history(args: argparse.Namespace) -> None:
    _, node_path, edge_path = git_paths()
    head = run_git(["rev-parse", "--verify", "HEAD"], check=False)
    if head.returncode != 0:
        print_json([])
        return
    result = run_git([
        "log",
        "--reverse",
        "--no-merges",
        "--format=%H",
        "--",
        f":(top,literal){node_path}",
        f":(top,literal){edge_path}",
    ])
    commits = [line for line in result.stdout.splitlines() if line]
    explorations = [exploration_data(commit) for commit in commits]
    explorations = [item for item in explorations if item["point_ids"]]
    if args.limit == 0:
        explorations = []
    elif args.limit:
        explorations = explorations[-args.limit :]
    print_json(explorations)


def main() -> None:
    parser = argparse.ArgumentParser(prog="graph.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add")
    p.add_argument("text")
    p.add_argument("--kind", default="point")
    p.add_argument("--tags", default="")
    p.add_argument("--status", default="active")
    p.add_argument("--evidence", default="idea")
    p.add_argument("--source-hint", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=add)

    p = sub.add_parser("update")
    p.add_argument("node_id")
    p.add_argument("--text")
    p.add_argument("--kind")
    p.add_argument("--tags")
    p.add_argument("--status")
    p.add_argument("--evidence")
    p.add_argument("--source-hint")
    p.add_argument("--note")
    p.set_defaults(func=update)

    p = sub.add_parser("link")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--relation", default="related_to")
    p.add_argument("--note", default="")
    p.set_defaults(func=link)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--limit", type=nonnegative_int, default=10)
    p.set_defaults(func=search)

    p = sub.add_parser("node")
    p.add_argument("node_id")
    p.set_defaults(func=show_node)

    p = sub.add_parser("neighborhood")
    p.add_argument("node_id")
    p.set_defaults(func=neighborhood)

    p = sub.add_parser("list")
    p.add_argument("--tag", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--status", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--limit", type=nonnegative_int, default=50)
    p.set_defaults(func=list_nodes)

    p = sub.add_parser("history", help="derive exploration nodes from Git history")
    p.add_argument("--limit", type=nonnegative_int, default=50)
    p.set_defaults(func=history)

    p = sub.add_parser("exploration", help="inspect one Git-backed exploration")
    p.add_argument("revision", help="commit, tag, or other Git revision")
    p.set_defaults(func=exploration)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
