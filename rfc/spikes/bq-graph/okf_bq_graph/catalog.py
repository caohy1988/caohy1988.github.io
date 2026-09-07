"""Catalog seed provider (2026-09-06 Catalog-seeded chain, plan U1 / KTD1-KTD2).

Fresh Dataplex Catalog discovery: paginated `entries.list` on the configured entry group selects the configured entry
uniquely by name (bodies of unrelated entries are never fetched), then `entries.get(view=ALL)` returns the runtime
aspect with its values (the default FULL view can expose keys only for optional aspects). The parser validates the
`okf-context-runtime` aspect against trusted configuration and freezes the returned pin. HTTP and mock readers share
the same parser; only the real HTTP reader may label a seed `catalog`, every other reader is `catalog-mock`.

Refusals are typed and never fall back to a fixture, the active head, vector search or a saved response:
  CATALOG_ERROR          transport / HTTP / non-JSON failure (identifiable, blocked, not a security result)
  PAGE_CAP               discovery exhausted the page cap without finishing the list
  ENTRY_NOT_FOUND        the configured entry was not listed
  ENTRY_AMBIGUOUS        the configured entry was listed more than once
  ENTRY_MISMATCH         the GET returned a different entry name or entry type
  ASPECT_MISSING         no runtime aspect under the configured key
  ASPECT_KEYS_ONLY       the aspect is present without `data` (a non-ALL / keys-only read)
  INVALID_PIN            malformed / missing / wrong-typed pin fields, unsafe path, inconsistent concept id
  UNSUPPORTED_CONTRACT   runtime contract not in the supported set
  SCOPE_REFUSED          ownership / destination / source binding differs from trusted configuration
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Protocol

from . import BUNDLE_ID, DATASET, LOCATION, PROJECT
from .seed import ConceptSeed

CATALOG_API = "https://dataplex.googleapis.com/v1/"
SUPPORTED_CONTRACTS = ("graph-spike-v1",)
PROJECT_NUMBER = "201486563047"
DEFAULT_GROUP = f"projects/{PROJECT}/locations/us-central1/entryGroups/okf-rfc-demo"
DEFAULT_ENTRY = f"{DEFAULT_GROUP}/entries/acme-retail-kc-unblock/metrics/gross-margin"
DEFAULT_ASPECT_KEY = f"{PROJECT_NUMBER}.us-central1.okf-context-runtime"
DEFAULT_ENTRY_TYPE = f"projects/{PROJECT_NUMBER}/locations/us-central1/entryTypes/okf-bundle"
AUTHORED_ASPECT_SUFFIXES = (".okf", ".overview")   # preserved, never runtime input

PUB_RE = re.compile(r"pub_[0-9a-f]{16}")
HEX40_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
LOCAL_DERIVED_RE = re.compile(r"[0-9a-f]{40}\+local\.[0-9a-f]{16}")   # B2 owned P2 only; never a clean-source label
REQUIRED_FIELDS = ("runtime_contract", "runtime_project", "runtime_dataset", "runtime_location", "bundle_id",
                   "publication_id", "concept_id", "concept_path", "concept_file_sha256", "source_pin",
                   "source_manifest_sha256", "source_repository", "source_root", "managed_by_profile",
                   "managed_by_deployment", "compiler_version")
OPTIONAL_FIELDS = ("managed_by_principal", "binding_verified_at", "published_snapshot_id")


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


# ----------------------------------------------------------------------------- trusted configuration
@dataclass(frozen=True)
class CatalogConfig:
    """The allowlist the returned pin is checked against. Catalog values never widen it."""
    group: str = DEFAULT_GROUP
    entry: str = DEFAULT_ENTRY
    aspect_key: str = DEFAULT_ASPECT_KEY
    entry_type: str = DEFAULT_ENTRY_TYPE
    runtime_project: str = PROJECT
    runtime_dataset: str = DATASET
    runtime_location: str = LOCATION
    bundle_id: str = BUNDLE_ID
    source_repository: str = "https://github.com/GoogleCloudPlatform/knowledge-catalog"
    source_root: str = "okf/bundles/acme_retail"
    managed_by_profile: str = "okf-kc-self-unblock/1"
    managed_by_deployment: str = "acme-retail-kc-unblock-20260906"
    compiler_version: str = "okf_bq_graph.compile/0.1.0"
    page_size: int = 100
    max_pages: int = 5
    allow_local_derived_source: bool = False   # B2 owned lifecycle pins only

    def __post_init__(self) -> None:
        if not self.entry.startswith(self.group + "/entries/"):
            raise ValueError("configured entry must belong to the configured entry group")
        if self.page_size < 1 or self.max_pages < 1:
            raise ValueError("page_size and max_pages must be positive")


# ----------------------------------------------------------------------------- readers
class Response:
    """Transport-neutral result of one Catalog call: HTTP status, parsed JSON (or None) and the raw bytes."""
    __slots__ = ("status", "json", "raw", "error")

    def __init__(self, status: Optional[int], raw: bytes = b"", error: Optional[str] = None):
        self.status, self.raw, self.error = status, raw, error
        self.json: Optional[Any] = None
        if raw:
            try:
                self.json = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self.json = None

    @property
    def ok(self) -> bool:
        return self.status == 200 and isinstance(self.json, dict)


class Reader(Protocol):
    mode: str

    def list_entries(self, group: str, page_size: int, page_token: Optional[str]) -> Response: ...
    def get_entry(self, name: str, view: str) -> Response: ...


class HttpReader:
    """The only reader whose seeds may be labelled `catalog`. google-auth AuthorizedSession, bounded connect/read
    timeouts on every send, no refresh retries beyond one bounded attempt, no redirects."""
    mode = "catalog"

    def __init__(self, session: Any = None, timeout: tuple = (10, 20), api: str = CATALOG_API):
        self._session, self.timeout, self.api = session, timeout, api

    def _sess(self) -> Any:
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession, Request
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            req = Request()

            def bounded(*a: Any, **kw: Any) -> Any:
                kw["timeout"] = self.timeout[1]
                return req(*a, **kw)
            self._session = AuthorizedSession(creds, auth_request=bounded, max_refresh_attempts=1)
        return self._session

    def _call(self, url: str, params: dict) -> Response:
        try:
            r = self._sess().request("GET", url, params=params, timeout=self.timeout, allow_redirects=False)
        except Exception as e:  # noqa: BLE001 - transport failure is an identifiable blocked state, never a pass
            return Response(None, b"", f"{type(e).__name__}: {str(e)[:300]}")
        return Response(r.status_code, r.content or b"")

    def list_entries(self, group: str, page_size: int, page_token: Optional[str]) -> Response:
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._call(f"{self.api}{group}/entries", params)

    def get_entry(self, name: str, view: str) -> Response:
        return self._call(f"{self.api}{name}", {"view": view})


class MockReader:
    """Injected responses for the hermetic suite. `pages` is the ordered list of list-response bodies (dicts or raw
    bytes / (status, bytes) tuples); `entries` maps entry name -> GET body. Seeds read through it are `catalog-mock`."""
    mode = "catalog-mock"

    def __init__(self, pages: list, entries: dict, get_status: int = 200):
        self.pages, self.entries, self.get_status = pages, entries, get_status
        self.calls: list[tuple] = []

    @staticmethod
    def _resp(body: Any, status: int = 200) -> Response:
        if isinstance(body, tuple):
            status, body = body
        if isinstance(body, bytes):
            return Response(status, body)
        if body is None:
            return Response(status, b"")
        return Response(status, _canon(body))

    def list_entries(self, group: str, page_size: int, page_token: Optional[str]) -> Response:
        self.calls.append(("list", group, page_size, page_token))
        idx = int(page_token[1:]) if page_token else 0
        if idx >= len(self.pages):
            return Response(404, b'{"error":{"code":404,"message":"no such page"}}')
        return self._resp(self.pages[idx])

    def get_entry(self, name: str, view: str) -> Response:
        self.calls.append(("get", name, view))
        if name not in self.entries:
            return Response(404, b'{"error":{"code":404,"message":"entry not found"}}')
        return self._resp(self.entries[name], self.get_status)


def mock_pages(names: list[str], per_page: int) -> list[dict]:
    """List-response pages carrying only entry names (what discovery consumes), with continuation tokens."""
    pages = []
    for i in range(0, max(len(names), 1), per_page):
        chunk = names[i:i + per_page]
        page = {"entries": [{"name": n} for n in chunk]}
        if i + per_page < len(names):
            page["nextPageToken"] = f"p{i // per_page + 1}"
        pages.append(page)
    return pages


# ----------------------------------------------------------------------------- results
@dataclass
class CatalogRefusal:
    status: str
    reason: str
    stage: str                       # "list" | "get" | "parse"
    http_status: Optional[int] = None
    details: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return False

    def record(self) -> dict:
        return {"status": self.status, "reason": self.reason, "stage": self.stage, "http_status": self.http_status,
                "details": self.details}


@dataclass(frozen=True)
class CatalogPin:
    """The frozen, validated runtime pin. Every field passed the trusted-configuration checks."""
    runtime_contract: str
    runtime_project: str
    runtime_dataset: str
    runtime_location: str
    bundle_id: str
    publication_id: str
    concept_id: str
    concept_path: str
    concept_file_sha256: str
    source_pin: str
    source_manifest_sha256: str
    source_repository: str
    source_root: str
    managed_by_profile: str
    managed_by_deployment: str
    compiler_version: str
    managed_by_principal: Optional[str] = None
    binding_verified_at: Optional[str] = None
    published_snapshot_id: Optional[str] = None

    def seed(self, origin: str) -> ConceptSeed:
        return ConceptSeed(self.concept_id, origin=origin)

    def record(self) -> dict:
        return asdict(self)


@dataclass
class CatalogSeed:
    mode: str                        # "catalog" (HttpReader only) | "catalog-mock"
    pin: CatalogPin
    entry: str
    aspect_key: str
    discovery: dict                  # pages, entries listed, match count, raw hashes
    authored_aspects: list[str]      # keys preserved as-is; never runtime input
    raw_entry_sha256: str

    @property
    def ok(self) -> bool:
        return True

    def record(self) -> dict:
        return {"status": "OK", "mode": self.mode, "entry": self.entry, "aspect_key": self.aspect_key,
                "discovery": self.discovery, "authored_aspects": self.authored_aspects,
                "raw_entry_sha256": self.raw_entry_sha256, "pin": self.pin.record(),
                "note": ("fresh Dataplex list + get(view=ALL) under the operator's ADC credential; Catalog attests no principal"
                         if self.mode == "catalog" else "injected mock responses through the real parser: not a live Catalog read")}


# ----------------------------------------------------------------------------- discovery
def _http_refusal(stage: str, r: Response, what: str) -> CatalogRefusal:
    if r.status is None:
        return CatalogRefusal("CATALOG_ERROR", f"{what}: transport failure {r.error}", stage, None)
    if r.status != 200:
        msg = ""
        if isinstance(r.json, dict):
            msg = str((r.json.get("error") or {}).get("message") or "")[:200]
        return CatalogRefusal("CATALOG_ERROR", f"{what}: HTTP {r.status} {msg}".rstrip(), stage, r.status)
    return CatalogRefusal("CATALOG_ERROR", f"{what}: non-JSON or non-object body ({len(r.raw)} bytes)", stage, r.status)


def discover(reader: Reader, cfg: CatalogConfig, retain: Optional[Any] = None) -> dict:
    """Paginate the group's entries and select the configured entry by exact name; then GET it with view=ALL.
    Returns {"status": "OK", "entry": <json>, "discovery": {...}} or {"status": <refusal>, "refusal": CatalogRefusal}.
    `retain(name, raw_bytes)` (optional) receives every raw response for run-owned retention before parsing."""
    listed: list[str] = []
    pages = 0
    token: Optional[str] = None
    hashes: list[str] = []
    while True:
        if pages >= cfg.max_pages:
            return {"status": "PAGE_CAP", "refusal": CatalogRefusal("PAGE_CAP", f"page cap {cfg.max_pages} reached with a continuation token pending",
                                                                    "list", details={"pages": pages, "listed": len(listed)})}
        r = reader.list_entries(cfg.group, cfg.page_size, token)
        pages += 1
        if retain is not None:
            retain(f"catalog_list_{pages - 1}", r.raw)
        hashes.append(sha256_hex(r.raw))
        if not r.ok:
            return {"status": "CATALOG_ERROR", "refusal": _http_refusal("list", r, f"entries.list page {pages - 1}")}
        entries = r.json.get("entries", [])
        if not isinstance(entries, list):
            return {"status": "CATALOG_ERROR", "refusal": CatalogRefusal("CATALOG_ERROR", "entries is not a list", "list", r.status)}
        for e in entries:
            name = e.get("name") if isinstance(e, dict) else None
            if isinstance(name, str):
                listed.append(name)
        token = r.json.get("nextPageToken") or None
        if not token:
            break
    matches = [n for n in listed if n == cfg.entry]
    disc = {"pages": pages, "entries_listed": len(listed), "matches": len(matches), "list_sha256": hashes, "page_size": cfg.page_size}
    if not matches:
        return {"status": "ENTRY_NOT_FOUND", "refusal": CatalogRefusal("ENTRY_NOT_FOUND", "configured entry not listed in the group", "list", details=disc)}
    if len(matches) > 1:
        return {"status": "ENTRY_AMBIGUOUS", "refusal": CatalogRefusal("ENTRY_AMBIGUOUS", f"configured entry listed {len(matches)} times", "list", details=disc)}
    g = reader.get_entry(cfg.entry, "ALL")
    if retain is not None:
        retain("catalog_entry", g.raw)
    disc["entry_sha256"] = sha256_hex(g.raw)
    if not g.ok:
        return {"status": "CATALOG_ERROR", "refusal": _http_refusal("get", g, "entries.get(view=ALL)"), "discovery": disc}
    return {"status": "OK", "entry": g.json, "discovery": disc, "raw_entry_sha256": disc["entry_sha256"]}


# ----------------------------------------------------------------------------- parsing / validation
def _safe_concept_path(p: str) -> bool:
    if not p.endswith(".md") or p.startswith("/") or "\\" in p or "\x00" in p:
        return False
    norm = posixpath.normpath(p)
    return norm == p and not any(part in ("", ".", "..") for part in p.split("/"))


def parse_pin(entry: Any, cfg: CatalogConfig) -> CatalogPin | CatalogRefusal:
    """Validate one entries.get(view=ALL) body against `cfg` and freeze the pin. Rejects before any content read."""
    if not isinstance(entry, dict):
        return CatalogRefusal("INVALID_PIN", "entry body is not an object", "parse")
    if entry.get("name") != cfg.entry:
        return CatalogRefusal("ENTRY_MISMATCH", "returned entry name differs from the configured entry", "parse",
                              details={"returned": entry.get("name")})
    if entry.get("entryType") != cfg.entry_type:
        return CatalogRefusal("ENTRY_MISMATCH", "returned entryType is not the shipped okf-bundle type", "parse",
                              details={"returned": entry.get("entryType")})
    aspects = entry.get("aspects")
    if not isinstance(aspects, dict) or cfg.aspect_key not in aspects:
        return CatalogRefusal("ASPECT_MISSING", f"no runtime aspect under {cfg.aspect_key}", "parse")
    asp = aspects[cfg.aspect_key]
    if not isinstance(asp, dict) or "data" not in asp:
        return CatalogRefusal("ASPECT_KEYS_ONLY", "runtime aspect present without data (keys-only / non-ALL view)", "parse")
    data = asp["data"]
    if not isinstance(data, dict) or not data:
        return CatalogRefusal("INVALID_PIN", "runtime aspect data is empty or not an object", "parse")
    missing = [k for k in REQUIRED_FIELDS if not isinstance(data.get(k), str) or not data.get(k).strip()]
    if missing:
        return CatalogRefusal("INVALID_PIN", f"missing/empty/non-string fields: {', '.join(missing)}", "parse", details={"missing": missing})
    for k in OPTIONAL_FIELDS:
        if k in data and data[k] is not None and not isinstance(data[k], str):
            return CatalogRefusal("INVALID_PIN", f"optional field {k} is not a string", "parse")
    if data["runtime_contract"] not in SUPPORTED_CONTRACTS:
        return CatalogRefusal("UNSUPPORTED_CONTRACT", f"runtime_contract {data['runtime_contract']!r} not in {SUPPORTED_CONTRACTS}", "parse")
    scope = {"runtime_project": cfg.runtime_project, "runtime_dataset": cfg.runtime_dataset, "runtime_location": cfg.runtime_location,
             "bundle_id": cfg.bundle_id, "source_repository": cfg.source_repository, "source_root": cfg.source_root,
             "managed_by_profile": cfg.managed_by_profile, "managed_by_deployment": cfg.managed_by_deployment,
             "compiler_version": cfg.compiler_version}
    wrong = {k: data[k] for k, v in scope.items() if data[k] != v}
    if wrong:
        return CatalogRefusal("SCOPE_REFUSED", "ownership/destination/source scope differs from trusted configuration: " + ", ".join(sorted(wrong)),
                              "parse", details={"returned": wrong, "expected": {k: scope[k] for k in wrong}})
    if not PUB_RE.fullmatch(data["publication_id"]):
        return CatalogRefusal("INVALID_PIN", "publication_id is not pub_<16 hex>", "parse")
    pin_ok = HEX40_RE.fullmatch(data["source_pin"]) or (cfg.allow_local_derived_source and LOCAL_DERIVED_RE.fullmatch(data["source_pin"]))
    if not pin_ok:
        return CatalogRefusal("INVALID_PIN", "source_pin is not a 40-hex revision" + (" or an allowed local derivation" if cfg.allow_local_derived_source else ""), "parse")
    for k in ("source_manifest_sha256", "concept_file_sha256"):
        if not HEX64_RE.fullmatch(data[k]):
            return CatalogRefusal("INVALID_PIN", f"{k} is not 64 hex", "parse")
    if not _safe_concept_path(data["concept_path"]):
        return CatalogRefusal("INVALID_PIN", "concept_path is not a safe bundle-relative .md path", "parse", details={"concept_path": data["concept_path"]})
    expected_id = f"{data['bundle_id']}|{data['publication_id']}|Concept|{data['concept_path'][:-3]}"
    if data["concept_id"] != expected_id:      # exact, case-sensitive, capitalised `Concept`
        return CatalogRefusal("INVALID_PIN", "concept_id is not the exact scoped Concept id of concept_path under publication_id", "parse",
                              details={"returned": data["concept_id"], "expected": expected_id})
    fields = {k: data[k] for k in REQUIRED_FIELDS}
    fields.update({k: data.get(k) for k in OPTIONAL_FIELDS})
    return CatalogPin(**fields)


def read_seed(reader: Reader, cfg: CatalogConfig, retain: Optional[Any] = None) -> CatalogSeed | CatalogRefusal:
    """discover + parse. The seed's mode is the reader's mode: only HttpReader yields `catalog`."""
    d = discover(reader, cfg, retain)
    if d["status"] != "OK":
        ref: CatalogRefusal = d["refusal"]
        ref.details = dict(ref.details, **({"discovery": d["discovery"]} if "discovery" in d else {}))
        return ref
    pin = parse_pin(d["entry"], cfg)
    if isinstance(pin, CatalogRefusal):
        pin.details = dict(pin.details, discovery=d["discovery"])
        return pin
    aspects = d["entry"].get("aspects") or {}
    authored = sorted(k for k in aspects if k != cfg.aspect_key)
    mode = "catalog" if isinstance(reader, HttpReader) else "catalog-mock"
    return CatalogSeed(mode=mode, pin=pin, entry=cfg.entry, aspect_key=cfg.aspect_key, discovery=d["discovery"],
                       authored_aspects=authored, raw_entry_sha256=d["raw_entry_sha256"])


def is_live_reader(reader: Any) -> bool:
    return isinstance(reader, HttpReader)


def sample_entry(cfg: CatalogConfig = CatalogConfig(), **overrides: Any) -> dict:
    """The recorded 2026-09-07 KC-unblock entry shape (values from the probe evidence) for hermetic tests; `overrides`
    patch the runtime aspect's data."""
    data = {"binding_verified_at": "2026-09-07T05:14:10.847600+00:00", "bundle_id": cfg.bundle_id,
            "compiler_version": cfg.compiler_version,
            "concept_file_sha256": "912be604fe7f681322b2ba6414b5791e9eb91b73aad1cae7afa666cedfe7d3c9",
            "concept_id": f"{cfg.bundle_id}|pub_190192147fd7fd78|Concept|metrics/gross-margin",
            "concept_path": "metrics/gross-margin.md", "managed_by_deployment": cfg.managed_by_deployment,
            "managed_by_principal": "writer@example.test", "managed_by_profile": cfg.managed_by_profile,
            "publication_id": "pub_190192147fd7fd78", "runtime_contract": "graph-spike-v1",
            "runtime_dataset": cfg.runtime_dataset, "runtime_location": cfg.runtime_location, "runtime_project": cfg.runtime_project,
            "source_manifest_sha256": "190192147fd7fd780b0da94c596045e363b29b4c23963959503cc677f1a3b5d5",
            "source_pin": "31da799a9aef176df12e91abbd119ea9385b75ec", "source_repository": cfg.source_repository,
            "source_root": cfg.source_root}
    data.update(overrides)
    return {"name": cfg.entry, "entryType": cfg.entry_type,
            "entrySource": {"system": "okf-kc-self-unblock", "labels": {"bundle": cfg.bundle_id}},
            "aspects": {f"{PROJECT_NUMBER}.us-central1.okf": {"data": {"okf_type": "Metric", "status": "stable"}},
                        cfg.aspect_key: {"aspectType": f"projects/{PROJECT_NUMBER}/locations/us-central1/aspectTypes/okf-context-runtime", "data": data},
                        "655216118709.global.overview": {"data": {"content": "# Definition\n..."}}}}
