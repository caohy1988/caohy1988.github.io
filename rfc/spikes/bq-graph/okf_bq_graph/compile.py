"""Deterministic OKF bundle -> graph projection compiler (spec §3, plan Task 2).

No LLM. Never executes bundle code. Strict path resolution per OKF §6:
`/x` is bundle-root relative, `x` is document-relative; a bare root-relative
path that only resolves from the root is accepted but labelled
`root_fallback` and inferred. Anything escaping the bundle is rejected.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from .model import (COMPILER_VERSION, Edge, Node, edge_id, node_id, sha256_bytes,
                    sha256_text, stable_json, to_rows)

RESERVED = {"index.md", "log.md"}
KNOWN_KEYS = {"type", "title", "description", "resource", "tags", "generated", "verified",
              "status", "stale_after", "sources", "usage_window", "runtime", "parameters",
              "computation", "executor", "attester", "timestamp"}
MD_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:")
LOG_DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
LOG_KIND_RE = re.compile(r"^\*\*([^*]+)\*\*[:\s]*")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
MAX_SECTION_CHARS = 2400   # parity with the pinned Neo4j parser


class _Loader(yaml.SafeLoader):
    """Keep timestamps as authored text (YAML 1.2 core behaviour)."""


_Loader.yaml_implicit_resolvers = {
    ch: [(t, r) for t, r in rs if t != "tag:yaml.org,2002:timestamp"]
    for ch, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


# ---------------------------------------------------------------- helpers

def split_frontmatter(text: str) -> tuple[dict, str, bool]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, True
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                fm = yaml.load("\n".join(lines[1:i]), Loader=_Loader) or {}
            except yaml.YAMLError:
                return {}, text, False
            if not isinstance(fm, dict):
                return {}, text, False
            return fm, "\n".join(lines[i + 1:]).lstrip("\n"), True
    return {}, text, False


def iter_lines(body: str):
    open_marker: Optional[str] = None
    for i, line in enumerate(body.splitlines()):
        m = FENCE_RE.match(line.lstrip())
        if m:
            marker = m.group(1)
            if open_marker is None:
                open_marker = marker
            elif marker[0] == open_marker[0] and len(marker) >= len(open_marker):
                open_marker = None
            yield i, line, True
            continue
        yield i, line, open_marker is not None


def strip_fences(text: str) -> str:
    return "\n".join(l for _, l, f in iter_lines(text) if not f)


def split_sections(body: str) -> list[tuple[str, str, int]]:
    sections: list[tuple[str, list[str]]] = []
    heading, cur = "_preamble", []
    for _, line, in_fence in iter_lines(body):
        if not in_fence and line.startswith("# "):
            if any(l.strip() for l in cur):
                sections.append((heading, cur))
            heading, cur = line[2:].strip(), []
        else:
            cur.append(line)
    if any(l.strip() for l in cur):
        sections.append((heading, cur))
    out = []
    for h, lines in sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        if len(text) <= MAX_SECTION_CHARS:
            out.append((h, text, 1))
            continue
        buf, size, part = [], 0, 1
        for p in text.split("\n\n"):
            if buf and size + len(p) > MAX_SECTION_CHARS:
                out.append((h, "\n\n".join(buf), part)); part += 1; buf, size = [], 0
            buf.append(p); size += len(p) + 2
        if buf:
            out.append((h, "\n\n".join(buf), part))
    return out


def actor_kind(raw: str) -> str:
    if raw.startswith("human:"):
        return "human"
    if raw.startswith("process:"):
        return "process"
    return "agent"


def _scalar(v: Any) -> Optional[str]:
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    return json.dumps(v, default=str, sort_keys=True)


def _tags(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [t.strip() for t in v.split(",") if t.strip()]
    if isinstance(v, (list, tuple)):
        return [str(t) for t in v]
    return [str(v)]


# ---------------------------------------------------------------- compiler

class Compiler:
    def __init__(self, root: str, bundle_id: str, source_pin: str):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(root)
        self.bundle_id = bundle_id
        self.source_pin = source_pin
        self.warnings: list[dict] = []
        self.rejections: list[dict] = []

    # -- path resolution (OKF §6, strict)
    def resolve(self, raw: str, from_dir: str) -> tuple[Optional[str], str]:
        """Return (bundle-relative posix path or None, resolution label)."""
        target = raw.split("#", 1)[0].split("?", 1)[0]
        if not target:
            return None, "empty"
        if "://" in target or target.startswith(("mailto:", "tel:", "//")):
            return None, "url"
        if target.startswith("/"):
            cand = posixpath.normpath(target.lstrip("/"))
            if cand.startswith("..") or cand.startswith("/"):
                return None, "escape"
            return cand, "absolute"
        cand = posixpath.normpath(posixpath.join(from_dir, target) if from_dir else target)
        if cand.startswith("../") or cand == "..":
            return None, "escape"
        if (self.root / cand).exists():
            return cand, "relative"
        cand2 = posixpath.normpath(target)
        if cand2.startswith("../") or cand2 == "..":
            return None, "escape"
        if cand2 != cand and (self.root / cand2).exists():
            return cand2, "root_fallback"
        return cand, "unresolved"

    # -- manifest
    def source_manifest(self) -> list[dict]:
        rows = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root).as_posix()
            if any(part.startswith(".") for part in rel.split("/")):
                continue
            b = p.read_bytes()
            rows.append({"path": rel, "sha256": sha256_bytes(b), "bytes": len(b)})
        return rows

    def compile(self) -> dict:
        manifest = self.source_manifest()
        manifest_digest = sha256_text(stable_json({"compiler": COMPILER_VERSION, "bundle_id": self.bundle_id,
                                                   "source_pin": self.source_pin, "files": manifest}))
        pub = "pub_" + manifest_digest[:16]
        B, P = self.bundle_id, pub
        nodes: dict[str, Node] = {}
        edges: list[Edge] = []
        concept_by_path: dict[str, str] = {}   # rel .md path -> node_id
        file_sha = {m["path"]: m["sha256"] for m in manifest}

        def nid(kind: str, local: str) -> str:
            return node_id(B, P, kind, local)

        def add_edge(src: str, dst: str, rel: str, decl: str, ordinal: int = 0, **kw: Any) -> Edge:
            e = Edge(edge_id=edge_id(B, P, src, dst, rel, decl, ordinal), bundle_id=B, publication_id=P,
                     src_id=src, dst_id=dst, relation=rel, declaration=decl, **kw)
            edges.append(e)
            return e

        def actor(raw: str) -> str:
            a = nid("Actor", f"actor:{raw}")
            if a not in nodes:
                nodes[a] = Node(node_id=a, bundle_id=B, publication_id=P, kind="Actor", local_id=f"actor:{raw}",
                                title=raw, actor_kind=actor_kind(raw))
            return a

        def artifact(rel: str) -> str:
            a = nid("Artifact", f"art:{rel}")
            if a not in nodes:
                p = self.root / rel
                text = None
                if p.exists() and p.stat().st_size <= 65536:
                    try:
                        text = p.read_bytes().decode("utf-8")
                    except UnicodeDecodeError:
                        text = None
                nodes[a] = Node(node_id=a, bundle_id=B, publication_id=P, kind="Artifact", local_id=f"art:{rel}",
                                path=rel, title=rel, stub=not p.exists(), file_sha256=file_sha.get(rel),
                                text=text, text_sha256=sha256_text(text) if text else None,
                                attrs=stable_json({"kind": "code" if rel.endswith((".py", ".sql", ".js")) else "file"}))
            return a

        def stub_concept(rel_md: str) -> str:
            cid = rel_md[:-3]
            c = nid("Concept", cid)
            if c not in nodes:
                nodes[c] = Node(node_id=c, bundle_id=B, publication_id=P, kind="Concept", local_id=cid, path=rel_md,
                                title=Path(cid).name.replace("-", " ").title(), type="Concept", status=None, stub=True)
            return c

        md_files = [m["path"] for m in manifest if m["path"].endswith(".md")
                    and posixpath.basename(m["path"]) not in RESERVED]
        parsed: dict[str, dict] = {}
        # pass 1: concept nodes + sections + actors + sources
        for rel in md_files:
            text = (self.root / rel).read_text(encoding="utf-8-sig")
            fm, body, ok = split_frontmatter(text)
            if not ok:
                self.warnings.append({"path": rel, "warning": "unparseable frontmatter; defaults applied"})
            cid = rel[:-3]
            cdir = posixpath.dirname(cid)
            c = nid("Concept", cid)
            concept_by_path[rel] = c
            extra = {str(k): v for k, v in fm.items() if str(k) not in KNOWN_KEYS}
            gen = fm.get("generated") if isinstance(fm.get("generated"), dict) else {}
            nodes[c] = Node(
                node_id=c, bundle_id=B, publication_id=P, kind="Concept", local_id=cid, path=rel,
                title=_scalar(fm.get("title")) or Path(cid).name.replace("-", " ").title(),
                type=_scalar(fm.get("type")) or "Concept", status=_scalar(fm.get("status")) or "stable",
                stale_after=_scalar(fm.get("stale_after")), stub=False, resource=_scalar(fm.get("resource")),
                description=_scalar(fm.get("description")), tags=_tags(fm.get("tags")),
                runtime=_scalar(fm.get("runtime")), file_sha256=file_sha[rel],
                text=body, text_sha256=sha256_text(body),
                extra_frontmatter=stable_json(extra) if extra else None,
                attrs=stable_json({"has_frontmatter": bool(fm), "frontmatter_ok": ok,
                                   "parameters": fm.get("parameters"), "receipt": (fm.get("executor") or {}).get("receipt")
                                   if isinstance(fm.get("executor"), dict) else None,
                                   "generated_at": _scalar(gen.get("at")) if gen else None}))
            parsed[rel] = {"fm": fm, "body": body, "cid": cid, "dir": cdir, "node": c}
            # trust family
            if gen and isinstance(gen.get("by"), str):
                add_edge(c, actor(gen["by"]), "GENERATED_BY", "frontmatter.generated", authored_at=_scalar(gen.get("at")))
            ver = fm.get("verified")
            if isinstance(ver, dict):
                ver = [ver]
            for i, v in enumerate(ver or []):
                if isinstance(v, dict) and isinstance(v.get("by"), str):
                    add_edge(c, actor(v["by"]), "VERIFIED_BY", f"frontmatter.verified[{i}]", i, authored_at=_scalar(v.get("at")))
            # sections
            secs = []
            for order, (heading, stext, part) in enumerate(split_sections(body)):
                s = nid("Section", f"{cid}#s{order}")
                nodes[s] = Node(node_id=s, bundle_id=B, publication_id=P, kind="Section", local_id=f"{cid}#s{order}",
                                path=rel, title=heading, heading=heading, section_order=order, text=stext,
                                text_sha256=sha256_text(stext), attrs=stable_json({"part": part, "chars": len(stext)}))
                add_edge(c, s, "HAS_SECTION", "body.h1", order)
                if secs:
                    add_edge(secs[-1], s, "NEXT", "body.order", order)
                secs.append(s)
            parsed[rel]["sections"] = secs
        # pass 2: sources, links, computation family, footnotes (needs full concept set)
        resolved_sources: set[str] = set()
        for rel, pr in parsed.items():
            fm, c, cdir = pr["fm"], pr["node"], pr["dir"]
            shared_window = fm.get("usage_window") if isinstance(fm.get("usage_window"), dict) else {}
            sid_to_source: dict[str, str] = {}
            for i, entry in enumerate(fm.get("sources") or []):
                if not isinstance(entry, dict) or not entry.get("resource"):
                    self.warnings.append({"path": rel, "warning": f"sources[{i}] without resource dropped"})
                    continue
                res = str(entry["resource"])
                s = nid("Source", f"src:{res}")
                if s not in nodes:
                    nodes[s] = Node(node_id=s, bundle_id=B, publication_id=P, kind="Source", local_id=f"src:{res}",
                                    resource=res, title=_scalar(entry.get("title")),
                                    attrs=stable_json({"author": entry.get("author"),
                                                       "last_modified": _scalar(entry.get("last_modified")),
                                                       "is_url": "://" in res}))
                if entry.get("id"):
                    sid_to_source[str(entry["id"])] = s
                window = entry.get("usage_window") if isinstance(entry.get("usage_window"), dict) else shared_window
                add_edge(c, s, "DERIVES_FROM", f"frontmatter.sources[{i}]", i,
                         attrs=stable_json({"id": entry.get("id"), "usage_count": entry.get("usage_count"),
                                            "usage_window_from": _scalar((window or {}).get("from")),
                                            "usage_window_to": _scalar((window or {}).get("to"))}))
                if "://" not in res and " " not in res and s not in resolved_sources:
                    # RESOLVES_TO is a property of the Source node, emitted once per Source
                    resolved_sources.add(s)
                    target, how = self.resolve(res, cdir)
                    decl = "frontmatter.sources[].resource"
                    if how == "escape":
                        self.rejections.append({"path": rel, "field": f"sources[{i}].resource", "raw": res, "reason": "escapes bundle"})
                    elif target and target.endswith(".md") and target in concept_by_path:
                        add_edge(s, concept_by_path[target], "RESOLVES_TO", decl, resolution=how, inferred=(how == "root_fallback"))
                    elif target and (self.root / target).exists():
                        add_edge(s, artifact(target), "RESOLVES_TO", decl, resolution=how, inferred=(how == "root_fallback"))
                    elif target and target.endswith(".md"):
                        add_edge(s, stub_concept(target), "RESOLVES_TO", decl, resolution="unresolved")
            # computation family (§10): executor -> Concept (Skill); attester -> Artifact; computation file -> Artifact
            for fld, relname in (("executor", "EXECUTED_BY"), ("attester", "ATTESTED_BY")):
                blk = fm.get(fld)
                res = blk.get("resource") if isinstance(blk, dict) else None
                if not isinstance(res, str) or "://" in res:
                    continue
                target, how = self.resolve(res, cdir)
                if how == "escape" or target is None:
                    self.rejections.append({"path": rel, "field": f"{fld}.resource", "raw": res, "reason": how})
                    continue
                if target.endswith(".md"):
                    dst = concept_by_path.get(target) or stub_concept(target)
                else:
                    dst = artifact(target)
                add_edge(c, dst, relname, f"frontmatter.{fld}.resource", resolution=how, inferred=(how == "root_fallback"))
            if isinstance(fm.get("computation"), str) and "://" not in fm["computation"]:
                target, how = self.resolve(fm["computation"], cdir)
                if target and how != "escape":
                    add_edge(c, artifact(target), "REFERENCES", "frontmatter.computation", resolution=how)
            # body links + footnotes per section
            seen: set[tuple] = set()
            for s in pr["sections"]:
                sec = nodes[s]
                clean = strip_fences(sec.text or "")
                for ordinal, m in enumerate(MD_LINK_RE.finditer(clean)):
                    ltext, raw = m.group(1), m.group(2)
                    target, how = self.resolve(raw, cdir)
                    if how == "escape":
                        self.rejections.append({"path": rel, "section": sec.heading, "raw": raw, "reason": "escapes bundle"})
                        continue
                    if how == "url" or target is None or not target.endswith(".md") or posixpath.basename(target) in RESERVED:
                        continue
                    dst = concept_by_path.get(target) or stub_concept(target)
                    key = (c, dst, sec.heading, raw)
                    if key not in seen:
                        seen.add(key)
                        add_edge(c, dst, "LINKS_TO", "body_link", len(seen), section_id=s, resolution=how,
                                 inferred=(how == "root_fallback"),
                                 attrs=stable_json({"text": ltext, "raw": raw, "section": sec.heading,
                                                    "resolved": target in concept_by_path}))
                    mk = (s, dst)
                    if mk not in seen:
                        seen.add(mk)
                        add_edge(s, dst, "MENTIONS", "body_link", 0, resolution=how)
                non_def = "\n".join(l for l in clean.splitlines() if not FOOTNOTE_DEF_RE.match(l))
                for ref in sorted(set(FOOTNOTE_REF_RE.findall(non_def))):
                    if ref in sid_to_source:
                        add_edge(s, sid_to_source[ref], "CITES", f"footnote[^{ref}]")
                    else:
                        self.warnings.append({"path": rel, "section": sec.heading, "warning": f"footnote [^{ref}] has no sources[].id"})
        # pass 3: logs
        order = 0
        for m in manifest:
            if posixpath.basename(m["path"]) != "log.md":
                continue
            rel_dir = posixpath.dirname(m["path"])
            fm, body, _ = split_frontmatter((self.root / m["path"]).read_text(encoding="utf-8-sig"))
            date = None
            for _, line, in_fence in iter_lines(body):
                if in_fence:
                    continue
                dm = LOG_DATE_RE.match(line.strip())
                if dm:
                    date = dm.group(1); continue
                st = line.strip()
                if date and st.startswith(("- ", "* ")):
                    text = st[2:].strip()
                    km = LOG_KIND_RE.match(text)
                    lid = f"log:{rel_dir or '.'}:{order}"
                    ln = nid("LogEntry", lid)
                    nodes[ln] = Node(node_id=ln, bundle_id=B, publication_id=P, kind="LogEntry", local_id=lid,
                                     path=m["path"], entry_date=date, title=km.group(1).strip() if km else None,
                                     text=re.sub(r"\s+", " ", text), text_sha256=sha256_text(text),
                                     extra_frontmatter=stable_json(fm) if fm else None)
                    targets = [x.group(2) for x in MD_LINK_RE.finditer(text)] + re.findall(r"`([^`\s]+\.md)`", text)
                    seen_t: set[str] = set()
                    for raw in targets:
                        target, how = self.resolve(raw, rel_dir)
                        if target and target.endswith(".md") and target in concept_by_path and target not in seen_t:
                            seen_t.add(target)
                            add_edge(ln, concept_by_path[target], "REFERENCES", "log_entry", len(seen_t), resolution=how)
                    order += 1
        # pass 4: unreferenced non-md files stay in the manifest as artifacts
        for m in manifest:
            if not m["path"].endswith(".md"):
                artifact(m["path"])

        node_rows = sorted(to_rows(list(nodes.values())), key=lambda r: r["node_id"])
        edge_rows = sorted(to_rows(edges), key=lambda r: r["edge_id"])
        sections = [r for r in node_rows if r["kind"] == "Section"]
        output_manifest = {"nodes": len(node_rows), "edges": len(edge_rows),
                           "nodes_sha256": sha256_text(stable_json(node_rows)),
                           "edges_sha256": sha256_text(stable_json(edge_rows))}
        return {
            "bundle_id": B, "publication_id": P, "source_pin": self.source_pin,
            "compiler_version": COMPILER_VERSION, "source_manifest": manifest,
            "source_manifest_sha256": manifest_digest, "output_manifest": output_manifest,
            "nodes": node_rows, "edges": edge_rows,
            "section_texts": [{"node_id": s["node_id"], "text": s["text"], "text_sha256": s["text_sha256"]} for s in sections],
            "warnings": sorted(self.warnings, key=stable_json),
            "rejections": sorted(self.rejections, key=stable_json),
            "counts": _counts(node_rows, edge_rows),
        }


def _counts(nodes: list[dict], edges: list[dict]) -> dict:
    out: dict[str, Any] = {"nodes_by_kind": {}, "edges_by_relation": {}, "stubs": 0}
    for n in nodes:
        out["nodes_by_kind"][n["kind"]] = out["nodes_by_kind"].get(n["kind"], 0) + 1
        if n["stub"] and n["kind"] == "Concept":
            out["stubs"] += 1
    for e in edges:
        out["edges_by_relation"][e["relation"]] = out["edges_by_relation"].get(e["relation"], 0) + 1
    return out


def compile_bundle(root: str, bundle_id: str, source_pin: str) -> dict:
    return Compiler(root, bundle_id, source_pin).compile()


def validate_projection(projection: dict) -> dict:
    """Referential integrity, key uniqueness, scope, and count checks."""
    reasons: list[str] = []
    nodes, edges = projection["nodes"], projection["edges"]
    B, P = projection["bundle_id"], projection["publication_id"]
    ids = [n["node_id"] for n in nodes]
    idset = set(ids)
    if len(ids) != len(idset):
        reasons.append("DUPLICATE_NODE_ID")
    eids = [e["edge_id"] for e in edges]
    if len(eids) != len(set(eids)):
        reasons.append("DUPLICATE_EDGE_ID")
    for n in nodes:
        if n["bundle_id"] != B or n["publication_id"] != P or not n["node_id"].startswith(f"{B}|{P}|"):
            reasons.append("NODE_SCOPE_MISMATCH"); break
    for e in edges:
        if e["src_id"] not in idset or e["dst_id"] not in idset:
            reasons.append("DANGLING_EDGE"); break
        if e["bundle_id"] != B or e["publication_id"] != P:
            reasons.append("EDGE_SCOPE_MISMATCH"); break
    for s in projection.get("section_texts", []):
        if sha256_text(s["text"]) != s["text_sha256"]:
            reasons.append("SECTION_DIGEST_MISMATCH"); break
    om = projection["output_manifest"]
    if om["nodes"] != len(nodes) or om["edges"] != len(edges):
        reasons.append("MANIFEST_COUNT_MISMATCH")
    return {"valid": not reasons, "reasons": sorted(set(reasons)), "counts": projection["counts"],
            "nodes": len(nodes), "edges": len(edges), "sections": len(projection.get("section_texts", []))}


if __name__ == "__main__":
    import sys
    from . import BUNDLE_ID, SOURCE_PIN
    root = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    proj = compile_bundle(root, BUNDLE_ID, SOURCE_PIN)
    v = validate_projection(proj)
    print(json.dumps({"publication_id": proj["publication_id"], "validation": v,
                      "warnings": proj["warnings"], "rejections": proj["rejections"]}, indent=2))
    if out:
        with open(out, "w") as fh:
            json.dump(proj, fh, indent=1, sort_keys=True)
