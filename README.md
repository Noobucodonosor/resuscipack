# resuscipack — Atlante Disciplinare & Workbench Editoriale

Motore Python di **indicizzazione, analisi epistemica e navigazione editoriale** progettato per organizzare e interrogare un corpus bibliografico multidisciplinare di oltre **1.370 volumi**, sviluppato con metodologia **ADR-Driven**.

> **Nota sul copyright:** questo repository contiene esclusivamente il codice sorgente, gli schemi dati, le icone SVG e i test; **nessun libro o PDF protetto da copyright è presente nel repository**.

## Funzionalità Principali
- **Schema Corpus Immutabile & Ricerca Full-Text:** modellazione relazionale in SQLite con `FTS5`, identificatori deterministici (`block_pk` / `block_uid`) e ingestione append-only.
- **Spettro Disciplinare & Cross-Referencing:** estrazione strutturata di discipline, luoghi, operatori concettuali e ponti tematici tra testi diversi (*"Libro Sbagliato"*).
- **Workbench Editoriale HTML/SVG:** interfaccia leggera per esplorare l'atlante disciplinare e generare percorsi di studio e sintesi con apparato delle fonti.
- **Qualità & Verificabilità:** validatore multi-gate e test automatici (`pytest`).

## Stack Tecnologico
- **Core:** Python 3, SQLite (`FTS5`), JSON Schema, HTML5/CSS3/SVG, `pytest`
- **Architettura & Governance:** Architecture Decision Records in [`docs/adr/README.md`](./docs/adr/README.md)

## Test
```bash
pytest
```
