"""Structured retrieval seeds (2026-09-06 Catalog-seeded chain).

`ConceptSeed` carries one exact scoped Concept ID (`bundle|publication|Concept|local`) into governed retrieval. It is
the runtime-owned value a Catalog read returned (or, when labelled so, a harness injection). It is never wrapped in the
`forced:` fixture prefix: a forced seed is a harness override built from a local path, a concept seed is an exact
identity that must already exist in the requested publication.
"""
from __future__ import annotations

from dataclasses import dataclass

CONCEPT_ID_PARTS = 4


@dataclass(frozen=True)
class ConceptSeed:
    concept_id: str
    origin: str = "catalog"           # "catalog" | "catalog-mock" | "injected-fixture-seed" (adversarial, never a discovery)

    def __post_init__(self) -> None:
        parts = self.concept_id.split("|")
        if len(parts) != CONCEPT_ID_PARTS or parts[2] != "Concept" or not all(parts):
            raise ValueError(f"malformed concept id: {self.concept_id!r}")

    @property
    def bundle_id(self) -> str:
        return self.concept_id.split("|", 3)[0]

    @property
    def publication_id(self) -> str:
        return self.concept_id.split("|", 3)[1]

    @property
    def local(self) -> str:
        return self.concept_id.split("|", 3)[3]

    def __str__(self) -> str:           # cache keys / scope records: the exact id, never a fixture path
        return f"concept:{self.concept_id}"
