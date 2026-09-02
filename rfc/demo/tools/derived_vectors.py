#!/usr/bin/env python3
"""Independent re-derivation of derived/identities.json (Python, stdlib only).

Adapted from okf-phase0-mvp/golden/vectors_gen.py (canonical CBOR, domain-
separated SHA-256, canon:v1 text normalization). Reads derived/bundle bytes
on disk plus the fixture compile manifests, recomputes the derived
observation / snapshot / publication triple and concept versions, and
compares with what tools/build-derived.mjs (JS) pinned. Read-only: never
touches okf-phase0-mvp/ or the authored fixture.

Usage: python3 tools/derived_vectors.py   (exit 0 on match)
"""
import hashlib, json, sys, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
BUNDLE = DEMO / "derived" / "bundle"
MANIFESTS = DEMO / "fixture" / "golden" / "manifests"
PINNED = json.loads((DEMO / "derived" / "identities.json").read_text("utf-8"))
C = PINNED["inputs"]


def _head(major, arg):
    if arg < 24:
        return bytes([(major << 5) | arg])
    for ai, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if arg < (1 << (8 * size)):
            return bytes([(major << 5) | ai]) + arg.to_bytes(size, "big")
    raise ValueError("length too large")


def cbor(obj):
    if obj is False: return b"\xf4"
    if obj is True: return b"\xf5"
    if obj is None: return b"\xf6"
    if isinstance(obj, int):
        if obj < 0: raise TypeError("negative")
        return _head(0, obj)
    if isinstance(obj, bytes): return _head(2, len(obj)) + obj
    if isinstance(obj, str):
        b = unicodedata.normalize("NFC", obj).encode("utf-8")
        return _head(3, len(b)) + b
    if isinstance(obj, list): return _head(4, len(obj)) + b"".join(cbor(x) for x in obj)
    if isinstance(obj, dict):
        items = sorted((cbor(k), cbor(v)) for k, v in obj.items())
        return _head(5, len(items)) + b"".join(k + v for k, v in items)
    raise TypeError(type(obj))


def h(domain, obj):
    return hashlib.sha256(domain.encode("ascii") + b"\x00" + cbor(obj)).digest()


def hexid(d): return "sha256:" + d.hex()


def normalize_text(s):
    s = unicodedata.normalize("NFC", s.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(ln.rstrip(" \t") for ln in s.split("\n")).rstrip("\n") + "\n"


def split_frontmatter(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0] != "---": raise ValueError("no frontmatter block")
    close = lines[1:].index("---") + 1
    return "\n".join(lines[1:close]), "\n".join(lines[close + 1:])


def main():
    file_hashes = {}
    for p in sorted(BUNDLE.rglob("*")):
        if p.is_dir(): continue
        if p.is_symlink() or not p.is_file(): raise ValueError(f"non-regular file: {p}")
        path = unicodedata.normalize("NFC", p.relative_to(BUNDLE).as_posix())
        file_hashes[path] = hashlib.sha256(p.read_bytes()).digest()
    pairs = [[k, v] for k, v in sorted(file_hashes.items(), key=lambda kv: kv[0].encode("utf-8"))]
    source_manifest_hash = h("okf-context:source-manifest:v1", pairs)
    mh = {n: hashlib.sha256((MANIFESTS / f"{n}.json").read_bytes()).digest()
          for n in ("canonicalization-manifest", "semantic-config", "resolver-manifest", "vocabulary-manifest")}
    observation_id = h("okf-context:observation:v1",
                       {"bundle_key": C["bundle_key"], "revision": C["revision"], "source_uri": C["source_uri"]})
    snapshot_id = h("okf-context:snapshot:v1", {
        "bundle_key": C["bundle_key"],
        "source_manifest_hash": source_manifest_hash,
        "canonicalization_manifest_hash": mh["canonicalization-manifest"],
        "compiler_semantics_version": C["compiler_semantics_version"],
        "semantic_config_hash": mh["semantic-config"],
        "vocabulary_manifest_hash": mh["vocabulary-manifest"],
        "resolver_manifest_hash": mh["resolver-manifest"],
    })
    publication_id = h("okf-context:publication:v1", {
        "deployment_key": C["deployment_key"],
        "observation_id": observation_id,
        "snapshot_id": snapshot_id,
        "profile_contract_version": C["profile_contract_version"],
    })
    concept_versions = {}
    for path in file_hashes:
        if not path.endswith(".md") or path in ("index.md", "log.md"): continue
        fm, body = split_frontmatter((BUNDLE / path).read_text("utf-8"))
        concept_versions[path] = hexid(h("okf-context:concept-version:v1",
                                         [f"{C['bundle_key']}#{path[:-3]}", normalize_text(fm), normalize_text(body)]))
    got = {
        "observation_id": hexid(observation_id),
        "snapshot_id": hexid(snapshot_id),
        "publication_id": hexid(publication_id),
        "source_manifest_hash": hexid(source_manifest_hash),
        "concept_version_ids": concept_versions,
        "file_sha256": {k: v.hex() for k, v in file_hashes.items()},
    }
    ok = True
    for k in ("observation_id", "snapshot_id", "publication_id", "source_manifest_hash"):
        same = got[k] == PINNED[k]; ok &= same
        print(("OK  " if same else "FAIL"), k, got[k])
    for k in ("concept_version_ids", "file_sha256"):
        same = got[k] == PINNED[k]; ok &= same
        print(("OK  " if same else "FAIL"), k, f"({len(got[k])} entries)")
    # §11-style gate: frontmatter `type` on every non-reserved .md
    for path in file_hashes:
        if path.endswith(".md") and path not in ("index.md", "log.md"):
            fm, _ = split_frontmatter((BUNDLE / path).read_text("utf-8"))
            if not any(ln.startswith("type: ") and ln[6:].strip() for ln in fm.split("\n")):
                ok = False; print("FAIL missing type:", path)
    print("derived identities: Python == JS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
