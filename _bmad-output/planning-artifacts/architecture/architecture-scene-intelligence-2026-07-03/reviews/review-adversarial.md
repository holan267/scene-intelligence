---
title: Adversarial Architecture Review — Scene Intelligence
target: ARCHITECTURE-SPINE.md (2026-07-03)
reviewer: adversarial
date: 2026-07-03
verdict: CONDITIONAL — the AD set is coherent at the paradigm level but leaves ~10 one-level-down seams where two fully AD-compliant units still build incompatibly. Most are shared-store consistency, identity stability, and unnamed-domain ownership holes.
---

# Adversarial Review — Scene Intelligence Architecture Spine

## Method

For each finding I name **two concrete units one level down**, show that **each obeys every relevant AD to the letter**, show the **concrete incompatibility** that survives anyway, then propose a **NEW or TIGHTENED AD** (Binds / Prevents / Rule) that closes it. Findings are ordered most-severe first. Vague "could be clearer" items are excluded.

The spine's own dependency diagram, AD-3 (single-writer/domain), AD-4 (Postgres SoT, vector/FTS derivative), and AD-5 (idempotent/resumable per (video_id, scene_id, stage)) do most of the heavy lifting — but they legislate *logical* ownership without pinning the *physical* consistency, *identity stability*, and *cross-store ordering* that those very rules depend on to be true.

---

## Finding 1 — `scene_id` is positional, but AD-5 lets the pipeline re-mint it; AD-3 user-state is a foreign key to it → silent mis-binding [SEVERE]

**Units:** `pipeline/stages/detect` (mints scene identity) vs `api` user-state writer (writes FR-12 `used`, keyed on `scene_id`).

**Both AD-compliant:**
- `detect` obeys AD-5 ("Orchestrator sở hữu vòng đời tạo/xoá Scene"; re-running a stage is safe) and the naming convention `scene_id = "<video_id>_s<n>"`, n = scene sequence number.
- `api` obeys AD-3 (API is single-writer of user-state) and AD-1 (results identified by `scene_id`). It stores `used` against `scene_id` as its key.

**Concrete incompatibility:** `scene_id` is *ordinal/positional*, not content-derived. AD-5 explicitly permits re-ingesting a Video ("xử lý lại một Video mà không nhân đôi dữ liệu"). A re-run of `detect` with a newer PySceneDetect version or a changed threshold produces a different number of scenes and shifts every subsequent `_s<n>`. After re-detect, `<video_id>_s5` covers a *different* `(start_ms, end_ms)`. The API's `used` marker — legitimately written against `_s5` and untouched by the pipeline (AD-3 forbids the pipeline touching user-state) — now labels the wrong content. No AD pins scene identity to be stable across re-detect. This is a two-owner-of-identity defect: the pipeline mints the key, the API foreign-keys to it, and the pipeline may silently redefine the key's meaning.

**Proposed TIGHTENED AD-1a — Scene identity is content-stable across re-ingest**
- **Binds:** AD-1, AD-3, AD-5, FR-12
- **Prevents:** re-detect silently re-pointing a stable id at different content; cross-domain foreign keys (user-state, eval set) rotting on re-ingest
- **Rule:** `scene_id` MUST be stable for the same content boundary across re-ingests. Either derive it from a content key (e.g. `<video_id>_<start_frame>` or a hash of the boundary), OR treat a boundary change as a new scene version and require an explicit, logged re-bind/invalidate step for all cross-domain references (user-state, eval ground truth) before the old id is retired. Ordinal `_s<n>` is display-only, never an identity or foreign key.

---

## Finding 2 — `describe` and `embed`/`index` are independent AD-5 filters with no freshness contract → vector and FTS legs of the funnel disagree with the SoT [SEVERE]

**Units:** `pipeline/stages/describe` (writes `scene_document` to Postgres) vs `pipeline/stages/embed`+`index` (write `scene_embedding` to the vector store and the FTS index).

**Both AD-compliant:**
- Each writes only its own field-namespace with a stage version/checksum (AD-5).
- Postgres holds `scene_document` as SoT; vector + FTS are rebuildable derivatives (AD-4). AD-7 keeps exactly one `scene_embedding`.

**Concrete incompatibility:** AD-4 guarantees the derivatives are *rebuildable*, not *fresh*. Nothing forces `embed`/`index` to re-run when `describe` rewrites `scene_document` (e.g. FR-13 stopword recompute, new Qwen prompt). So `scene_embedding` can encode document v1 while Postgres holds document v2, and the FTS index can be at yet another version. AD-8's funnel reads the ANN leg (vector, v1) **in parallel with** the BM25/FTS leg and the SQL filter (Postgres, v2) — the two legs now describe different text for the same scene, RRF merges inconsistent evidence, and AD-15 eval faithfully measures this incoherent state. This is a staleness/ordering hole across the shared derived stores that AD-5's per-namespace isolation actively *hides* (each stage looks internally consistent).

**Proposed NEW AD-16 — Derived artifacts carry and enforce source freshness**
- **Binds:** AD-4, AD-5, AD-7, AD-8, FR-14
- **Prevents:** vector/FTS encoding a stale `scene_document`; funnel legs ranking different versions of the same scene
- **Rule:** every derived artifact (`scene_embedding`, FTS row, visual embedding) MUST store the `source_checksum` of the exact `scene_document`/keyframe it derived from. A stage that rewrites a namespace MUST enqueue re-run of every downstream-derived stage. The Search Service MUST treat any derived artifact whose `source_checksum` ≠ current SoT as not-ready (exclude from results or trigger rebuild), never rank it.

---

## Finding 3 — No cross-store write-ordering / visibility gate → a half-indexed scene leaks into results [SEVERE]

**Units:** `pipeline/stages/embed`+`index` (writer that must land rows in Postgres SoT **and** the vector store, two distinct stores when pgvector→Qdrant per Deferred) vs `search` (reader that fans out to both).

**Both AD-compliant:** AD-2 mandates the two sides communicate *only* via the 3 stores (no cross-process calls), AD-4 makes Postgres SoT, AD-10 says a crashed worker retries. Each is honored.

**Concrete incompatibility:** There is no distributed transaction across Postgres and a separate vector store, and no AD pins write order or a "scene is visible" gate. Two failure interleavings, both reachable under AD-10 retry:
1. Vector point written, worker crashes before the Postgres commit → a vector exists with no SoT row, violating AD-4's "no data existing only in the vector store" — and the ANN leg can surface a scene the SQL filter/FTS can't resolve.
2. Postgres row committed, vector write fails → FTS leg finds the scene, ANN leg misses it → the scene is "half-visible," ranking is arbitrary, and eval sees flapping recall.
AD-4's rebuildability does not prevent transient partial-index visibility; it only guarantees eventual reconstructability.

**Proposed NEW AD-17 — SoT-first write order + explicit search-visibility gate**
- **Binds:** AD-2, AD-4, AD-8, AD-10
- **Prevents:** partially-indexed scenes appearing in results; orphan vectors with no SoT row
- **Rule:** the SoT row MUST be committed before any derivative is written; a scene enters search results **only** when an `indexed_ready` marker in Postgres confirms all derived artifacts are present and checksum-matched (Finding 2). The Search Service MUST filter on `indexed_ready` in tier ① (SQL filter). Reconciliation (drop orphan vectors, rebuild missing derivatives) is a defined, owned job, not incidental.

---

## Finding 4 — Job/queue state is a third data-domain AD-3 never named; API and workers both write it → cancel/status race [SEVERE — silent dimension]

**Units:** `api` Ingest/Job API (enqueues jobs, serves status per AD-10; per Structural Seed `api/` owns "ingest/job API") vs `pipeline/workers` (consume queue, update progress/status).

**Both AD-compliant:** AD-3 carves exactly two domains — *enrichment* (pipeline) and *user-state* (API). Job execution state (queued / running / failed / progress / cancel) is **neither**. So AD-3 constrains nobody here, and both units write `job.*` legally. AD-10 requires status to be "queryable" and to "retry on crash" but never names the writer or the state machine.

**Concrete incompatibility:** A user cancels via the API (writes `job.status='cancelled'`) while a worker concurrently transitions the same job `running → done`. Last-writer-wins either loses the cancel or resurrects a cancelled job; a retry after crash can re-run a job the API already cancelled. Two writers, one entity, no owner — exactly what AD-3 exists to prevent, but its two-domain enumeration left a gap.

**Proposed NEW AD-18 — Job/queue state is a named third domain with split ownership**
- **Binds:** AD-2, AD-3, AD-10, FR-1, UJ-3
- **Prevents:** two writers racing on `job.status`; lost cancels; resurrected jobs
- **Rule:** job/queue state is a third single-writer domain. **Execution-state transitions** (queued→running→done→failed→retry) are owned solely by the queue runtime/workers. The API owns only *submission* and a separate `cancel_requested` flag; workers observe `cancel_requested` at safe checkpoints and effect the terminal transition. The job state machine (states + legal transitions) is pinned in the spine.

---

## Finding 5 — AD-7 "exactly one embedding" contradicts the addendum's sub-embeddings, and the RRF collapse rule is unpinned → N:1 vectors-per-scene with ambiguous merge cardinality [HIGH]

**Units:** `pipeline/stages/embed` (writes the `scene_text` vector collection) vs the RRF-merge step inside `search`.

**Both AD-compliant:** AD-7 says "đúng một `scene_embedding`." Addendum §3 explicitly permits "Chunk Scene đa nhịp (1 Scene 2 nội dung rất khác → 2 sub-embedding)." An implementer can follow either the AD (1 vector) or the addendum (N sub-vectors) and claim compliance — the spine sources both. AD-8 mandates `Vector ANN ∥ BM25 → RRF merge`.

**Concrete incompatibility:** If `embed` emits sub-embeddings, the ANN leg returns up to N points for one `scene_id`, while the BM25/FTS leg returns one row per scene. AD-1/AD-13 require exactly one result row per `scene_id` with one `score`. Nothing pins how multiple sub-embedding hits collapse to scene granularity *before or within* RRF (max? sum? RRF-per-point then dedup?). Two compliant Search Service builds produce different rankings for identical data — and eval (AD-15) measures whichever one happens to ship.

**Proposed TIGHTENED AD-7a — One indexable vector per scene OR a pinned collapse rule**
- **Binds:** AD-1, AD-7, AD-8, AD-13
- **Prevents:** N:1 vector:scene cardinality leaking into RRF; divergent rankings across compliant builds; AD-7↔addendum contradiction
- **Rule:** the `scene_text` vector point id MUST be `scene_id`, one point per scene (reconcile the addendum: sub-beat handling, if used, MUST aggregate to a single per-scene vector or a single per-scene score before RRF, via a rule pinned here — e.g. max-pool score keyed on `scene_id`). RRF operates on scene-granular candidates only.

---

## Finding 6 — AD-5 gives *logical* namespace isolation; concurrent enrichers do *physical* read-modify-write on one JSONB row → lost updates [HIGH]

**Units:** two enrichers at the `enrich*` stage, e.g. `ASR enricher` vs `OCR enricher` (also face, object — independent, parallelized for the throughput NFR).

**Both AD-compliant:** AD-5 — each "chỉ ghi field-namespace của riêng nó." Addendum §6 stores metadata as "PostgreSQL (metadata + JSONB)."

**Concrete incompatibility:** Logical namespace isolation ≠ physical write isolation. If each enricher does `UPDATE scene SET meta = <full JSONB with my key set>` on the shared row, concurrent writers overwrite each other's JSONB blob (classic lost update) even though they "own different keys." AD-5's isolation is only true if the *physical* storage granularity is one writable cell per (scene, stage). The spine never pins that, so a compliant implementation using a shared JSONB column races.

**Proposed TIGHTENED AD-5a — Physical single-writer-per-cell backs the logical namespace**
- **Binds:** AD-3, AD-5
- **Prevents:** concurrent enrichers lost-updating a shared JSONB blob
- **Rule:** each stage's output MUST be persisted in storage it exclusively writes — a per-stage row/table keyed by (scene_id, stage), or a dedicated column, or key-scoped `jsonb_set` that never rewrites the whole column. No two stages may issue a full-object write to the same row/column.

---

## Finding 7 — Clip-trim is an orphan responsibility and `thumbnail_url` auth is unpinned → auth-gate bypass and an ownerless compute step [HIGH]

**Units:** `search` / `api` result producer (emits AD-13 envelope with `thumbnail_url`) vs `web` UI (fetches media) — and the FR-10 clip-trim step, which no named unit owns.

**Both AD-compliant:** AD-13 lists `thumbnail_url` in the envelope; the Invariants rule says "UI không bao giờ chạm DB/kho trực tiếp." AD-11 keeps the original immutable (only proxy/thumbnail added). AD-14 requires app-wide auth gating and air-gap. Object storage is a leaf. Each unit honors its ADs.

**Concrete incompatibility (two edges):**
1. **Auth bypass:** if the producer puts a direct/presigned object-storage URL in `thumbnail_url`, the browser fetches bytes straight from object storage — an unauthenticated capability URL that sidesteps the app-wide auth gate (AD-14) and arguably the "UI never touches stores directly" rule. If instead it must be API-proxied, that's a different contract. The spine never says which, so two compliant builds differ on whether media is auth-gated.
2. **Ownerless trim:** FR-10 requires a clip trimmed to `(start_ms, end_ms)`. Object storage can't trim (leaf). The pipeline is done and AD-2 forbids it serving read requests. The Search Service is read-only and "không ghi." So *no named unit* owns producing the trimmed clip — an orphan compute responsibility.

**Proposed NEW AD-19 — All media flows through the API auth boundary; clip-trim is an owned read-side endpoint**
- **Binds:** AD-11, AD-13, AD-14, FR-9, FR-10
- **Prevents:** unauthenticated media URLs bypassing the app auth gate; an ownerless clip-extraction step
- **Rule:** `thumbnail_url` and all clip/proxy URLs in the envelope are API-relative and served through the API under the same session auth (no direct-to-store URLs leave the server boundary). Clip trimming is owned by a read-side API media endpoint that reads the immutable original/proxy from object storage; neither the pipeline nor the Search Service serves media bytes.

---

## Finding 8 — AD-15 "same path" + AD-8 conditional/approximate/cached path → non-reproducible recall@10, undermining FR-14/SM-2 [HIGH]

**Units:** `eval` harness vs `search` Search Service.

**Both AD-compliant:** AD-15 forbids eval building a parallel retrieval path — it must call the same Search Service. AD-8 makes rerank conditional ("bỏ khi #1 bỏ xa #2"), ANN approximate with an `ef_search` knob, and permits query caching.

**Concrete incompatibility:** the "real path" is intentionally non-deterministic and adaptive: approximate ANN, a branchy conditional-rerank, and cache all shift the top-10 run-to-run and config-to-config. FR-14 requires "đổi công thức → chạy lại và so sánh chỉ số," and SM-2 gates the MVP on recall@10 ≥ 0.85 / MRR ≥ 0.7. Measuring an adaptive path faithfully (AD-15) yields metrics that move with sampling/branch noise, so a formula change can't be distinguished from variance. AD-15 and reproducibility pull against each other, and nothing pins a deterministic evaluation mode.

**Proposed NEW AD-20 — Deterministic eval mode on the same code path**
- **Binds:** AD-8, AD-15, FR-14, SM-2, SM-C3
- **Prevents:** metric deltas dominated by ANN/rerank/cache variance instead of formula changes
- **Rule:** the Search Service MUST expose a pinned evaluation mode over the *same* code path: fixed `ef_search`, rerank forced on, cache bypassed (consistent with SM-C3's cache-miss requirement), fixed seeds. Eval always runs in this mode so metric deltas reflect formula changes, not sampling. Production adaptivity stays; eval pins it.

---

## Finding 9 — Interval semantics and frame↔ms rounding are unpinned; single Video framerate assumes CFR → adjacent-scene overlap/gap and non-frame-accurate clips [MEDIUM-HIGH]

**Units:** `detect` (mints `start_ms`/`end_ms` by converting PySceneDetect frame indices → ms) vs the FR-10 clip/timecode export (converts ms → frames to trim).

**Both AD-compliant:** AD-12 — everything in integer ms, SMPTE display-only, framerate stored at Video level. Both units use ms throughout.

**Concrete incompatibility (three edges):**
1. **Interval inclusivity unpinned:** for adjacent scenes with `scene1.end_ms == scene2.start_ms`, the spine never says whether the interval is `[start, end)` or `[start, end]`. The boundary frame is claimed by both or neither → overlap/double-counting in eval and dedup, or a dropped frame in clips.
2. **Rounding direction unpinned:** if `detect` floors frame→ms and the trimmer rounds ms→frame, clip boundaries drift up to a frame; adjacent scenes gap/overlap by a frame.
3. **CFR assumption:** "framerate lưu ở cấp Video" cannot faithfully convert ms↔frame for VFR/telecine broadcast media (MXF/MPEG-TS). This silently compromises the frame-accuracy AD-12 explicitly promises to keep ready for the deferred NLE round-trip.

**Proposed TIGHTENED AD-12a — Half-open intervals, pinned rounding, VFR-aware framerate**
- **Binds:** AD-1, AD-12, FR-2, FR-10; Deferred NLE round-trip
- **Prevents:** adjacent-scene overlap/gap; frame-boundary drift; false frame-accuracy on VFR media
- **Rule:** scene intervals are half-open `[start_ms, end_ms)`; adjacent scenes share exactly the boundary ms with no overlap. `start_ms = round(frame * 1000 / fps)` with one pinned rounding rule used by both mint and trim; store the source frame index alongside ms where frame accuracy matters. VFR/telecine media MUST carry a per-Video handling decision (e.g. store frame index as canonical, ms derived) — a single scalar framerate is invalid for VFR.

---

## Finding 10 — AD-11 + AD-5 create a delete/re-ingest ownership deadlock: the pipeline may delete a Scene but may not clean the API-owned user-state that references it [MEDIUM-HIGH]

**Units:** `pipeline` orchestrator (owns Scene create/delete per AD-5) vs `api` user-state (only writer of user-state per AD-3, referencing `scene_id`).

**Both AD-compliant:** AD-5 gives the orchestrator scene lifecycle including deletion. AD-3 forbids any component writing another's domain — so the pipeline must not touch user-state, and only the API may delete a user-state row.

**Concrete incompatibility:** on Video deletion or re-ingest with fewer scenes, the pipeline legally deletes `scene_id` rows. The `used` user-state referencing those scenes is owned by the API, which has no signal that the scenes vanished (AD-2: sides communicate only via stores; no cross-process call). The pipeline can't clean it (AD-3), the API doesn't know to (no event). Result: orphaned user-state that *no unit may legally reconcile*. Cross-domain delete cascade is a dimension the initiative altitude owns and the spine leaves silent.

**Proposed NEW AD-21 — Cross-domain deletion cascade via SoT, not cross-process calls**
- **Binds:** AD-2, AD-3, AD-5, FR-12
- **Prevents:** orphaned user-state / eval references after scene deletion; a reconciliation nobody may perform
- **Rule:** scene deletion is a state transition in the SoT (soft-delete/tombstone), not a hard delete, so cross-domain owners can react. The API reconciles its user-state against scene tombstones on read/GC; eval ground truth references are validated against tombstones. No owner ever writes another domain's rows; each reacts to the SoT tombstone it observes.

---

## Finding 11 — `score`, `highlights[]`, and USER_STATE cardinality are interface/entity contracts the spine never pins [MEDIUM]

**Units:** `search` (produces the AD-13 envelope, both text-funnel and FR-11 visual paths) vs `web` UI / `eval` (consume it); and `api` user-state writer for editor A vs editor B.

**Both AD-compliant:** AD-13 defines the envelope *shape* — `score`, `highlights[]` — and AD-7 gives FR-11 a separate visual path. The ERD pins `SCENE ||--o| USER_STATE` (0..1 user-state per scene). Everyone honors these.

**Concrete incompatibilities (three under-pinned contracts):**
1. **`score` semantics:** the envelope has `score` but no defined scale/meaning. Text search's `score` (RRF or reranker logit) and FR-11 visual's `score` (cosine) live in the *same* envelope field on different, incomparable scales. A UI score bar or any cross-search comparison is meaningless. Also note AD-8's "no search bypasses the funnel (kể cả Eval)" literally contradicts AD-7's separate visual path — FR-11 *is* a bypassing search path; AD-8's scope must be narrowed to NL/text search.
2. **`highlights[]` shape:** undefined — which field matched, offsets vs snippets? UI renders it, search produces it, no contract.
3. **USER_STATE cardinality vs multi-user auth:** the ERD's `o|` forces exactly one user-state per scene → `used` is *global/shared*, yet AD-14 auth is per-user login. So editor A marking a scene "used" hides it from editor B (FR-12's hide option). PRD's "tránh lặp lại giữa các bản tin" is ambiguous between per-editor and per-newsroom. The entity model silently pins global, causing cross-editor interference and write races on the single shared row.

**Proposed TIGHTENED AD-13a — Pin score/highlights contracts; scope AD-8; decide user-state grain**
- **Binds:** AD-7, AD-8, AD-13, AD-14, FR-11, FR-12
- **Prevents:** incomparable `score` across search types; undefined `highlights[]`; global-vs-per-user `used` ambiguity
- **Rule:** (a) `score` is a defined, path-scoped rank score (e.g. normalized 0–1 per path) and clients MUST NOT compare scores across search types; `highlights[]` has a pinned shape `{field, snippet, [offsets]}`. (b) AD-8's "no bypass" is scoped to NL/text search; FR-11 visual search is a declared, separate read path (resolving the AD-8↔AD-7 conflict). (c) user-state grain (per-user vs per-newsroom `used`) is pinned in the ERD; if per-user, USER_STATE is `o{` keyed by (scene_id, user_id) and the single-shared-row race disappears.

---

## Dimensions the initiative altitude owns but the spine leaves silent

- **Job/queue state domain** — no owner in AD-3's two-domain carve (Finding 4).
- **Cross-store write ordering / partial-index visibility** — no atomicity or ready-gate (Finding 3).
- **Derived-artifact freshness** — AD-4 gives rebuildability, not consistency (Finding 2).
- **Cross-domain deletion cascade** — orphaned user-state after scene delete (Finding 10).
- **`score` / `highlights[]` / user-state cardinality** — envelope and entity contracts unpinned (Finding 11).
- **Interval inclusivity + frame↔ms rounding + VFR** — canonical-time edge cases (Finding 9).
- **Deterministic eval mode** — reproducibility of the MVP-gating metric (Finding 8).
- **Scene identity stability across re-ingest** — the load-bearing foreign key for two other domains (Finding 1).

## Net assessment

The paradigm (CQRS-lite, 3-store, single-writer, funnel) is sound and the AD set is internally near-consistent. The systematic weakness is that AD-3/AD-4/AD-5 legislate **logical** ownership and rebuildability while leaving **physical consistency, identity stability, cross-store ordering, and freshness** unpinned — precisely the seams where two compliant units diverge. Adopting AD-16 (freshness), AD-17 (write-order/visibility), AD-18 (job domain), and TIGHTENED AD-1a (stable identity) closes the four severe holes; the remaining tightenings (5a, 7a, 12a, 13a, 19, 20, 21) close the rest.
