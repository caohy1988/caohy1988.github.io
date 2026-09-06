"""Projection model: versioned, scoped node/edge identities (spec §3).

Every node and edge is bound to (bundle_id, publication_id). IDs are
deterministic functions of the pinned source bytes, so two compilations of
the same bytes yield byte-identical projections.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

COMPILER_VERSION = "okf_bq_graph.compile/0.1.0"

NODE_KINDS = ("Concept", "Section", "Source", "Actor", "Artifact", "LogEntry")
RELATIONS = (
    "LINKS_TO", "HAS_SECTION", "NEXT", "CITES", "MENTIONS", "DERIVES_FROM",
    "RESOLVES_TO", "GENERATED_BY", "VERIFIED_BY", "EXECUTED_BY", "ATTESTED_BY",
    "REFERENCES",
)
# Relation set used by the pinned Neo4j impact query (spec §4).
IMPACT_RELATIONS = ("LINKS_TO", "EXECUTED_BY", "DERIVES_FROM", "RESOLVES_TO", "HAS_SECTION", "MENTIONS")

_SAFE = re.compile(r"[^A-Za-z0-9_./#:@\-]")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def node_id(bundle_id: str, publication_id: str, kind: str, local: str) -> str:
    assert kind in NODE_KINDS, kind
    return f"{bundle_id}|{publication_id}|{kind}|{local}"


def edge_id(bundle_id: str, publication_id: str, src: str, dst: str, relation: str,
            declaration: str, ordinal: int = 0) -> str:
    assert relation in RELATIONS, relation
    h = sha256_text("\x1f".join([bundle_id, publication_id, src, dst, relation, declaration, str(ordinal)]))[:24]
    return f"{bundle_id}|{publication_id}|{relation}|{h}"


@dataclass
class Node:
    node_id: str
    bundle_id: str
    publication_id: str
    kind: str
    local_id: str
    path: Optional[str] = None
    title: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    stale_after: Optional[str] = None
    stub: bool = False
    actor_kind: Optional[str] = None
    heading: Optional[str] = None
    section_order: Optional[int] = None
    text: Optional[str] = None
    text_sha256: Optional[str] = None
    resource: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    runtime: Optional[str] = None
    entry_date: Optional[str] = None
    extra_frontmatter: Optional[str] = None   # JSON, preserved unknown keys
    file_sha256: Optional[str] = None
    attrs: Optional[str] = None               # JSON, kind-specific extras


@dataclass
class Edge:
    edge_id: str
    bundle_id: str
    publication_id: str
    src_id: str
    dst_id: str
    relation: str
    declaration: str                 # e.g. body_link, frontmatter.sources[1], footnote, frontmatter.executor
    section_id: Optional[str] = None
    authored_at: Optional[str] = None  # VERIFIED_BY / GENERATED_BY timestamp text as authored
    resolution: Optional[str] = None # absolute | relative | root_fallback | url | unresolved
    inferred: bool = False           # true when the edge is not a literal authored declaration
    attrs: Optional[str] = None      # JSON provenance (usage_count, window, link text, raw target)


def to_rows(items: list[Any]) -> list[dict]:
    return [asdict(x) for x in items]


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
