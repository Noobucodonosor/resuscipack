"""Test suite completa per il sottosistema `resuscipack.epistemic` (ADR-0002, TASK-EPIST-01..03).

Tutti i test distruttivi operano esclusivamente dentro `tempfile.TemporaryDirectory()`.
I passaggi storici reali vengono letti in modalità `file:...?mode=ro` senza mutare nulla fuori sandbox.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resuscipack.corpus.normalizer import make_block_uid, make_book_uid, normalize_for_match
from resuscipack.corpus.schema import init_corpus_db, supersede_block
from resuscipack.epistemic import (
    ALL_OP_TAGS,
    GeneratorArchetype,
    OpTag,
    SchemaValidationError,
    find_wrong_book_candidates,
    get_bridges_for_node,
    persist_block_extraction,
    seed_verified_empirical_bridges,
    validate_and_upsert_bridge,
    validate_batch_anti_template,
    validate_block_extraction,
    validate_op_tags,
    verifica_scheda,
    verifica_scheda_report,
)
from resuscipack.epistemic.batch_cli import MissingCredentialsError, run_batch_extraction

HISTORICAL_FTS5_DB = Path("/Users/dany/from_baidu/atomic_iceberg/data/biblioteca_fts5.db")


def _insert_book_and_block(
    conn: sqlite3.Connection,
    *,
    title: str,
    surface_domain: str,
    content: str,
    page: int = 10,
    role: str = "body",
) -> Tuple[int, str]:
    bk_uid = make_book_uid(title, "test")
    conn.execute(
        """
        INSERT OR IGNORE INTO books (
            book_uid, title, author, year, surface_domain, language, source_kind, page_count, is_active
        ) VALUES (?, ?, 'Autore Test', 1975, ?, 'it', 'test', 500, 1)
        """,
        (bk_uid, title, surface_domain),
    )
    book_pk = int(
        conn.execute("SELECT book_pk FROM books WHERE book_uid = ?", (bk_uid,)).fetchone()[0]
    )
    norm_c = normalize_for_match(content)
    blk_uid = make_block_uid(bk_uid, page, page, norm_c)
    cur = conn.execute(
        """
        INSERT INTO blocks (
            block_uid, book_pk, book_title, is_active, block_role, page_start, page_end,
            printed_page, section_title, content, norm_content, char_count, est_tokens, source_origin
        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'Sezione', ?, ?, ?, ?, 'test')
        """,
        (
            blk_uid,
            book_pk,
            title,
            role,
            page,
            page,
            str(page),
            content,
            norm_c,
            len(content),
            max(1, len(content) // 4),
        ),
    )
    conn.commit()
    return int(cur.lastrowid), blk_uid


# ---------------------------------------------------------------------------
# TASK-EPIST-01: OpTag & Schema BlockExtraction v2.1
# ---------------------------------------------------------------------------


def test_op_tags_closed_vocabulary_has_24_primitives() -> None:
    assert len(ALL_OP_TAGS) == 24
    tags = validate_op_tags(["BOUNDED_TOLERANCE", "SIGNED_DEVIATION_FEEDBACK"])
    assert tags == [OpTag.BOUNDED_TOLERANCE, OpTag.SIGNED_DEVIATION_FEEDBACK]

    with pytest.raises(ValueError, match="fuori dall'Enum"):
        validate_op_tags(["INVENTED_FAKE_TAG"])

    with pytest.raises(ValueError, match="tra 1 e 3"):
        validate_op_tags([])


def test_schema_v21_math_textbook_allows_sig_null_and_paratext_silence() -> None:
    prodi_text = (
        "3.12 TEOREMA L'applicazione inversa di un'applicazione f: A -> B, se esiste è unica. "
        "Supponiamo dunque che g e g' siano applicazioni B -> A soddisfacenti alle relazioni. "
        "Per la proprietà associativa della composizione, si ha (g' o f) o g = g' o (f o g)."
    )
    payload = {
        "yield": "high",
        "units": [
            {
                "kind": "thm",
                "mode": "proves",
                "stmt": "Giovanni Prodi dimostra che se un'applicazione f ammette inversa, tale applicazione inversa è unica.",
                "quote": "L'applicazione inversa di un'applicazione f: A -> B, se esiste è unica.",
                "who": ["Giovanni Prodi"],
                "vs": None,
                "concepts": ["applicazione inversa", "unicità"],
            },
            {
                "kind": "proof_idea",
                "mode": "proves",
                "stmt": "L'unicità dell'applicazione inversa segue direttamente dalla proprietà associativa della composizione di funzioni.",
                "quote": "Per la proprietà associativa della composizione",
                "who": [],
                "vs": None,
                "concepts": ["associatività", "composizione di funzioni"],
            },
        ],
        "sig": None,
    }
    ext = validate_block_extraction(payload, block_content=prodi_text)
    assert ext.sig is None
    assert len(ext.units) == 2

    # Paratesto: diritto al silenzio
    paratext_ext = validate_block_extraction(
        {"yield": "low_or_paratext", "units": [], "sig": None},
        block_content="Indice dei nomi: Archimede 12, 45, 78",
    )
    assert paratext_ext.units == ()
    assert paratext_ext.sig is None


def test_schema_v21_sabotage_deixis_domain_stripping_leakage_and_fake_quote() -> None:
    marconi_text = (
        "L'esperimento ebbe luogo il 30 giugno 1934 nel mare di Santa Margherita Ligure. "
        "In posizione opportuna erano state fissate sulla superficie del mare due boe di traguardo, "
        "poste a cinquanta metri l'una dall'altra."
    )
    base_unit = {
        "kind": "exp",
        "mode": "narrates",
        "stmt": "Guglielmo Marconi esegue il 30 giugno 1934 l'esperimento di navigazione cieca a Santa Margherita Ligure.",
        "quote": "L'esperimento ebbe luogo il 30 giugno 1934 nel mare di Santa Margherita Ligure.",
        "who": ["Guglielmo Marconi"],
        "vs": None,
        "concepts": ["radionavigazione"],
    }

    # 1. Sabotaggio: citazione inventata
    bad_quote = {**base_unit, "quote": "questa frase non compare affatto nel libro originale"}
    with pytest.raises(SchemaValidationError, match="non trovata verbatim"):
        validate_block_extraction({"yield": "high", "units": [bad_quote], "sig": None}, block_content=marconi_text)

    # 2. Sabotaggio: deissi non risolta ("Egli...", "il Nostro")
    bad_deixis = {**base_unit, "stmt": "Il Nostro fece navigare la nave tra due punti nel Golfo."}
    with pytest.raises(SchemaValidationError, match="deissi"):
        validate_block_extraction({"yield": "high", "units": [bad_deixis], "sig": None}, block_content=marconi_text)

    # 3. Sabotaggio: domain_stripping violato ("panfilo", "boe" dentro sig.mech)
    with pytest.raises(SchemaValidationError, match="domain_stripping"):
        validate_block_extraction(
            {
                "yield": "high",
                "units": [base_unit],
                "sig": {
                    "op_tags": ["BOUNDED_TOLERANCE"],
                    "role": "embodied_intuition",
                    "mech": "Il panfilo passa tra due boe in mare seguendo il segnale.",
                },
            },
            block_content=marconi_text,
        )

    # 4. Sabotaggio: formula |x - x0| < 25 iniettata in sig.mech (leakage!)
    with pytest.raises(SchemaValidationError, match="zero-leakage"):
        validate_block_extraction(
            {
                "yield": "high",
                "units": [base_unit],
                "sig": {
                    "op_tags": ["BOUNDED_TOLERANCE"],
                    "role": "embodied_intuition",
                    "mech": "Passaggio di un punto mobile nel varco descritto da |x - x0| < 25 metri.",
                },
            },
            block_content=marconi_text,
        )

    # 5. Sabotaggio: kind='dispute' senza campo `vs`
    bad_dispute = {**base_unit, "kind": "dispute", "vs": None}
    with pytest.raises(SchemaValidationError, match="vs"):
        validate_block_extraction({"yield": "high", "units": [bad_dispute], "sig": None}, block_content=marconi_text)


def test_anti_template_batch_gate_rejects_repetitive_prefixes() -> None:
    src_text = "Un esperimento controllato mostra una variazione proporzionale misurabile tra tensione e distanza."
    unit = {
        "kind": "claim",
        "mode": "applies",
        "stmt": "L'esperimento controllato documenta una variazione proporzionale misurabile tra tensione e distanza.",
        "quote": "mostra una variazione proporzionale misurabile tra tensione e distanza",
        "who": [],
        "vs": None,
        "concepts": ["proporzionalità"],
    }
    cloned = [
        validate_block_extraction(
            {
                "yield": "medium",
                "units": [unit],
                "sig": {
                    "op_tags": ["PROPORTIONAL_SCALING"],
                    "role": "embodied_intuition",
                    "mech": f"Questo brano illustra chiaramente la variazione del parametro numero {i} nel sistema.",
                },
            },
            block_content=src_text,
        )
        for i in range(6)
    ]
    with pytest.raises(SchemaValidationError, match="Anti-Template"):
        validate_batch_anti_template(cloned)


# ---------------------------------------------------------------------------
# TASK-EPIST-02: Validatore Deterministico a 6 Gate (`verifica_citazioni.py`)
# ---------------------------------------------------------------------------


def test_verifica_citazioni_all_6_gates_pass_and_each_sabotage_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "pack_corpus.db"
        conn = init_corpus_db(db_path)

        frajese_text = (
            "Osserviamo anzitutto che una corrispondenza biunivoca tra gli elementi di due "
            "insiemi finiti può aversi SE E SOLTANTO SE i due insiemi hanno lo stesso numero di elementi."
        )
        marconi_text = (
            "L'esperimento ebbe luogo il 30 giugno 1934 nel mare di Santa Margherita Ligure. "
            "In posizione opportuna erano state fissate sulla superficie del mare due boe di traguardo, "
            "poste a cinquanta metri l'una dall'altra."
        )
        pk1, uid1 = _insert_book_and_block(
            conn, title="Frajese - Matematica", surface_domain="matematica", content=frajese_text
        )
        pk2, uid2 = _insert_book_and_block(
            conn, title="Masini - Marconi", surface_domain="storia_della_scienza", content=marconi_text
        )
        conn.close()

        valid_card = tmp_path / "valid_card.md"
        valid_md = f"""---
id: test.nodo
titolo: Nodo di Test Completo
stato: validata_auto
---

## Contesto
Due insiemi finiti si accoppiano uno a uno se hanno lo stesso numero di elementi [^1].

## Libro Sbagliato
Nel mare ligure l'esperimento radio-guidato passa nel varco di 50 metri [^2]:
- Centro tra le boe ↔ valore di riferimento $x_0$
- Semivarco di 25 metri ↔ raggio di tolleranza $\\delta$

1. Le due boe distanti 50 metri fissano un intervallo fisico centrato sulla rotta ideale.
2. Lo strumento indicatore fornisce lo scostamento con segno rispetto al centro anche a oblò oscurati.
3. Restare in rotta equivale quindi a soddisfare la condizione $|x - x_0| < 25$.

## Enunciati
- **[Definizione]** Due insiemi A e B si dicono equipotenti se esiste una biiezione tra essi. — *Giustificazione:* Formalizza il confronto diretto elemento per elemento senza contare [^1].
- **[Teorema]** L'equipotenza è una relazione simmetrica. — *Giustificazione:* L'inversa di una funzione biiettiva è anch'essa biiettiva.

## Note
[^1]: [block_pk={pk1} | block_uid={uid1}] «una corrispondenza biunivoca tra gli elementi di due insiemi finiti può aversi SE E SOLTANTO SE i due insiemi hanno lo stesso numero di elementi» — Attilio Frajese (p. 105)
[^2]: [block_pk={pk2} | block_uid={uid2}] «due boe di traguardo, poste a cinquanta metri l'una dall'altra» — Giancarlo Masini (p. 417)
"""
        valid_card.write_text(valid_md, encoding="utf-8")
        assert verifica_scheda(valid_card, db_path=db_path) == []

        # Sabotaggio Gate 1: block_uid alterato o blocco disattivato
        bad_g1 = tmp_path / "bad_g1.md"
        bad_g1.write_text(valid_md.replace(uid1, "blk_00000000000000000000"), encoding="utf-8")
        rep_g1 = verifica_scheda_report(bad_g1, db_path=db_path)
        assert rep_g1.gate_errors["gate1_block_identity"]

        # Sabotaggio Gate 2: citazione troppo corta (<4 parole) o non presente
        bad_g2 = tmp_path / "bad_g2.md"
        bad_g2.write_text(
            valid_md.replace(
                "due boe di traguardo, poste a cinquanta metri l'una dall'altra",
                "due boe",
            ),
            encoding="utf-8",
        )
        rep_g2 = verifica_scheda_report(bad_g2, db_path=db_path)
        assert rep_g2.gate_errors["gate2_verbatim_span"]

        # Sabotaggio Gate 3: nota orfana [^3] definita ma mai citata
        bad_g3 = tmp_path / "bad_g3.md"
        bad_g3.write_text(
            valid_md
            + f"\n[^3]: [block_pk={pk2} | block_uid={uid2}] «L'esperimento ebbe luogo il 30 giugno 1934 nel mare» — Masini\n",
            encoding="utf-8",
        )
        rep_g3 = verifica_scheda_report(bad_g3, db_path=db_path)
        assert rep_g3.gate_errors["gate3_no_orphan_footnotes"]

        # Sabotaggio Gate 4: enunciato senza etichetta / senza Giustificazione
        bad_g4 = tmp_path / "bad_g4.md"
        bad_g4.write_text(
            valid_md.replace("- **[Teorema]** L'equipotenza è una relazione simmetrica. — *Giustificazione:*", "- L'equipotenza è simmetrica:"),
            encoding="utf-8",
        )
        rep_g4 = verifica_scheda_report(bad_g4, db_path=db_path)
        assert rep_g4.gate_errors["gate4_labeled_enunciati"]

        # Sabotaggio Gate 5: deissi editoriale "il Nostro" / "ibidem"
        bad_g5 = tmp_path / "bad_g5.md"
        bad_g5.write_text(
            valid_md.replace("Due insiemi finiti", "Come afferma il Nostro in ibidem, due insiemi finiti"),
            encoding="utf-8",
        )
        rep_g5 = verifica_scheda_report(bad_g5, db_path=db_path)
        assert rep_g5.gate_errors["gate5_zero_dangling_deixis"]

        # Sabotaggio Gate 6: sezione Libro Sbagliato con meno di 3 passi inferenziali
        bad_g6 = tmp_path / "bad_g6.md"
        bad_g6.write_text(
            valid_md.replace(
                "2. Lo strumento indicatore fornisce lo scostamento con segno rispetto al centro anche a oblò oscurati.\n"
                "3. Restare in rotta equivale quindi a soddisfare la condizione $|x - x_0| < 25$.",
                "",
            ),
            encoding="utf-8",
        )
        rep_g6 = verifica_scheda_report(bad_g6, db_path=db_path)
        assert rep_g6.gate_errors["gate6_wrong_book_bridge_rigor"]

        # Verifica anche che superseding di un blocco renda il vecchio block_pk non attivo (Gate 1 grida!)
        conn_w = sqlite3.connect(str(db_path))
        pk3, _ = _insert_book_and_block(
            conn_w, title="Masini - Marconi", surface_domain="storia_della_scienza", content=marconi_text + " Nuova scansione."
        )
        supersede_block(conn_w, pk2, pk3)
        conn_w.commit()
        conn_w.close()
        rep_superseded = verifica_scheda_report(valid_card, db_path=db_path)
        assert rep_superseded.gate_errors["gate1_block_identity"]


# ---------------------------------------------------------------------------
# TASK-EPIST-03: Test Empirico Reale (Marconi, Galvani, Cartesio) & Batch CLI
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HISTORICAL_FTS5_DB.exists(), reason="DB storico biblioteca_fts5.db non presente")
def test_empirical_wrong_book_bridges_on_real_marconi_galvani_descartes_passages() -> None:
    """Legge in mode=ro i 3 passaggi reali da `biblioteca_fts5.db`, li carica in un `pack_corpus.db`
    temporaneo, esegue `seed_verified_empirical_bridges` e verifica l'inversione disciplinare."""
    ro_conn = sqlite3.connect(f"file:{HISTORICAL_FTS5_DB}?mode=ro", uri=True)
    try:
        real_rows: Dict[str, Tuple[str, str, str]] = {}
        for key, rowid, dom in [
            ("marconi", 32427, "storia_della_scienza"),
            ("galvani", 3487, "medicina_biologia"),
            ("descartes", 52642, "filosofia_scienze_umane"),
            ("prodi", 32541, "matematica"),
        ]:
            title, content = ro_conn.execute(
                "SELECT title, content FROM passages_fts WHERE rowid = ?", (rowid,)
            ).fetchone()
            real_rows[key] = (title, dom, content)
    finally:
        ro_conn.close()

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "pack_corpus.db"
        conn = init_corpus_db(db_path)
        for idx, (_, (title, dom, content)) in enumerate(real_rows.items(), start=1):
            _insert_book_and_block(conn, title=title, surface_domain=dom, content=content, page=idx * 10)

        # Anche un blocco matematico con lo stesso tag viene escluso dal filtro di inversione!
        prodi_pk, prodi_uid = _insert_book_and_block(
            conn,
            title="Manuale Analisi - Disequazioni",
            surface_domain="matematica",
            content="Definizione formale: la disequazione definisce l'intorno simmetrico attorno al punto.",
            page=99,
        )
        persist_block_extraction(
            conn,
            block_pk=prodi_pk,
            block_uid=prodi_uid,
            extraction=validate_block_extraction(
                {
                    "yield": "medium",
                    "units": [
                        {
                            "kind": "def",
                            "mode": "defines",
                            "stmt": "Il manuale di analisi definisce l'intorno simmetrico attorno al punto tramite disequazione.",
                            "quote": "la disequazione definisce l'intorno simmetrico attorno al punto",
                            "who": [],
                            "vs": None,
                            "concepts": ["intorno simmetrico"],
                        }
                    ],
                    "sig": {
                        "op_tags": ["BOUNDED_TOLERANCE"],
                        "role": "genesis_problem",
                        "mech": "Vincolo di appartenenza a un margine simmetrico attorno a un riferimento.",
                    },
                },
                block_content="Definizione formale: la disequazione definisce l'intorno simmetrico attorno al punto.",
            ),
        )
        conn.commit()
        conn.close()

        seed_res = seed_verified_empirical_bridges(db_path)
        assert seed_res["missing_keys"] == []
        assert set(seed_res["seeded_blocks"].keys()) == {
            "marconi_santa_margherita",
            "galvani_catena_rialpo",
            "cartesio_regola_x",
        }
        assert seed_res["bridges_upserted"] >= 6

        conn_ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            # Query 1: P0.5 Valore assoluto/intorni -> trova Marconi (escludendo i manuali di matematica!)
            arch_tol = GeneratorArchetype(
                node_id="P0.5",
                canonical_domains=("matematica", "informatica"),
                target_op_tags=(OpTag.BOUNDED_TOLERANCE, OpTag.SIGNED_DEVIATION_FEEDBACK),
                generator_query="mantenere un punto mobile entro un varco fisso azzerando lo scostamento",
            )
            cands_tol = find_wrong_book_candidates(conn_ro, arch_tol, limit=10)
            assert cands_tol
            assert "Marconi" in cands_tol[0].book_title
            assert all(c.surface_domain != "matematica" for c in cands_tol)

            # Query 2: P0.2 Congiunzione logica in serie -> trova Galvani
            arch_and = GeneratorArchetype(
                node_id="P0.2",
                canonical_domains=("matematica", "informatica"),
                target_op_tags=(OpTag.SERIES_CONJUNCTION_GATE,),
                generator_query="attivazione binaria lungo una catena di elementi in serie",
            )
            cands_and = find_wrong_book_candidates(conn_ro, arch_and, limit=10)
            assert cands_and and "Galvani" in cands_and[0].book_title

            # Query 3: P4.1 Crittanalisi / ricerca vincolata -> trova Cartesio
            arch_crypto = GeneratorArchetype(
                node_id="P4.1",
                canonical_domains=("matematica", "informatica"),
                target_op_tags=(OpTag.CONSTRAINED_SEARCH_DECODING,),
                generator_query="decodifica di simboli ignoti mediante enumerazione ordinata di congetture",
            )
            cands_crypto = find_wrong_book_candidates(conn_ro, arch_crypto, limit=10)
            assert cands_crypto and "Descartes" in cands_crypto[0].book_title

            # Verifica recupero ponti validati per nodo (anche con sub-id P0.5.valore-assoluto)
            p05_bridges = get_bridges_for_node(conn_ro, "P0.5.valore-assoluto")
            assert len(p05_bridges) == 1
            assert len(p05_bridges[0]["chain_steps"]) >= 3
            assert len(p05_bridges[0]["mapping"]) >= 2
        finally:
            conn_ro.close()


def test_bridge_validator_rejects_decorative_analogy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "pack_corpus.db"
        conn = init_corpus_db(db_path)
        bpk, _ = _insert_book_and_block(
            conn,
            title="Libro Storia",
            surface_domain="storia_della_scienza",
            content="Testo storico documentato con lunghezza adeguata per i controlli.",
        )
        # Meno di 3 passi inferenziali -> rifiutato
        with pytest.raises(ValueError, match="almeno 3 passaggi"):
            validate_and_upsert_bridge(
                conn,
                node_id="P0.5",
                block_pk=bpk,
                target_op_tags=[OpTag.BOUNDED_TOLERANCE],
                mapping={"A": "x", "B": "y"},
                chain_steps=["Passo 1 troppo breve o solo due passi.", "Secondo passo insufficiente."],
                score=0.8,
            )
        # Meno di 2 corrispondenze 1-a-1 -> rifiutato
        with pytest.raises(ValueError, match="almeno 2 corrispondenze"):
            validate_and_upsert_bridge(
                conn,
                node_id="P0.5",
                block_pk=bpk,
                target_op_tags=[OpTag.BOUNDED_TOLERANCE],
                mapping={"SoloUna": "x"},
                chain_steps=[
                    "1. Primo passaggio inferenziale documentato.",
                    "2. Secondo passaggio inferenziale strutturale.",
                    "3. Terzo passaggio didattico verso il concetto.",
                ],
                score=0.8,
            )
        conn.close()


def test_batch_cli_fail_honest_without_env_key_and_idempotent_with_injected_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "pack_corpus.db"
        conn = init_corpus_db(db_path)
        _insert_book_and_block(
            conn,
            title="Trattato di Analisi",
            surface_domain="matematica",
            content="Teorema fondamentale: ogni funzione continua su un intervallo chiuso e limitato ammette massimo e minimo assoluti.",
        )
        _insert_book_and_block(
            conn,
            title="Indice Analitico",
            surface_domain="matematica",
            content="Cauchy, 12, 14, 89",
            role="paratext",
        )
        conn.close()

        # 1. Dry-run funziona senza credenziali e ignora il paratesto
        dry = run_batch_extraction(db_path, wave=3, dry_run=True)
        assert dry["mode"] == "dry_run"
        assert dry["pending_blocks"] == 1
        assert dry["estimated_input_tokens"] > 0

        # 2. Senza API key fallisce esplicitamente senza scrivere alcun mock!
        with pytest.raises(MissingCredentialsError):
            run_batch_extraction(db_path, wave=3, dry_run=False)

        conn_check = sqlite3.connect(str(db_path))
        assert conn_check.execute("SELECT count(*) FROM epistemic_units").fetchone()[0] == 0
        conn_check.close()

        # 3. Con callable iniettato scrive l'unità valida ed è idempotente al secondo lancio
        calls = []

        def fake_llm(prompt: str, row: sqlite3.Row) -> dict:
            calls.append(int(row["block_pk"]))
            return {
                "yield": "high",
                "units": [
                    {
                        "kind": "thm",
                        "mode": "proves",
                        "stmt": "Il teorema di Weierstrass garantisce che ogni funzione continua su un intervallo chiuso e limitato possiede massimo e minimo assoluti.",
                        "quote": "ogni funzione continua su un intervallo chiuso e limitato ammette massimo e minimo assoluti",
                        "who": ["Karl Weierstrass"],
                        "vs": None,
                        "concepts": ["continuità", "massimo e minimo", "compattezza"],
                    }
                ],
                "sig": None,
            }

        res1 = run_batch_extraction(db_path, wave=3, llm_fn=fake_llm)
        assert res1["blocks_processed"] == 1
        assert res1["units_written"] == 1
        assert len(calls) == 1

        # Secondo giro: 0 blocchi pendenti (idempotenza totale)
        res2 = run_batch_extraction(db_path, wave=3, llm_fn=fake_llm)
        assert res2["blocks_processed"] == 0
        assert len(calls) == 1


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "pack_corpus.db").exists(),
    reason="pack_corpus.db non ancora generato da Wave 0",
)
def test_canonical_pack_corpus_db_has_verified_wrong_book_bridges_readonly() -> None:
    """Verifica in sola lettura (mode=ro) che `data/pack_corpus.db` contenga i ponti empirici
    validati (Marconi a Santa Margherita, Galvani, Cartesio) e risponda in <50ms."""
    canon_db = Path(__file__).resolve().parents[1] / "data" / "pack_corpus.db"
    conn = sqlite3.connect(f"file:{canon_db}?mode=ro", uri=True)
    try:
        n_sigs = conn.execute("SELECT count(*) FROM structural_signatures").fetchone()[0]
        n_bridges = conn.execute(
            "SELECT count(*) FROM curiosity_bridges WHERE status = 'validated'"
        ).fetchone()[0]
        assert n_sigs >= 3
        assert n_bridges >= 9

        for nid in ("P0.5", "P0.2", "P4.1", "numeri.relativi", "logica.vero-falso-non-e-o"):
            bridges = get_bridges_for_node(conn, nid)
            assert bridges, f"Nessun ponte Libro Sbagliato trovato per {nid}"
            assert len(bridges[0]["chain_steps"]) >= 3
            assert len(bridges[0]["mapping"]) >= 2
    finally:
        conn.close()


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "cards" / "numeri.quantita.md").exists(),
    reason="Schede canoniche in data/cards non ancora migrate",
)
def test_canonical_cards_pass_all_6_gates_readonly() -> None:
    """Verifica in sola lettura che tutte le schede migrate in `data/cards/` superino i 6 Gate."""
    root = Path(__file__).resolve().parents[1]
    cards_dir = root / "data" / "cards"
    canon_db = root / "data" / "pack_corpus.db"
    cards = sorted(p for p in cards_dir.glob("*.md") if not p.name.startswith("_"))
    assert len(cards) >= 1
    for card in cards:
        errs = verifica_scheda(card, db_path=canon_db)
        assert errs == [], f"Errori su {card.name}: {errs}"


