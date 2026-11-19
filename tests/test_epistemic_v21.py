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
    DEFAULT_NODE_ARCHETYPES,
    GeneratorArchetype,
    OpTag,
    SchemaValidationError,
    decompress_concept,
    discover_and_validate_bridges,
    find_wrong_book_candidates,
    get_bridges_for_node,
    parse_historical_year,
    persist_block_extraction,
    resolve_entry_chronology,
    seed_verified_empirical_bridges,
    validate_and_upsert_bridge,
    validate_batch_anti_template,
    validate_block_extraction,
    validate_op_tags,
    verifica_scheda,
    verifica_scheda_report,
)
from resuscipack.epistemic.batch_cli import (
    MissingCredentialsError,
    _VERTEX_TOKEN_CACHE,
    run_batch_extraction,
    select_nucleo_aureo_book_pks,
)

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

        # 2. Senza API key (gemini) e senza gcloud (vertex) fallisce esplicitamente senza scrivere alcun mock!
        with pytest.raises(MissingCredentialsError):
            run_batch_extraction(db_path, wave=3, provider="gemini", dry_run=False)

        _VERTEX_TOKEN_CACHE.invalidate()
        monkeypatch.setattr(
            "resuscipack.epistemic.batch_cli._fetch_gcloud_access_token",
            lambda: (_ for _ in ()).throw(MissingCredentialsError("gcloud mock assente")),
        )
        with pytest.raises(MissingCredentialsError):
            run_batch_extraction(db_path, wave=3, provider="vertex", dry_run=False)
        _VERTEX_TOKEN_CACHE.invalidate()

        conn_check = sqlite3.connect(str(db_path))
        assert conn_check.execute("SELECT count(*) FROM epistemic_units").fetchone()[0] == 0
        assert conn_check.execute("SELECT count(*) FROM block_extraction_log").fetchone()[0] == 0
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


def test_block_extraction_log_prevents_rebilling_paratext_and_supports_retry_and_bridge_discovery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "pack_corpus.db"
        status_path = Path(tmp) / "wave1_status.json"
        conn = init_corpus_db(db_path)

        # Inseriamo 2 libri in dominio storia_della_scienza / musica_acustica
        pk_paratext, _ = _insert_book_and_block(
            conn,
            title="Giancarlo Masini - Guglielmo Marconi (UTET)",
            surface_domain="storia_della_scienza",
            content="Indice analitico generale dei nomi e delle illustrazioni fuori testo.",
            page=5,
        )
        pk_exp, _ = _insert_book_and_block(
            conn,
            title="Alvise Vidolin - Musica Elettronica",
            surface_domain="musica_acustica",
            content=(
                "Regolando la distanza della sorgente sonora rispetto al microfono entro una fascia simmetrica "
                "attorno al punto di equilibrio, il segnale d'errore guida il rientro automatico al centro."
            ),
            page=42,
        )
        # Verifica select_nucleo_aureo_book_pks
        selected_pks = select_nucleo_aureo_book_pks(conn)
        assert len(selected_pks) == 2
        conn.close()

        attempts: Dict[int, int] = {}

        def fake_llm_with_retry(prompt: str, row: sqlite3.Row) -> dict:
            bpk = int(row["block_pk"])
            attempts[bpk] = attempts.get(bpk, 0) + 1
            if bpk == pk_paratext:
                # Restituisce yield low_or_paratext con 0 unità
                return {"yield": "low_or_paratext", "units": [], "sig": None}
            if attempts[bpk] == 1:
                # Primo tentativo fallisce Gate verbatim per testare 1-shot self-repair
                return {
                    "yield": "high",
                    "units": [
                        {
                            "kind": "exp",
                            "mode": "applies",
                            "stmt": "Il controllo acustico corregge la posizione usando un errore con segno.",
                            "quote": "frase inventata non presente nel testo",
                            "who": ["Alvise Vidolin"],
                            "vs": None,
                            "concepts": ["feedback acustico"],
                        }
                    ],
                    "sig": None,
                }
            # Secondo tentativo dopo prompt di correzione passa!
            assert "ATTENZIONE CORREZIONE OBBLIGATORIA" in prompt
            return {
                "yield": "high",
                "units": [
                    {
                        "kind": "exp",
                        "mode": "applies",
                        "stmt": "Alvise Vidolin descrive il controllo della sorgente dentro una fascia simmetrica tramite segnale d'errore.",
                        "quote": "il segnale d'errore guida il rientro automatico al centro",
                        "who": ["Alvise Vidolin"],
                        "vs": None,
                        "concepts": ["fascia simmetrica", "controllo feedback"],
                    }
                ],
                "sig": {
                    "op_tags": ["BOUNDED_TOLERANCE", "SIGNED_DEVIATION_FEEDBACK"],
                    "role": "embodied_intuition",
                    "mech": "Mantenimento di un punto mobile dentro una fascia simmetrica attorno all'equilibrio tramite feedback continuo.",
                },
            }

        res1 = run_batch_extraction(
            db_path,
            wave=1,
            limit=10,
            workers=1,
            status_file=status_path,
            llm_fn=fake_llm_with_retry,
        )
        assert res1["blocks_processed"] == 2
        assert res1["paratext_logged"] == 1
        assert res1["units_written"] == 1
        assert res1["signatures_written"] == 1
        assert status_path.exists()

        # Secondo run: NEANCHE il blocco low_or_paratext viene ri-chiamato!
        res2 = run_batch_extraction(
            db_path,
            wave=1,
            limit=10,
            workers=1,
            llm_fn=fake_llm_with_retry,
        )
        assert res2["blocks_processed"] == 0
        assert attempts[pk_paratext] == 1
        assert attempts[pk_exp] == 2

        # Verifica discovery automatico su DEFAULT_NODE_ARCHETYPES
        assert len(DEFAULT_NODE_ARCHETYPES) >= 14
        conn2 = sqlite3.connect(str(db_path))
        conn2.row_factory = sqlite3.Row

        def fake_bridge_llm(prompt: str) -> dict:
            if "NODO TARGET: P0.5" in prompt:
                return {
                    "is_valid": True,
                    "mapping": {
                        "Punto di equilibrio acustico": "Centro di riferimento x0",
                        "Fascia simmetrica attorno al centro": "Intorno |x - x0| < delta",
                    },
                    "chain_steps": [
                        "1. La distanza della sorgente definisce uno scostamento rispetto al punto d'equilibrio.",
                        "2. Il segnale d'errore con segno riporta il sistema nella fascia simmetrica ammessa.",
                        "3. Questa dinamica coincide con la disequazione a valore assoluto |x - x0| < delta.",
                    ],
                    "score": 0.91,
                }
            return {"is_valid": False, "reason": "Non pertinente per questo nodo."}

        b_stats = discover_and_validate_bridges(
            conn2,
            fake_bridge_llm,
            top_k_per_node=3,
        )
        assert b_stats["bridges_validated"] == 1
        assert b_stats["bridges_rejected"] >= 1
        p05_bridges = get_bridges_for_node(conn2, "P0.5")
        assert len(p05_bridges) == 1
        assert p05_bridges[0]["block_pk"] == pk_exp

        # Verifica che i candidati rifiutati siano cachati come 'rejected_decorative' e saltati al 2° giro
        rej_cnt = conn2.execute(
            "SELECT COUNT(*) FROM curiosity_bridges WHERE status = 'rejected_decorative'"
        ).fetchone()[0]
        assert rej_cnt >= 1
        b_stats2 = discover_and_validate_bridges(
            conn2,
            fake_bridge_llm,
            top_k_per_node=3,
        )
        assert b_stats2["candidates_checked"] == 0

        # Verifica anche rifiuto automatico se score < 0.88 nonostante is_valid=True
        bpk_low, buid_low = _insert_book_and_block(
            conn2,
            title="Acustica Deboli",
            surface_domain="musica_acustica",
            content="Vibrazione sonora con ampiezza limitata e controllo analogico continuo.",
            page=50,
        )
        persist_block_extraction(
            conn2,
            block_pk=bpk_low,
            block_uid=buid_low,
            extraction=validate_block_extraction(
                {
                    "yield": "medium",
                    "units": [
                        {
                            "kind": "claim",
                            "mode": "applies",
                            "stmt": "Il segnale sonoro subisce una limitazione d'ampiezza tramite controllo analogico.",
                            "quote": "Vibrazione sonora con ampiezza limitata",
                            "who": [],
                            "vs": None,
                            "concepts": ["ampiezza limitata"],
                        }
                    ],
                    "sig": {
                        "op_tags": ["BOUNDED_TOLERANCE"],
                        "role": "embodied_intuition",
                        "mech": "Limitazione simmetrica dell'escursione di un oscillatore tramite retroazione continua.",
                    },
                },
                block_content="Vibrazione sonora con ampiezza limitata e controllo analogico continuo.",
            ),
        )
        conn2.commit()
        b_stats3 = discover_and_validate_bridges(
            conn2,
            lambda _p: {
                "is_valid": True,
                "mapping": {"Oscillazione": "x", "Fascia": "delta"},
                "chain_steps": ["1. Primo passaggio inferenziale.", "2. Secondo passaggio.", "3. Terzo passaggio."],
                "score": 0.72,
            },
            top_k_per_node=5,
        )
        assert b_stats3["bridges_validated"] == 0
        assert (
            conn2.execute(
                "SELECT status FROM curiosity_bridges WHERE block_pk = ?", (bpk_low,)
            ).fetchone()[0]
            == "rejected_decorative"
        )
        conn2.close()


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


# ---------------------------------------------------------------------------
# TASK-SPEC-03: Decompressore Sinottico Cronologico e Modale
# ---------------------------------------------------------------------------


def test_decompressor_historical_year_parser_and_chronology() -> None:
    assert parse_historical_year("1638") == (1638, "1638")
    assert parse_historical_year("1635-1647") == (1635, "1635-1647")
    assert parse_historical_year("2001/2002") == (2001, "2001/2002")
    assert parse_historical_year("300 a.C.") == (-300, "300 a.C.")
    assert parse_historical_year("III sec. a.C.") == (-250, "III sec. a.C.")
    assert parse_historical_year("585 BC") == (-585, "585 a.C.")
    assert parse_historical_year("XVII") == (1650, "XVII sec.")
    assert parse_historical_year("XIX secolo") == (1850, "XIX sec.")
    assert parse_historical_year("Seicento") == (1650, "Seicento")
    assert parse_historical_year("Ottocento") == (1850, "Ottocento")
    assert parse_historical_year("1970s") == (1970, "1970s")
    assert parse_historical_year("anni '80") == (1980, "anni '80")
    assert parse_historical_year("anni Ottanta") == (1980, "anni Ottanta")

    # Rumore non cronologico deve essere scartato
    for junk in ("C++11", "12/06/14", "20", "4500", ""):
        assert parse_historical_year(junk) is None, f"{junk!r} non dovrebbe essere parsato come anno"

    # Priorità cronologica: blocco v2.2 -> epoca autore -> anno pubblicazione -> undated
    assert resolve_entry_chronology(["1638"], ["Galileo"], "Titolo", None, 1964) == (
        1638,
        "1638",
        "block_metadata_year",
    )
    assert resolve_entry_chronology(["C++11"], ["Euclide"], "Elementi", "Attilio Frajese", 1970) == (
        -300,
        "~300 a.C.",
        "author_epoch",
    )
    assert resolve_entry_chronology([], ["Autore Moderno"], "Libro", None, 1974) == (
        1974,
        "1974",
        "book_publication_year",
    )
    assert resolve_entry_chronology([], [], "Senza data", None, None)[0] is None


def test_decompressor_synthetic_chronological_modal_and_disputes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "decomp.db"
        conn = init_corpus_db(db_path)

        specs = [
            (
                "Euclide - Elementi",
                "matematica",
                1970,
                "Le grandezze incommensurabili non ammettono una misura comune finita per il calcolo infinitesimale geometrico.",
                "defines",
                "def",
                ["Euclide"],
                None,
                ["300 a.C."],
                "Le grandezze incommensurabili non ammettono una misura comune finita",
                "Euclide definisce le grandezze incommensurabili come prive di misura comune finita.",
            ),
            (
                "Bonaventura Cavalieri - Geometria degli indivisibili",
                "matematica",
                1966,
                "Il metodo degli indivisibili considera i continui composti di infinite linee per il calcolo infinitesimale, ma Roberval propone un fondamento diverso.",
                "critiques",
                "dispute",
                ["Bonaventura Cavalieri", "Roberval"],
                "Roberval contesta l'impostazione geometrica pura degli indivisibili di Cavalieri",
                ["1635"],
                "Il metodo degli indivisibili considera i continui composti di infinite linee",
                "Bonaventura Cavalieri difende il calcolo degli indivisibili contro le critiche di Roberval.",
            ),
            (
                "Giovanni Prodi - Analisi Matematica",
                "matematica",
                1977,
                "La definizione rigorosa di limite elimina le difficoltà dell'analisi infinitesimale classica mediante intervalli arbitrariamente piccoli.",
                "proves",
                "thm",
                ["Giovanni Prodi"],
                None,
                ["1970"],
                "elimina le difficoltà dell'analisi infinitesimale classica mediante intervalli",
                "Giovanni Prodi dimostra come i limiti formalizzino l'analisi infinitesimale.",
            ),
            (
                "PRIMIGI",
                "miscellanea_tecnica",
                2018,
                "Catalogo calzature disponibile in lotto infinitesimale a magazzino per il 2018.",
                "applies",
                "claim",
                ["PRIMIGI"],
                None,
                ["2018"],
                "lotto infinitesimale a magazzino",
                "Listino commerciale PRIMIGI per la stagione 2018.",
            ),
        ]

        for idx, (title, dom, yr, content, mode, kind, who, vs, hist_yrs, quote, stmt) in enumerate(specs, start=1):
            bk_pk, blk_uid = _insert_book_and_block(conn, title=title, surface_domain=dom, content=content, page=idx * 10)
            ext = validate_block_extraction(
                {
                    "yield": "high",
                    "macro_disciplines": ["matematica"],
                    "topics": ["infinitesimale"],
                    "places": ["Bologna"] if "Cavalieri" in title else [],
                    "years": hist_yrs,
                    "units": [
                        {
                            "kind": kind,
                            "mode": mode,
                            "stmt": stmt,
                            "quote": quote,
                            "who": who,
                            "vs": vs,
                            "concepts": ["calcolo infinitesimale", "indivisibili"],
                        }
                    ],
                    "sig": None,
                },
                block_content=content,
                require_v22_metadata=True,
            )
            persist_block_extraction(conn, block_pk=bk_pk, block_uid=blk_uid, extraction=ext)

        from resuscipack.epistemic import compute_all_book_spectra

        compute_all_book_spectra(conn)
        report = decompress_concept(conn, "infinitesimale")

        assert report.total_entries == 3
        assert report.distinct_books == 3
        assert [e.sort_year for e in report.timeline] == [-300, 1635, 1970]
        assert [e.mode for e in report.timeline] == ["defines", "critiques", "proves"]
        assert all("PRIMIGI" not in e.book_title for e in report.timeline)
        assert report.disputes_count == 1
        assert "Roberval" in report.disputes[0].vs_dispute
        assert set(report.by_mode.keys()) == {"defines", "critiques", "proves"}
        for e in report.timeline:
            assert e.block_pk > 0 and e.verbatim_quote and e.stmt
        conn.close()


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "pack_corpus.db").exists(),
    reason="pack_corpus.db non presente",
)
def test_decompressor_live_corpus_concepts() -> None:
    canon_db = Path(__file__).resolve().parents[1] / "data" / "pack_corpus.db"
    conn = sqlite3.connect(f"file:{canon_db}?mode=ro", uri=True)
    try:
        for concept in ("infinitesimale", "probabilità", "entropia", "parallele"):
            report = decompress_concept(conn, concept, max_entries=20, max_per_book=2)
            assert report.total_entries >= 4, f"Poche voci per {concept!r}: {report.total_entries}"
            assert report.distinct_books >= 3, f"Pochi libri per {concept!r}: {report.distinct_books}"
            assert report.disputes_count >= 1, f"Nessuna controversia `vs_dispute` per {concept!r}"

            dated = [e.sort_year for e in report.timeline if e.sort_year is not None]
            assert dated == sorted(dated), f"Timeline non monotona per {concept!r}: {dated}"
            for e in report.timeline:
                assert e.block_pk > 0
                assert e.verbatim_quote.strip()
                assert e.stmt.strip()
                assert e.mode in {"defines", "proves", "applies", "critiques", "extends", "presupposes", "narrates"}
    finally:
        conn.close()


