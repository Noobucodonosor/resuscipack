# AGENTS.md — Contesto & Linee Guida per Agenti AI e Sviluppatori

> **REGOLA AUREA (MANDATORY):**
> Prima di modificare l'architettura, toccare il modello dati, aggiungere endpoint o sviluppare nuove feature, **DEVI leggere [`docs/adr/README.md`](./docs/adr/README.md)** e gli ADR specifici nella cartella [`docs/adr/`](./docs/adr/).

---

## 1. Panoramica del Progetto

- **Nome Progetto:** `resuscipack` (P.A.C.K. — *Pedagogical Agentic Curriculum Knowledge*)
- **Repository:** `dany/resuscipack`
- **Descrizione Sintetica:** Infrastruttura locale-first per l'estrazione epistemica integrale dal patrimonio librario (~1.365 opere autentiche), la scoperta rigorosa di ponti interdisciplinari (*"Il Libro Sbagliato" / "Marconi a Santa Margherita"*) e il tavolo di studio attivo dalla 1ª elementare alla laurea **SecAI (L-31 Informatica / Sicurezza AI, UniMi)** e relativi gate OFA.
- **Stack Tecnologico:**
  - **Backend & Core:** Python 3 (`.venv` locale isolato), Flask, SymPy, PyYAML, Pytest
  - **Frontend:** HTML5 / CSS3 / Vanilla JS + KaTeX (Tavolo di Studio a 2 colonne, zero framework pesanti, zero `.slice()` di troncamento)
  - **Database:** SQLite3 + FTS5 (`data/pack_corpus.db` immutabile `block_pk`/`block_uid` per il corpus; `data/student_state.db` separato per progressi, diagnostica Fast-Forward e portfolio Hero)
  - **Servizi Esterni / AI (Opzionali per Wave 1–4):** Batch API asincrone (Gemini / DeepSeek) invocate esclusivamente da CLI con chiavi lette da variabili d'ambiente (`.env` mai committato; zero fallback mock)

---

## 2. Mappa dei File Principali

| File / Cartella | Ruolo |
| :--- | :--- |
| [`docs/adr/README.md`](./docs/adr/README.md) | **Indice degli ADR**, diagramma architetturale Mermaid e **Master Task Backlog**. |
| [`docs/adr/0001-immutable-corpus-and-wave0.md`](./docs/adr/0001-immutable-corpus-and-wave0.md) | Schema SQLite immutabile (`block_pk`/`block_uid`), bonifica Wave 0 (splicing Baidu OCR + 32 EPUB) e manifesto OCR Wave 1–4. |
| [`docs/adr/0002-block-extraction-and-wrong-book-bridge.md`](./docs/adr/0002-block-extraction-and-wrong-book-bridge.md) | Schema `BlockExtraction v2.1`, 24 `op_tags`, ponte *Libro Sbagliato* e validatore deterministico a 6 Gate (`verifica_citazioni.py`). |
| [`docs/adr/0003-secai-spine-and-study-workbench.md`](./docs/adr/0003-secai-spine-and-study-workbench.md) | Spina dorsale curricolare a 4 strati (1ª elementare -> OFA -> SecAI), Fast-Forward `SymPy` e Tavolo di Studio a 2 colonne. |
| `.github/ISSUE_TEMPLATE/` | Template standard per l'apertura di GitHub Issues (`adr_task.yml`, `bug_report.yml`). |
| `resuscipack/corpus/` | Ingestione idempotente Wave 0, normalizzazione testo, schema SQLite `pack_corpus.db` e manifesto OCR. |
| `resuscipack/epistemic/` | `op_tags.py`, validazione `schema_v21.py`, inversione disciplinare `bridge.py`, CLI batch e `verifica_citazioni.py`. |
| `resuscipack/curriculum/` | DAG unificato a 4 strati (`dag.py`), generatori e verificatori `SymPy` (`drills_sympy.py`), stato studente (`student_state.py`) e parser schede (`cards.py`). |
| `resuscipack/workbench/app.py` | Server Flask e API REST del Tavolo di Studio (Bussola Hero, Fast-Forward, Scheda v3, Lettore Libro Vero `/api/block/<block_pk>`). |
| `resuscipack/workbench/templates/index.html` | Interfaccia web minimalista a 2 colonne (60% Scheda Decisione di Progetto + 40% Pagina Originale del Libro). |
| `data/curriculum/` & `data/cards/` | Grafo curricolare JSON versionato, registro testi Open-Access (€0) e schede Markdown verificate. |

---

## 3. Metodologia di Lavoro (ADR + GitHub Issues)

1. **Ogni decisione architetturale o di sicurezza** è documentata in un file `docs/adr/NNNN-titolo.md`.
2. **Ogni task operativo** ha un codice univoco (`TASK-<MODULO>-XX`) censito sia nell'ADR di origine, sia in `docs/adr/README.md`, sia come **GitHub Issue**.
3. **Priorità Standard:**
   - `P0-critical`: Integrità crittografica delle fonti/citazioni, immutabilità `block_pk`/`block_uid`, protezione segreti, assenza di mock.
   - `P1-high`: Pipeline Wave 0, validatori deterministici, DAG SecAI, esercizi `SymPy`, Tavolo di Studio a 2 colonne.
   - `P2-medium`: Arricchimenti batch Wave 1–4, esportazione Anki, estensioni future multi-dominio (`SPEC.md`).
4. **Sviluppo & Commit Atomici:**
   - Lavora su un `TASK-<MODULO>-XX` alla volta, esclusivamente dentro `.venv`.
   - Mantieni **STRICT READ-ONLY** su tutte le cartelle storiche esterne (`/Users/dany/from_baidu`, `/Users/dany/Desktop/PACK copy 4`, `/Users/dany/Documents/ChatGPT/pack-next`, `/Users/dany/Desktop/pc4`).
   - Esegui sempre il **Verification Step** prima di concludere e usa commit strutturati:
     ```bash
     git commit -m "feat(TASK-SECAI-01): descrizione sintetica della modifica"
     ```

---

## 4. Sicurezza & Regole Critiche

- **Mai committare segreti o database:** Il file `.env`, l'ambiente `.venv/` e i database SQLite (`data/*.db*`, `*.sqlite*`) devono restare sempre in `.gitignore`.
- **Zero Mock & Zero Troncamenti:** Nessun fallback deterministico finto su fallimento API; nessun `.slice(0, 10)` sui risultati mostrati all'utente.
- **Verifica Pre-Release:** Prima di generare commit di rilascio o fare push, esegui:
  ```bash
  python3 ~/.gemini/config/skills/adr-github-methodology/scripts/pre_release_check.py
  ```

---

## 5. Comandi Rapidi di Sviluppo e Test

```bash
# Creazione / attivazione ambiente virtuale isolato
.venv/bin/python --version

# Avvio del Tavolo di Studio SecAI in locale (http://127.0.0.1:5050)
.venv/bin/python -m resuscipack.workbench.app --port 5050

# Verifica deterministica a 6 Gate delle schede in data/cards/
.venv/bin/python -m resuscipack.epistemic.verifica_citazioni data/cards/

# Esecuzione dell'intera test suite end-to-end e unitaria
.venv/bin/pytest -v

# Controllo conformità ADR e assenza segreti/DB tracciati
python3 ~/.gemini/config/skills/adr-github-methodology/scripts/pre_release_check.py
```
