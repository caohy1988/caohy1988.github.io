# Intent — Catalog-seeded receipt chain (Slice A, hermetic)

Extend `chain.py` so a freshly read Dataplex Catalog runtime pin (publication + exact Concept id), not a fixture, controls
which Acme context and computation the existing receipt consumer accepts, including while the publication head changes.
Hermetic first: every Catalog read in the suite is an injected response through the real parser and is labelled
`catalog-mock`; only `catalog.HttpReader` may label a seed `catalog`. No board-pack/RFC claim edits, no merge, no GQL,
embeddings, reservation or restricted-SA work. Live Slice B (B1 original entry, B2 owned dataset/entry lifecycle,
stale/republish/mixed-payload cases) is a separate pass and is not claimed by this slice.
