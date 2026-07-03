# Competitive Landscape Digest — Scene Intelligence (2026-07-03)

Scoped for PRD; hero use-case = broadcast/news video editor finding B-roll under deadline, exporting to NLE.

## 1. Competitors & comparables

### A. Cloud "video AI" building blocks (APIs, not products) — cloud-only, pay-per-minute
- **Azure AI Video Indexer** — broadest single-API enrichment (transcription, OCR, face/celebrity, labels, topics, brands, translation); decent web portal; limited on-prem via Azure Arc/edge; per-input-minute pricing. Gap: generic metadata, not editor-workflow/NLE-integrated; NL search bolt-on.
- **AWS Rekognition Video** — label ~$0.10/min, shot detection ~$0.05/min, face/moderation ~$0.10/min. Pure API, no UI, no NL search. You build the product on top.
- **Google Cloud Video Intelligence** — label ~$0.10/min, others ~$0.12/min. Pure API. Same gap.
- Takeaway: giants are **infrastructure, not the newsroom product**. Their weaknesses = your wedge: no editor UX, no NLE export, weak/absent semantic search, cloud-only, poor Vietnamese.

### B. Video-native semantic/foundation-model search
- **Twelve Labs** — reference multimodal video understanding (Marengo 3.0 embeddings + Pegasus scene descriptions); NL search "no tags needed"; ~$0.042/min index. Claims cloud/self-hosted/on-prem, SOC2; on Bedrock. Gap: search engine not editor product; English-centric; self-hosting heavy. Build-vs-buy component.
- **Moments Lab (ex-Newsbridge)** — **closest direct competitor**; purpose-built for media/newsrooms; MXT multimodal AI → human-like NL scene descriptions; broadcaster/sports/news focus. Cloud SaaS; pricing not public. Gap: cloud-first (weak on-prem/sovereignty), Western-language focus. **Watch most.**
- **Vidrovr** — was strong broadcast video-search; **acquired by CesiumAstro (Feb 2026), pivoted to defense/geospatial → exiting media**. An opening + a TAM caution.
- **Valossa** — smaller video-to-text/semantic search.

### C. MAM/DAM players adding AI search
- **iconik** — cloud MAM popular with post/creative; AI tagging at ingest; ~$20/seat entry, real cost $500+/mo. Cloud-only, general (not newsroom-deadline) UX, tagging not deep semantic.
- **eMAM** — **eMAM 6.0 "eMAM Next" = on-prem AI tool**, semantic search via Whisper + Twelve Labs. Evidence market is moving to on-prem AI + best-of-breed model licensing.
- **Avid MediaCentral** — incumbent newsroom platform, unified with Wolftech News, AI story assembly; on-prem+cloud; search mostly text-metadata. Entrenched (also integration target).
- **Dalet (Galaxy/Pyramid)** — enterprise MAM+orchestration; launched Dalet Content Discovery (AI in newsroom); on-prem+cloud; heavyweight/expensive.
- **Vizrt Viz One** — MAM + AI enrichment via DeepVA partnership (best-of-breed plugged in).
- **Reduct.video** — transcript-centric search/editing; weak for visual B-roll.
- **ELEMENTS / EditShare Flow** — storage/MAM with mature **NLE panels** (Premiere/Resolve/Media Composer) for search + rough-cut import. This is the integration bar to clear.

## 2. What NL-video-search emphasizes 2025-2026
- Multimodal embeddings over keyword tagging (hybrid semantic+lexical emerging default).
- Generative NL scene descriptions per scene (improves recall via plain-language search).
- RAG-over-video (ask a question → exact clip + explanation).
- Agentic search (multi-step resolve vague editorial queries).
- Moment/frame-level search, not asset-level — jump straight to timecode.

## 3. Editor / newsroom reality
- Today: MAM/DAM search (filename + manual tags + transcript) + tribal knowledge + manual scrubbing. Deadline pain = under-tagged footage → scrub hours of rushes.
- **NLE-native AI now table stakes:** **Adobe Premiere Pro 25.x "Media Intelligence" (2025)** = on-device NL visual search, spoken-word search, metadata search in one panel. BUT bin-scoped (footage already in project), on-device, single-editor. Wedge = **enterprise archive scale, shared/on-prem, Vietnamese**.
- **Integration bar (make-or-break):** NLE panels (search MAM + drag rough-cut into timeline without leaving NLE); interchange = XML (FCP/Premiere), **AAF (Avid)**, **EDL**, growing OpenTimelineIO; deliver timecode-correct sequence/selects; handle proxy vs high-res conform, "media offline."
- Pain to target: under-tagged archives; keyword misses visual concepts; no jump-to-moment; silos; export friction; multilingual footage invisible to English-only AI.

## 4. Differentiation for ON-PREM, Vietnamese-capable system
1. **True on-premise / air-gapped** — mandatory for many TV stations (sovereignty, rights, egress cost). Open lane (validated by eMAM on-prem move).
2. **Vietnamese-first ASR + OCR** — cloud giants mediocre at Vietnamese; local stacks exist (Speechmatics/AppTek on-prem VN ASR, open VietASR, VLSP datasets). Vietnamese OCR for lower-thirds = concrete edge.
3. **Newsroom-tuned editor-first UX + NLE round-trip** — beat generic APIs/DAMs on the deadline workflow.
4. **Data control / cost predictability** — no per-minute egress/processing bill scaling with archive.
5. **Best-of-breed model composition** — own pipeline + UX + Vietnamese layer, not the frontier model.

## 5. Pricing / business-model norms
- Cloud AI APIs: per-input-minute, per-feature stacked; cost scales with archive size.
- MAM/DAM SaaS: per-seat + storage/consumption (opacity a complaint).
- Enterprise broadcast (Dalet/Avid/Vizrt): large perpetual/annual on-prem licenses + support/services; six-figure deals; high-touch sales.
- **Likely model here:** on-prem perpetual/annual license per station (or per-channel/per-storage-tier) + support/maintenance + optional pro-services for archive ingest. Neutralizes the giants' per-minute meter.

## Bottom line
- Watch = **Moments Lab** + **Adobe Premiere Media Intelligence**. **Vidrovr vacated media → timely opening.**
- Defensible position = **on-prem + Vietnamese ASR/OCR + newsroom editor UX with true NLE export (XML/AAF/EDL + panel)**, best-of-breed/open models.
- Must-have to be credible: jump-to-moment semantic search + Premiere/Resolve round-trip delivering timecode-correct selects (not just "search returns a file").
