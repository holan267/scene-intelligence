# Rubric Review — ARCHITECTURE-SPINE (scene-intelligence)

Reviewer: rubric walker · Date: 2026-07-03
Target: `architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md`
Driving PRD: `prd-scene-intelligence-2026-07-03/prd.md` (+ `addendum.md`)

Verdict scale: PASS / WEAK / FAIL, one-line reason each.

---

## 1. Fixes the real divergence points for the level below, misses none — **WEAK**

The 15 ADs cover the load-bearing invariants an epic team could otherwise split on: unit-of-index (AD-1), read/write split (AD-2), single-writer ownership (AD-3), SoT + derived stores (AD-4), idempotent stages (AD-5), keyframe-only vision (AD-6), single search embedding (AD-7), fixed funnel (AD-8), Vietnamese-first (AD-9), durable queue (AD-10), immutable media (AD-11), ms timecode (AD-12), API envelope (AD-13), on-prem/one-language (AD-14), eval-on-real-path (AD-15). That is a genuinely strong set — most real divergence points are nailed.

Two divergence points are left open:

- **Sub-scene chunking is unreconciled.** Addendum §3 explicitly permits "Chunk Scene đa nhịp (1 Scene 2 nội dung rất khác → 2 sub-embedding)", but AD-7's Rule says "đúng **một** scene_embedding" per scene and AD-1 makes `scene_id` the atomic return unit. Two builders will diverge: one enforces strictly one vector/scene, another emits multiple sub-scene vectors. The spine does not say whether a multi-content scene is re-split (new scene_ids) or carries N embeddings. This is a live divergence the spine should close.
- **Filter taxonomy (FR-7) is not fixed.** FR-7 names filters (cỡ cảnh / có mặt người / độ dài / không-logo) but no AD or convention pins the canonical filterable field set/names, so ingest (which must populate them) and search/UI can drift on which structured attributes exist and how they are keyed.

## 2. Every AD's Rule is enforceable and prevents its stated divergence — **PASS**

Rules are concrete and testable: single-writer per domain (AD-3), rebuild-from-Postgres (AD-4), per-stage field-namespace + checksum (AD-5), named Vietnamese-capable models on the whole NL path (AD-9), fixed funnel order with named reranker (AD-8), immutable original media (AD-11), integer-ms timecode (AD-12), one search envelope shape (AD-13). Each maps directly to its "Prevents" line and is machine/review-checkable. Note: a few thresholds are left as tuning knobs rather than invariants — AD-8 "bỏ rerank khi #1 bỏ xa #2" and AD-11 "confidence ≥ ngưỡng" have no numeric value — which is acceptable at initiative altitude (they are tuning, not structural divergence). AD-7's rule is enforceable but collides with the addendum (see item 1).

## 3. Nothing under Deferred could let two units diverge — **WEAK**

Most deferrals are safely isolated behind an existing boundary: Qdrant migration and OpenSearch/BM25 are quarantined behind Search Service + AD-4 rebuild; NLE round-trip is kept ready by AD-12; k8s/HA sit behind the container boundary; analytics is a separate read path. Good.

Two deferred/open items are live divergence risks, not silent-safe:

- **Query-understanding (filter extraction from NL)** is parked as open question §8.2 ("chưa quyết"). It is flagged, so not silent — but it directly governs how AD-8's stage-① SQL filter gets populated from a free-text query. Undecided, an epic can build a plain search box while another builds an LLM filter-splitter, changing the read path's front edge. Should at least be an explicit open question inside the read-path AD, not only in the Deferred bin.
- **Backup/DR is deferred, but Postgres is the single source of truth** (AD-4: everything else rebuilds from it). Deferring backup of the one non-rebuildable store is an operational risk masquerading as "infra survey later". This does not cause *unit-to-unit* divergence, so it lands more squarely under item 6, but it is the one deferral whose absence is load-bearing.

## 4. Named tech is verified-current — **PASS (defer depth to version reviewer)**

Stack is marked "verified mid-2026" against `stack-verification.md` and is internally consistent (Python 3.12, PG 18.x, pgvector 0.8.4, FastAPI 0.139.x, React 19.2 / Vite 7.x, transformers ~4.5x). The explicit "**không MinIO CE**" exclusion is a deliberate, defensible call. One entry stands out and is worth the version reviewer's attention: **"Ultralytics YOLO26"** as a version label — confirm this is a real released line and not a mislabel. Several rows use "current" rather than a pinned version (PhoWhisper, VietOCR, Qwen3-VL, BGE-M3, bge-reranker-v2-m3, vLLM); that is acceptable for a seed but the pinning is exactly the depth the version reviewer should close.

## 5. Covers the driving PRD's capabilities (FR-1..FR-14 governed) — **PASS**

The Capability→Architecture map lists all 14 FRs, each with a home module and governing AD(s), and every FR resolves to at least one enforceable AD. Spot-check holds: FR-11 visual similarity → AD-7 (separate visual collection, off the text path); FR-13 noise-suppression → AD-4/AD-9 (IDF stopword in ingest); FR-14 eval → AD-15 (same Search Service). No FR is unmapped. Weakest cell is FR-7 (filtering) — mapped to AD-8/AD-13 but neither actually fixes the filter attribute set (see item 1). Success metrics SM-1 (p95 latency) and SM-4 (ingest throughput) are named in the PRD but have no observability hook in the spine to measure them (see item 6).

## 6. Every dimension the initiative altitude owns is decided/deferred/open — especially the operational envelope — **WEAK**

Covered: deployment (Docker Compose, single GPU node, AD-14 + Structural Seed), infra (on-prem, air-gapped), security/auth *in principle* (whole-app login gating, secrets outside repo, `[ASSUMPTION: SSO/LDAP]` flagged; detailed RBAC deferred), config (env/.env), job durability/retry (AD-10), and rebuildability (AD-4).

Gaps — dimensions left thin or silent:

- **Environments / promotion path — SILENT.** No dev/test/prod topology, no migration or upgrade story for schema changes or re-enrichment rollouts. AD-5 stage-versioning helps re-runs but there is no word on how the deployed system evolves.
- **Observability beyond logs — near-silent.** Only "structured JSON logs with video_id/scene_id/stage" and queryable job status. There is no metrics/latency/throughput instrumentation, yet SM-1 (p95 ≤ 2s) and SM-4 (≥2× realtime/GPU) are the product's acceptance gates and FR/UJ-3 promises an ingest progress board. The means to observe the very NFRs the system is judged on is not decided.
- **Backup/DR — deferred, but the SoT is not.** Since only Postgres is non-rebuildable (AD-4), deferring its backup is the one operational deferral that is load-bearing; should at minimum be an explicit open question, not a general "infra survey" line.

Auth being decided-in-principle with mechanism deferred is acceptable for an internal MVP. The environments and observability silences are the real flags.

## 7. Consistency conventions cover where independent builders would actually drift — **WEAK**

Strong coverage on the drift points that bite hardest: id/scene_id format, snake_case, past-tense event names, vector collection names, `*_ms` integers, confidence float 0–1, the `{results, meta}` envelope, and a shared `{error:{code,message,detail}}` shape. These prevent the classic cross-team drift.

Uncovered API-surface drift points, all on the exact boundary AD-13 declares "hard":

- **Pagination/sorting** of search results — envelope has `results[]` + `meta{}` but no page/limit/cursor or sort convention; two teams will invent different ones.
- **Score semantics** — `score` is in the envelope but nothing says whether it is normalized 0–1, raw rerank logit, or RRF score; UI and eval will interpret it differently.
- **URL/versioning + resource URL scheme** — no API version convention, and `thumbnail_url` / clip-download URL construction against object storage is unspecified.

These are genuine independent-builder drift points on the one interface the spine calls a hard boundary, so the conventions table is good but incomplete.

---

## Summary of findings (weakest first)

1. **Item 6 (WEAK)** — Operational envelope has silent dimensions: environments/promotion path (silent), observability = logs only (no metrics for the p95/throughput SMs it will be judged on), backup/DR of the Postgres SoT deferred though load-bearing.
2. **Item 7 (WEAK)** — Conventions miss API-surface drift on the "hard boundary": pagination/sorting, `score` normalization semantics, API versioning + resource URL scheme.
3. **Item 1 (WEAK)** — Two divergence points unfixed: sub-scene chunking (addendum §3) contradicts AD-7 "exactly one scene_embedding"; FR-7 filter attribute set is not pinned anywhere.
4. **Item 3 (WEAK)** — Query-understanding (NL→filter extraction) is undecided yet governs the front edge of the AD-8 read path; Postgres-SoT backup deferral is load-bearing.
5. **Item 4 (PASS, note)** — "Ultralytics YOLO26" version label needs confirmation; several models pinned as "current" — depth left to the version reviewer.

Items 2 and 5 PASS. Overall the spine is well-formed and unusually disciplined on the search/ingest core; the weaknesses cluster in the operational envelope and the API contract's finer edges.
