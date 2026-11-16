# ADR-0002: Schema Polimorfico `BlockExtraction v2.1`, Ponte Simmetrico "Il Libro Sbagliato" e Validazione a 6 Gate

- **Stato:** Accettato (`Accepted`)
- **Priorità:** P0 — Critica
- **Data:** 2026-11-16
- **Autori:** `@wrongbook`, `@scale`, `@secai`, `@critic` (`Noobucodonosor`)
- **Fonti:** Studio Archeologico Forense `PACK` (`PACK_scopi_esaustivi.md`, `CHAIN_DISCOVERY_SPEC.md`, `graph_navigator.py`, `SPEC.md`, `Wiki/Corpus Epistemico.md`, `_analisi_claude/MANIFESTO.md`), Audit empirico su `biblioteca_fts5.db` (`rowid=32427` Marconi, `rowid=3486–3487` Galvani, `rowid=52642` Cartesio, `rowid=32541` Prodi).

---

## 1. Contesto e Problema

L'obiettivo fondativo di `PACK` / `resuscipack` è digerire l'intero corpus (~1.365 volumi autentici) come un **unico libro distribuito** composto da unità epistemiche indirizzabili, capace sia di estrarre definizioni, teoremi e controversie dai trattati STEM/filosofici, sia di scoprire **"Il Libro Sbagliato"** (pista *"Marconi a Santa Margherita"*): un episodio, esperimento o pratica artigianale contenuto in un libro distante per disciplina dichiarata che illumina fisicamente e operativamente un concetto matematico o informatico (sciogliendo l'*"effetto Sudoku"*).

I cinque tentativi storici precedenti hanno fallito su questa pista per cause tecniche misurate:
1. **Lexical Lock-in & Rumore Grafo v5 (`PACK copy 5`):** `find_unexpected_sources()` cercava la parola esatta del concetto; sui passaggi reali (es. Marconi tra due boe a 50 m con oblò accecati, Galvani e la catena umana con Rialpo, Cartesio sulle ricamatrici e la scrittura velata) la sovrapposizione lessicale coi termini del programma SecAI/OFA è **0%**, mentre il grafo a 136k nodi premiava spazzatura OCR (`N3 = 0.807`) ed elenchi cronologici (`N1 = 0.877`).
2. **Cecità da Troncamento (`PACK copy 4`):** `MiniLM-L12-v2` a 128 token tagliava il 93,1% dei blocchi, amputando la seconda metà dei passaggi dove risiede il meccanismo operativo.
3. **Falsi Positivi Regex (`epistemic_graph.py`):** `infer_lenses()` classificava Cartesio (`Regola X`) sotto `fisica` perché la parola *"profonda"* contiene *"onda"*, e Galvani sotto `biologia` perché *"una specie di catena"* contiene *"specie"*.
4. **Collasso in Template e Mock (`giustificazioni/` e `deep_delve.sqlite3`):** obbligare l'LLM a compilare tutte le lenti anche su indici analitici o blocchi astratti ha generato 83.000 stringhe template ripetitive e 2.335 risposte deterministiche finte.

---

## 2. Decisione Architetturale

Adottiamo un'architettura epistemica a **zero mock, zero leakage e diritto al silenzio**, articolata in quattro componenti dentro `resuscipack/epistemic/`:

1. **Schema Polimorfico Compatto `BlockExtraction v2.1` (`schema_v21.py`):**
   - Opera a livello di `block_pk` / `block_uid` immutabile (nessuna ripetizione di metadati bibliografici nell'output LLM; media ponderata **~335 token BPE/blocco** = ~34,3M token output sul 100% del corpus).
   - **Diritto al Silenzio (`yield="low_or_paratext"` e `sig=null`):** i blocchi paratestuali producono `units=[]`; i trattati matematici/informatici puri (~65% dei blocchi, es. Prodi, Apostol, Tanenbaum) estraggono `units[]` rigorosi (`def`, `thm`, `proof_idea`, `proc`, `dispute` con campo `vs` per *Con chi in disaccordo*) e pongono obbligatoriamente **`sig: null`**, evitando analogie forzate.
   - **Controllo Anti-Deissi e Verbatim:** ogni `unit.stmt` è autocontenuta (vietati riferimenti opachi come *"il Nostro"*, *"ivi"*, *"ibidem"*); ogni `unit.quote` è verificata deterministicamente su `blocks.norm_content`.
   - **Gate Anti-Template di Batch:** rifiuta lotti in cui le firme `sig.mech` presentano prefissi stereotipati ripetuti o entropia lessicale collassata.

2. **Ponte Simmetrico a 3 Stadi senza Leakage (`op_tags.py` & `bridge.py`):**
   - **Stadio Lato Libro (Bottom-Up, cieco al curriculum):** quando un blocco contiene un fenomeno o meccanismo operativo (~35% dei blocchi), `sig` assegna `1..3` tag dal vocabolario chiuso di **24 `OpTag` universali** (`BOUNDED_TOLERANCE`, `SIGNED_DEVIATION_FEEDBACK`, `LATENT_STATE_SENSING`, `SERIES_CONJUNCTION_GATE`, `CONSTRAINED_SEARCH_DECODING`, ecc.) e impone il **`domain_stripping`** su `sig.mech` (divieto di usare sostantivi dell'oggetto di superficie come *nave, panfilo, boe, rana, ricamatrice*).
   - **Stadio Lato Nodo (`GeneratorArchetype`):** ogni nodo didattico dichiara `canonical_domains` da escludere (`surface_domain NOT IN canonical_domains`), `target_op_tags` e la descrizione pre-formale del fenomeno generatore.
   - **Stadio di Validazione (`curiosity_bridges`):** un ponte entra in `curiosity_bridges` solo se supera l'invariante non-decorativo: **mappatura esplicita 1-a-1 di almeno 2 grandezze** (`oggetto fisico ↔ oggetto formale`) e **catena inferenziale $\ge 3$ passi**.

3. **Validatore Deterministico a 6 Gate per le Schede Studio (`verifica_citazioni.py`):**
   Ogni scheda in `data/cards/<node_id>.md` deve superare 6 controlli automatici contro `data/pack_corpus.db` aperto in `mode=ro`:
   - *Gate 1:* `block_pk` e `block_uid` esistenti e attivi (`is_active=1`);
   - *Gate 2:* citazione verbatim tra `4` e `25` parole presente in `norm_content`;
   - *Gate 3:* corrispondenza biunivoca esatta tra rimandi `[^n]` nel testo e note `[^n]:` (zero orfani);
   - *Gate 4:* 100% delle voci in `## Enunciati` etichettate `[Definizione|Assioma|Teorema|Convenzione]` con `*Giustificazione:*` non vuota;
   - *Gate 5:* zero deissi editoriali pendenti o rinvii ciechi (`ivi`, `ibidem`, `op. cit.`, `il Nostro`);
   - *Gate 6:* per ogni sezione/blocco *Libro Sbagliato*, presenza obbligatoria di mappatura 1-a-1 ($\ge 2$ corrispondenze) e catena inferenziale $\ge 3$ passi ancorata a `[^n]`.

4. **CLI Batch Idempotente Fail-Honest (`batch_cli.py`):**
   - Processa a ondate (`Wave 1..4`) solo i `block_pk` attivi con `block_role='body'` non ancora estratti; legge `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` solo da variabili d'ambiente e fallisce esplicitamente in assenza di credenziali (mai fallback deterministici finti).

---

## 3. Conseguenze

- **Positive:**
  - Aggancio riproducibile di passaggi a **0% di overlap lessicale** (verificato su Marconi a Santa Margherita, Galvani & Rialpo, Cartesio Regola X) senza inquinare i manuali formali.
  - Riduzione del 65% dei token di output JSON rispetto a schemi verbosi (~335 tok/blocco), mantenendo il 100% del corpus sotto €20–€48 una tantum.
  - Impossibilità strutturale di reintrodurre citazioni inventate, link rotti o template ripetitivi.
- **Trade-off / Vincoli:**
  - Richiede che ogni scheda `.md` rispetti rigorosamente il contratto dei pedici `[^n]: [block_pk=... | block_uid=...] «...»` e la grammatica di `## Enunciati`.

---

## 4. Task Operativi Collegati (con Definition of Done)

- [x] **TASK-EPIST-01**: **Vocabolario Chiuso `OpTag` e Validatore `BlockExtraction v2.1`**
  - *File coinvolti*: `resuscipack/epistemic/op_tags.py`, `resuscipack/epistemic/schema_v21.py`
  - *Acceptance Criteria*: Enum di 24 `OpTag`, validazione `units[]` + `sig` opzionale (`sig=null` ammesso per manuali STEM), check anti-deissi, `domain_stripping` contro sostantivi di superficie, gate anti-template di batch e persistenza SQLite idempotente.
  - *Verification Step*: `.venv/bin/pytest tests/test_epistemic_v21.py -k "schema or op_tags"`
- [x] **TASK-EPIST-02**: **Validatore Deterministico v3 a 6 Gate (`verifica_citazioni.py`)**
  - *File coinvolti*: `resuscipack/epistemic/verifica_citazioni.py`
  - *Acceptance Criteria*: Verifica in `mode=ro` su `pack_corpus.db` di tutti i 6 Gate (identità `block_pk`/`block_uid`, span verbatim 4–25 parole, zero note orfane, enunciati etichettati e giustificati, zero deissi pendenti, rigore sezione Libro Sbagliato $\ge 3$ passi + mappatura 1-a-1).
  - *Verification Step*: `.venv/bin/pytest tests/test_epistemic_v21.py -k "verifica_citazioni"`
- [x] **TASK-EPIST-03**: **Motore "Il Libro Sbagliato", Seed dei 3 Ponti Reali e Batch CLI Wave 1–4**
  - *File coinvolti*: `resuscipack/epistemic/bridge.py`, `resuscipack/epistemic/batch_cli.py`, `tests/test_epistemic_v21.py`
  - *Acceptance Criteria*: Query di inversione disciplinare funzionante, seed verificato sul corpus reale per Marconi (Santa Margherita), Galvani (Rialpo/stanza chiusa) e Cartesio (Regola X), CLI batch idempotente che legge chiavi solo da env e rifiuta mock.
  - *Verification Step*: `.venv/bin/pytest tests/test_epistemic_v21.py -v`
