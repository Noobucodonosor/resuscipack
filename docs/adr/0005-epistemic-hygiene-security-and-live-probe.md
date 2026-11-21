# ADR-0005: Hardening P0, Bonifica Epistemica, Grafo delle Fonti & Sonda Viva (`M5`)

- **Stato:** Accettato (`Accepted`)
- **Priorità:** P0 — Critica (Sicurezza, Affidabilità Dati & Prodotto)
- **Data:** 2026-11-21
- **Autori:** Daniele Bertuccio, `Noobucodonosor` (Orchestrator)
- **Fonti:** Audit multifocale del 21 novembre 2026, `summa_problemi_resuscipack.md`, `audit_universale_milestone.md`, `implementation_plan_m5.md`.

---

## 1. Contesto e Problema

L'audit forense post-`M4` su `pack_corpus.db` (`1.424` libri attivi, `124.796` blocchi, `139.458` unità epistemiche) e sul codice di `resuscipack` ha evidenziato due ordini di criticità che impediscono sia il rilascio sicuro sia il raggiungimento della qualità culturale attesa:

1. **Vulnerabilità P0 di sicurezza e portabilità:**
   - `drills_sympy.py` usa `sp.sympify()` direttamente su input utente da `POST /api/drill/submit` (rischio RCE/DoS via `eval()` e espressioni esplosive).
   - `/api/search` restituisce `snippet(passages_fts, 2, '<mark>', '</mark>', ...)` senza HTML-escape; il fallback `el.innerHTML` in `editorial_shared.js` espone a Stored XSS su `35` blocchi del corpus contenenti `<script`/`onerror=`.
   - `6` test in `test_corpus_wave0.py` e `test_workbench_secai.py` falliscono su clone pulito in assenza di `data/pack_corpus.db` (`1,07 GB`).
2. **Gap epistemici e di prodotto (`M1–M4`):**
   - `actors_json` è corrotto al `92,0%` (`128.244` unità) per il bug del prompt sulla chiave `w`.
   - `11.247` blocchi (`9,01%`, `67` `canonical_book`, es. Geymonat `book_pk=992`) provengono da PDF 2-up/2-colonne letti di traverso.
   - `maxItems: 2` sul `98,7%` del corpus e `is_residual_paratext_block()` hanno azzerato `1.481` blocchi ricchi di fonti e bibliografie ragionate.
   - Il Decompressore fallisce su sintagmi con parole-guscio, stemmer cieco (`cardinalità` → *cardinali*), `_ROMAN_CENTURY_RE` (`d.C.`), e la UI `M4` lascia non esposti `corpus_figures` (`1.193` immagini), DAG/Fast-Forward e Sonda di Sintagma.

---

## 2. Decisione Architetturale

1. **Sicurezza & Portabilità P0:**
   - Sostituire `sp.sympify()` in `drills_sympy.py` con parser sicuro (`parse_expr(..., evaluate=False)` + whitelist caratteri/simboli + `global_dict` ristretto + limite nodi/esponenti anti-DoS).
   - Eseguire `html.escape()` lato server su `/api/search` intorno a marcatori sentinella prima di inserire `<mark>`, e costruire i nodi `<mark>` in `atlas.js` senza `innerHTML` non sanitizzato.
   - Separare i test dipendenti dal corpus da `1,07 GB` con marker `@pytest.mark.real_corpus` e fornire fixture SQLite Open-Access in `tmp_path` per l'esecuzione CI portabile.
2. **Bonifica Epistemica €0 (`Blocco A`):**
   - Aggiornare `batch_cli.py` (definizione esplicita `w`, uso rigoroso di `k="thm"`, flag `--deep-blocks`, overlap opzionale di 1 pagina).
   - Correggere i 3 micro-bug deterministici in `decompressor.py` (`_ROMAN_CENTURY_RE`), `spectrum.py` (`is_residual_paratext_block`) e `curriculum_mapper.py`.
   - Eseguire pulizia deterministica idempotente (`hygiene_cleanup.py`) di `actors_json`, `books.author` e titoli troncati su `data/pack_corpus.db` preservando `block_pk`/`block_uid`.
3. **Pilota Geymonat & Grafo delle Fonti (`bibliographic_citations`):**
   - Aggiungere split verticale 2-up in `ocr_ingest.py` (`TemporaryDirectory`, sorgenti `STRICT READ-ONLY`, `supersede_block()` conforme ad `ADR-0001`).
   - Aggiungere la tabella additiva `bibliographic_citations` in `corpus/schema.py` ed estrattore `biblio_extractor.py` senza tetto a 2 elementi.
4. **Sonda Viva & Emersione Funzioni (`units_fts`, `concept_edges`, UI):**
   - Aggiungere gli indici derivati `units_fts` e `concept_edges` e il motore deterministico `phrase_analyzer.py` (`POST /api/probe/selection`) per interrogare il corpus evidenziando sintagmi/frasi in `/libro`.
   - Esporre in UI (secondo `design-taste-frontend` + `modern-web-guidance`) le figure originali (`corpus_figures`), la scheda *Fonti & Bibliografia Ragionata* e l'accesso al percorso diagnostico DAG/Fast-Forward.

---

## 3. Conseguenze

- **Positive:** elimina i rischi RCE/DoS/XSS P0, rende `pytest` eseguibile in CI senza `pack_corpus.db`, risana il 92% di `actors_json` a €0 e trasforma la lettura passiva in interrogazione viva del corpus.
- **Vincoli / Trade-off:** nessuna modifica a `block_pk`, `block_uid` o `blocks.content` esistenti; ogni intervento di ri-estrazione usa `supersede_block()`. I test sul corpus reale restano eseguibili in locale con `pytest -m real_corpus`.

---

## 4. Task Operativi Collegati

- [x] **TASK-SEC-01** (`#15`): Sostituzione `sp.sympify()` con parser AST sicuro e limiti anti-DoS (`drills_sympy.py`) — **P0**
- [x] **TASK-SEC-02** (`#16`): Eliminazione Stored XSS su `/api/search` e fallback `innerHTML` (`app.py`, `atlas.js`, `editorial_shared.js`) — **P0**
- [x] **TASK-QA-01** (`#17`): Portabilità `pytest` con fixture SQLite in `tmp_path` e marker `@pytest.mark.real_corpus` — **P0**
- [x] **TASK-HYG-01** (`#18`): Fix prompt `w`/`thm`/`--deep-blocks`/overlap in `batch_cli.py` e 3 micro-bug (`decompressor.py`, `spectrum.py`, `curriculum_mapper.py`) — **P1**
- [x] **TASK-HYG-02** (`#19`): Script `hygiene_cleanup.py` (`--dry-run` / `--apply`) per bonifica `actors_json` e `books.author` — **P1**
- [ ] **TASK-PILOT-01** (`#20`): Split verticale 2-up in `ocr_ingest.py` per pilota Geymonat (`book_pk=992`) — *infrastruttura completata, ri-estrazione Vision opzionale su conferma utente* — **P1**
- [ ] **TASK-BIBLIO-01** (`#21`): Tabella `bibliographic_citations` (`schema.py`) ed estrattore `biblio_extractor.py` — *schema + selettore €0 pronti, popolamento batch su conferma utente* — **P1**
- [x] **TASK-PROBE-01** (`#22`): Indici `units_fts` + `concept_edges` e motore `phrase_analyzer.py` (`POST /api/probe/selection`) — **P1**
- [x] **TASK-UI-04** (`#23`): Sonda Viva in `/libro`, emersione `corpus_figures`, Fonti e Percorso DAG/Fast-Forward secondo `design-taste-frontend` — **P1**
