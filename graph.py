#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NODES = ROOT / "nodes.jsonl"
EDGES = ROOT / "edges.jsonl"
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def ensure_files() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not NODES.exists():
        NODES.write_text("", encoding="utf-8")
    if not EDGES.exists():
        EDGES.write_text("", encoding="utf-8")


def nodes() -> list[dict]:
    ensure_files()
    return read_jsonl(NODES)


def edges() -> list[dict]:
    ensure_files()
    return read_jsonl(EDGES)


def save_nodes(rows: list[dict]) -> None:
    ensure_files()
    write_jsonl(NODES, rows)


def save_edges(rows: list[dict]) -> None:
    ensure_files()
    write_jsonl(EDGES, rows)


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def parse_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
    keys = ["id", "kind", "text", "tags", "status", "evidence", "source_hint", "note", "created_at", "updated_at"]
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
        "created_at": now(),
        "updated_at": now(),
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
        "created_at": now(),
    }
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
    node["updated_at"] = now()
    save_nodes(rows)
    print_json(compact_node(node))


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
    p.add_argument("--limit", type=int, default=10)
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
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=list_nodes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
