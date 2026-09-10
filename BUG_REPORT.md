# MedAssist AI — QA Bug Report

**Date:** 2026-08-26 (original); **updated 2026-08-30**
**Scope:** backend (`backend/`), including the RAG layer and the newly-added `app/llm/` layer
**Test baseline at time of writing:** 209 passed, 0 failed
**Method:** every finding marked VERIFIED was reproduced by executing code, not by reading it. Findings marked UNVERIFIED are code-read only and are labelled as such.

### Changelog

**2026-08-30 — Phase 0 reconciliation.** RAG-1 through RAG-6 verified as FIXED by reading committed code and running regression tests. Key evidence: `indexer.py` stores raw term counts (RAG-1); scoring is query-intrinsic with four conjunctive sufficiency gates including non-entity floors (RAG-2); entity boundary is structural and fail-closed (RAG-3); adherence retrieval uses correct topic and full sufficiency gate (RAG-4); names match code — `tfidf_cosine_score` for lexical, `semantic_score` for real dense embeddings (RAG-5); `embeddings.py` is a 443-line module with `OllamaEmbedder` wired into production retriever (RAG-6). Metformin wrong-topic regression (`"metformin gastrointestinal bleeding interaction"`) measured at `ne_coverage=0.000, ne_cosine=0.000` — hard structural zero, not threshold-sensitive. Case added to `eval_retrieval.py`.

## Severity scale

| | Meaning |
|---|---|
| **S1** | Can produce a wrong clinical output, or destroy clinical data, without an error |
| **S2** | The system's behaviour does not match what its code, docs, or API claim |
| **S3** | Hygiene: correct behaviour, but a maintenance or deployment hazard |

## Summary

| ID | Sev | Status | Title |
|---|---|---|---|
| HIST-1 | S1 | **FIXED** | Deleting a schedule silently erased the patient's adherence history |
| HIST-2 | S2 | **FIXED** | `active=True` never expired, so a finished course read as live forever |
| HIST-3 | S2 | **FIXED** | `active=False` conflated "clinician stopped this drug" with "plan was replaced" |
| HIST-4 | S3 | **FIXED** | Model comment overclaimed what `passive_deletes="all"` protects |
| RAG-1 | S2 | **FIXED** | BM25 document term frequency is always 0 or 1 — the saturation term is inert |
| RAG-2 | S1 | **FIXED** | `relevance_score` is a per-query rank, not a confidence, so `has_sufficient_evidence` is nearly unfalsifiable |
| RAG-3 | S1 | **FIXED** | `drug_filter` fails open: an unknown drug silently searches the whole corpus |
| RAG-4 | S2 | **FIXED** | Adherence retrieval cites a topic the corpus does not contain, on a query that is 80% out-of-vocabulary |
| RAG-5 | S3 | **FIXED** | `HybridEvidenceRetriever` / `semantic_score` / `compute_vector_score` are all purely lexical |
| RAG-6 | S3 | **FIXED** | `EMBEDDING_MODEL` is configured and the model is installed, but no code reads either |
| RAG-7 | S3 | OPEN | The corpus is 10 chunks / 187 tokens — a fixture, not a retrieval corpus |
| LLM-1 | S2 | OPEN | Two divergent implementations of the same prompt-injection defence; neither is wired in |
| LLM-2 | S2 | OPEN | The entire generative layer is dark — models pulled, client tested, nothing calls it |
| LLM-3 | S3 | CLOSED | `app/analysis/prompts.py` deleted; `safety_rules.py` docstrings cleansed |
| AUTH-1 | S2 | OPEN | JWT carries no token_version, so there is no token revocation path |
| DATA-1 | S2 | OPEN | `db.delete(patient)` and raw-SQL patient delete behave differently |
| CFG-1 | S3 | OPEN | No `.env.example`; `SECRET_KEY` is a placeholder |
| CFG-2 | S3 | OPEN | `echo=settings.DEBUG` floods logs with every SQL statement |
| API-1 | S3 | OPEN | Two different `/health` response shapes |
| SEC-1 | S1 | CLOSED | The `sk-proj-…` OpenAI key pasted into chat must be rotated |

---

## Answer to "did you install Qwen 3 or Llama?"

**Yes — and I told you the opposite earlier in this session. That was wrong.** `ollama list` on this machine:

| Model | Size | Pulled |
|---|---|---|
| `qwen3:8b` | 5.2 GB | 2 days ago (2026-08-24) |
| `llama3.2:3b` | 2.0 GB | 6 days ago |
| `phi3:latest` | 2.2 GB | 13 days ago |
| `nomic-embed-text:latest` | 274 MB | 13 days ago |

Ollama itself is installed at `C:\Users\Tariq\AppData\Local\Programs\Ollama\ollama`. `backend/.env` sets `OLLAMA_MODEL="qwen3:8b"`, and `backend/app/llm/client.py` (dated 2026-08-24) is a working async client for it. My earlier claim that no model had been downloaded and no model code existed was based on a stale read of the tree — this is the concurrent-builder situation, where files appear between my reads. I should have re-checked before asserting a negative.

**But "installed" is not "in use", and the distinction matters for your FYP writeup.** No endpoint and no service imports `app.llm` — the only importers are `backend/smoke_llm.py` (a manual smoke script) and `backend/test_llm_prompt.py`. `app/graph/__init__.py` is 0 bytes, so the LangGraph layer does not exist. Qwen 3 is pulled, the transport is written and tested, and the request path never calls it. See **LLM-2**.

---

## FIXED THIS SESSION

### HIST-1 — S1 — Deleting a schedule silently erased the patient's adherence history

**Was:** `medication_events.schedule_id` carried `ON DELETE CASCADE`.

**Reproduced** against a copy of the live `medication.db` before the fix:

- `DELETE FROM medication_schedules WHERE id = 36` → **8 logged doses destroyed**, no error.
- Deleting one `prescribed_medications` row → **14 schedules and 56 events destroyed**, no error.

**Why S1:** adherence is computed *only* from `medication_events` (`expected_doses = total_taken + total_missed + total_skipped`). Nothing else stores it and nothing recomputes it. So a deleted event does not produce a wrong number that looks wrong — it produces a *plausible* number that is a lie, with no trace that anything was removed. A clinician reviewing 100% adherence cannot distinguish "took every dose" from "the missed doses were deleted".

**Fixed:** FK is now `RESTRICT` (migration `c7e4b91a53d8`). One constraint covers the chain, because the CASCADEs above it terminate on it:

```
DELETE a medication_schedule    -> refused
DELETE a prescribed_medication  -> refused (its CASCADE into schedules trips this)
DELETE a prescription           -> refused, transitively
DELETE a patient                -> still permitted
```

The last line is deliberate: events cascade from `patients` on their own FK, so an erasure obligation is not blocked by a foreign key. Every *narrower* delete — where the accidents happen — is refused.

**Tests:** `test_schedule_lifecycle.py` (behavioural, against `create_all`), `test_migrations.py::test_the_migration_makes_event_deletes_restrict` (schema, against a migrated database — SQLite cannot `ALTER` a foreign key, so the migration rebuilds the table, and that rebuild is the step that could silently drop the clause).

### HIST-2 — S2 — `active=True` never expired

**Was:** a course that ended last month kept `active=True` forever, because both consumers (`get_todays_doses`, `create_due_reminders`) re-filter on the course dates at query time. The column disagreed with the schedule's own `end_date`, and the column was the one that looked authoritative.

**Fixed:** `COMPLETED` is derived from `end_date` by `MedicationSchedule.lifecycle_on(local_today)` and is **not storable** — a CHECK constraint restricts the column to `ACTIVE | CANCELLED | SUPERSEDED`. A stored `COMPLETED` would need a job to notice the day a course ends: a job that can fail, be forgotten, or run in the wrong timezone, leaving the column stale in exactly the way `active` already was.

`lifecycle_on` takes the date rather than reading the clock because "today" is the *patient's* today — a zero-argument property would use the server's date and be wrong by up to a day for anyone outside the server's zone, the same bug class `dose_instant_utc` exists to prevent.

### HIST-3 — S2 — `active=False` conflated two clinically opposite facts

**Was:** one boolean covered both "the clinician discontinued this medication, so those doses were not meant to be taken" and "a newer schedule replaced this row, so the doses logged against it were taken correctly". Indistinguishable afterwards. A reviewer looking at a gap in adherence could not tell whether the patient was taken off the drug or the dose time simply moved — and those lead to opposite conclusions.

**Fixed:** `CANCELLED` when `PrescribedMedication.is_active is False`; `SUPERSEDED` for anything else the generation run no longer wants. The migration backfills every retired row to `SUPERSEDED`, not `CANCELLED`, because `SUPERSEDED` asserts only "no longer the current plan" — true of every `active=0` row — whereas `CANCELLED` would assert a clinical decision the old column never recorded.

### HIST-4 — S3 — I had overclaimed what `passive_deletes="all"` protects

Found by a test that failed for the right reason. `passive_deletes="all"` governs parent *deletes* only. It stops SQLAlchemy pre-emptively NULLing children's FKs when the parent is deleted (letting the DB's RESTRICT speak), but it does **not** suppress nulling on collection de-association — so `schedule.events.clear()` raises `NOT NULL constraint failed: medication_events.schedule_id`, not the RESTRICT. Outcome is safe either way (loud error, no data lost), but by a different mechanism than my comment claimed. Comment and test both corrected.

---

## OPEN — RAG layer (work-order item C)

All five RAG findings were reproduced by running the retriever. **Corpus reality:** 10 chunks, 187 distinct tokens, 8 drugs (amoxicillin, clopidogrel, lisinopril, metformin, propranolol, sertraline, sildenafil, warfarin), 3 topics (contraindications, interactions, warnings).

### C.7 probe result: does semantic retrieval exist? **Yes, as of 2026-08-28.**

> **2026-08-30 update:** `app/rag/embeddings.py` (443 lines) implements a real dense arm using `nomic-embed-text` via Ollama's `/api/embed`. It participates in ranking only, never in gating, because its measured sufficiency band is 0.007 wide (unusable as a threshold). The paraphrase limitations below still apply to the *lexical* arm; the dense arm addresses exactly this gap.

Your probe — query `"blood thinner bleeding risk"` against the Warfarin hemorrhage evidence:

```
0.545  lex=1.000 sem=0.089  warfarin  | Section 7: Drug Interactions - NSAIDs and Aspirin
0.431  lex=0.721 sem=0.142  warfarin  | Section 4: Warnings and Precautions - Hemorrhage
0.190  ...                  sertraline
```

It looks like a success and is not one. `blood` and `thinner` are **not in the corpus vocabulary at all**. The only tokens that matched were `bleeding` (df=2) and `risk` (df=5). Retrieval found warfarin because the query happened to share the literal word *bleeding* with the target document; the paraphrase "blood thinner" contributed exactly zero.

The decisive test is the synonym with no shared vocabulary:

```
'blood thinner'             -> NOTHING RETRIEVED
'blood thinner medication'  -> NOTHING RETRIEVED
'stomach sugar pill'        -> NOTHING RETRIEVED       (vs metformin)
'bleeding'                  -> 0.671 warfarin | Warnings and Precautions - Hemorrhage
```

A patient or clinician who says "blood thinner" instead of "warfarin" retrieves nothing. **This is bag-of-words retrieval.** Two documents that share no vocabulary score zero however close in meaning.

Also worth noting from the probe: the **Hemorrhage** section is *not* the top hit for a bleeding-risk query in either the paraphrased or the exact-name version — the NSAIDs/Aspirin interaction section outranks it both times.

The good news: the module docstrings in `app/rag/retriever.py:4-8` and `app/rag/indexer.py:6-10` **already state this honestly** ("Both signals are lexical: there is no embedding model here"). That part of C.8 is done. The identifiers still lie (RAG-5).

### RAG-1 — S2 — **FIXED** — BM25's document term frequency is always 0 or 1

> **Fixed 2026-08-28.** `indexer.py` now stores raw `Counter(tokens)` counts in `self.term_freq[token][chunk_id] = count` (a `Dict[str, Dict[str, int]]`). Query tokens are deduplicated via `_distinct()`. The inverted index scan is replaced with a dictionary lookup.
>
> *Original finding preserved below for historical reference.*

`app/rag/indexer.py:112-114`:

```python
tf_count = sum(1 for cid, _ in self.inverted_index[t] if cid == chunk_id)
```

`_build_index` (lines 74-77) iterates `Counter(tokens).items()`, so it appends **exactly one posting per (token, chunk)**. The counting scan can therefore only ever return 1.

**Measured:** maximum `tf_count` reachable across the entire corpus = **1**.

The correctly-computed normalized frequency stored alongside it on line 77 is discarded by the `_`. For `warfarin`, the stored tf values are `[0.0625, 0.0714]` — real, unused numbers.

**Effect:** BM25's saturation term collapses to the constant `(k1+1) / (1 + k1·(1−b+b·dl/avgdl))`, so `compute_lexical_score` is a length-normalized IDF sum — a coordination match, not BM25. A chunk that mentions "hemorrhage" ten times ranks identically to one that mentions it once.

**And it is inverted from its intent.** Query-side repetition is *not* saturated either:

```
score(['warfarin'])       = 1.4794
score(['warfarin']*3)     = 4.4383      # exactly 3x — linear, no diminishing returns
```

So the implementation ignores the frequency BM25 exists to saturate (document-side) and linearly amplifies the one BM25 either ignores or saturates separately (query-side). This is not academic: `retrieve_for_interaction` builds `query = f"{drug_a} {drug_b} interaction {mechanism} {clinical_effect}"` by concatenating free-text alert fields, so a word repeated in an alert message silently reweights retrieval.

**Fix:** store the *raw* count in the posting (BM25 does its own length normalization via `b`; using the pre-normalized tf would double-count) and look it up rather than counting:

```python
# in _build_index
self.inverted_index[token].append((chunk.chunk_id, count))   # raw, not count/doc_len

# in compute_lexical_score
tf_count = self._tf.get(t, {}).get(chunk_id, 0)
```

Also replace the linear scan with a `Dict[str, Dict[str, int]]` — an O(len(postings)) scan per query term defeats the point of an inverted index. And deduplicate query tokens, or add a proper `k3` query-saturation term.

### RAG-2 — S1 — **FIXED** — `relevance_score` is a per-query rank wearing a confidence's clothes

> **Fixed 2026-08-28.** Scoring is now query-intrinsic: `compute_lexical_coverage` normalises against an ideal score depending only on the query, `compute_tfidf_cosine` is standard cosine. Sufficiency requires four conjunctive gates: whole-query coverage ≥ 0.30, whole-query cosine ≥ 0.16, non-entity coverage ≥ 0.14, non-entity cosine ≥ 0.08. The metformin wrong-topic regression (`"metformin gastrointestinal bleeding interaction"`) scores `ne_coverage=0.000, ne_cosine=0.000` — hard structural zero. Case added to `eval_retrieval.py`.
>
> *Original finding preserved below for historical reference.*

`app/rag/retriever.py:104-116`. `max_lex` is the maximum over the candidate set **for this query**, so the best-matching chunk always receives `norm_lex = 1.0` and therefore `relevance_score ≥ 0.5`, whatever its absolute match quality.

**Measured** top-hit scores:

```
0.586  'interaction'
0.618  'aspirin'
0.642  'renal'
0.671  'bleeding'
0.671  'warfarin'
0.837  'metformin lactic acidosis'
0.528  'clot prevention drug'        <-- see below
0.000  'adherence'   (out of vocabulary)
0.000  'monitoring'  (out of vocabulary)
0.000  'dose'        (out of vocabulary)
```

The distribution is **bimodal, not graded**: ≥ 0.5 whenever any single query token appears anywhere in the corpus, and 0.0 on a total vocabulary miss. There is nothing in between. Against that, the gates are `has_sufficient_evidence` at 0.40 (interaction) and 0.35 (contraindication) — and **no threshold at all** for adherence, which uses `len(evidence) > 0`. So the flag is True for every query with one matching word and False only on a total miss, and `FindingEvidenceBundle.all_findings_supported` aggregates it.

**The worst measured case.** Query `"clot prevention drug"`:

```
0.528  sertraline | Section 7: Drug Interactions - Serotonergic Drugs
0.523  sildenafil | Section 7: Drug Interactions
```

A clot-prevention question returns an **SSRI's** interaction section as top evidence, at a confidence that clears both thresholds. It matched on the generic word `drug` (df=3), because `_build_index` line 67 indexes `chunk.section` into the same field as the body text — so section titles like "Drug Interactions" make `drug` and `interactions` match nearly every label.

**Why S1:** under the Phase 5.5 layout this renders beneath `📄 VERIFIED CLINICAL EVIDENCE`, and `build_prompt` places it in a section literally headed `VERIFIED CLINICAL EVIDENCE [trusted]`. A clinician — and shortly a model — is told this is verified evidence for the finding. The separation you required between deterministic findings and AI-assisted summary is sound, but it does not help if the middle tier confidently cites the wrong drug.

**Fix:** two independent changes.

1. Stop normalizing against the query's own maximum. Threshold on the raw fused score, or normalize against a fixed scale, then calibrate the cut-off on a held-out set of queries with known answers.
2. Independently of scoring: before setting `has_sufficient_evidence`, require the top chunk's `drug_name` to match the finding's drug. That is a cheap, deterministic check that catches every case in RAG-2 and RAG-3 regardless of how the ranking behaves.

### RAG-3 — S1 — **FIXED** — `drug_filter` fails open

> **Fixed 2026-08-28.** Entity boundary is now structural: `_resolve_entity_candidates` returns `None` for unknown drugs, caller returns `[]` immediately. `entity_verified` defaults `False`, set `True` only on successful entity resolution. `citable_evidence` and `build_prompt` both filter on `entity_verified`. Unfiltered fallback is informational only and cannot satisfy `has_sufficient_evidence`.
>
> *Original finding preserved below for historical reference.*

`app/rag/retriever.py:92-94`:

```python
if d_lower in self.index.by_drug:
    candidates = self.index.by_drug[d_lower]
```

When the requested drug is **not** in the corpus, the filter is silently dropped and the search runs over everything.

**Measured:**

```
search("bleeding risk", drug_filter="ibuprofen")  ->  ['warfarin', 'warfarin']
'ibuprofen' in by_drug: False
```

The corpus covers 8 drugs. Every other medication a patient is actually prescribed takes this path. Combined with RAG-2, a contraindication finding about ibuprofen receives **warfarin** evidence at ≥ 0.5 confidence with `has_sufficient_evidence = True`.

The module docstring claims this layer *"ensur[es] strict citation provenance and irrelevance rejection"*. On this path it does the opposite of both.

Note that the fallback chains in `retrieve_for_interaction` (lines 145-149) and `retrieve_for_contraindication` (168-172) drop the filter *deliberately* as a third attempt. That is a defensible design choice on its own — but it must not be allowed to set a "sufficient evidence" flag, and right now it does.

**Fix:** when the requested drug is absent from the index, return `[]`. "No evidence for this drug in the corpus" is the truthful answer and is exactly what a reviewer needs to see. Keep the unfiltered fallback if you want it, but mark its results as unattributed and never let them satisfy `has_sufficient_evidence`.

### RAG-4 — S2 — **FIXED** — Adherence retrieval cites a topic that does not exist

> **Fixed 2026-08-28.** `retrieve_for_adherence_risk` now reports `topic="warnings"` (what the corpus actually contains), applies the same four-conjunct sufficiency gate, and does not fall back to unfiltered search.
>
> *Original finding preserved below for historical reference.*

`retrieve_for_adherence_risk` returns `EvidenceResult(topic="adherence_guidelines", ...)`. The corpus contains three topics: `contraindications`, `interactions`, `warnings`. There is no adherence-guideline document.

Worse, of the query it constructs — `f"{critical_str} adherence monitoring missed doses clinical risk"` — these tokens are **out of vocabulary**: `adherence`, `monitoring`, `missed`, `dose`, `clinical`. Only `doses` (df=1) and `risk` (df=5) exist. So the query effectively reduces to the drug name plus "risk", and the result is drug-label text labelled as adherence guidance, with `has_sufficient = len(evidence) > 0` — no threshold at all.

**Fix:** either add real adherence-guideline documents to the corpus, or have this path return no evidence and say so plainly. The second is honest and takes ten minutes; the first is the better FYP contribution.

### RAG-5 — S3 — **FIXED** — The names assert semantics the code does not have

> **Fixed 2026-08-28.** `tfidf_cosine_score` is now the lexical cosine field. `semantic_score` holds actual dense similarity from `nomic-embed-text` (or `None` when unavailable). `HybridEvidenceRetriever` is now an accurate name — it genuinely does hybrid retrieval.
>
> *Original finding preserved below for historical reference.*

`HybridEvidenceRetriever`, `RetrievedEvidenceChunk.semantic_score`, `ClinicalCorpusIndex.compute_vector_score` — all lexical. `semantic_score` is TF-IDF cosine over sparse bag-of-words vectors.

The docstrings have already been corrected to say so, which is genuinely better than most code in this state. But a reader trusts identifiers over prose, and `semantic_score` appears in every scored result. Rename to `tfidf_cosine_score` and `LexicalEvidenceRetriever` — or install the embedding path and earn the name (see RAG-6; the model is already on disk).

This is the item you flagged as not cosmetic: *"Do not leave the architecture documentation claiming hybrid semantic RAG if the code is actually bag-of-words retrieval… It changes what your FYP actually is."* The docstrings comply. The public API does not.

### RAG-6 — S3 — **FIXED** — `EMBEDDING_MODEL` is dangling, but not for the reason I said earlier

> **Fixed 2026-08-28.** `app/rag/embeddings.py` (443 lines) implements `OllamaEmbedder` calling `/api/embed`, `SemanticIndex` with lazy embedding, L2 normalisation, query caching, retry/cooldown, and a test double. `get_default_retriever()` wires it into production.
>
> *Original finding preserved below for historical reference.*

`backend/.env:18` and `app/core/config.py:26` set `EMBEDDING_MODEL = "nomic-embed-text"`. I previously told you this pointed at a model that was never installed. **It is installed** — `nomic-embed-text:latest`, 274 MB, pulled 13 days ago.

The real finding is narrower and more interesting: the embedding model is sitting on disk, unused, while the retriever does bag-of-words. No code reads `EMBEDDING_MODEL`, and no code calls Ollama's `/api/embeddings`.

**Fix — pick one, and say which in the writeup:** delete the setting, or spend the afternoon adding a real dense-retrieval arm. With a 10-chunk corpus, embedding all of it takes seconds, and `"blood thinner"` would then actually retrieve warfarin. That single change converts RAG-5 from a naming lie into an accurate description, and it is the smallest available upgrade to what the FYP demonstrates.

### RAG-7 — S3 — The corpus is a fixture, not a corpus

10 chunks, 187 distinct tokens, 8 drugs. "Top 3 of 10" is a third of the corpus. Every ranking observation in this report — including the ones I am confident about — is measured on an index small enough that ranking barely matters. Report it as a demonstration fixture; do not present retrieval metrics computed on it as evaluation results.

---

## OPEN — Ranking Quality

Deliberately separated from the safety gates above. The findings in this section are about *which* correct-drug chunk ranks first, not about whether a wrong-drug chunk can get through. They degrade citation precision, not safety, and they are tracked apart because they must not be folded into a threshold-calibration pass.

> **Any change in this section invalidates the threshold calibration in `eval_retrieval.py` and requires re-running it.** The floors in `app/rag/retriever.py` are derived from the scores of the chunk that currently ranks first. Change the ranking function and the must-pass minima move, so the floors must be re-derived from the new distribution before they can be trusted again. Do not tune thresholds and ranking in the same pass.

### RAG-8 — S2 — Wrong-but-adjacent chunk outranks the correct one

For the production warfarin/ibuprofen interaction query — `"Warfarin Ibuprofen interaction Displaced protein binding Major bleeding risk"` — the retriever returns:

```
rank 1  CHK-WAR-002  Section 4: Warnings and Precautions - Hemorrhage
        cov 0.388  cos 0.254  ne_cov 0.285  ne_cos 0.166
rank 2  CHK-WAR-001  Section 7: Drug Interactions - NSAIDs and Aspirin
        cov 0.377  cos 0.195  ne_cov 0.278  ne_cos 0.120
```

`CHK-WAR-001` is the correct chunk: the query names ibuprofen and protein-binding displacement, and that is literally the NSAID drug-interaction section. It loses by 0.011 coverage. Both chunks are about warfarin, so the entity boundary is doing its job and no safety gate is bypassed — but a clinician reading the citation is pointed at the general bleeding warning rather than the specific interaction that was flagged.

Two consequences worth recording:

1. **Citation precision.** This must be fixed before Phase 3 puts citations into patient-facing output. A citation that is adjacent-but-wrong is harder to catch on review than one that is obviously wrong.
2. **It biased the calibration.** Because the harness measures rank-1 scores, the non-entity floor was derived from `CHK-WAR-002`'s `ne_cos` of 0.166 — while the *correct* chunk scores 0.120. Any floor at or above 0.14 would reject the correct chunk the moment ranking is fixed. This is why `NON_ENTITY_MIN_COSINE` is set at 0.08 rather than nearer the measured must-pass edge, and it is the concrete argument for the band-midpoint choice documented in `retriever.py`.

**Not diagnosed yet.** Note that both ranking components agree on the wrong answer — `CHK-WAR-002` wins on coverage (0.388 vs 0.377) *and* on cosine (0.254 vs 0.195) — so the 0.5/0.5 blend is not the cause and reweighting it will not help. That points at the scoring function itself rather than the combination: most likely `b=0.75` length normalisation favouring the shorter Warnings chunk, or document-side term-frequency saturation flattening the interactions chunk's repeated mentions of the very terms that should make it win. Diagnose before changing anything.

**Scheduled:** start of Phase 2, or a dedicated pass before Phase 3. Not in Phase 1.

---

## OPEN — generative layer (`app/llm/`, `app/analysis/`)

The code here is well-built, well-commented and well-tested (`test_llm_prompt.py`: 37 passed). `app/llm/prompt.py` implements the trust-tiered structure you specified, in the exact order you specified, and goes further than the spec in two ways worth acknowledging: it strips zero-width and bidi characters before matching (so `SYS<ZWSP>TEM INSTRUCTIONS` cannot slip past the forgery regex while still reading as a header to the model), and it restates the untrusted-section reminder *after* the patient block, which is the cheapest available mitigation for an instruction placed at the end of a note. `client.py` handles qwen3's `<think>` blocks twice — once via the API flag, once via regex — on the correct reasoning that a model swap could otherwise put unreviewed chain-of-thought into a clinician-facing field silently.

The findings below are about wiring and duplication, not about the quality of what was written.

### LLM-1 — S2 — Two divergent implementations of the same injection defence, neither wired in

| | `app/llm/prompt.py` | `app/analysis/prompts.py` |
|---|---|---|
| Entry point | `build_prompt` | `build_clinician_brief_prompt` |
| Neutraliser | `_neutralise` (line-oriented, regex forgery match, invisible-char strip) | `sanitize_untrusted` / `render_untrusted_block` |
| Untrusted format | neutralised prose, last section | JSON array of strings, fenced |
| Called by | `smoke_llm.py`, `test_llm_prompt.py` | nothing |

`app/analysis` does not import `app/llm` at all. Two independent defences against the same attack will drift, and when one gets wired up the other becomes a decoy that a future reviewer may mistake for the live path. The JSON-array approach in `analysis/prompts.py` is arguably the stronger primitive (structured data cannot be mistaken for prose); `llm/prompt.py` has the better neutraliser (invisible-character handling). **Pick one, port the other's strengths into it, delete the loser.** This is a safety-critical contract; having two of it is worse than having one imperfect one.

### LLM-2 — S2 — The generative layer is dark

`app/llm/client.py`, `app/llm/prompt.py`, `app/analysis/prompts.py`, `app/analysis/response_validator.py`, `app/analysis/action_validator.py` all exist and are tested. **No endpoint or service imports any of them.** `app/graph/__init__.py` is 0 bytes.

This is not a defect — it is your build order working as designed, and the sequencing you insisted on (*"The eventual multi-agent layer should sit on top of working medication data and workflows, not replace them"*) is why the data layer is in good enough shape to have found HIST-1. It is in this report for one reason: **it must not be described as working in the FYP writeup.** "Qwen 3 8B installed and a tested Ollama transport exists" is true and creditable. "The system generates AI-assisted clinical summaries" is not true yet.

The remaining gap before wiring is real, and RAG-2/RAG-3 are on its critical path: `build_prompt`'s `clinical_evidence` parameter is fed from the retriever and lands in a section headed `VERIFIED CLINICAL EVIDENCE [trusted]`. Wiring the model before fixing RAG-3 means a model is handed wrong-drug evidence with a trust label on it. **Fix RAG-2 and RAG-3 before connecting Qwen 3.**

### LLM-3 — S3 — Stale docstring asserting a falsehood

`app/analysis/prompts.py` opens with:

> NOTHING IN THE RUNNING SYSTEM CALLS THIS MODULE YET. There is no model in this codebase.

The first sentence is still true. The second is not — `app/llm/client.py` and a pulled `qwen3:8b` both exist. This is the same class of problem as RAG-5: documentation that was accurate when written and now misleads. Same fix for the LLM comments at `app/rules/safety_rules.py:6,73`.

---

## OPEN — previously reported, still open

### AUTH-1 — S2 — No token revocation path

The JWT originally carried no `ver` (token_version) claim, so there was no way to invalidate a specific issued token. A stolen token was valid until expiry and nothing could kill it — not a password change, not an admin action. Adding a `token_version` column to the `User` model, embedding it in the JWT as the `ver` claim, and enforcing it in the `get_current_user` dependency is the correct fix. This allows `/logout-all` to bump the version, instantly invalidating all previously issued tokens for that user.

### DATA-1 — S2 — Two behaviours for one intent on patient deletion

`Patient`'s eight relationships declare no ORM cascade, so `db.delete(patient)` raises `IntegrityError`, while the equivalent raw SQL cascades cleanly (each child FK carries `ON DELETE CASCADE`). One intent, two outcomes, depending on which layer you go through.

Latent today — no patient-deletion path exists — and deliberately not fixed inside the schedule-lifecycle work, because inventing a deletion path was outside that scope. It becomes urgent the moment a data-protection erasure request needs handling. Decide it then, deliberately, and note that HIST-1's `RESTRICT` was specifically designed *not* to block this path.

### CFG-1 — S3 — Deployment configuration

No `.env.example`, so a new checkout has no documented list of required settings. `SECRET_KEY="change-this..."` is fine for local development and must be replaced with a proper random secret before deployment — as you said. A committed `.env.example` with every key present and every value blank is the fix for both halves.

### CFG-2 — S3 — SQL log noise

`echo=settings.DEBUG` in `app/database.py` emits every statement. Fine locally, unusable in any shared environment, and a plausible route to logging patient data. Gate it on its own setting.

### API-1 — S3 — Two `/health` shapes

Two health endpoints return differently-shaped JSON. Any monitor that parses one breaks on the other. Pick one shape.

### SEC-1 — S1 — Requires action from you, not a code change

The `sk-proj-…` OpenAI key you pasted into chat earlier must be treated as **compromised by disclosure** and rotated at the provider. It was never used, never echoed into a file, and is not stored anywhere in this repository — I checked. Rotate it anyway: a key that has appeared in a chat transcript should be assumed public. Note that you do not need it — this project runs local inference through Ollama with no vendor account.

---

## Recommended order

1. **RAG-3** then **RAG-2** — highest severity, and both are on the critical path to wiring Qwen 3. RAG-3 is a five-line change; the drug-name check in RAG-2 is another five and catches most of what the scoring rework would.
2. **RAG-1** — correctness of the retrieval you already claim to have.
3. **RAG-6 decision** — delete `EMBEDDING_MODEL`, or use the model that is already on disk. This one decides what your FYP says it is.
4. **RAG-5 / LLM-3 / RAG-4** rename and documentation pass, once 1-3 have settled what the code actually does.
5. **LLM-1** — collapse the two prompt builders into one before either is wired in.
6. Then Phase 5.5.

`AUTH-1` and `DATA-1` are real but not blockers for Phase 5.5. `CFG-1` is a five-minute job worth doing before anyone else clones the repo.
