// Proves the JS hashing port reproduces the Phase 0 golden triple from the
// authored fixture bytes on disk. Read-only. `node tools/check-authored-identities.mjs`
import { createRequire } from "node:module";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const demo = join(here, "..");
const A = require(join(demo, "adapter.js"));

function walk(dir, base = dir, out = {}) {
  for (const n of readdirSync(dir).sort()) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) walk(p, base, out);
    else out[relative(base, p).split("\\").join("/")] = new Uint8Array(readFileSync(p));
  }
  return out;
}
const golden = JSON.parse(readFileSync(join(demo, "fixture/golden/identities.json"), "utf8"));
const files = walk(join(demo, "fixture/bundle"));
const manifests = {};
for (const n of ["canonicalization-manifest", "semantic-config", "resolver-manifest", "vocabulary-manifest"])
  manifests[n] = new Uint8Array(readFileSync(join(demo, "fixture/golden/manifests", n + ".json")));
const got = A.computeIdentities(files, golden.inputs, manifests);
let ok = true;
for (const k of ["observation_id", "snapshot_id", "publication_id", "source_manifest_hash"]) {
  const same = got[k] === golden[k];
  ok &&= same;
  console.log((same ? "OK  " : "FAIL") + " " + k + " " + got[k]);
}
for (const p of Object.keys(golden.concept_version_ids)) {
  const same = got.concept_version_ids[p] === golden.concept_version_ids[p];
  ok &&= same;
  if (!same) console.log("FAIL concept_version_id " + p);
}
for (const n of Object.keys(golden.manifest_hashes)) ok &&= got.manifest_hashes[n] === golden.manifest_hashes[n];
console.log(ok ? "authored golden triple + concept versions reproduced by hash.js" : "MISMATCH");
process.exit(ok ? 0 : 1);
