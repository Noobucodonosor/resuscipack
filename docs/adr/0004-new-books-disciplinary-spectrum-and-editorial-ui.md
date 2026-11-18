# ADR-0004: "Nuovi Libri" Continui, Spettro Disciplinare Percentuale, Doppio "Libro Sbagliato" & Esperienza Editoriale Anti-Slop

- **Stato:** Accettato (`Accepted`)
- **Priorità:** P0 — Critica
- **Data:** 2026-11-18
- **Autori:** Daniele Bertuccio, `Noobucodonosor` (Orchestrator)
- **Fonti:** Manifesto dell'utente del 18 novembre 2026 (*«nobilitazione dell'ovvio, contezza di tutto contemporaneamente, dare carne alla matematica attraverso i giusti passaggi dei testi, scrivere nuovi libri»*), regole vive di agosto 2026 (*«le macchine da studio non mi piacciono, fai dei documenti normali... argomenti semplici ma spiegati dignitosamente»*), `PACK_scopi_esaustivi.md`, `PACK copy 5/discipline_reconstructor.py`, `resuscipack/corpus/` (`pack_corpus.db`).

---

## 1. Contesto e Problema

Dopo Wave 0 (`1.372` volumi, `107.050` blocchi) e Wave 1 (`3.608` blocchi estratti, `10.380` unità epistemiche, `135` ponti operativi), l'ispezione dal vivo del Tavolo di Studio v1 ha rivelato tre scarti rispetto alla visione reale del progetto:

1. **Il cruscotto da ingegnere invece del libro:** la prima interfaccia web (`index.html`) espone in primo piano codici interni (`P0.5`, `G00`, `Strato 0..3`, `block_pk=28379`, `score 0.96`, `6/6 Gate`) e ingabbia i testi in maschere rigide (`## Contesto`, `## Enunciati`, bollini di stato). Così facendo riproduce la *ricerca della forma* anziché *dare carne alla matematica attraverso i giusti passaggi dei testi* per scrivere veri **nuovi libri**.
2. **Contezza simultanea ancora ferma al ~3,4%:** finora sono stati digeriti `3.608` blocchi su `107.050` (~52 libri su `1.372`), e restano **83 volumi muti (`18.502` pagine)** privi di testo ricercabile (tra cui *Euclide Elementi*, *Galileo Opere Vol. 1*, *Archimede Opere*, *Tom Apostol Vol. 1–3*, *Newton Principia*, *Maxwell* e i 7 `.djvu`). Finché l'intero corpus non è estratto, il sistema non possiede *contezza di tutto contemporaneamente*.
3. **Manca la seconda metà del "Libro Sbagliato" — la Composizione Percentuale e la Ricostruzione Disciplinare dal Basso:** lo schema `BlockExtraction v2.1` intercetta gli isomorfismi meccanici (`BOUNDED_TOLERANCE`, `SERIES_CONJUNCTION_GATE`), ma non calcola ancora di quali discipline tratti ogni libro pagina per pagina. Nella monografia di Masini su *Guglielmo Marconi* (`book_pk=514`, `537` blocchi), già oggi 241 blocchi su 537 (**44,9%** grezzo) attraversano coste, stretti, promontori e rotte oceaniche reali (*Isola di Wight → Cape Lizard in Cornovaglia*, *Terranova*, *Golfo della Spezia*, *Santa Margherita Ligure*). Senza etichettatura multi-disciplinare per blocco, né lo *Spettro Percentuale* del volume né *"La Geografia (o la Musica, la Logica...) secondo i 1.372 libri"* possono emergere automaticamente.

---

## 2. Decisione Architetturale

Evolviamo `resuscipack` lungo **5 pilastri integrati** (completamento del corpus, spettro percentuale, decompressione sinottica, motore di scrittura dei nuovi libri, interfaccia editoriale anti-slop):

### A. Completamento al 100% della Biblioteca (`M1` — Contezza Simultanea)
1. **OCR degli 83 volumi muti (`18.502` pagine):** recupero prioritario di Euclide, Galileo, Archimede, Apostol, Newton, Maxwell, Spoletini-Mandrioli e dei 7 `.djvu` tramite pipeline `pc4`/Colab GPU o Gemini Vision Batch (sui crediti Google Cloud attivi), inserimento append-only in `blocks` senza alterare alcun `block_pk` esistente.
2. **Upgrade `BlockExtraction v2.2` + Recupero scarti OCR:** normalizzazione tollerante sugli errori di spaziatura tipica dei vecchi OCR (`ali' altra` / sillabazioni), correzione automatica dell'inversione `kind`/`mode` (es. `'narrates'`) e recupero dei `1.489` blocchi scartati in Wave 1.
3. **Estrazione Integrale Wave 2 → Wave 4:** esecuzione completa su tutti i `107.050+` blocchi fino al 100% della biblioteca.

### B. Spettro Disciplinare Percentuale & Doppio "Libro Sbagliato" (`M2`)
1. **Etichettatura Multi-Disciplina & Luoghi su ogni Blocco (`BlockExtraction v2.2`):**
   Ogni blocco sostantivo riceve un array controllato `disciplines[]` (es. `fisica`, `telecomunicazioni_elettronica`, `matematica`, `informatica`, `geografia_territorio`, `nautica_mare`, `storia_politica_economica`, `filosofia`, `musica_acustica`, `medicina_biologia`, `arte_architettura`, `diritto_societa`) più `places[]` espliciti (es. `Santa Margherita Ligure`, `Cornovaglia`, `Terranova`).
   **Regola anti-illusione:** è vietato chiedere a un LLM di stimare a occhio le percentuali di un libro dal titolo o dal riassunto.
2. **Calcolo Matematico Deterministico delle Percentuali (`book_discipline_spectrum`):**
   Su tutti i blocchi sostantivi $B$ di ciascun libro si calcolano e salvano due metriche verificabili:
   - **Copertura sul libro ($\text{Cov}$):**
     $$\text{Cov}(d) = 100 \times \frac{\sum_{b \in B:\, d \in \text{disc}(b)} \text{chars}(b)}{\sum_{b \in B} \text{chars}(b)}$$
     *(Indica in quale frazione del testo reale compare la disciplina $d$; poiché un singolo passaggio può toccare Fisica e Geografia insieme, le coperture sono indipendenti e ogni fetta è cliccabile per leggere i blocchi esatti).*
   - **Composizione tematica normalizzata ($\text{Share}$ a somma 100,0%):**
     $$\text{Share}(d) = 100 \times \frac{\sum_{b \in B} w_{b,d} \cdot \text{chars}(b)}{\sum_{b \in B} \text{chars}(b)}, \qquad w_{b,d} = \frac{\mathbb{1}[d \in \text{disc}(b)]}{|\text{disc}(b)|}$$
3. **Il Doppio Volto del "Libro Sbagliato":**
   - *Livello A — Isomorfismo Operativo:* fenomeni in un dominio remoto che agiscono una legge matematica/informatica (`curiosity_bridges`, es. Marconi a Santa Margherita ↔ $|x-x_0|<25$).
   - *Livello B — Contenuto Collaterale & Ricostruzione dal Basso (`discipline_reconstructor.py`):* per qualunque disciplina $D$, raccoglie e ordina tutti i passaggi ad alta densità dove $D$ compare dentro libri il cui `surface_domain` primario **non** è $D$ (es. *"La Geografia secondo PACK"* estratta da Masini, Kelvin, Abbagnano, Galvani).
4. **Decompressore Sinottico (`Chi / Come / Dove / Quando / Con chi in disaccordo`):**
   Vista cronologica e modale su un concetto attraverso tutti i `1.372` volumi, distinguendo chi `defines`, `proves`, `applies`, `critiques`, `extends` e `presupposes`.
5. **Ontologia Ministeriale v6 (`2.813+` obiettivi) & Mappatura sulla Contezza Simultanea (`TASK-SPEC-04`):**
   Importa in forma versionata i **53 file JSON** di `ontologia_v6` più l'integrazione del **Quinto Anno di Matematica Liceo Scientifico** da `CONTENUTI_PROGRAMMI_MINISTERIALI.txt` (`2.828` obiettivi totali in `data/curriculum/ministerial_ontology/ontology_v6_consolidated.json`), tenendo sempre distinto per la regola `R4` di `SPEC.md` il livello `institutional_declared` dalla copertura empirica `corpus_learnable`. Le fondamenta scolastiche del DAG si estendono a **64 nodi (`1ª elementare → 5ª superiore`, totale 108 nodi)** coprendo al 100% gli obiettivi matematici di Primaria, Medie e Liceo Scientifico come *radar anti-lacune* per il **Volume I**. Al termine di `M1` si esegue la mappatura bidirezionale sui 1.372 libri.

### C. Motore Editoriale dei "Nuovi Libri" Continui (`M3` — Dare Carne alla Matematica)
1. **Generazione Autoriale di Capitoli Continui (`resuscipack/books/`):**
   - **Nobilitazione dell'ovvio in prosa adulta:** niente tono da sussidiario né schede burocratiche; i capitoli scorrono come un libro vero costruito a partire dalle parole vive dei testi (*Euclide, Frajese, Prodi, Bellissima, Boole, Masini, Galvani, Cartesio, Apostol*).
   - **La carne genera l'osso (anti-poltrona):** ogni passaggio narrativo/storico conduce dentro il calcolo simbolico completo e si chiude con verifiche pratiche (`SymPy`, laboratorio codice, prove a libro chiuso) così il lettore acquisisce padronanza reale per l'OFA e gli esami SecAI.
   - **Apparato delle Fonti a 3 Colori & Rilettura Critica:** in coda a ogni capitolo, separazione esplicita fra `[Verificato sul corpus, con pagina e block_uid]`, `[Ricostruzione matematica/addestramento]` e `[Esercizi originali]`, oltre a una passata avversaria separata anti-errori prima di promuovere il capitolo.
2. **Due Volumi verso SecAI (L-31 UniMi):**
   - **Volume I — *Dall'Ovvio al Simbolo (Verso l'OFA Matematica I)*:** dalle radici del contare e dell'uguale fino a logica, insiemi, calcolo simbolico, grafici e trigonometria.
   - **Volume II — *I Ponti Nascosti di SecAI*:** copre i 20 *Shadow Gates* (inclusa la lacuna a 0 CFU di Probabilità e Statistica prima di Machine Learning, Matematica del Discreto, Crittografia, C/Sistemi e Testing).

### D. Interfaccia Editoriale Anti-Slop (`M4` — `design-taste-frontend` + `modern-web-guidance`)
1. **Obbligo di Skill Frontend:** ogni modifica HTML/CSS/JS deve seguire prima **`modern-web-guidance`** (`npx -y modern-web-guidance@latest search/retrieve`) e **`design-taste-frontend`** (`copy-voice.md`, `layout-v4.md`, `copy-lint.mjs`, `consistency.mjs`, `gate.mjs`).
2. **Abolizione totale del gergo interno nella UI:** spariscono dalla vista utente sigle e metadati tecnici (`P0.5`, `G00`, `Strato 0`, `block_pk`, `score 0.96`, `6/6 Gate`, contatori di debug).
3. **Due superfici essenziali da lettura vera:**
   - **Il Libro Continuo:** lettura distesa a larghezza tipografica ottimale con formule KaTeX e figure; al clic su una nota, un cassetto/pannello laterale apre la pagina autentica del libro citato con passaggio evidenziato e navigazione tra pagine.
   - **L'Atlante dei 1.372 Libri:** per ogni opera mostra la sua barra dello **Spettro Disciplinare Percentuale** (clicca *"Geografia 18%"* per leggere subito le pagine geografiche di Marconi) e le raccolte tematiche costruite dal basso.

---

## 3. Conseguenze

- **Positive:**
  - Allinea l'intero sistema alla visione reale dell'utente: i `1.372` libri lavorano insieme come memoria simultanea invisibile, producendo veri libri nuovi leggibili con piacere e rigore verso SecAI.
  - Rende trasparente e misurabile al carattere quanto ciascun libro contiene di ogni disciplina, sbloccando finalmente il "libro sbagliato" sia per analogia strutturale sia per geografia/storia/filosofia collaterale.
  - Impone controlli automatici di qualità sia sui testi matematici (rilettura critica + apparato 3 colori + `SymPy`) sia sul frontend (`copy-lint.mjs`, `consistency.mjs`, `gate.mjs`).
- **Vincoli / Trade-off:**
  - Richiede l'upgrade da `BlockExtraction v2.1` a `v2.2` (`disciplines[]`, `places[]`) con re-indicizzazione/integrazione dei `3.608` blocchi già estratti in Wave 1 e completamento OCR dei volumi muti prima di generare i capitoli finali a piena contezza.

---

## 4. Task Operativi Collegati (Roadmap verso il Completamento)

- [x] **TASK-CORPUS-04** *(M1)*: OCR degli 83 volumi muti (`79` canonici attivi con blocchi pieni + `4` duplicati di scansione verificati = `83/83`: Euclide, Galileo, Archimede, Apostol, Newton *Principia*/*Ottica*, Maxwell, Boyle, Copernico, Spoletini, `boheme`, 7 `.djvu`) e ingestione append-only in `pack_corpus.db` *(GCS `.md` + `1.193` figure su 16 volumi, `3.581` blocchi `djvutxt`, `13.601` `vertex_vision_batch` su Shard V1–V4 + `509` `vertex_vision_ocr`; `+18.506` blocchi attivi post-Wave-0, `107.050` chiavi Wave 0 preservate append-only, `124.744 == passages_fts_docsize`)*.
- [x] **TASK-EPIST-05** *(M1)*: Upgrade a `BlockExtraction v2.2` (`macro_disciplines[]` a 22 voci, `topics[]`, `places[]`, `years[]`, tabella `block_metadata_v22`, normalizzazione OCR/LaTeX-greco-array, riconciliazione `kind/mode`, backfill leggero Wave 1 solo-metadati e `responseSchema` packer `pack_size=8` con Vertex Batch JSONL `-50%`).
- [x] **TASK-EPIST-06** *(M1)*: Esecuzione integrale Wave 2, Wave 3 e Wave 4 su tutti i `1.416` libri attivi in `pack_corpus.db` (zero mock) *(`block_extraction_log=122.141` totali / `122.138` attivi; copertura sostanziale **`98,51%`** = `120.684 / 122.515` con `0` volumi scoperti; `106.265` `block_metadata_v22`, `139.382` `epistemic_units`, `25.965` `structural_signatures`, `175` `curiosity_bridges` validati con `score 0.89–0.98`)*.
- [ ] **TASK-SPEC-01** *(M2)*: Calcolo deterministico dello *Spettro Disciplinare Percentuale per Libro* ($\text{Cov}$ e $\text{Share}$ su tabella `book_discipline_spectrum`).
- [ ] **TASK-SPEC-02** *(M2)*: Motore di *Ricostruzione delle Discipline dal Basso* (`discipline_reconstructor.py` v2: *"La Geografia dentro i libri non geografici"*, Musica, Fisica, Logica).
- [ ] **TASK-SPEC-03** *(M2)*: *Decompressore Sinottico Cronologico e Modale* (`Chi / Come / Dove / Quando / Con chi in disaccordo`) sull'intero corpus.
- [ ] **TASK-SPEC-04** *(M2)*: *Ontologia Ministeriale v6 (`2.813+` obiettivi) & Mappatura Bidirezionale della Contezza Simultanea (`1ª Elementare → 5ª Superiore`)* (`resuscipack/curriculum/ministerial_ontology.py`, `resuscipack/epistemic/curriculum_mapper.py` — import `v6_sources`, integrazione Quinto Anno e espansione DAG a 108 nodi già acquisiti in `TASK-SPEC-04a`; mappatura empirica finale sui 1.372 libri aperta post-`M1`).
- [ ] **TASK-BOOK-01** *(M3)*: Motore Autoriale dei *Nuovi Libri* continui con figure Baidu, apparato fonti a 3 colori e passata avversaria di rilettura critica.
- [ ] **TASK-BOOK-02** *(M3)*: Stesura *Volume I — Dall'Ovvio al Simbolo* (dalle fondamenta elementari al Gate OFA) con palestra `SymPy` integrata nel testo.
- [ ] **TASK-BOOK-03** *(M3)*: Stesura *Volume II — I Ponti Nascosti di SecAI* (Probabilità 0 CFU, Discreto, Crittografia, Sistemi, Testing + 5 testi Open-Access).
- [ ] **TASK-UI-01** *(M4)*: Rifondazione Design System editoriale anti-slop tramite `design-taste-frontend` + `modern-web-guidance` (rimozione totale dei codici interni dalla UI).
- [ ] **TASK-UI-02** *(M4)*: Lettore continuo dei *Nuovi Libri* con pagina originale e figure a fianco + esercizi di padronanza.
- [ ] **TASK-UI-03** *(M4)*: *Atlante dei 1.372 Libri* con barre interattive dello Spettro Percentuale e mosaici per disciplina dal basso.
