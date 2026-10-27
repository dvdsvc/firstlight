#!/usr/bin/env python3
"""Holdout probe for seeded relation completion on mixed DOCX document graphs.

This is deliberately method-agnostic: prose becomes sentence nodes linked by
document order; tables become cell nodes linked by row/column adjacency.  A
subset of already extracted bindings is used only as fixed seed channels.
The remaining bindings stay hidden for evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
AGE_RE = re.compile(r"(?<![\d.])(?P<n>\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*(?P<e>\d+(?:\.\d+)?)(?![\d.])")
SENT_RE = re.compile(r"[。！？!?；;]+")


def normalise(text: str) -> str:
    text = text.replace("\\pm", "±").replace("＋", "+")
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    return re.sub(r"\s*±\s*", "±", text)


def key(sample: str, number: float, error: float) -> tuple[str, float, float]:
    return (re.sub(r"[^a-z0-9]+", "", sample.lower()), round(number, 3), round(error, 3))


def entity_pattern(sample: str) -> re.Pattern[str]:
    parts = re.findall(r"[a-z]+|\d+", sample.lower())
    body = r"[-\s]*".join(re.escape(part) for part in parts)
    # `js-092样品` is an OCR-joined occurrence of `js-09 2样品`.
    return re.compile(r"(?<![a-z0-9])" + body + r"(?!(?:[a-z]|\d(?!\s*(?:件\s*)?样品)))", re.I)


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter() if node.tag.rsplit("}", 1)[-1] == "t").strip()


@dataclass
class Node:
    id: str
    kind: str
    text: str
    table: int | None = None
    row: int | None = None
    col: int | None = None


def read_docx(path: Path) -> tuple[dict[str, Node], list[tuple[str, str, float, str]]]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W}body")
    nodes: dict[str, Node] = {}
    edges: list[tuple[str, str, float, str]] = []
    previous_tail: str | None = None
    table_id = 0
    paragraph_id = 0
    for child in body if body is not None else []:
        if child.tag == f"{W}p":
            sentences = [item.strip() for item in SENT_RE.split(normalise(text_of(child))) if item.strip()]
            current: list[str] = []
            for sentence_id, sentence in enumerate(sentences):
                node_id = f"p{paragraph_id}s{sentence_id}"
                nodes[node_id] = Node(node_id, "text", sentence)
                if current:
                    edges.append((current[-1], node_id, 1.0, "text_next"))
                current.append(node_id)
            if previous_tail and current:
                edges.append((previous_tail, current[0], 3.5, "body_next"))
            if current:
                previous_tail = current[-1]
            paragraph_id += 1
        elif child.tag == f"{W}tbl":
            rows = child.findall(f".//{W}tr")
            grid: list[list[str]] = []
            for r, row in enumerate(rows):
                row_nodes = []
                for c, cell in enumerate(row.findall(f"./{W}tc")):
                    node_id = f"t{table_id}r{r}c{c}"
                    nodes[node_id] = Node(node_id, "table", normalise(text_of(cell)), table_id, r, c)
                    row_nodes.append(node_id)
                    if c:
                        edges.append((row_nodes[-2], node_id, 0.7, "table_row"))
                    if r < len(grid) and c < len(grid[r - 1]):
                        edges.append((grid[r - 1][c], node_id, 0.9, "table_col"))
                if row_nodes:
                    grid.append(row_nodes)
            if previous_tail and grid and grid[0]:
                edges.append((previous_tail, grid[0][0], 4.0, "body_table"))
            if grid and grid[-1]:
                previous_tail = grid[-1][-1]
            table_id += 1
    return nodes, edges


def add_edge(adj: dict[str, list[tuple[str, float, str]]], a: str, b: str, cost: float, edge_type: str) -> None:
    adj[a].append((b, cost, edge_type))
    adj[b].append((a, cost, edge_type))


def dijkstra(adj: dict[str, list[tuple[str, float, str]]], sources: list[str], limit: float = 9.0) -> dict[str, float]:
    best = {source: 0.0 for source in sources}
    queue = [(0.0, source) for source in sources]
    heapq.heapify(queue)
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != best.get(node) or cost > limit:
            continue
        for nxt, edge_cost, _ in adj[node]:
            candidate = cost + edge_cost
            if candidate <= limit and candidate < best.get(nxt, float("inf")):
                best[nxt] = candidate
                heapq.heappush(queue, (candidate, nxt))
    return best


def load_r1(path: Path) -> tuple[list[str], list[dict]]:
    payload = json.loads(path.read_text())
    samples, events = [], []
    for sample in payload.get("samples", []):
        sample_id = sample.get("id")
        if not sample_id:
            continue
        samples.append(sample_id)
        for event in sample.get("measure_events", []):
            value = event.get("value") or {}
            error = value.get("error") or {}
            if value.get("number") is not None and error.get("value") is not None:
                events.append({"sample": sample_id, "number": float(value["number"]), "error": float(error["value"])})
    return samples, events


def mentions(nodes: dict[str, Node], samples: list[str]) -> tuple[dict[str, list[str]], dict[tuple[float, float], list[str]]]:
    entities = defaultdict(list)
    ages = defaultdict(list)
    patterns = {sample: entity_pattern(sample) for sample in samples}
    for node_id, node in nodes.items():
        for sample, pattern in patterns.items():
            if pattern.search(node.text.lower()):
                entities[sample].append(node_id)
        for match in AGE_RE.finditer(node.text):
            ages[(round(float(match["n"]), 3), round(float(match["e"]), 3))].append(node_id)
    return entities, ages


def split_seed(events: list[dict], entities: dict[str, list[str]], ages: dict[tuple[float, float], list[str]]) -> tuple[list[dict], list[dict]]:
    grounded = [event for event in events if entities.get(event["sample"]) and ages.get((round(event["number"], 3), round(event["error"], 3)))]
    grounded.sort(key=lambda event: key(event["sample"], event["number"], event["error"]))
    seeds, held_out = [], []
    # Deterministic 1/3 split, with every document retaining a real heldout set.
    for index, event in enumerate(grounded):
        (seeds if index % 3 == 0 else held_out).append(event)
    return seeds, held_out


def node_role_pair(a: Node, b: Node) -> tuple[str, int | None]:
    if a.kind == b.kind == "table" and a.table == b.table and a.row == b.row:
        return ("same_table_row", abs((a.col or 0) - (b.col or 0)))
    if a.kind == b.kind == "text":
        return ("text_zone", None)
    return ("cross_structure", None)


def rank_candidates(
    nodes: dict[str, Node],
    entities: dict[str, list[str]],
    ages: dict[tuple[float, float], list[str]],
    distances: dict[str, dict[str, float]],
    signatures: set[tuple[str, int | None]],
    limit: int = 3,
) -> dict[tuple[float, float], list[tuple[str, float]]]:
    labels = {}
    for age_key, age_nodes in ages.items():
        scored = []
        for sample, dist in distances.items():
            base = min((dist.get(age_node, float("inf")) for age_node in age_nodes), default=float("inf"))
            if base == float("inf"):
                continue
            motif_bonus = 0.0
            for entity_node in entities[sample]:
                for age_node in age_nodes:
                    signature = node_role_pair(nodes[entity_node], nodes[age_node])
                    if signature in signatures:
                        motif_bonus = max(motif_bonus, 1.5 if signature[0] == "same_table_row" else 0.6)
            scored.append((sample, round(base - motif_bonus, 3)))
        labels[age_key] = sorted(scored, key=lambda item: item[1])[:limit]
    return labels


def recall(events: list[dict], labels: dict[tuple[float, float], list[tuple[str, float]]]) -> int:
    return sum(
        event["sample"] in {sample for sample, _ in labels.get((round(event["number"], 3), round(event["error"], 3)), [])}
        for event in events
    )


def direct_signature(a_id: str, b_id: str, nodes: dict[str, Node]) -> tuple[str, int | None]:
    a, b = nodes[a_id], nodes[b_id]
    if a_id == b_id and a.kind == "text":
        return ("same_text_frame", None)
    if a.kind == b.kind == "table" and a.table == b.table and a.row == b.row:
        return ("same_table_row", abs((a.col or 0) - (b.col or 0)))
    return ("other", None)


def closest_link(
    sample: str,
    age_key: tuple[float, float],
    entities: dict[str, list[str]],
    ages: dict[tuple[float, float], list[str]],
    distances: dict[str, dict[str, float]],
) -> tuple[float, str, str] | None:
    best: tuple[float, str, str] | None = None
    for entity_node in entities.get(sample, []):
        for age_node in ages.get(age_key, []):
            distance = distances[sample].get(age_node, float("inf"))
            candidate = (distance, entity_node, age_node)
            if distance < float("inf") and (best is None or candidate < best):
                best = candidate
    return best


def direct_link(
    sample: str,
    age_key: tuple[float, float],
    entities: dict[str, list[str]],
    ages: dict[tuple[float, float], list[str]],
    nodes: dict[str, Node],
) -> tuple[str, str, tuple[str, int | None]] | None:
    options = []
    for entity_node in entities.get(sample, []):
        for age_node in ages.get(age_key, []):
            signature = direct_signature(entity_node, age_node, nodes)
            if signature[0] != "other":
                options.append((entity_node, age_node, signature))
    return min(options) if options else None


def state_delta_probe(name: str, docx: Path, r1: Path) -> dict:
    """Use the complete current state as seeds and report only unconsumed links."""
    samples, events = load_r1(r1)
    nodes, raw_edges = read_docx(docx)
    adj: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for a, b, cost, edge_type in raw_edges:
        add_edge(adj, a, b, cost, edge_type)
    entities, ages = mentions(nodes, samples)
    distances = {sample: dijkstra(adj, positions) for sample, positions in entities.items()}
    consumed = {key(event["sample"], event["number"], event["error"]) for event in events}

    supported_signatures: set[tuple[str, int | None]] = set()
    for event in events:
        age_key = (round(event["number"], 3), round(event["error"], 3))
        link = direct_link(event["sample"], age_key, entities, ages, nodes)
        if link:
            _, _, signature = link
            supported_signatures.add(signature)

    labels = rank_candidates(nodes, entities, ages, distances, set())
    deltas = []
    for age_key, ranked in labels.items():
        if not ranked:
            continue
        sample, energy = ranked[0]
        event_key = key(sample, *age_key)
        if event_key in consumed:
            continue
        link = direct_link(sample, age_key, entities, ages, nodes)
        if not link:
            continue
        entity_node, age_node, signature = link
        if signature not in supported_signatures:
            continue
        deltas.append({
            "sample": sample,
            "number": age_key[0],
            "error": age_key[1],
            "energy": energy,
            "signature": f"{signature[0]}:{signature[1]}",
            "entity_node": entity_node,
            "value_node": age_node,
            "evidence": nodes[age_node].text[:360],
        })
    deltas.sort(key=lambda item: (item["energy"], item["sample"], item["number"]))
    return {
        "name": name,
        "status": "ok",
        "known_binding_count": len(events),
        "supported_signatures": sorted(f"{kind}:{delta}" for kind, delta in supported_signatures),
        "uncovered_candidate_count": len(deltas),
        "uncovered_candidates": deltas[:30],
    }


def probe(name: str, docx: Path, r1: Path) -> dict:
    samples, events = load_r1(r1)
    nodes, raw_edges = read_docx(docx)
    adj: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for a, b, cost, edge_type in raw_edges:
        add_edge(adj, a, b, cost, edge_type)
    entities, ages = mentions(nodes, samples)
    seeds, held_out = split_seed(events, entities, ages)
    if not seeds or not held_out:
        return {"name": name, "status": "insufficient_grounded_bindings", "nodes": len(nodes), "grounded": len(seeds) + len(held_out)}

    # Learn only topology signatures from observed bindings, never isotope words.
    signatures: set[tuple[str, int | None]] = set()
    for seed in seeds:
        age_key = (round(seed["number"], 3), round(seed["error"], 3))
        for entity_node in entities[seed["sample"]]:
            for age_node in ages[age_key]:
                signatures.add(node_role_pair(nodes[entity_node], nodes[age_node]))

    distances = {sample: dijkstra(adj, positions) for sample, positions in entities.items()}
    candidate_labels = rank_candidates(nodes, entities, ages, distances, signatures)
    baseline_labels = rank_candidates(nodes, entities, ages, distances, set())
    top1_labels = rank_candidates(nodes, entities, ages, distances, signatures, limit=1)
    baseline_top1_labels = rank_candidates(nodes, entities, ages, distances, set(), limit=1)
    recovered_count = recall(held_out, candidate_labels)
    baseline_count = recall(held_out, baseline_labels)
    top1_count = recall(held_out, top1_labels)
    baseline_top1_count = recall(held_out, baseline_top1_labels)
    recovered = [
        event for event in held_out
        if event["sample"] in {sample for sample, _ in candidate_labels.get((round(event["number"], 3), round(event["error"], 3)), [])}
    ]
    return {
        "name": name,
        "status": "ok",
        "nodes": len(nodes),
        "entity_occurrences": sum(map(len, entities.values())),
        "age_value_nodes": sum(map(len, ages.values())),
        "grounded_bindings": len(seeds) + len(held_out),
        "seed_bindings": len(seeds),
        "heldout_bindings": len(held_out),
        "recovered_heldout": recovered_count,
        "top3_relation_recall": round(recovered_count / len(held_out), 3),
        "baseline_recovered_heldout": baseline_count,
        "baseline_top3_relation_recall": round(baseline_count / len(held_out), 3),
        "top1_recovered_heldout": top1_count,
        "top1_relation_recall": round(top1_count / len(held_out), 3),
        "baseline_top1_recovered_heldout": baseline_top1_count,
        "baseline_top1_relation_recall": round(baseline_top1_count / len(held_out), 3),
        "learned_topology_signatures": sorted(f"{kind}:{delta}" for kind, delta in signatures),
        "recovered_examples": recovered[:5],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", required=True, metavar="NAME|DOCX|R1_JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("holdout", "delta"), default="holdout")
    args = parser.parse_args()
    results = []
    for raw in args.case:
        name, docx, r1 = raw.split("|", 2)
        runner = state_delta_probe if args.mode == "delta" else probe
        results.append(runner(name, Path(docx), Path(r1)))
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    summary_keys = (
        ("name", "status", "known_binding_count", "uncovered_candidate_count")
        if args.mode == "delta"
        else ("name", "status", "nodes", "grounded_bindings", "seed_bindings", "heldout_bindings", "recovered_heldout", "top3_relation_recall")
    )
    print(json.dumps([{key: item.get(key) for key in summary_keys} for item in results], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
