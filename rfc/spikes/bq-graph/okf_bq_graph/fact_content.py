"""Canonical content manifest for a literal SQL fixture (`okf-fact-content/1`).

The ordinary-SQL comparison selects its fact-data version as the digest of the receipt example's synthetic
fixture script (`fixtures/facts/fixture.sql`, vendored byte for byte from the pinned SDK commit). A script
digest alone says nothing about *what* rows it loads, so this module derives a canonical schema-and-rows
manifest from the script and hashes that too. Both digests are recorded on the plan's `facts.selected_version`
and re-checked by `validate_plan` every time the card is built.

This is a bounded extractor for the shapes the fixture actually uses — `CREATE OR REPLACE TABLE` with one column
per line and `INSERT INTO … (columns) VALUES (…)` with literal tuples — not a SQL interpreter. It fails on any
statement it did not consume, so a fixture that grows a construct it does not understand fails loudly instead of
producing a digest that silently omits rows.

Canonical form: UTF-8 JSON, sorted object keys, compact separators, ASCII escaping, one trailing newline. Rows are
sorted by their own compact encoding (duplicates retained). NUMERIC values are decimal strings with nine fractional
digits, INT64 decimal strings, TIMESTAMP UTC with six fractional digits and `Z`, DATE ISO dates, null as null.
"""
from __future__ import annotations

import ast
import datetime as _dt
import decimal
import hashlib
import json
import re
from pathlib import Path

FORMAT = "okf-fact-content/1"

_TABLE = re.compile(r"CREATE OR REPLACE TABLE `(?:[\w-]+\.)?(\w+)`\s*\((.*?)\);", re.S)
_INSERT = re.compile(r"INSERT INTO `(?:[\w-]+\.)?(\w+)`\s*\((.*?)\)\s*VALUES\s*(.*?);", re.S)
_TYPED_LITERAL = re.compile(r"\b(?:NUMERIC|TIMESTAMP|DATE)\s+(?=')")


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cook(field: dict, value):
    if value is None:
        return None
    typ = field["type"]
    if typ == "NUMERIC":
        return format(decimal.Decimal(value), ".9f")
    if typ == "TIMESTAMP":
        return (_dt.datetime.fromisoformat(value).astimezone(_dt.timezone.utc)
                .isoformat(timespec="microseconds").replace("+00:00", "Z"))
    if typ == "INT64":
        return str(int(value))
    if typ == "DATE":
        return _dt.date.fromisoformat(value).isoformat()
    return value


def extract(sql_text: str) -> dict:
    """Derive the manifest from a literal fixture script. Raises ValueError on anything it cannot consume."""
    sql = re.sub(r"--[^\n]*", "", sql_text)
    tables: dict[str, dict] = {}
    for match in _TABLE.finditer(sql):
        name, ddl = match.groups()
        fields = []
        for line in ddl.strip().split(","):
            col, typ, *mode = line.split()
            if mode not in ([], ["NOT", "NULL"]):
                raise ValueError(f"{name}.{col}: unsupported column clause {' '.join(mode)!r}")
            fields.append({"name": col, "type": typ, "mode": "REQUIRED" if mode else "NULLABLE"})
        if name in tables:
            raise ValueError(f"{name}: created twice")
        tables[name] = {"schema": fields, "rows": []}
    sql = _TABLE.sub("", sql)
    for match in _INSERT.finditer(sql):
        name, columns, values = match.groups()
        if name not in tables:
            raise ValueError(f"{name}: INSERT into a table the script did not create")
        schema = tables[name]["schema"]
        if [c.strip() for c in columns.split(",")] != [f["name"] for f in schema]:
            raise ValueError(f"{name}: INSERT column list differs from the table's schema order")
        rows = ast.literal_eval("[" + _TYPED_LITERAL.sub("", values) + "]")
        for row in rows:
            if len(row) != len(schema):
                raise ValueError(f"{name}: a row has {len(row)} values for {len(schema)} columns")
            tables[name]["rows"].append([_cook(f, v) for f, v in zip(schema, row)])
    sql = _INSERT.sub("", sql)
    if sql.strip():
        raise ValueError(f"unconsumed SQL in the fixture script: {sql.strip()[:120]!r}")
    for table in tables.values():
        table["rows"].sort(key=encoded)
    return {"format": FORMAT, "tables": dict(sorted(tables.items()))}


def canonical_bytes(manifest: dict) -> bytes:
    return encoded(manifest)


def row_counts(manifest: dict) -> dict[str, int]:
    return {name: len(table["rows"]) for name, table in manifest["tables"].items()}


def per_table_digests(manifest: dict) -> dict[str, str]:
    return {name: sha256(encoded(table)) for name, table in manifest["tables"].items()}


def manifest_from_file(path: Path | str) -> dict:
    return extract(Path(path).read_text())


if __name__ == "__main__":
    import sys
    m = manifest_from_file(sys.argv[1])
    raw = canonical_bytes(m)
    sys.stdout.write(raw.decode())
    print(json.dumps({"sha256": sha256(raw), "bytes": len(raw), "row_counts": row_counts(m)}, indent=1), file=sys.stderr)
