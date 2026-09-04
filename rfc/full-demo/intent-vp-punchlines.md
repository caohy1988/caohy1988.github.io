# Intent — VP punchline strip on /rfc/full-demo/

Haiyuan 2026-09-04 (iterated): VP of BigQuery needs punchlines.

**Thesis:** BigQuery is the **runtime** of Knowledge Catalog + OKF.

**Why BQ (Haiyuan):**
1. More **deterministic retrieval** from OKF that lives in KC.
2. **Easier IAM** (deployment-scoped vs EntryGroup cascade).
3. **BigQuery Graph** retrieves the **OKF chain** via the OKF standard the easy way (Observation → Snapshot → Publication → edges) — platform Graph GA; on this page the chain is shown via SQL/evidence today; Graph path is the RFC optional projection (relational remains authoritative). Do **not** invent a live Graph query capture.

Honesty: OKF core on this site is **v0.2**. If punchline says “OKF 2.0,” treat it as Haiyuan’s VP shorthand for the runtime-standard story and keep a quiet honesty note that normative text is OKF v0.2 + optional runtime profile — do not claim a published OKF 2.0 core change.
