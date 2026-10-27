#!/usr/bin/env python3
"""Small, deterministic probe for seeded low-entropy table-path recovery.

This is deliberately not an extractor.  It proves one narrow hypothesis:
given a few trustworthy entity hooks in an HTML table, can the repeated
record block containing them be recovered without using the table headers?
"""

from __future__ import annotations

import argparse
import html.parser
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SPACE_RE = re.compile(r"\s+")
ENTITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+$")
AGE_RE = re.compile(r"^\d+(?:\.\d+)?\s*[±\+\-]\s*\d+(?:\.\d+)?$")
DECIMAL_RE = re.compile(r"^\d+\.\d+$")
INTEGER_RE = re.compile(r"^\d+$")


def clean(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def normalise(value: str) -> str:
    return clean(value).lower().replace("－", "-").replace("–", "-")


class TableParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_rows = []
        elif tag == "tr" and self._table_rows is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table_rows is not None:
            self._table_rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_rows is not None:
            self.tables.append(self._table_rows)
            self._table_rows = None


def cell_kind(value: str) -> str:
    value = clean(value)
    if not value:
        return "empty"
    if ENTITY_RE.fullmatch(value):
        return "entity"
    if AGE_RE.fullmatch(value):
        return "value_plus_error"
    if DECIMAL_RE.fullmatch(value):
        return "decimal"
    if INTEGER_RE.fullmatch(value):
        return "integer"
    return "text"


def row_signature(row: list[str]) -> tuple[str, ...]:
    kinds = [cell_kind(cell) for cell in row]
    while kinds and kinds[-1] == "empty":
        kinds.pop()
    return tuple(kinds)


def entity_root(value: str) -> str:
    """Return the stable prefix of a hyphen-number analysis identifier."""
    parts = normalise(value).split("-")
    while parts and parts[-1].isdigit():
        parts.pop()
    return "-".join(parts) if parts else normalise(value)


@dataclass(frozen=True)
class SeedHit:
    table_index: int
    row_index: int
    column_index: int
    value: str


def locate_seeds(tables: list[list[list[str]]], seeds: Iterable[str]) -> list[SeedHit]:
    wanted = {normalise(seed) for seed in seeds}
    hits: list[SeedHit] = []
    for table_index, table in enumerate(tables):
        for row_index, row in enumerate(table):
            for column_index, cell in enumerate(row):
                if normalise(cell) in wanted:
                    hits.append(SeedHit(table_index, row_index, column_index, cell))
    return hits


def longest_contiguous_run(indices: list[int]) -> tuple[int, int]:
    if not indices:
        raise ValueError("Cannot recover a path without candidate rows")
    best_start = best_end = start = previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            previous = index
        else:
            if previous - start > best_end - best_start:
                best_start, best_end = start, previous
            start = previous = index
    if previous - start > best_end - best_start:
        best_start, best_end = start, previous
    return best_start, best_end


def signature_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    return sum(a == b for a, b in zip(left, right))


def recover_vertical_record_path(
    table: list[list[str]],
    *,
    entity_column: int,
    seed_roots: set[str],
    expected_signature: tuple[str, ...],
) -> dict | None:
    """Recover one table segment using only hooks and repeated row shape."""

    candidates: list[int] = []
    for row_index, row in enumerate(table):
        if len(row) <= entity_column or not ENTITY_RE.fullmatch(clean(row[entity_column])):
            continue
        if entity_root(row[entity_column]) not in seed_roots:
            continue
        signature = row_signature(row)
        overlap = signature_overlap(signature, expected_signature)
        if overlap >= max(3, len(expected_signature) - 2):
            candidates.append(row_index)
    if not candidates:
        return None
    start, end = longest_contiguous_run(candidates)
    records = []
    for row_index in range(start, end + 1):
        row = table[row_index]
        records.append(
            {
                "source_row": row_index,
                "entity": row[entity_column],
                "age_like_values": [
                    {"column": column, "raw": cell}
                    for column, cell in enumerate(row)
                    if AGE_RE.fullmatch(clean(cell))
                ],
                "signature": list(row_signature(row)),
            }
        )

    return {
        "orientation": "vertical_row_path",
        "entity_column": entity_column,
        "path_rows": {"start": start, "end": end, "count": end - start + 1},
        "template": list(expected_signature),
        "records": records,
    }


def recover_continuation_path(tables: list[list[list[str]]], hits: list[SeedHit]) -> dict:
    """Recover all adjacent table segments sharing the hooked entity/template.

    A continued table can be physically split by a page break.  Its relation is
    inferred from repeated record shape and the same entity root, not from a
    caption such as 'continued Table 1'.
    """
    entity_columns = Counter(hit.column_index for hit in hits)
    entity_column, seed_count = entity_columns.most_common(1)[0]
    seed_roots = {entity_root(hit.value) for hit in hits if hit.column_index == entity_column}
    expected_signature = Counter(
        row_signature(tables[hit.table_index][hit.row_index])
        for hit in hits
        if hit.column_index == entity_column
    ).most_common(1)[0][0]
    seed_table_indexes = {hit.table_index for hit in hits}

    # Expand from the seed tables only through immediately neighbouring tables
    # that continue the same entity-root/template pattern.
    selected = set(seed_table_indexes)
    changed = True
    while changed:
        changed = False
        for table_index in range(len(tables)):
            if table_index in selected:
                continue
            if not ({table_index - 1, table_index + 1} & selected):
                continue
            segment = recover_vertical_record_path(
                tables[table_index],
                entity_column=entity_column,
                seed_roots=seed_roots,
                expected_signature=expected_signature,
            )
            if segment is not None:
                selected.add(table_index)
                changed = True

    segments = []
    records = []
    for table_index in sorted(selected):
        segment = recover_vertical_record_path(
            tables[table_index],
            entity_column=entity_column,
            seed_roots=seed_roots,
            expected_signature=expected_signature,
        )
        if segment is None:
            continue
        segment["table_index"] = table_index
        segments.append(segment)
        for record in segment["records"]:
            records.append({"table_index": table_index, **record})

    return {
        "orientation": "vertical_row_path_with_continuations",
        "entity_column": entity_column,
        "seed_count": seed_count,
        "seed_roots": sorted(seed_roots),
        "template": list(expected_signature),
        "table_segments": segments,
        "record_count": len(records),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown", type=Path)
    parser.add_argument("r1_json", type=Path)
    parser.add_argument("--sample", default="js-jch")
    parser.add_argument("--seed-count", type=int, default=3)
    parser.add_argument("--seed", action="append", default=[], help="Explicit entity hook; repeatable")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    r1 = json.loads(args.r1_json.read_text())
    sample = next(item for item in r1["samples"] if normalise(item["id"]) == normalise(args.sample))
    seeds = args.seed or [spot["id"] for spot in sample.get("spots", [])][: args.seed_count]

    parser_html = TableParser()
    parser_html.feed(args.markdown.read_text())
    hits = locate_seeds(parser_html.tables, seeds)
    if not hits:
        raise SystemExit(f"No seed hooks found for {args.sample}: {seeds}")
    recovered = recover_continuation_path(parser_html.tables, hits)

    report = {
        "experiment": "seeded_low_entropy_table_path",
        "source": str(args.markdown),
        "sample": args.sample,
        "seed_hooks": seeds,
        "located_hooks": [hit.__dict__ for hit in hits],
        "table_indexes": sorted({hit.table_index for hit in hits}),
        "recovered_path": recovered,
        "interpretation": (
            "The path is selected from hook coordinates, entity-root continuity, and repeated row shape. "
            "No table header or column name participates in the decision."
        ),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "seed_hooks": seeds,
        "located_hooks": len(hits),
        "segments": [
            {"table_index": segment["table_index"], "rows": segment["path_rows"]}
            for segment in recovered["table_segments"]
        ],
        "record_count": recovered["record_count"],
        "entities": [record["entity"] for record in recovered["records"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
