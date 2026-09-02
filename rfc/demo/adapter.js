/* BQAA → derived OKF adapter (one-way, observer-only).
   Input: a BQAA `agent_events` trace (fixture JSON). Output: a derived OKF
   v0.2 bundle (path → text) plus the identity chain for that bundle,
   computed with the same PROFILE.md rules as the authored fixture.
   The authored bundle is never read or written by this adapter.
   Loads as a browser global (OkfBqaaAdapter) or CommonJS (tools/). */
(function (root, factory) {
  var api = factory(root.OkfHash || (typeof require === "function" ? require("./hash.js") : null));
  if (typeof module === "object" && module.exports) module.exports = api;
  root.OkfBqaaAdapter = api;
})(typeof self !== "undefined" ? self : globalThis, function (H) {
  "use strict";

  var ADAPTER_VERSION = "okf-bqaa-adapter:v0";
  var NEVER_EMIT = ["concept_version_id", "bundle_path", "source_path", "principal", "user_id",
                    "query_text", "sql", "parameter_values", "destination_table"];

  var TYPE_DIRS = {
    "Metric": "metrics",
    "Attested Computation": "computations",
    "Business Concept": "concepts",
    "Policy": "policies",
    "BigQuery Table": "tables"
  };

  function slug(title) {
    return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }
  function pathFor(item) {
    var dir = TYPE_DIRS[item.type] || "concepts";
    return dir + "/" + slug(item.title) + ".md";
  }
  function relLink(fromPath, toPath) {
    var fromDir = fromPath.split("/").slice(0, -1).join("/");
    var toDir = toPath.split("/").slice(0, -1).join("/");
    if (fromDir === toDir) return toPath.split("/").pop();
    return "../" + toPath;
  }
  function find(events, pred) {
    for (var i = 0; i < events.length; i++) if (pred(events[i])) return events[i];
    return null;
  }
  function findAll(events, pred) { return events.filter(pred); }

  // ---- observe: pull only what an observer is allowed to see -------------
  function observe(trace) {
    var ev = trace.events;
    var ask = find(ev, function (e) { return e.event_type === "LLM_REQUEST" && e.content && e.content.role === "user"; });
    var retrieve = find(ev, function (e) {
      return e.event_type === "TOOL_COMPLETED" && e.attributes && e.attributes.tool && e.attributes.tool.kind === "okf-context:retrieve" && e.status === "OK";
    });
    var receipts = findAll(ev, function (e) {
      return e.event_type === "TOOL_COMPLETED" && e.attributes && e.attributes.tool && e.attributes.tool.kind === "okf-context:attested-computation" && e.status === "OK";
    });
    var errors = findAll(ev, function (e) { return e.status === "ERROR"; });
    var receipt = receipts.length ? receipts[receipts.length - 1] : null;
    var okf = retrieve ? retrieve.attributes.okf : { items: [], excluded: [], links: [] };
    var span = { first: ev[0].timestamp, last: ev[ev.length - 1].timestamp };
    return {
      table: trace.table,
      writer: trace.writer,
      agent: trace.agent,
      session_id: ev[0].session_id,
      trace_id: ev[0].trace_id,
      invocation_id: ev[0].invocation_id,
      event_count: ev.length,
      span: span,
      question: ask && ask.content ? ask.content.text : null,
      context_ref: retrieve ? retrieve.attributes.context_ref : null,
      observed_publication_id: okf.publication_id || null,
      mode: okf.mode || null,
      items: okf.items || [],
      excluded: okf.excluded || [],
      links: okf.links || [],
      receipt: receipt ? receipt.attributes.okf : null,
      receipt_context_ref: receipt ? receipt.attributes.context_ref : null,
      error_codes: errors.map(function (e) { return (e.attributes.okf && e.attributes.okf.error_code) || e.error_message; })
    };
  }

  // ---- adapt: derived bundle text ----------------------------------------
  function yamlStr(s) { return JSON.stringify(String(s)); }

  function stubDoc(obs, item, all, bundleKey) {
    var path = pathFor(item);
    var isExcluded = !!item.excluded;
    var status = isExcluded ? "deprecated" : "draft";
    var fm = [];
    fm.push("type: " + item.type);
    fm.push("title: " + item.title);
    fm.push("description: Derived from BQAA observation, not authored. " +
      (isExcluded
        ? "Observed as excluded from current-mode retrieval (" + item.reason + ")."
        : "Observed at rank " + item.rank + " of " + obs.items.length + " in retrieval envelope " + obs.context_ref + "."));
    fm.push("status: " + status);
    fm.push("tags: [bqaa-derived, observer-only, " + slug(item.type) + "]");

    // supersedes: inferred from the excluded list (superseded reason)
    if (!isExcluded && item.type === "Metric") {
      var superseded = all.filter(function (o) { return o.excluded && o.type === "Metric" && /superseded/.test(o.reason || ""); });
      if (superseded.length) {
        fm.push("supersedes:");
        superseded.forEach(function (o) { fm.push("  - " + pathFor(o)); });
      }
    }
    // links: observed edges (from retrieve attributes)
    var links = obs.links.filter(function (l) { return l.from === item.title; });
    if (links.length) {
      fm.push("links:");
      links.forEach(function (l) {
        var target = all.filter(function (o) { return o.title === l.to; })[0];
        if (!target) return;
        fm.push("  - target: " + pathFor(target));
        fm.push("    rel: " + l.rel);
        fm.push("    confidence: inferred");
      });
    }
    // §10.2 keys observed on the receipt for the computation stub
    if (item.type === "Attested Computation" && obs.receipt) {
      fm.push("runtime: " + obs.receipt.runtime);
      fm.push("parameters:");
      obs.receipt.parameter_schema.forEach(function (p) {
        fm.push("  - { name: " + p.name + ", type: " + p.type + ", required: " + (p.required ? "true" : "false") + " }");
      });
      if (obs.receipt.receipt_fields) {
        fm.push("executor:");
        fm.push("  receipt:");
        obs.receipt.receipt_fields.forEach(function (f) { fm.push("    - " + f); });
      }
    }
    fm.push("sources:");
    fm.push("  - resource: bqaa://" + obs.table + "?session_id=" + obs.session_id);
    fm.push("    title: BQAA observer trace " + obs.trace_id + " (" + obs.writer.label + ")");
    if (item.type === "Attested Computation" && obs.receipt) {
      fm.push("  - resource: okf:computation-version:" + obs.receipt.computation_version_id);
      fm.push("    title: Sanctioned artifact in authored publication " + obs.receipt.publication_id.slice(0, 23) + "… (observed via receipt " + obs.receipt.receipt_id + ")");
    }

    var body = [];
    body.push("# " + item.title);
    body.push("");
    body.push("**Derived from BQAA observation, not authored.** This stub was emitted by");
    body.push("`" + ADAPTER_VERSION + "` from `" + obs.event_count + "` observer events in");
    body.push("`" + obs.table + "` (session `" + obs.session_id + "`). The observer");
    body.push("sees titles, types, ranks, edges and receipts — never authored text,");
    body.push("bundle paths, `concept_version_id`, SQL, parameter values or the principal.");
    body.push("");
    if (isExcluded) {
      body.push("## Observed exclusion");
      body.push("");
      body.push("Excluded from `" + obs.mode + "`-mode retrieval: " + item.reason + ".");
      body.push("The current definition is [" + all[0].title + "](" + relLink(path, pathFor(all[0])) + ").");
    } else {
      body.push("## Observed retrieval");
      body.push("");
      body.push("- context_ref `" + obs.context_ref + "`, rank " + item.rank + " of " + obs.items.length + ", mode `" + obs.mode + "`.");
      body.push("- Observed type `" + item.type + "`; authored body not observed.");
      if (links.length) {
        links.forEach(function (l) {
          var target = all.filter(function (o) { return o.title === l.to; })[0];
          if (target) body.push("- Edge `" + l.rel + "` → [" + l.to + "](" + relLink(path, pathFor(target)) + ") (inferred from envelope attributes).");
        });
      }
    }
    if (item.type === "Attested Computation" && obs.receipt) {
      body.push("");
      body.push("## Observed execution contract");
      body.push("");
      body.push("- Runtime `" + obs.receipt.runtime + "`; " + obs.receipt.parameter_schema.length + " declared parameters (names and types only; values are never observed).");
      body.push("- No `computation:` artifact is declared here: the observer never sees SQL. The sanctioned artifact lives in the authored publication and is referenced by its `computation_version_id` under `sources`.");
      body.push("- Last observed verdict `" + obs.receipt.verdict + "` (`" + obs.receipt.verdict_reason + "`), receipt `" + obs.receipt.receipt_id + "`.");
      if (obs.error_codes.length) body.push("- Observed fail-closed errors before success: " + obs.error_codes.map(function (c) { return "`" + c + "`"; }).join(", ") + ".");
    }
    body.push("");
    body.push("Authored counterpart: `" + obs.observed_publication_id.slice(0, 23) + "…` (publication_id observed on the tool span). This derived bundle (`" + bundleKey + "`) never writes back to it.");
    return { path: path, text: "---\n" + fm.join("\n") + "\n---\n" + body.join("\n") + "\n" };
  }

  function logDoc(obs, docs, bundleKey) {
    var day = obs.span.last.slice(0, 10);
    var lines = [];
    lines.push("# Log");
    lines.push("");
    lines.push("## " + day);
    lines.push("");
    lines.push("- Derived from BQAA observation, not authored. `" + ADAPTER_VERSION + "` read " + obs.event_count +
      " observer events (session `" + obs.session_id + "`, trace `" + obs.trace_id + "`) from `" + obs.table +
      "` and emitted " + docs.length + " stubs into `" + bundleKey + "`. The authored bundle was not read and was not modified.");
    lines.push("- Observed: [" + obs.items[0].title + "](" + pathFor(obs.items[0]) + ") retrieved at rank 1 for context_ref `" + obs.context_ref + "` (" + obs.mode + " mode).");
    obs.excluded.forEach(function (x) {
      lines.push("- Observed (not affirmed here): [" + x.title + "](" + pathFor(x) + ") excluded from retrieval — " + x.reason + ".");
    });
    if (obs.receipt) {
      lines.push("- Observed receipt `" + obs.receipt.receipt_id + "` on `" + obs.receipt_context_ref + "`: verdict `" + obs.receipt.verdict + "` (`" + obs.receipt.verdict_reason + "`). Nothing was executed or attested.");
    }
    return { path: "log.md", text: lines.join("\n") + "\n" };
  }

  function adapt(trace) {
    var obs = observe(trace);
    var bundleKey = "bqaa-derived-cymbal-demo";
    var all = obs.items.slice();
    obs.excluded.forEach(function (x) { all.push({ type: x.type, title: x.title, reason: x.reason, excluded: true }); });
    var docs = all.map(function (item) { return stubDoc(obs, item, all, bundleKey); });
    docs.push(logDoc(obs, docs, bundleKey));
    var files = {};
    docs.forEach(function (d) { files[d.path] = d.text; });
    var constants = {
      bundle_key: bundleKey,
      source_uri: "bqaa://" + obs.table + "?session_id=" + obs.session_id,
      revision: "bqaa-trace:" + obs.trace_id,
      deployment_key: "cymbal-finance-prod/eu/bqaa-derived-demo",
      compiler_semantics_version: "okf-context-compiler:v0.1",
      profile_contract_version: "okf-context/1",
      adapter_version: ADAPTER_VERSION
    };
    return { observation: obs, constants: constants, files: files, docs: docs, bundle_key: bundleKey };
  }

  // ---- identity chain (PROFILE.md; mirrors vectors_gen.py steps 1–6) ----
  // files: { path: string | Uint8Array }, manifests: { name: Uint8Array }
  function computeIdentities(files, constants, manifests) {
    var paths = Object.keys(files).sort(function (a, b) { return H.compareBytes(H.utf8(a), H.utf8(b)); });
    var fileHashes = {};
    paths.forEach(function (p) {
      var bytes = files[p] instanceof Uint8Array ? files[p] : H.utf8(files[p]);
      fileHashes[p] = H.sha256(bytes);
    });
    var manifestPairs = paths.map(function (p) { return [p, fileHashes[p]]; });
    var sourceManifestHash = H.h("okf-context:source-manifest:v1", manifestPairs);

    var mh = {};
    ["canonicalization-manifest", "semantic-config", "resolver-manifest", "vocabulary-manifest"].forEach(function (n) {
      if (!manifests[n]) throw new Error("missing compile manifest: " + n);
      mh[n] = H.sha256(manifests[n]);
    });

    var obsObj = { bundle_key: constants.bundle_key, revision: constants.revision, source_uri: constants.source_uri };
    var observationId = H.h("okf-context:observation:v1", obsObj);
    var snapObj = {
      bundle_key: constants.bundle_key,
      source_manifest_hash: sourceManifestHash,
      canonicalization_manifest_hash: mh["canonicalization-manifest"],
      compiler_semantics_version: constants.compiler_semantics_version,
      semantic_config_hash: mh["semantic-config"],
      vocabulary_manifest_hash: mh["vocabulary-manifest"],
      resolver_manifest_hash: mh["resolver-manifest"]
    };
    var snapshotId = H.h("okf-context:snapshot:v1", snapObj);
    var pubObj = {
      deployment_key: constants.deployment_key,
      observation_id: observationId,
      snapshot_id: snapshotId,
      profile_contract_version: constants.profile_contract_version
    };
    var publicationId = H.h("okf-context:publication:v1", pubObj);

    var conceptVersions = {};
    paths.forEach(function (p) {
      if (!/\.md$/.test(p) || p === "index.md" || p === "log.md") return;
      var text = files[p] instanceof Uint8Array ? new TextDecoder().decode(files[p]) : files[p];
      var parts = H.splitFrontmatter(text);
      var key = constants.bundle_key + "#" + p.slice(0, -3);
      conceptVersions[p] = H.hexid(H.h("okf-context:concept-version:v1", [key, H.normalizeText(parts.frontmatter), H.normalizeText(parts.body)]));
    });

    var fileSha = {};
    paths.forEach(function (p) { fileSha[p] = H.hex(fileHashes[p]); });
    var mhx = {};
    Object.keys(mh).forEach(function (n) { mhx[n] = H.hexid(mh[n]); });
    return {
      observation_id: H.hexid(observationId),
      snapshot_id: H.hexid(snapshotId),
      publication_id: H.hexid(publicationId),
      source_manifest_hash: H.hexid(sourceManifestHash),
      manifest_hashes: mhx,
      file_sha256: fileSha,
      concept_version_ids: conceptVersions
    };
  }

  // Opaque demo envelope id for the derived publication (labelled as minted
  // by the demo; production envelope ids are random, never derived).
  function demoEnvelopeId(publicationId) {
    return "env-" + H.hex(H.h("okf-demo:envelope-id:v0", publicationId)).slice(0, 16);
  }

  // Deep key scan for the never-emit assertion on agent-facing payloads.
  function keysDeep(obj, out) {
    out = out || {};
    if (Array.isArray(obj)) obj.forEach(function (v) { keysDeep(v, out); });
    else if (obj && typeof obj === "object") Object.keys(obj).forEach(function (k) { out[k] = true; keysDeep(obj[k], out); });
    return out;
  }
  function neverEmitViolations(payload) {
    var keys = keysDeep(payload);
    return NEVER_EMIT.filter(function (k) { return keys[k]; });
  }

  return {
    ADAPTER_VERSION: ADAPTER_VERSION, NEVER_EMIT: NEVER_EMIT, TYPE_DIRS: TYPE_DIRS,
    observe: observe, adapt: adapt, pathFor: pathFor, computeIdentities: computeIdentities,
    demoEnvelopeId: demoEnvelopeId, keysDeep: keysDeep, neverEmitViolations: neverEmitViolations
  };
});
