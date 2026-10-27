#!/usr/bin/env python3
"""Seeded Relation Completion on a mixed text/table document graph.

The document is one weighted graph.  Text sentences form a locally connected
chain; table cells form a locally connected grid.  Existing sample-value
bindings are fixed Dirichlet boundaries through low-resistance channels.
Harmonic label propagation then gives the minimum Dirichlet-energy extension
over the full graph.  The output is a low-energy candidate forest, never one
forced value-to-entity assignment.
"""

from __future__ import annotations

import argparse
import heapq
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import csc_matrix, diags
from scipy.sparse.linalg import spsolve


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PAIR_RE = re.compile(r"(?<![\d.])(?P<n>-?\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*(?P<e>\d+(?:\.\d+)?)(?![\d.])")
SCALAR_RE = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])")
BROKEN_NUMERIC_RE = re.compile(r"(?<![\d.])\d[\d.]{2,}(?![\d.])")
SENTENCE_RE = re.compile(r"[。！？!?；;]+")
# Section headings are deterministic document structure, not soft semantic
# hints.  A numbered result subsection such as ``3.1.2 ... (MZ819)`` owns the
# following local text until the next heading.
NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:(?:\d+\s*[.．]\s*)+\d*\s*[^\d]|\d+\s*(?:[、．]|　+)\s*[^\d])"
)
SECTION_SAMPLE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,8}\s*-?\s*\d{2,6})(?![A-Za-z0-9])")


def norm(text: str) -> str:
    text = text.replace("\\pm", "±").replace("＋", "+")
    text = text.replace("－", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    return re.sub(r"\s*±\s*", "±", text)


def pair_key(number: float, error: float) -> tuple[float, float]:
    # Isotope ratios routinely carry 6-8 meaningful decimal places.  Pair
    # identity must preserve them; three-decimal rounding silently turns
    # analytical errors such as 0.000007 into zero.
    return round(float(number), 9), round(float(error), 9)


def binding_key(sample: str, number: float, error: float) -> tuple[str, float, float]:
    return re.sub(r"[^a-z0-9]+", "", sample.lower()), *pair_key(number, error)


def numeric_signature(value: float) -> str:
    return re.sub(r"\D", "", format(float(value), ".12g"))


def insertion_deletion_distance(left: str, right: str) -> int:
    """Edit distance that permits dropped/inserted OCR glyphs, not substitution."""
    rows = [0] * (len(right) + 1)
    for char_left in left:
        previous, rows[0] = rows[0], rows[0] + 1
        for offset, char_right in enumerate(right, start=1):
            old = rows[offset]
            if char_left == char_right:
                rows[offset] = previous
            else:
                rows[offset] = min(rows[offset] + 1, rows[offset - 1] + 1)
            previous = old
    return rows[-1]


def entity_pattern(sample: str) -> re.Pattern[str]:
    parts = re.findall(r"[a-z]+|\d+", norm(sample).lower())
    body = r"[-\s]*".join(map(re.escape, parts))
    # OCR often merges a following sample count into an otherwise canonical
    # ID, e.g. ``js-092 samples`` for ``js-09, 2 samples``.  This only
    # normalizes an already-known root; it never invents an entity.
    return re.compile(
        rf"(?<![a-z0-9]){body}(?![a-z0-9])|(?<![a-z0-9]){body}(?=\d+\s*(?:件\s*)?样品)",
        re.I,
    )


def text_of(element: ET.Element) -> str:
    return "".join(item.text or "" for item in element.iter() if item.tag.rsplit("}", 1)[-1] == "t").strip()


@dataclass
class Node:
    id: str
    kind: str
    text: str = ""
    table: int | None = None
    row: int | None = None
    col: int | None = None
    pair: tuple[float, float] | None = None
    origin: str | None = None
    section: str | None = None
    neighbours: list[tuple[str, float, str]] = field(default_factory=list)


class DocumentGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self._counter = 0
        self.section_owners: dict[str, set[str]] = defaultdict(set)

    def add_node(self, node: Node) -> str:
        self.nodes[node.id] = node
        return node.id

    def fresh_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}:{self._counter}"

    def edge(self, left: str, right: str, resistance: float, kind: str) -> None:
        self.nodes[left].neighbours.append((right, resistance, kind))
        self.nodes[right].neighbours.append((left, resistance, kind))


def add_value_node(graph: DocumentGraph, pair: tuple[float, float], origin: str, containers: list[str], source_kind: str) -> str:
    value_id = graph.fresh_id("value")
    graph.add_node(Node(value_id, "value", pair=pair, origin=source_kind))
    for container in containers:
        graph.edge(value_id, container, 0.65, f"value_{source_kind}")
    return value_id


def add_explicit_values(graph: DocumentGraph, container: str) -> None:
    text = graph.nodes[container].text
    for match in PAIR_RE.finditer(text):
        add_value_node(graph, pair_key(match["n"], match["e"]), container, [container], "explicit")


def is_numbered_heading(text: str) -> bool:
    return bool(NUMBERED_HEADING_RE.match(text))


def heading_samples(text: str) -> set[str]:
    return {re.sub(r"[^a-z0-9]+", "", token.lower()) for token in SECTION_SAMPLE_RE.findall(text)}


def build_document_graph(path: Path) -> DocumentGraph:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W}body")
    graph = DocumentGraph()
    previous_tail: str | None = None
    paragraph_index = 0
    table_index = 0
    current_section = "section:frontmatter"
    for child in body if body is not None else []:
        if child.tag == f"{W}p":
            paragraph_text = norm(text_of(child))
            if is_numbered_heading(paragraph_text):
                current_section = f"section:{paragraph_index}"
                graph.section_owners[current_section].update(heading_samples(paragraph_text))
                # A numbered heading is a hard document boundary.  Do not
                # connect the preceding section to this one through ordinary
                # body adjacency; the heading itself remains connected to its
                # own following paragraph as local context.
                previous_tail = None
            sentence_nodes = []
            for sentence_index, sentence in enumerate(SENTENCE_RE.split(paragraph_text)):
                sentence = sentence.strip()
                if not sentence:
                    continue
                node_id = f"text:{paragraph_index}:{sentence_index}"
                graph.add_node(Node(node_id, "text", text=sentence, section=current_section))
                add_explicit_values(graph, node_id)
                if sentence_nodes:
                    graph.edge(sentence_nodes[-1], node_id, 3.0, "text_adjacent")
                sentence_nodes.append(node_id)
            if previous_tail and sentence_nodes:
                graph.edge(previous_tail, sentence_nodes[0], 8.0, "body_adjacent")
            if sentence_nodes:
                previous_tail = sentence_nodes[-1]
            paragraph_index += 1
            continue
        if child.tag != f"{W}tbl":
            continue
        rows = child.findall(f".//{W}tr")
        table_rows: list[list[str]] = []
        row_nodes: list[str] = []
        for row_index, row in enumerate(rows):
            row_id = f"row:{table_index}:{row_index}"
            graph.add_node(Node(row_id, "table_row", table=table_index, row=row_index))
            row_nodes.append(row_id)
            if row_index:
                graph.edge(row_nodes[-2], row_id, 1.1, "table_row_adjacent")
            cells = []
            for col_index, cell in enumerate(row.findall(f"./{W}tc")):
                cell_id = f"cell:{table_index}:{row_index}:{col_index}"
                graph.add_node(Node(cell_id, "table_cell", text=norm(text_of(cell)), table=table_index, row=row_index, col=col_index, section=current_section))
                graph.edge(row_id, cell_id, 2.5, "row_membership")
                add_explicit_values(graph, cell_id)
                if cells:
                    graph.edge(cells[-1], cell_id, 3.0, "table_horizontal")
                if row_index and col_index < len(table_rows[row_index - 1]):
                    graph.edge(table_rows[row_index - 1][col_index], cell_id, 3.2, "table_vertical")
                cells.append(cell_id)
            # Adjacent cells yield *candidate* value/error pairs.  They are
            # not declared to be ages; seed channels decide which topology is
            # worth propagating and the final forest retains uncertainty.
            # A cross-cell pair is valid only when both cells are bare scalar
            # slots.  Values embedded in IDs or already paired cells are not
            # allowed to manufacture an artificial age/error pair.
            for left, right in zip(cells, cells[1:]):
                left_text, right_text = graph.nodes[left].text, graph.nodes[right].text
                if re.fullmatch(r"-?\d+(?:\.\d+)?", left_text) and re.fullmatch(r"\d+(?:\.\d+)?", right_text):
                    add_value_node(graph, pair_key(left_text, right_text), left, [left, right], "table_horizontal_pair")
            if row_index:
                previous_cells = table_rows[row_index - 1]
                for above, below in zip(previous_cells, cells):
                    above_text, below_text = graph.nodes[above].text, graph.nodes[below].text
                    if re.fullmatch(r"-?\d+(?:\.\d+)?", above_text) and re.fullmatch(r"\d+(?:\.\d+)?", below_text):
                        add_value_node(graph, pair_key(above_text, below_text), above, [above, below], "table_vertical_pair")
            table_rows.append(cells)
        if previous_tail and row_nodes:
            graph.edge(previous_tail, row_nodes[0], 8.0, "body_table")
        if row_nodes:
            previous_tail = row_nodes[-1]
        table_index += 1
    return graph


def load_state(path: Path) -> tuple[list[str], list[dict]]:
    data = json.loads(path.read_text())
    samples, bindings = [], []
    for sample in data.get("samples", []):
        sample_id = sample.get("id")
        if not sample_id:
            continue
        samples.append(sample_id)
        for event in sample.get("measure_events", []):
            value = event.get("value") or {}
            error = value.get("error") or {}
            if value.get("number") is not None and error.get("value") is not None:
                bindings.append({"sample": sample_id, "pair": pair_key(value["number"], error["value"])})
    return samples, bindings


def attach_entity_roots(graph: DocumentGraph, samples: list[str]) -> dict[str, str]:
    roots = {}
    containers = [node for node in graph.nodes.values() if node.kind in {"text", "table_cell"}]
    for sample in samples:
        root_id = f"root:{sample}"
        graph.add_node(Node(root_id, "entity_root", text=sample))
        pattern = entity_pattern(sample)
        for container in containers:
            if pattern.search(container.text.lower()):
                graph.edge(root_id, container.id, 0.08, "entity_mention")
        roots[sample] = root_id
    return roots


def dijkstra(graph: DocumentGraph, source: str, limit: float = 25.0) -> dict[str, float]:
    best = {source: 0.0}
    queue = [(0.0, source)]
    while queue:
        cost, node_id = heapq.heappop(queue)
        if cost != best.get(node_id) or cost > limit:
            continue
        for next_id, resistance, _ in graph.nodes[node_id].neighbours:
            candidate = cost + resistance
            if candidate < best.get(next_id, float("inf")) and candidate <= limit:
                best[next_id] = candidate
                heapq.heappush(queue, (candidate, next_id))
    return best


def find_broken_seed_container(graph: DocumentGraph, root_id: str, pair: tuple[float, float], limit: float) -> tuple[str, str] | None:
    expected = numeric_signature(pair[0]) + numeric_signature(pair[1])
    local = dijkstra(graph, root_id, limit=limit)
    direct = {
        node_id
        for node_id, _, _ in graph.nodes[root_id].neighbours
        if graph.nodes[node_id].kind in {"text", "table_cell"}
    }

    def shares_root_context(node_id: str) -> bool:
        if node_id in direct:
            return True
        position = text_position(node_id)
        if position is None:
            return False
        paragraph, _ = position
        return any(text_position(anchor) and text_position(anchor)[0] == paragraph for anchor in direct)

    matches: list[tuple[float, str, str]] = []
    for node_id, distance in local.items():
        node = graph.nodes[node_id]
        if node.kind not in {"text", "table_cell"} or not shares_root_context(node_id):
            continue
        for token in BROKEN_NUMERIC_RE.findall(node.text):
            observed = re.sub(r"\D", "", token)
            looks_collapsed = len(observed) > len(expected) or token.count(".") >= 2
            if looks_collapsed and observed != expected and insertion_deletion_distance(observed, expected) == 1:
                matches.append((distance, node_id, token))
    if not matches:
        return None
    _, node_id, token = min(matches)
    return node_id, token


def install_seed_channels(
    graph: DocumentGraph,
    roots: dict[str, str],
    bindings: list[dict],
    *,
    grounding_limit: float,
    ocr_repair_limit: float,
) -> tuple[set[tuple[str, float, float]], list[tuple[str, str]], list[dict], list[dict]]:
    by_pair: dict[tuple[float, float], list[str]] = defaultdict(list)
    for node in graph.nodes.values():
        if node.kind == "value" and node.pair is not None:
            by_pair[node.pair].append(node.id)
    consumed = set()
    installed: list[tuple[str, str]] = []
    unmatched: list[dict] = []
    repairs: list[dict] = []
    distances: dict[str, dict[str, float]] = {}
    for binding in bindings:
        sample, pair = binding["sample"], binding["pair"]
        consumed.add(binding_key(sample, *pair))
        if sample not in roots:
            unmatched.append({"sample": sample, "number": pair[0], "error": pair[1], "reason": "missing_state_root"})
            continue
        if not graph.nodes[roots[sample]].neighbours:
            unmatched.append({"sample": sample, "number": pair[0], "error": pair[1], "reason": "entity_not_located"})
            continue
        if not by_pair.get(pair):
            repaired = find_broken_seed_container(graph, roots[sample], pair, ocr_repair_limit)
            if repaired is None:
                unmatched.append({"sample": sample, "number": pair[0], "error": pair[1], "reason": "value_pair_not_located"})
                continue
            container, raw_token = repaired
            repaired_value = add_value_node(graph, pair, container, [container], "seed_ocr_repair")
            by_pair[pair].append(repaired_value)
            distances.pop(sample, None)
            repairs.append({"sample": sample, "number": pair[0], "error": pair[1], "container": container, "raw_token": raw_token})
        if sample not in distances:
            # Figure captions and bilingual captions can insert many ordinary
            # text nodes inside one numbered subsection.  Headings now break
            # the body graph, so seed grounding may safely traverse a longer
            # path within that structural domain.
            distances[sample] = dijkstra(graph, roots[sample], limit=grounding_limit)
        candidates = [value_id for value_id in by_pair[pair] if value_id in distances[sample]]
        if not candidates:
            unmatched.append({"sample": sample, "number": pair[0], "error": pair[1], "reason": "entity_value_disconnected"})
            continue
        chosen = min(candidates, key=lambda value_id: distances[sample][value_id])
        graph.edge(roots[sample], chosen, 0.01, "fixed_seed_binding")
        installed.append((sample, chosen))
    return consumed, installed, unmatched, repairs


def node_containers(graph: DocumentGraph, value_id: str) -> list[Node]:
    return [
        graph.nodes[next_id]
        for next_id, _, _ in graph.nodes[value_id].neighbours
        if graph.nodes[next_id].kind in {"text", "table_cell"}
    ]


def text_position(node_id: str) -> tuple[int, int] | None:
    if not node_id.startswith("text:"):
        return None
    _, paragraph, sentence = node_id.split(":")
    return int(paragraph), int(sentence)


def discover_broad_candidates(graph: DocumentGraph, seed_values: list[str]) -> set[str]:
    """Keep broad structural neighbours as recall-oriented candidates.

    This deliberately does not create a low-resistance edge.  Same-column and
    local-text resemblance is weak evidence: it keeps a candidate in the outer
    forest, but must not make it rank like a recovered record template.
    """
    values = [node.id for node in graph.nodes.values() if node.kind == "value"]
    eligible: set[str] = set()
    for seed_id in seed_values:
        seed = graph.nodes[seed_id]
        seed_containers = node_containers(graph, seed_id)
        for candidate_id in values:
            if candidate_id == seed_id:
                continue
            candidate = graph.nodes[candidate_id]
            candidate_containers = node_containers(graph, candidate_id)
            resistance: float | None = None
            for left in seed_containers:
                for right in candidate_containers:
                    if left.kind == right.kind == "table_cell" and left.table == right.table and left.col == right.col and seed.origin == candidate.origin:
                        resistance = 0.28
                    elif left.kind == right.kind == "text" and seed.origin == candidate.origin == "explicit":
                        left_pos, right_pos = text_position(left.id), text_position(right.id)
                        if (
                            left_pos
                            and right_pos
                            and left.section == right.section
                            and abs(left_pos[0] - right_pos[0]) <= 1
                        ):
                            resistance = min(resistance or float("inf"), 0.75)
            if resistance is not None:
                eligible.add(candidate_id)
    return eligible


def table_cell_index(graph: DocumentGraph) -> dict[tuple[int, int, int], str]:
    return {
        (node.table, node.row, node.col): node.id
        for node in graph.nodes.values()
        if node.kind == "table_cell" and node.table is not None and node.row is not None and node.col is not None
    }


def install_translated_templates(
    graph: DocumentGraph,
    roots: dict[str, str],
    seed_bindings: list[tuple[str, str]],
) -> dict[tuple[str, str], list[dict]]:
    """Translate an entity-to-record coordinate template across a table.

    A seed is not generalized as "every adjacent pair in this column".  Its
    two value/error cell offsets are measured from the source entity cell, then
    applied only to other already-known entity cells in the same table.
    """
    cells = table_cell_index(graph)
    values_by_cells: dict[tuple[str, frozenset[str]], list[str]] = defaultdict(list)
    for node in graph.nodes.values():
        if node.kind != "value" or node.origin not in {"table_horizontal_pair", "table_vertical_pair"}:
            continue
        anchors = frozenset(container.id for container in node_containers(graph, node.id) if container.kind == "table_cell")
        values_by_cells[(node.origin, anchors)].append(node.id)

    matches: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for source_sample, seed_id in seed_bindings:
        seed = graph.nodes[seed_id]
        if seed.origin not in {"table_horizontal_pair", "table_vertical_pair"}:
            continue
        seed_cells = [container for container in node_containers(graph, seed_id) if container.kind == "table_cell"]
        if len(seed_cells) != 2:
            continue
        source_root = roots[source_sample]
        source_entities = [graph.nodes[node_id] for node_id, _, _ in graph.nodes[source_root].neighbours if graph.nodes[node_id].kind == "table_cell"]
        for source_entity in source_entities:
            if source_entity.table != seed_cells[0].table or any(cell.table != source_entity.table for cell in seed_cells):
                continue
            offsets = tuple(sorted((cell.row - source_entity.row, cell.col - source_entity.col) for cell in seed_cells))
            for target_sample, target_root in roots.items():
                target_entities = [graph.nodes[node_id] for node_id, _, _ in graph.nodes[target_root].neighbours if graph.nodes[node_id].kind == "table_cell"]
                for target_entity in target_entities:
                    if target_entity.table != source_entity.table:
                        continue
                    target_ids = []
                    for row_offset, col_offset in offsets:
                        target_id = cells.get((target_entity.table, target_entity.row + row_offset, target_entity.col + col_offset))
                        if target_id is None:
                            target_ids = []
                            break
                        target_ids.append(target_id)
                    if len(target_ids) != 2:
                        continue
                    for candidate_id in values_by_cells.get((seed.origin, frozenset(target_ids)), []):
                        graph.edge(target_root, candidate_id, 0.12, "translated_template")
                        matches[(target_sample, candidate_id)].append({
                            "seed_sample": source_sample,
                            "seed_pair": list(seed.pair or ()),
                            "offsets": [list(offset) for offset in offsets],
                            "table": target_entity.table,
                        })
    return matches


def harmonic_extension(graph: DocumentGraph, roots: dict[str, str]) -> tuple[list[str], np.ndarray, list[str]]:
    node_ids = list(graph.nodes)
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    root_ids = [root_id for root_id in roots.values() if graph.nodes[root_id].neighbours]
    root_labels = [sample for sample, root_id in roots.items() if root_id in root_ids]
    if not root_ids:
        return node_ids, np.zeros((len(node_ids), 0))
    fixed = np.array([index[root_id] for root_id in root_ids], dtype=int)
    fixed_set = set(fixed.tolist())
    unknown = np.array([position for position in range(len(node_ids)) if position not in fixed_set], dtype=int)
    unknown_pos = {position: offset for offset, position in enumerate(unknown)}
    fixed_pos = {position: offset for offset, position in enumerate(fixed)}
    conductance: dict[tuple[int, int], float] = defaultdict(float)
    for node_id, node in graph.nodes.items():
        left = index[node_id]
        for next_id, resistance, _ in node.neighbours:
            right = index[next_id]
            if left < right:
                conductance[(left, right)] += 1.0 / max(resistance, 1e-6)
    diagonal = np.zeros(len(unknown))
    rows, cols, data = [], [], []
    boundary = np.zeros((len(unknown), len(fixed)))
    for (left, right), weight in conductance.items():
        for a, b in ((left, right), (right, left)):
            if a in unknown_pos:
                ia = unknown_pos[a]
                diagonal[ia] += weight
                if b in unknown_pos:
                    rows.append(ia); cols.append(unknown_pos[b]); data.append(-weight)
                elif b in fixed_pos:
                    boundary[ia, fixed_pos[b]] += weight
    rows.extend(range(len(unknown))); cols.extend(range(len(unknown))); data.extend((diagonal + 1e-8).tolist())
    laplacian = csc_matrix((data, (rows, cols)), shape=(len(unknown), len(unknown)))
    solved = spsolve(laplacian, boundary)
    if solved.ndim == 1:
        solved = solved[:, None]
    potentials = np.zeros((len(node_ids), len(fixed)))
    potentials[fixed, np.arange(len(fixed))] = 1.0
    potentials[unknown] = np.clip(solved, 0.0, None)
    row_sum = potentials.sum(axis=1, keepdims=True)
    potentials = np.divide(potentials, row_sum, out=potentials, where=row_sum > 0)
    return node_ids, potentials, root_labels


def complete_document(name: str, docx: Path, state_path: Path, threshold: float, ratio: float, graph_config: dict) -> dict:
    graph = build_document_graph(docx)
    samples, bindings = load_state(state_path)
    roots = attach_entity_roots(graph, samples)
    consumed, seed_bindings, unmatched, repairs = install_seed_channels(
        graph,
        roots,
        bindings,
        grounding_limit=float(graph_config["seed_grounding_limit"]),
        ocr_repair_limit=float(graph_config["ocr_repair_limit"]),
    )
    seed_values = [value_id for _, value_id in seed_bindings]
    broad_eligible = discover_broad_candidates(graph, seed_values)
    template_matches = install_translated_templates(graph, roots, seed_bindings)
    template_eligible = {value_id for _, value_id in template_matches}
    eligible_values = broad_eligible | template_eligible
    node_ids, potential, labels = harmonic_extension(graph, roots)
    if not labels:
        return {"name": name, "status": "no_grounded_entity_root"}
    candidates: dict[tuple[str, float, float], dict] = {}
    known_samples = {re.sub(r"[^a-z0-9]+", "", sample.lower()) for sample in samples}
    for node_index, node_id in enumerate(node_ids):
        node = graph.nodes[node_id]
        if node.kind != "value" or node.pair is None or node_id not in eligible_values:
            continue
        vector = potential[node_index]
        maximum = float(vector.max())
        if maximum <= 0:
            continue
        value_sections = {container.section for container in node_containers(graph, node_id) if container.section}
        owner_tokens = set().union(*(graph.section_owners.get(section, set()) for section in value_sections))
        section_owners = owner_tokens & known_samples
        if section_owners:
            label_indices = [
                index for index, sample in enumerate(labels)
                if re.sub(r"[^a-z0-9]+", "", sample.lower()) in section_owners
            ]
        else:
            label_indices = np.argsort(vector)[::-1][:4].tolist()
        owner_maximum = max((float(vector[index]) for index in label_indices), default=0.0)
        for label_index in sorted(label_indices, key=lambda index: vector[index], reverse=True):
            score = float(vector[label_index])
            score_ceiling = owner_maximum if section_owners else maximum
            if score < threshold or score < score_ceiling * ratio:
                continue
            sample = labels[label_index]
            normalized_sample = re.sub(r"[^a-z0-9]+", "", sample.lower())
            # A sample named in a numbered subsection title is a deterministic
            # local owner.  Cross-references inside that subsection (for
            # example, "consistent with MZ815") cannot claim its new values.
            if section_owners and normalized_sample not in section_owners:
                continue
            candidate_key = binding_key(sample, *node.pair)
            if candidate_key in consumed:
                continue
            record = {
                "sample": sample,
                "number": node.pair[0],
                "error": node.pair[1],
                "potential": round(score, 5),
                "energy": round(float(-np.log(max(score, 1e-12))), 5),
                "source_kind": node.origin,
                "candidate_scope": "translated_template" if (sample, node_id) in template_matches else "broad_diffusion",
                "template_paths": template_matches.get((sample, node_id), []),
                "section": sorted(value_sections),
                "evidence": [graph.nodes[next_id].text[:300] for next_id, _, _ in node.neighbours if graph.nodes[next_id].kind in {"text", "table_cell"}][:2],
            }
            existing = candidates.get(candidate_key)
            if existing is None or record["energy"] < existing["energy"]:
                candidates[candidate_key] = record
    forest = sorted(candidates.values(), key=lambda item: (item["energy"], item["sample"], item["number"]))
    return {
        "name": name,
        "status": "ok",
        "graph_nodes": len(graph.nodes),
        "known_bindings": len(bindings),
        "fixed_seed_channels": len(seed_values),
        "broad_diffusion_candidates": len(broad_eligible),
        "translated_template_candidates": len(template_eligible),
        "unmatched_seed_bindings": unmatched,
        "seed_ocr_repairs": repairs,
        "candidate_forest_size": len(forest),
        "candidate_forest": forest[:80],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", required=True, metavar="NAME|DOCX|STATE_JSON")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("seeded_document_forest_config.json"))
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--ratio", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    graph_config = json.loads(args.config.read_text())
    threshold = args.threshold if args.threshold is not None else float(graph_config["candidate_threshold"])
    ratio = args.ratio if args.ratio is not None else float(graph_config["candidate_ratio"])
    results = []
    for raw in args.case:
        name, docx, state = raw.split("|", 2)
        results.append(complete_document(name, Path(docx), Path(state), threshold, ratio, graph_config))
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([{key: result.get(key) for key in ("name", "status", "graph_nodes", "known_bindings", "fixed_seed_channels", "candidate_forest_size")} for result in results], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
