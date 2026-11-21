# ADR-0006: Standard di Conversione Lossless `PDF → Markdown` (`resuscipack-md v1`) & Cascata Ibrida Baidu + Quality Gate + Structured Vision

- **Stato:** Accettato (`Accepted`)
- **Priorità:** P0 — Critica (Fedeltà delle Fonti & Eliminazione Danno 2-up)
- **Data:** 2026-11-21
- **Autori:** Daniele Bertuccio, `Noobucodonosor` (Orchestrator)
- **Fonti:** Audit 2-up su `67` `canonical_book` (`11.247` blocchi mescolati), analisi requisiti lossless `PDF → Markdown` (`resuscipack-md v1`), `resuscipack/corpus/ocr_ingest.py`.

---

## 1. Contesto e Problema

Il passaggio `PDF → Markdown` è il collo di bottiglia a monte dell'intera infrastruttura epistemica:
1. I `11.247` blocchi provenienti da `pdftotext` su PDF 2-up / doppia colonna mescolano pagina sinistra e destra (Geymonat `book_pk=992`, Oppenheim & Schafer, Horowitz & Hill, Franciosi & De Giovanni, Casalegno & Mariani, Keyser).
2. Un Markdown piatto perde elementi essenziali per lo studio e la citazione:
   - numerazione stampata romana/araba e titoli correnti separati dal corpo;
   - micro-tipografia (apici/pedici matematici vs richiami di nota, chimica, greco antico politono, corsivi/grassetti semantici);
   - formule inline/display con numero di equazione (`\tag{...}`), blocchi formali (`Definizione`, `Teorema`, `Dimostrazione`), listati di codice;
   - note a piè di pagina ancorate (`[^pN-k]`), endnotes, glosse marginali, apparati critici, rimandi incrociati;
   - immagini/tavole/circuiti lossless con didascalie e **testo interno ricercabile** (`internal_labels`), tabelle complesse, box/riquadri;
   - bibliografie ragionate, riferimenti ad altri testi, glossari, indici e coppie esercizio/soluzione.

---

## 2. Decisione Architetturale: Cascata Ibrida a 4 Stadi (`resuscipack-md v1`)

Nessun singolo motore soddisfa da solo tutti i requisiti a costo sostenibile. Adottiamo una cascata a 4 stadi (`TemporaryDirectory` obbligatorio, sorgenti `STRICT READ-ONLY`, aggiornamento su `pack_corpus.db` solo tramite `supersede_block()`):

1. **Stadio 0 — Router Deterministico & Split Verticale 2-up (€0):**
   `classify_pdf_page(doc_path, page_num)` ispeziona dimensioni (`pdfinfo`), densità testuale (`pdftotext`) e immagini incorporate (`pdfimages -list`) classificando ogni pagina in `native_1col`, `native_2col`, `scanned_2up` o `scanned_1col`. Le pagine `scanned_2up` (`width > height * 1.15`) vengono prima divise verticalmente in `L` e `R`.
2. **Stadio 1 — Estrazione Strutturale di Massa & Ritaglio Figure (€0):**
   Baidu `PaddleOCR` / `PP-StructureV3` / `PaddleOCR-VL` (in locale/Colab GPU) esegue il lavoro di massa su layout multi-colonna, tabelle e ritaglio lossless delle tavole (`corpus_figures/`), affiancato da `extract_2up_pdf_text_columns()` per i PDF digitali nativi puliti.
3. **Stadio 2 — Quality Gate Deterministico (€0):**
   `evaluate_page_quality_gate()` controlla ogni Markdown prodotto prima dell'ingestione:
   - non-vuoto e densità coerente;
   - bilanciamento `$$...$$`;
   - corrispondenza biunivoca tra richiami `[^pN-k]` nel corpo e definizioni `[^pN-k]:` in calce;
   - assenza di caratteri corrotti (`\ufffd`, control char);
   - euristica anti-mescolamento 2-up e presenza di didascalie per tutte le figure attese.
   Le pagine che superano il Gate sono accettate (`route="accept"`); le altre passano allo Stadio 3 (`route="escalate_vision"`).
4. **Stadio 3 — Structured Vision LLM Chirurgico (`RESUSCIPACK_MD_PAGE_SCHEMA`):**
   Solo sulle pagine escalate (o volumi con apparato critico/glosse/circuiti densi), `transcribe_page_structured_vision()` richiede un JSON strutturato (`printed_page`, `running_header`, `section_title`, `block_role`, `body_markdown`, `footnotes[]`, `marginalia[]`, `boxes[]`, `figures[]` con `caption` e `internal_labels`, `tables_html[]`, `continues_on_next_page`), poi assemblato deterministicamente da `assemble_canonical_markdown()`.

---

## 3. Conseguenze

- **Positive:** sfrutta a costo zero i ritagli figure e il bulk OCR di Baidu, mentre garantisce fedeltà filologica su note, glosse, greco, formule ed etichette interne alle figure grazie al Quality Gate + Vision selettivo.
- **Vincoli:** le vecchie cartelle sorgenti (`~/from_baidu`, `~/Desktop/PACK copy 4/source_pdf`) restano `STRICT READ-ONLY`. Nessun fallback mock quando le credenziali Vertex mancano.

---

## 4. Task Operativi Collegati

- [x] **TASK-PDFMD-01**: Schema `resuscipack-md v1`, router di pagina, assembler canonico, Quality Gate e client Structured Vision (`resuscipack/corpus/pdf_md_pipeline.py`) — **P0**
- [x] **TASK-PDFMD-02**: Pilota comparativo reale su 3 pagine difficili (Geymonat 2-up, Horowitz & Hill 2-col circuiti/formule, Cavalieri Classici UTET) — **P1**
- [ ] **TASK-PDFMD-03**: Classificazione e bonifica selettiva dei `67` `canonical_book` a 2 colonne/2-up tramite cascata Baidu + Gate + Vision (`supersede_block()`) — **P1**
