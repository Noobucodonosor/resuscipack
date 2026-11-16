# ADR-0001: Schema Immutabile Content-Addressed del Corpus (`pack_corpus.db`) e Pipeline Wave 0–4

- **Stato:** Accettato (`Accepted`)
- **Priorità:** P0 — Critica (Baseline Dati)
- **Data:** 2026-11-16
- **Autori:** Team `resuscipack` (`@scale`, `@wrongbook`, `@secai`, `@critic`)
- **Fonti:** Audit forense su `biblioteca_fts5.db` (1.373 libri, 103.762 passaggi, 311,2 MB testo), `pack-next/state/library.sqlite3` (1.284 PDF, 115.420 pag.), `pc4/ocr_priority_manifest.json`, `PACK copy 4/source_pdf/` (1.328 file) e `PACK_EVOLUTION_AND_FEASIBILITY_SYNTHESIS.md`.

---

## 1. Contesto e Problema

Le iterazioni storiche di PACK hanno sofferto di quattro patologie strutturali sul livello dati:
1. **Mutabilità distruttiva dei `rowid` (`build_fts5_index.py`):** ogni rigenerazione cancellava il DB SQLite e reinseriva i passaggi in ordine alfabetico dei titoli, facendo slittare tutti i `rowid` interi referenziati dalle schede didattiche.
2. **Quattro "Buchi Neri" fisici nel patrimonio (~1.365 opere reali):**
   - **Buco A:** 4.162 pagine già estratte con Baidu `Unlimited-OCR` su 176 volumi ibridi venivano scartate a favore dei vecchi file sporchi `from_before` per un confronto errato sul conteggio parole dell'intero volume.
   - **Buco B (`Cultura_in_Ita5`):** 2.893 pagine (tra cui *Euclide — Elementi* 1.066p, *Galileo — Opere Vol. 1* 1.010p, *Archimede — Opere* 650p) contenevano solo la stringa watermark `www.scribd.com/Cultura_in_Ita5`, sfuggita al filtro `Cultura_in_Ita` e rimasta a **0 parole** in FTS5 e **0 job** in coda OCR.
   - **Buco C:** 10.209 pagine `ocr_required` in `pc4` (*Apostol Vol. 1–3*, *Newton Principia*, *Maxwell Vol. 1–2*, *Boyle*, *Laplace*, *Volta*, *Amerio*, *Carnap*, *Conte*, *Deitel*) + 3.474 pagine sotto-estratte (`<35 parole/pag.` su 42 PDF come *Spoletini-Mandrioli*).
   - **Buco D:** 32 volumi `.epub` (~245 MB di XHTML nativo) e 7 volumi `.djvu` (~2.650 pag., tra cui *Ben-Ari*, *Berzolari*, *Wittgenstein*, *Collins*) ignorati dall'importatore PDF-only, mentre 52 manuali PC multilingua ASUS (`0402..0C0A`) e 4 duplicati `.split('.')[0]` inquinavano l'indice.
3. **Troncamento silenzioso e colli di bottiglia locali:** `MiniLM-L12-v2` (128 token) tagliava il **93,1%** dei passaggi reali (mediana 354 parole / ~650 token), mentre i modelli LLM locali su MacBook Air M4 16GB richiedevano 70–120 giorni o producevano loop deterministici finti.

---

## 2. Decisione Architetturale

1. **Database Canonico Unico Append-Only (`data/pack_corpus.db`):**
   - Identità immutabile dei blocchi tramite `blocks(block_pk INTEGER PRIMARY KEY AUTOINCREMENT, block_uid TEXT UNIQUE NOT NULL)` con trigger `BEFORE DELETE` che vieta la cancellazione fisica di righe.
   - Indice full-text `passages_fts` dichiarato con `content='blocks', content_rowid='block_pk'` e mantenuto in sincrono automatico da trigger SQL `AFTER INSERT` e `AFTER UPDATE` su `blocks`: `fts_rowid` coincide **sempre** con `block_pk` e non slitta mai tra Wave 0 e Wave 4.
   - Quando un blocco sporco viene sostituito in un'ondata successiva da OCR migliore, il nuovo blocco viene accodato con nuovo `block_pk`, mentre il vecchio viene marcato `is_active = 0, superseded_by_pk = <new_pk>` (uscendo dall'indice FTS5 attivo ma restando risolvibile per tutte le citazioni storiche).
2. **Pipeline Wave 0 Locale a Costo €0 (`resuscipack/corpus/wave0_ingest.py`):**
   - Opera in **STRICT READ-ONLY** sulle cartelle storiche (`/Users/dany/from_baidu`, `/Users/dany/Desktop/PACK copy 4`, `/Users/dany/Documents/ChatGPT/pack-next`, `/Users/dany/Desktop/pc4`).
   - Esegue il **page-level splicing** delle 4.162 pagine Baidu OCR sui 176 volumi ibridi di `from_before`, ingerisce nativamente l'XHTML dei **32 `.epub`**, filtra i manuali ASUS/rumore amministrativo e deduplica i cloni `.split('.')[0]`.
   - Segmenta onestamente il testo senza troncamenti, classificando deterministicamente `block_role` (`'body'`, `'footnote'`, `'paratext'`) per non sprecare chiamate LLM sugli indici analitici nei batch successivi.
   - Migra deterministicamente in `legacy_rowid_map` e `data/legacy_card_migration.json` tutti i vecchi `rowid` usati nelle schede di `/Users/dany/from_baidu/grafo/elementari/` verificando il match normalizzato della citazione verbatim.
3. **Pianificazione Ondate OCR e Batch Cloud (`data/ocr_wave_manifest.json`):**
   - Censisce esattamente le ~19.226 pagine mancanti/sotto-estratte (Buchi B, C e 7 `.djvu`) ripartendole in `wave_1` (Nucleo Aureo + Canonici Matematici/SecAI, 4.549 pag. eseguibili in `<18 GPU-h` su singolo account Kaggle gratuito o Vision Batch) fino a `wave_4` (100% del corpus).

---

## 3. Conseguenze

- **Positive:** stabilità perpetua dei riferimenti `block_pk`/`block_uid` nelle schede `.md`; recupero immediato a costo zero di 4.162 pagine Baidu OCR e 32 libri `.epub` al Giorno 1; predisposizione nativa delle tabelle `epistemic_units`, `structural_signatures` e `curiosity_bridges` per lo schema `BlockExtraction v2.1` (`ADR-0002`) e il Tavolo di Studio SecAI (`ADR-0003`).
- **Trade-off / Vincoli:** il file binario `data/pack_corpus.db` (~550–700 MB) resta escluso da Git in `.gitignore` ed è rigenerabile deterministicamente tramite `wave0_ingest.py`.

---

## 4. Task Operativi Collegati (con Definition of Done)

- [x] **TASK-CORPUS-01**: **Schema SQLite append-only, trigger FTS5 external-content e normalizzatore testo/citazioni**
  - *File coinvolti*: `resuscipack/corpus/schema.py`, `resuscipack/corpus/normalizer.py`, `.gitignore`, `requirements.txt`
  - *Acceptance Criteria*: creazione idempotente delle 7 tabelle canoniche + trigger FTS5; `DELETE` fisico su `blocks` bloccato; disattivazione `is_active=0` rimuove la riga da `passages_fts` senza alterare i `block_pk` successivi.
  - *Verification Step*: `.venv/bin/pytest tests/test_corpus_wave0.py -k schema`
- [x] **TASK-CORPUS-02**: **Ingestione reale Wave 0 (Splicing 4.162 pag. Baidu, 32 EPUB, filtro rumore e migrazione `legacy_rowid_map`)**
  - *File coinvolti*: `resuscipack/corpus/wave0_ingest.py`, `data/pack_corpus.db`, `data/legacy_card_migration.json`
  - *Acceptance Criteria*: zero scritture nelle cartelle storiche; recupero effettivo delle pagine Baidu ibride e dei 32 `.epub`; presenza verificata di Marconi/Masini, Galvani e Cartesio; 100% dei `rowid` delle schede elementari mappati con citazione verbatim verificata.
  - *Verification Step*: `.venv/bin/pytest tests/test_corpus_wave0.py -k wave0`
- [x] **TASK-CORPUS-03**: **Generazione manifesto OCR multi-ondata (`wave_1..wave_4`) per chiusura Buchi B, C e DjVu**
  - *File coinvolti*: `resuscipack/corpus/ocr_manifest.py`, `data/ocr_wave_manifest.json`, `tests/test_corpus_wave0.py`
  - *Acceptance Criteria*: censimento esatto dei volumi `Cultura_in_Ita5` (Euclide, Galileo, Archimede), della coda `ocr_priority_manifest`, dei 42 PDF sotto-estratti e dei 7 `.djvu`, ripartiti in `wave_1..wave_4` con conteggio pagine e ore/token stimati.
  - *Verification Step*: `.venv/bin/pytest tests/test_corpus_wave0.py -k manifest`
