# ADR-0003: Spina Dorsale Curricolare a 4 Strati, Fast-Forward `SymPy` e Tavolo di Studio SecAI

- **Stato:** Accettato (`Accepted`)
- **Priorità:** P1 — Alta
- **Data:** 2026-11-16
- **Autori:** Team `resuscipack` (`@secai`, `@critic`)
- **Fonti:** `PACK copy 4/pack/data/secai_ofa_program.csv`, `secai_ofa_gates.csv`, `secai_hero_dossier.json`, `from_baidu/secai_curriculum_dag.json`, `from_baidu/grafo/_percorso-elementari.yaml`, `from_baidu/grafo/elementari/numeri.quantita.md`, Audit Swarm `#6`, `#9`, `#12`, `#13`.

---

## 1. Contesto e Problema

Per preparare lo studente adulto alla laurea triennale **SecAI (L-31 Informatica / Sicurezza e AI, UniMi)** evitando sia il blocco amministrativo dell'**OFA formale di Matematica** (scadenza 12 mesi dall'immatricolazione individuale, che congela il 2° e 3° anno — *Delayed OFA Trap*) sia l'impatto con i **20 Shadow Gates** non dichiarati (es. co-erogazione Q1 `Matematica I + II`, assenza totale a **0 CFU di Probabilità e Statistica** prima di `Machine Learning` in Q3, assenza di C/memoria prima di `Offensive Security`, assenza di Testing/SWE prima di `Progettazione di software sicuro`), i prototipi precedenti erano caduti in due estremi opposti:

1. **Estremo A (`PACK copy 4`):** partenza diretta da livello pre-universitario (`P0.1`), monolite da 2.030 righe e paralisi editoriale (`deep_delve` con 1.264/1.265 documenti bloccati in attesa di approvazione umana).
2. **Estremo B (`from_baidu`):** partenza corretta dalla 1ª elementare con schede *"Decisioni di Progetto"* (stile ADR matematico), ma scollegata dalla *Visione dell'Hero* SecAI e limitata a 1 query FTS5 lessicale per nodo, perdendo completamente i *"Libri Sbagliati"* (es. Marconi a Santa Margherita Ligure, Galvani, Cartesio, Boole) e lasciando irrisolta la verifica delle prove non algebriche e delle lacune librarie moderne.

Serve un'architettura pedagogica e software cristallina che consenta allo studente di iniziare **dal Giorno 1** identificando rapidamente i propri *Nodi Frontiera*, studiando con rigore matematico formale (zero salti impliciti / "effetto sudoku"), aprendo il libro vero su ogni pedice `[^n]` e consolidando la memoria procedurale senza alcuna coda di revisione bloccante.

---

## 2. Decisione Architetturale

1. **DAG Curricolare Unificato Aciclico a 4 Strati (`data/curriculum/secai_unified_dag.json` & `resuscipack/curriculum/dag.py`):**
   - **Strato 0 — Fondamenta ("Decisioni di Progetto" 1ª Elementare $\to$ 3ª Media, 45 nodi in 3 rami):** *Numeri e Operazioni*, *Spazio, Misure e Figure*, *Relazioni, Logica e Dati*. Ogni nodo dichiara la decisione progettuale, le primitive `target_op_tags` (allineate all'Enum a 24 valori di `ADR-0002`), l'archetipo generatore e la catena viva verso i Gate SecAI.
   - **Strato 1 — Bonifica OFA Pre-Immatricolazione (`P0.1–P0.8`, `P1.1–P1.2`, `P6.1`):** 11 unità mirate ad azzerare `G00` (`GATE-OFA-MATH`) prima dell'avvio del Q1. Include la riclassificazione empirica di `P0.8` (coperta dai test ufficiali `Testmatbasesol`, `test 0809..1617` e Hoepli Test `.epub`).
   - **Strato 2 — Ponti Anti-Baratro per i 20 Shadow Gates (`P2.1–P2.3`, `P3.1–P3.3`, `P4.1–P4.2`, `P5.1–P5.3`, `P6.2`):** 12 unità posizionate prima della finestra critica di ciascun esame (in primis le 44h di `P3.1–P3.3` per Algebra Lineare, Probabilità e Statistica prima di `G05 Machine Learning`).
   - **Strato 3 — I 21 Esami e Gate Ufficiali SecAI (`G00–G20`, 180 CFU):** traguardi dell'Hero con prerequisiti reali, finestra temporale e prove diagnostiche.
   - **Protocollo Onesto sulle Lacune Moderne (`data/curriculum/open_access_textbooks.json`):** registro esplicito di 5 testi/paper Open-Access gratuiti (€0: *Pro Git*, *Boneh & Shoup*, *OWASP WSTG + SWE at Google*, *OpenIntro Statistics*, paper fondativi arXiv Transformer/FGSM/Adversarial ML) per colmare senza allucinazioni LLM i temi assenti nel corpus storico (`P1.2`, `P4.1`, `P5.2`, `P5.3`, `P3.3`, `G14`, `G15`).

2. **Motore di Verifica Attiva Multi-Famiglia (`resuscipack/curriculum/drills_sympy.py`):**
   - **Fast-Forward Diagnostico Parametrico (`SymPy`):** permette al Giorno 1 di testare i nodi di `Strato 0` e `Strato 1` senza dover leggere schede su concetti già padroneggiati; valida equivalenza simbolica esatta (`7/20 == 0.35`, polinomi fattorizzati, potenze, radicali, moduli, logica, aritmetica modulare/RSA, complemento a due) e individua automaticamente i **Nodi Frontiera** (primi nodi con errore o prerequisiti appena soddisfatti). Un nodo è promosso per padronanza con $\ge 80\%$ ($\ge 4/5$) confermato; lo stato vive in un DB separato `data/student_state.db` lasciando `data/pack_corpus.db` immutabile.
   - **Verificatore Invarianti Grafici (`verify_graph_invariants`):** per prove grafiche (es. `P0.6` $y=|\log(x-2)|+1$), sblocca l'overlay della curva esatta solo dopo la verifica `SymPy` di 5 invarianti geometrici letti dal disegno su carta (dominio, asintoto, cuspide, punto sonda, monotonia).
   - **Rubrica Booleana di Dimostrazione (`evaluate_proof_rubric`):** per dimostrazioni scritte a libro chiuso (es. $\sqrt{2}\notin\mathbb{Q}$, principio dei cassetti, induzione, hash $\neq$ cifratura), verifica la presenza esplicita dei 4–5 lemmi obbligatori (catturando omissioni tipiche come `MCD(a,b)=1`).

3. **Governance Non-Bloccante delle Schede (`data/cards/*.md`) e Tavolo di Studio a 2 Colonne (`resuscipack/workbench/`):**
   - **3 Stati senza code umane preventive:** `rigettata` (bloccata dai 6 Gate di `verifica_citazioni.py`) $\to$ `validata_auto` (subito studiabile) $\to$ `consolidata` (promossa organicamente quando lo studente chiude gli esercizi del nodo senza segnalare salti logici).
   - **Formato Pedici Immutabili:** `[^n]: [block_pk=12345 | block_uid=blk_...] «citazione esatta 4-25 parole» — Autore, Titolo (p. N)`.
   - **Interfaccia Web Minimalista (`app.py` + KaTeX):**
     - *Barra Superiore Fissa ("Bussola dell'Hero"):* mostra in 1 riga la traiettoria dal nodo corrente ai Gate SecAI e la copertura dei gate.
     - *Colonna Sinistra (60%):* selettore tra *Fast-Forward Diagnostico*, *Scheda Decisione di Progetto v3* (con sezione `## Enunciati` giustificata e box *Dal Libro Sbagliato* da `curiosity_bridges`) e *Prova Hero*.
     - *Colonna Destra (40% — "Lettore del Libro Vero"):* al clic su qualsiasi pedice `[^n]` o ponte *Libro Sbagliato*, chiama `/api/block/<block_pk>`, visualizza l'intero passaggio originale senza troncamenti con la citazione evidenziata, permette di sfogliare `← Precedente | Successivo →` sullo stesso libro e offre ricerca FTS5 diretta su tutta la biblioteca.

---

## 3. Conseguenze

- **Positive:**
  - Valore immediato al Giorno 1 (scansione Fast-Forward dei *Nodi Frontiera* su `Strato 0` e studio rigoroso su schede migrate agli ID immutabili) mentre le Wave 1–4 arricchiscono in background `curiosity_bridges`.
  - Eliminazione strutturale dell'"effetto sudoku" (ogni regola formale ha genesi progettuale, etichetta logica, giustificazione e controesempio *"che cosa si rompe"*) e del blocco editoriale `deep_delve`.
  - Separazione netta tra `pack_corpus.db` (sola lettura per la webapp) e `student_state.db` (scrittura locale dei progressi).
- **Trade-off / Vincoli:**
  - Ogni scheda in `data/cards/` deve rispettare rigorosamente il formato a 6 Gate verificato da `resuscipack/epistemic/verifica_citazioni.py`.

---

## 4. Task Operativi Collegati (con Definition of Done)

- [x] **TASK-SECAI-01**: **Costruzione DAG Unificato a 4 Strati, Registro Open-Access e Migrazione Schede v3**
  - *File coinvolti*: `data/curriculum/secai_unified_dag.json`, `data/curriculum/open_access_textbooks.json`, `resuscipack/curriculum/dag.py`, `resuscipack/curriculum/cards.py`, `data/cards/*.md`
  - *Acceptance Criteria*: DAG aciclico verificato topologicamente (`Strato 0..3`, ~89+ nodi tra fondamenta, 23 unità `P0–P6` e 21 gate `G00–G20`); `numeri.quantita.md` e schede migrate aggiornate a `[block_pk=... | block_uid=...]` con `verifica_citazioni.py` = 0 errori.
  - *Verification Step*: `.venv/bin/pytest tests/test_workbench_secai.py -k "dag or cards"`
- [x] **TASK-SECAI-02**: **Motore Fast-Forward Diagnostico `SymPy`, Verifica Grafici/Dimostrazioni e Stato Studente Separato**
  - *File coinvolti*: `resuscipack/curriculum/drills_sympy.py`, `resuscipack/curriculum/student_state.py`
  - *Acceptance Criteria*: Generazione e correzione simbolica `SymPy` funzionante (accetta forme algebriche equivalenti), calcolo automatico dei *Nodi Frontiera*, verifica 5 invarianti grafici e rubrica dimostrazioni su DB isolato `student_state.db`.
  - *Verification Step*: `.venv/bin/pytest tests/test_workbench_secai.py -k "drills or state"`
- [x] **TASK-SECAI-03**: **Tavolo di Studio Web a 2 Colonne (Flask + KaTeX + Lettore Libro Vero su `/api/block/<block_pk>`)**
  - *File coinvolti*: `resuscipack/workbench/app.py`, `resuscipack/workbench/templates/index.html`, `resuscipack/workbench/static/style.css`, `resuscipack/workbench/static/app.js`, `tests/test_workbench_secai.py`
  - *Acceptance Criteria*: Bussola Hero sempre visibile, clic su pedice `[^n]` e su ponte *Libro Sbagliato* apre il blocco integrale con citazione evidenziata e navigazione adiacente sullo stesso libro, zero `.slice()` di troncamento, suite pytest 100% verde.
  - *Verification Step*: `.venv/bin/pytest tests/test_workbench_secai.py -v`
