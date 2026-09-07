# Slice B2 owned lifecycle — b2-20260907t162636z-cd45

verdict `B2_ALL_MET` · P1 `pub_190192147fd7fd78` · P2 `pub_ae9b6cb130731d01` · elapsed 222.97 s · dataset `okf_catalog_chain_b2_20260907t162636z_cd45` · entry prefix `projects/test-project-0728-467323/locations/us-central1/entryGroups/okf-rfc-demo/entries/acme-retail-catalog-chain/b2-20260907t162636z-cd45/`

| case | gate | expected | status | detail |
|---|---|---|---|---|
| b2-control | R1/R2 | CHAIN_CONNECTED on the owned entry/dataset with head = P1 | **MET** | chain CHAIN_CONNECTED, head pub_190192147fd7fd78 |
| historical-inflight | R3 | P1 served exactly while the head moved to P2 mid-request | **MET** | chain CHAIN_CONNECTED, head pub_190192147fd7fd78 |
| historical-fresh | R3 | fresh P1 request after the switch: head observed = P2, P1 served exactly | **MET** | chain CHAIN_CONNECTED, head pub_ae9b6cb130731d01 |
| fail-stale-withdrawn | R3/R6 | FAIL_STALE, no content, no receipt | **MET** | chain CHAIN_BROKEN at publication, head pub_ae9b6cb130731d01 |
| missing-runtime-aspect | R1/R6 | ASPECT_MISSING at seed, authored aspects intact | **MET** | chain CHAIN_BROKEN at seed, head None |
| wrong-publication-pin | R6 | FAIL_STALE (PUBLICATION_MISSING), no content, no receipt | **MET** | chain CHAIN_BROKEN at publication, head pub_ae9b6cb130731d01 |
| wrong-seed-pin | R6 | FAIL_STALE (SEED_MISSING), no content, no receipt | **MET** | chain CHAIN_BROKEN at publication, head pub_ae9b6cb130731d01 |
| mixed-payload-injection | R4 | tampered cases refused by the payload guard before the SDK | **MET** | chain CHAIN_BROKEN at approved, head pub_ae9b6cb130731d01 |
| recovery-control | R6 | valid pin restored: CHAIN_CONNECTED again (head = P2, P1 served) | **MET** | chain CHAIN_CONNECTED, head pub_ae9b6cb130731d01 |
| cleanup | R7/R8 | originals UNCHANGED, owned resources absent on readback, every lifecycle job terminal | **MET** |  |
