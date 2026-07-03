# Technology Reality-Check Review — Scene Intelligence Stack

- **Reviewer role:** Technology reality-check (web-verified, not from training memory)
- **Date:** 2026-07-03
- **Scope reviewed:** `ARCHITECTURE-SPINE.md` (Stack table + ADs) and `stack-verification.md`
- **Method:** Every committed technology cross-checked on the web as of mid-2026 for (a) currency/maintenance, (b) correct name/version, (c) fit to the on-prem, Vietnamese-first, tens-of-thousands-of-hours-of-video use case.

---

## Verdict

The stack is unusually well-researched and **broadly current and correct** for mid-2026. Names and versions check out; the two biggest calls the team already made (kill MinIO CE, upgrade Vi ASR to PhoWhisper-large) are right. **The stack's real weak point is licensing, not currency or fit.** Two committed components — **Ultralytics YOLO26 (AGPL-3.0)** and **InsightFace buffalo_l (non-commercial research only)** — are licensing traps for anything beyond a throwaway internal pilot, and the spine under-flags YOLO entirely. pgvector-for-MVP is **safe, not a trap**, given the scene-count math below. A handful of pins should be tightened.

Overall grade: **green with two licensing red flags and ~5 tightenings.**

---

## Pressure-test findings (the items the brief called out)

### 1. pgvector 0.8.4 vs "tens of thousands of hours" — SAFE for MVP (not a trap)

**Version:** 0.8.4 is confirmed the current release (Docker tags `0.8.4-pg18-*` published within days of this review). Pinning 0.8.4 is correct **and security-relevant**: 0.8.2 fixed CVE-2026-3172 (buffer overflow in parallel HNSW index builds), so 0.8.4 is the right floor for an on-prem deployment. Good pin.

**Scale estimate (the actual question):**

- "Tens of thousands of hours" → model 30,000 h (mid) to 90,000 h (high end).
- Broadcast **scene** (the index unit per AD-1, a group of shots) averages ~30–60 s. Use 45 s → ~80 scenes/hour.
  - 30,000 h → ~2.4M scenes; 90,000 h → ~7.2M scenes.
  - At a finer 30 s/scene: ~3.6M–10.8M scenes.
- **Vectors** = `scene_text` (1 BGE-M3 vector/scene, the search-critical index) **+** `scene_visual` (1 SigLIP2 vector/scene, FR-11 only).
  - **Text index alone: ~2.4M–10.8M vectors.**
  - Both collections: ~5M–21M vectors total.

**Judgment:** The search-critical text index (~2–11M × 1024-dim) sits **comfortably inside pgvector's proven comfort zone** (independent 2026 guidance puts the plain-pgvector/HNSW sweet spot at "at or below the low tens of millions," with dedicated DBs only needed past ~50M). Even both collections combined stay under the tens-of-millions line the spine already uses as its Qdrant trigger. **pgvector-for-MVP is the right, low-complexity call and honors AD-4 (single source of truth, rebuildable).** Two caveats to bake in now, not later:

- **RAM/HNSW build cost is the real constraint, not query correctness.** 10M × 1024-dim float32 ≈ 40 GB raw; an HNSW index on that reaches ~60–120 GB and must fit in memory during build (default `maintenance_work_mem` 64 MB forces a 10–50× slower disk build). At the upper end this can exceed a single MVP node's RAM.
- **Mitigation, on-prem-clean:** use `halfvec` (halves index size) and/or add **pgvectorscale** (Timescale's StreamingDiskANN, **PostgreSQL-licensed** — clean for an on-prem product) which is disk-resident and keeps RAM bounded regardless of dataset size. This lets you defer the Qdrant migration far longer and stay single-store. Recommend naming pgvectorscale explicitly in the spine as the "before Qdrant" step.

**Net:** not a trap. Keep pgvector for MVP; add `halfvec`/pgvectorscale to the plan for the 90k-hour end. Qdrant deferral trigger ("vài chục triệu vector") is correctly placed.

Sources: <https://github.com/pgvector/pgvector/releases> · <https://www.postgresql.org/about/news/pgvector-082-released-3245/> · <https://www.dbi-services.com/blog/pgvector-a-guide-for-dba-part-2-indexes-update-march-2026/> · <https://github.com/timescale/pgvectorscale>

### 2. PhoWhisper-large as Vietnamese ASR — CORRECT, still the defensible open default

VinAI PhoWhisper-large remains the SOTA open Vietnamese ASR and is still the reference baseline cited in 2026 Vietnamese-speech papers. Running it via **faster-whisper/CTranslate2** is sound for GPU throughput. Two integration notes:

- PhoWhisper ships as HF/Whisper weights; to run under faster-whisper it must be **converted to CTranslate2 format** (`ct2-transformers-converter`) — a one-time step, not a pre-packaged model. Call this out so it isn't discovered late.
- **License check:** confirm PhoWhisper-large's license permits your deployment (VinAI research assets sometimes carry non-commercial terms). Whisper itself is MIT; the fine-tune's terms are what matter for a product. Low risk but verify.

Sources: <https://huggingface.co/vinai/PhoWhisper-large> · <https://github.com/VinAIResearch/PhoWhisper>

### 3. Qwen3-VL for scene descriptions — CORRECT and current

Qwen3-VL is real and current: dense 2B/4B/8B/32B released Oct 2025, technical report Nov 2025, actively supported. 8B (~12–16 GB) / 32B (24 GB) sizing in the notes is accurate. Vietnamese is within its 32-language OCR/multilingual coverage with solid (not best-in-class) Vietnamese results. Apache-2.0 licensed → **clean for on-prem product.** The "Qwen2.5-VL is obsolete" call is right. No change.

Sources: <https://github.com/QwenLM/Qwen3-VL> · <https://arxiv.org/abs/2511.21631> · <https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct>

### 4. BGE-M3 + bge-reranker-v2-m3 for Vietnamese retrieval — CORRECT, with a Vietnamese-specialized upgrade to consider

Both are current, maintained (FlagEmbedding), multilingual (100+ langs), and pair cleanly (embedding + matching cross-encoder). MIT-licensed → clean on-prem. Good pragmatic default for AD-9.

**One upgrade worth noting:** 2026 Vietnamese-specific research (**ViRanker**, itself BGE-M3-based) now **outperforms bge-reranker-v2-m3 on Vietnamese rerank benchmarks.** Since rerank is the last, quality-determining stage of your AD-8 funnel, ViRanker is a low-risk, Vietnamese-first swap candidate for the rerank slot (keep BGE-M3 for embeddings). Treat as an eval experiment, not a blocker.

Sources: <https://huggingface.co/BAAI/bge-m3> · <https://huggingface.co/BAAI/bge-reranker-v2-m3> · <https://www.themoonlight.io/en/review/viranker-a-bge-m3-blockwise-parallel-transformer-cross-encoder-for-vietnamese-reranking>

### 5. YOLO26 — name/currency CORRECT, but LICENSE UNDER-FLAGGED (red flag)

YOLO26 is real: launched by Ultralytics **Jan 14, 2026**, NMS-free/end-to-end, current default. Name and "not a version number for YOLOE" nuance are right.

**Problem the spine misses entirely:** Ultralytics YOLO (incl. YOLO26) is **AGPL-3.0**. Commercial/product use requires an **Ultralytics Enterprise License**. AGPL's network-service copyleft is a genuine concern the moment this becomes a product sold to broadcasters (explicitly a planned direction in "Deferred → thương mại hoá"). Even internal deployment at a commercial broadcaster is a grey area. `stack-verification.md` flags InsightFace and Redis licenses but is silent on YOLO — that gap should be closed. **Action:** budget for an Ultralytics Enterprise license, or plan an Apache/BSD-licensed detector fallback (e.g., an RT-DETR-family model) if AGPL is unacceptable.

Sources: <https://docs.ultralytics.com/models/yolo26> · <https://www.ultralytics.com/license> · <https://github.com/ultralytics/ultralytics/issues/24844>

### 6. SigLIP2 in transformers (~4.5x) — CORRECT

SigLIP2 landed in transformers 4.49 (`v4.49.0-SigLIP-2`), so any 4.5x pin includes it. `Siglip2Model` (needed for the NaFlex variants) is the right class; multilingual (109 langs) fits AD-9's spirit for the visual-similarity path. Apache-2.0 weights → clean on-prem. No change.

Source: <https://huggingface.co/docs/transformers/model_doc/siglip2>

### 7. Object storage: MinIO → SeaweedFS / Garage / Ceph RGW — RIGHT to switch; refine the pick toward license

The decision to drop MinIO CE is **correct and important.** Confirmed: MinIO removed the CE admin console (May 2025) and **archived the community `minio/minio` repo (Apr 25, 2026)**, steering everyone to paid AIStor (~$100k entry). (Minor factual fix: the spine says "khai tử 2/2026" — the archive was **late April 2026**, console removal mid-2025.)

Among the three candidates, **for an on-prem product the license should drive the choice**, and they differ materially:

- **SeaweedFS — Apache-2.0.** Cleanest license, Go, mature, S3-compatible, scales single-node → multi-node. **Recommended default.**
- **Garage — AGPL-3.0.** Excellent lightweight like-for-like MinIO replacement, but AGPL is the same copyleft concern as YOLO for a product. Fine for internal, think twice for shipped product.
- **Ceph RGW — LGPL, operationally heavy.** Only worth it if the broadcaster **already runs Ceph**; otherwise disproportionate ops burden for an MVP.

**Action:** change the spine's "chọn 1" note to *prefer SeaweedFS (Apache-2.0) unless existing Ceph infra*, so the license-clean option is the default rather than a coin-flip.

Sources: <https://github.com/minio/minio/discussions/21326> · <https://itsfoss.com/news/minio-moves-away-from-open-source/> · <https://github.com/seaweedfs/seaweedfs>

### 8. Postgres-backed queue (Procrastinate/pgmq) vs Dramatiq — CORRECT for the constraints

Postgres-backed is the right call given AD-14 (air-gap, minimal infra) and AD-10 (durable, resumable, trackable). Nuances:

- **Procrastinate** is the stronger primary: pure-Python, PG 13+, async-native, uses `LISTEN/NOTIFY` + `FOR UPDATE SKIP LOCKED`, actively maintained, **no server-side extension** → best for air-gapped install. Recommend naming it the default over pgmq.
- **pgmq** requires installing a **Postgres C extension** — one more air-gap artifact to vendor and a superuser install step. Slightly worse fit than Procrastinate for AD-14.
- **Dramatiq** is correctly positioned as the Redis-backed fallback — but note Redis core is now **AGPL**; if you ever go that route, use **Valkey (BSD)** as the drop-in, exactly as `stack-verification.md` already says. Consistent, good.

Source: <https://github.com/procrastinate-org/procrastinate>

### 9. vLLM for serving — CORRECT; tighten the pin

vLLM is the right on-prem serving choice for Qwen3-VL throughput/multi-GPU, Apache-2.0 (clean). **Tighten "current" → require `vLLM >= 0.11.0`**, which is the floor for Qwen3-VL support; earlier versions won't load the model. Otherwise no change.

Sources: <https://docs.vllm.ai/en/latest/models/supported_models/> · <https://github.com/vllm-project/vllm/releases>

---

## Remaining stack rows — quick verification

| Row | Verdict | Note |
|---|---|---|
| Python 3.12 | ✅ current | 3.13 also GA; 3.12 is a safe conservative pin |
| FastAPI 0.139.x | ✅ current | 0.139.0 released Jul 1, 2026 |
| PostgreSQL 18.x | ✅ current | GA Sept 25, 2025; 19 is only in beta — 18 is the right prod choice |
| Qdrant 1.17.x | ✅ current | 1.17 released Feb 2026 (relevance feedback, latency, ACORN filtered-recall) |
| PySceneDetect 0.7 | ✅ current | BSD-3, VFR timestamps, Py ≥3.10 — clean |
| InsightFace buffalo_l 1.0 | ⚠️ **license trap** | see below |
| EasyOCR + VietOCR (pbcquoc) | ✅ | correct to pin the **Python** pbcquoc/vietocr; EasyOCR Apache-2.0. Verify VietOCR weight license for product |
| React 19.2 / Vite 7.x | ✅ current | React 19.2.x shipping through 2026; Vite 7 supported (Vite 8 now exists — 7 is a fine conservative pin) |

---

## Licensing summary (the through-line, and the real risk)

For an internal-only MVP, most of these are tolerable; for the **explicitly-planned commercialization** ("Deferred → thương mại hoá"), three items must be resolved and only one is currently flagged in the spine:

| Component | License | Product risk | Fix |
|---|---|---|---|
| **InsightFace buffalo_l** | Model packs **non-commercial research only** (code is MIT) | **High** — even internal use at a commercial broadcaster is arguably commercial | Buy InsightFace commercial license, or train/swap the recognition model |
| **Ultralytics YOLO26** | **AGPL-3.0** | **High** — copyleft on a shipped/network product; **not flagged in spine** | Ultralytics Enterprise License, or Apache/BSD detector (RT-DETR family) |
| **Redis (if used)** | AGPL | Medium | Already covered: use **Valkey (BSD)** |

Clean-license components (no action): Qwen3-VL, SigLIP2, BGE-M3 + reranker, vLLM, PySceneDetect, EasyOCR, SeaweedFS, pgvector, pgvectorscale, Procrastinate, FastAPI, PostgreSQL, React/Vite. Verify: PhoWhisper-large, VietOCR weights.

Sources: <https://github.com/deepinsight/insightface> · <https://www.insightface.ai/services/models-commercial-licensing> · <https://www.ultralytics.com/license>

---

## Recommended edits to the spine/stack notes

1. **Add a YOLO26 license flag** (AGPL-3.0 → Enterprise license or RT-DETR fallback) to `stack-verification.md` "Red flags" — currently missing.
2. **Elevate InsightFace** from ✅⚠️ to a hard pre-commercialization action item (non-commercial license blocks even internal broadcaster use, arguably).
3. **Name pgvectorscale (StreamingDiskANN, PostgreSQL-licensed)** as the explicit "before Qdrant" scaling step, and add `halfvec` + `maintenance_work_mem` sizing to the MVP DB notes — this is what keeps ~10M vectors on one node.
4. **Prefer SeaweedFS (Apache-2.0)** as the default object store in the "chọn 1" note (Garage is AGPL, Ceph is ops-heavy). Correct the MinIO archive date to Apr 2026.
5. **Tighten pins:** `vLLM >= 0.11.0` (Qwen3-VL floor); note PhoWhisper needs CTranslate2 conversion for faster-whisper.
6. **Optional quality upgrade:** evaluate **ViRanker** (Vietnamese-specialized, BGE-M3-based) in the AD-8 rerank slot against bge-reranker-v2-m3.

No committed technology is out-of-date or mis-named. The stack is production-realistic for mid-2026; close the licensing gaps and tighten the pins above.
