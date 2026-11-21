"""Test suite per il Motore Autoriale dei *Nuovi Libri* Continui (ADR-0004, TASK-BOOK-01).

Tutti i test distruttivi girano esclusivamente in `tempfile.TemporaryDirectory()`.
Zero mock silenziosi: senza credenziali o callable iniettato il sistema solleva `MissingCredentialsError`.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resuscipack.books import (
    CONTROLLED_SVG_IDS,
    DEFAULT_ASSETS_DIR,
    DEFAULT_BOOKS_DIR,
    DEFAULT_FIGURES_DIR,
    PILOT_CHAPTER_SPEC,
    VOL1_CHAPTER_SPECS,
    VOL2_CHAPTER_SPECS,
    ChapterSpec,
    assemble_chapter_dossier,
    find_corpus_figures_for_blocks,
    generate_and_verify_chapter,
    generate_controlled_svg,
    run_deterministic_chapter_audit,
    save_svg_diagram,
)
from resuscipack.books.catalog import ALL_OA_BOOK_UIDS
from resuscipack.curriculum.dag import load_unified_dag
from resuscipack.curriculum.drills_sympy import generate_drill_set, grade_drill_answer
from resuscipack.corpus.normalizer import make_block_uid, make_book_uid, normalize_for_match
from resuscipack.corpus.open_access_ingest import (
    OpenAccessBlockDraft,
    OpenAccessWorkDraft,
    ingest_open_access_sources,
)
from resuscipack.corpus.schema import DEFAULT_DB_PATH, connect_corpus_db, init_corpus_db
from resuscipack.epistemic import (
    persist_block_extraction,
    validate_block_extraction,
    verifica_scheda,
    verifica_scheda_report,
)
from resuscipack.epistemic.verifica_citazioni import leggi_scheda
from resuscipack.epistemic.batch_cli import MissingCredentialsError, _VERTEX_TOKEN_CACHE


def _seed_book_block(
    conn: sqlite3.Connection,
    *,
    title: str,
    surface_domain: str,
    content: str,
    quote: str,
    stmt: str,
    discs: Sequence[str] = ("matematica",),
    page: int = 10,
) -> Tuple[int, str]:
    bk_uid = make_book_uid(title, "test")
    conn.execute(
        """
        INSERT OR IGNORE INTO books (
            book_uid, title, author, year, surface_domain, language, source_kind, page_count, is_active
        ) VALUES (?, ?, 'Autore Storico', 1968, ?, 'it', 'test', 250, 1)
        """,
        (bk_uid, title, surface_domain),
    )
    book_pk = int(conn.execute("SELECT book_pk FROM books WHERE book_uid = ?", (bk_uid,)).fetchone()[0])
    norm_c = normalize_for_match(content)
    blk_uid = make_block_uid(bk_uid, page, page, norm_c)
    cur = conn.execute(
        """
        INSERT INTO blocks (
            block_uid, book_pk, book_title, is_active, block_role, page_start, page_end,
            printed_page, section_title, content, norm_content, char_count, est_tokens, source_origin
        ) VALUES (?, ?, ?, 1, 'body', ?, ?, ?, 'Capitolo Test', ?, ?, ?, ?, 'test')
        """,
        (blk_uid, book_pk, title, page, page, str(page), content, norm_c, len(content), max(1, len(content) // 4)),
    )
    blk_pk = int(cur.lastrowid)
    ext = validate_block_extraction(
        {
            "yield": "high",
            "macro_disciplines": list(discs),
            "topics": ["corrispondenza biunivoca", "uguaglianza"],
            "places": [],
            "years": ["1968"],
            "units": [
                {
                    "kind": "def",
                    "mode": "defines",
                    "stmt": stmt,
                    "quote": quote,
                    "who": ["Autore Storico"],
                    "vs": None,
                    "concepts": ["corrispondenza biunivoca", "uguaglianza"],
                }
            ],
            "sig": None,
        },
        block_content=content,
        require_v22_metadata=True,
    )
    persist_block_extraction(conn, block_pk=blk_pk, block_uid=blk_uid, extraction=ext)
    conn.commit()
    return blk_pk, blk_uid


def test_svg_diagrams_and_corpus_figure_finder() -> None:
    assert len(CONTROLLED_SVG_IDS) == 18
    for did in CONTROLLED_SVG_IDS:
        svg_text = generate_controlled_svg(did, title=f"Diagramma {did}")
        root = ET.fromstring(svg_text)
        assert root.tag.endswith("svg")
        assert root.attrib.get("viewBox")
        assert root.find(".//{http://www.w3.org/2000/svg}title") is not None

    with pytest.raises(ValueError, match="non riconosciuto"):
        generate_controlled_svg("diagramma_inventato")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        chapter_dir = tmp_dir / "vol1"
        assets_dir = tmp_dir / "assets"
        chapter_dir.mkdir(parents=True)

        asset = save_svg_diagram(
            "marconi_tolerance_corridor",
            assets_dir,
            filename="tol.svg",
            caption="Corridoio simmetrico",
            chapter_dir=chapter_dir,
        )
        assert asset.path.exists()
        assert asset.rel_path == "../assets/tol.svg"

        # Verifica ricerca figure Baidu OCR su DB sintetico
        db_path = tmp_dir / "figs.db"
        conn = init_corpus_db(db_path)
        blk_pk, _ = _seed_book_block(
            conn,
            title="Libro Illustrato Test",
            surface_domain="fisica_ingegneria",
            content="Schema del circuito equivalente in corrente alternata con figura sperimentale dettagliata.",
            quote="Schema del circuito equivalente in corrente alternata",
            stmt="Il testo presenta lo schema del circuito equivalente.",
            page=13,
        )
        bk_uid = str(conn.execute("SELECT book_uid FROM books").fetchone()[0])
        fig_dir = tmp_dir / "corpus_figs" / bk_uid
        fig_dir.mkdir(parents=True)
        (fig_dir / "page_0013_0.jpg").write_bytes(b"fake-jpg-header")

        found = find_corpus_figures_for_blocks(
            conn, [blk_pk], figures_root=tmp_dir / "corpus_figs", chapter_dir=chapter_dir
        )
        assert len(found) == 1
        assert found[0].kind == "corpus_figure"
        assert found[0].block_pk == blk_pk
        assert found[0].page == 13
        conn.close()


def test_verifica_citazioni_book_chapter_mode_pass_and_sabotages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        db_path = tmp_dir / "chapter_gate.db"
        conn = init_corpus_db(db_path)
        quote = "quando tra due insiemi è possibile stabilire una corrispondenza biunivoca"
        blk_pk, blk_uid = _seed_book_block(
            conn,
            title="Frajese - Storia",
            surface_domain="matematica",
            content="Nella teoria elementare, quando tra due insiemi è possibile stabilire una corrispondenza biunivoca essi sono equipotenti.",
            quote=quote,
            stmt="La corrispondenza biunivoca stabilisce l'equipotenza tra due insiemi.",
            page=4,
        )
        conn.close()

        assets_dir = tmp_dir / "assets"
        svg = save_svg_diagram("balance_and_number_line", assets_dir, chapter_dir=tmp_dir)

        base_frontmatter = (
            f"---\n"
            f"tipo: capitolo_libro\n"
            f"id: vol1.cap01\n"
            f"titolo: Capitolo Test\n"
            f"fonti:\n"
            f"  - block_pk: {blk_pk}\n"
            f"    block_uid: {blk_uid}\n"
            f'    citazione: "{quote}"\n'
            f"---\n\n"
        )
        valid_body = (
            f"# Capitolo 1\n\n"
            f"## Il contare prima dei nomi\n\n"
            f"Contare significa associare elementi uno a uno: in termini precisi, {quote} [^1].\n\n"
            f"Formalmente una funzione $f: A \\to B$ è biiettiva se $\\forall b \\in B\\, \\exists! a \\in A$ tale che $f(a) = b$.\n\n"
            f"![Diagramma]({svg.rel_path})\n\n"
            f"## Apparato delle fonti\n\n"
            f"### [Verificato sul testo]\n"
            f"[^1]: [block_pk={blk_pk} | block_uid={blk_uid}] «{quote}» — Autore, Frajese (p. 4)\n\n"
            f"### [Ricostruzione matematica / addestramento]\n"
            f"- Formalizzazione mediante quantificatori universali ed esistenziali.\n\n"
            f"### [Esercizi originali]\n"
            f"- Verifica quante biiezioni esistono su un insieme di 4 elementi.\n"
        )

        ok_path = tmp_dir / "cap_ok.md"
        ok_path.write_text(base_frontmatter + valid_body, encoding="utf-8")
        assert verifica_scheda(ok_path, db_path=db_path) == []

        # Sabotaggio 1: gergo di debug esposto nella prosa
        jargon_path = tmp_dir / "cap_jargon.md"
        jargon_path.write_text(
            base_frontmatter + valid_body.replace("Contare significa", "Come si vede in P0.5 e block_pk=99, contare significa"),
            encoding="utf-8",
        )
        rep_jargon = verifica_scheda_report(jargon_path, db_path=db_path)
        assert not rep_jargon.ok and rep_jargon.gate_errors["gate4_labeled_enunciati"]

        # Sabotaggio 2: manca un colore nell'Apparato
        missing_col = tmp_dir / "cap_2colors.md"
        missing_col.write_text(
            base_frontmatter + valid_body.replace("### [Esercizi originali]\n- Verifica quante biiezioni esistono su un insieme di 4 elementi.", ""),
            encoding="utf-8",
        )
        rep_col = verifica_scheda_report(missing_col, db_path=db_path)
        assert not rep_col.ok and rep_col.gate_errors["gate4_labeled_enunciati"]

        # Sabotaggio 3: immagine rotta
        broken_img = tmp_dir / "cap_img.md"
        broken_img.write_text(
            base_frontmatter + valid_body.replace(svg.rel_path, "../assets/non_esiste.svg"),
            encoding="utf-8",
        )
        rep_img = verifica_scheda_report(broken_img, db_path=db_path)
        assert not rep_img.ok and rep_img.gate_errors["gate4_labeled_enunciati"]

        # Sabotaggio 4: nota orfana / rimando spezzato
        orphan = tmp_dir / "cap_orphan.md"
        orphan.write_text(
            base_frontmatter + valid_body.replace("[^1].", "[^1] e [^2]."),
            encoding="utf-8",
        )
        rep_orp = verifica_scheda_report(orphan, db_path=db_path)
        assert not rep_orp.ok and rep_orp.gate_errors["gate3_no_orphan_footnotes"]

        # Sabotaggio 5: citazione inventata
        fake_q = base_frontmatter.replace(quote, "citazione inventata mai scritta nel libro originale") + valid_body.replace(
            f"«{quote}»", "«citazione inventata mai scritta nel libro originale»"
        )
        fake_path = tmp_dir / "cap_fake.md"
        fake_path.write_text(fake_q, encoding="utf-8")
        rep_fake = verifica_scheda_report(fake_path, db_path=db_path)
        assert not rep_fake.ok and rep_fake.gate_errors["gate2_verbatim_span"]

        # Sabotaggio 6: deissi opaca nella prosa
        deixis_path = tmp_dir / "cap_deixis.md"
        deixis_path.write_text(
            base_frontmatter + valid_body.replace("Contare significa", "Come afferma ibidem il Nostro, contare significa"),
            encoding="utf-8",
        )
        rep_deix = verifica_scheda_report(deixis_path, db_path=db_path)
        assert not rep_deix.ok and rep_deix.gate_errors["gate5_zero_dangling_deixis"]


def test_author_engine_fail_honest_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        db_path = tmp_dir / "no_creds.db"
        conn = init_corpus_db(db_path)
        _seed_book_block(
            conn,
            title="Test No Creds",
            surface_domain="matematica",
            content="La corrispondenza biunivoca associa esattamente un elemento di un insieme a un solo elemento dell'altro.",
            quote="corrispondenza biunivoca associa esattamente un elemento di un insieme",
            stmt="La corrispondenza biunivoca associa elementi uno a uno.",
        )
        conn.close()

        spec = ChapterSpec(
            volume_id="vol1_ofa",
            chapter_number=1,
            slug="no_creds",
            title="Test",
            subtitle="Test",
            node_ids=("numeri.quantita",),
            concept_queries=("corrispondenza biunivoca",),
            drill_keys=("drill_counting_bijection",),
            svg_diagram_id="balance_and_number_line",
        )

        # 1. Gemini senza API key -> MissingCredentialsError, nessun file scritto
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(MissingCredentialsError):
            generate_and_verify_chapter(
                spec,
                db_path=db_path,
                output_dir=tmp_dir / "out",
                assets_dir=tmp_dir / "assets",
                provider="gemini",
            )
        assert not (tmp_dir / "out" / "01_no_creds.md").exists()

        # 2. Vertex senza `gcloud` -> MissingCredentialsError
        _VERTEX_TOKEN_CACHE.invalidate()

        def _fail_subprocess(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("gcloud non disponibile")

        monkeypatch.setattr(subprocess, "run", _fail_subprocess)
        with pytest.raises(MissingCredentialsError):
            generate_and_verify_chapter(
                spec,
                db_path=db_path,
                output_dir=tmp_dir / "out2",
                assets_dir=tmp_dir / "assets2",
                provider="vertex",
            )
        assert not (tmp_dir / "out2" / "01_no_creds.md").exists()


def test_author_engine_compile_critique_and_auto_revision_loop() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        db_path = tmp_dir / "loop.db"
        conn = init_corpus_db(db_path)

        b1, _ = _seed_book_block(
            conn,
            title="Attilio Frajese - Storia della Matematica",
            surface_domain="matematica",
            content="Nella geometria di Galileo e Cantor la corrispondenza biunivoca permette di confrontare insiemi senza contare preventivamente gli elementi.",
            quote="corrispondenza biunivoca permette di confrontare insiemi senza contare",
            stmt="La corrispondenza biunivoca confronta insiemi senza bisogno di enumerazione preventiva.",
            page=10,
        )
        b2, _ = _seed_book_block(
            conn,
            title="Deitel - Architettura e Basi Numeriche",
            surface_domain="informatica",
            content="Ogni sistema di numerazione posizionale assegna a ciascuna cifra un peso pari a una potenza della base b scelta.",
            quote="sistema di numerazione posizionale assegna a ciascuna cifra un peso",
            stmt="La notazione posizionale pesa ogni cifra secondo le potenze della base.",
            discs=("informatica", "matematica"),
            page=597,
        )
        b3, _ = _seed_book_block(
            conn,
            title="Wittgenstein - Lezioni sui Fondamenti",
            surface_domain="filosofia_epistemologia",
            content="Il segno di uguaglianza esprime una regola simmetrica e transitiva d'equivalenza e non soltanto il comando di eseguire una somma.",
            quote="segno di uguaglianza esprime una regola simmetrica e transitiva",
            stmt="L'uguaglianza è una relazione simmetrica e transitiva di equilibrio.",
            discs=("filosofia_epistemologia", "matematica"),
            page=28,
        )
        conn.close()

        spec = ChapterSpec(
            volume_id="vol1_ofa",
            chapter_number=1,
            slug="pilota_test",
            title="Dall'ovvio al numero",
            subtitle="Corrispondenze, posizioni e simmetria",
            node_ids=("numeri.quantita", "numeri.posizionale", "relazioni.uguaglianza-bilancia"),
            concept_queries=("corrispondenza biunivoca", "posizionale", "uguaglianza"),
            extra_block_pks=(b1, b2, b3),
            drill_keys=("drill_counting_bijection", "drill_positional_value", "drill_equality_balance"),
            svg_diagram_id="balance_and_number_line",
        )

        # Costruiamo 4 paragrafi sostanziosi (>= 500 parole complessive) per superare davvero `min_prose_words=500`
        long_filler = (
            "Quando accostiamo due collezioni finite senza ricorrere al nome verbale dei numeri, eseguiamo una "
            "operazione di appaiamento esatto che precede ogni alfabeto aritmetico: ciascun elemento del primo insieme "
            "trova un unico compagno nel secondo, rendendo osservabile l'invarianza rispetto alla disposizione spaziale "
            "e preparando l'astrazione matematica delle classi di equipotenza tra insiemi finiti e infiniti."
        )
        author_calls: list[str] = []
        critic_calls: list[str] = []

        def fake_author(prompt: str, schema: Mapping[str, Any]) -> Mapping[str, Any]:
            author_calls.append(prompt)
            attempt = len(author_calls)
            extra_bug = "In questo nodo P0.5 vediamo subito un dettaglio." if attempt == 1 else "L'equilibrio dei due membri resta invariato applicando la medesima operazione a destra e a sinistra."
            return {
                "opening_epigraph_quote_id": "Q1",
                "sections": [
                    {
                        "heading": "Contare senza parole: l'appaiamento uno a uno",
                        "paragraphs": [
                            f"La radice più profonda del numero non risiede nei simboli tracciati su carta, bensì nel gesto operativo di accostare due insiemi. La corrispondenza biunivoca permette di stabilire l'equipotenza senza enumerazione preliminare [Q1]. {long_filler}",
                            f"Formalmente, data una coppia di insiemi $A$ e $B$, una funzione $f: A \\to B$ è biiettiva se e soltanto se per ogni $y \\in B$ esiste un unico $x \\in A$ tale che $f(x) = y$. Su insiemi finiti di cardinalità $n$, il numero di biiezioni distinte cresce come $n!$. {long_filler}",
                        ],
                        "include_figure": False,
                    },
                    {
                        "heading": "Il peso della posizione e il valore dello zero",
                        "paragraphs": [
                            f"Passare da semplici tacche a un alfabeto finito di dieci cifre richiede un salto concettuale decisivo: il valore di un simbolo dipende dal posto che occupa [Q2]. In una base $b \\ge 2$, ogni intero positivo $N$ si decompone univocamente nella somma $\\sum_{{k=0}}^m c_k b^k$. {long_filler}",
                        ],
                        "include_figure": True,
                    },
                    {
                        "heading": "L'uguale come bilancia simmetrica",
                        "paragraphs": [
                            f"Un errore diffuso consiste nel leggere il segno $=$ come un comando unidirezionale che produce un risultato a destra. Al contrario, la relazione di uguaglianza istituisce una simmetria rigorosa [Q3]: $a = b \\iff b = a$. {extra_bug} {long_filler}",
                        ],
                        "include_figure": False,
                    },
                ],
                "worked_examples": [
                    {
                        "title": "Equazione sulla bilancia",
                        "problem": "Risolvi $3x + 4 = 19$ mantenendo l'equilibrio ad ogni passaggio.",
                        "steps": [
                            "Sottraiamo $4$ a entrambi i membri per isolare il termine con l'incognita: $3x + 4 - 4 = 19 - 4$, ottenendo $3x = 15$.",
                            "Dividiamo entrambi i membri per $3 \\neq 0$, da cui segue $x = 5$.",
                        ],
                        "conclusion": "Sostituendo $x = 5$ nell'espressione iniziale si ottiene $3(5) + 4 = 19$, identità verificata.",
                    }
                ],
                "original_exercises": [
                    {
                        "prompt": "Converti il numero decimale $37$ in base $2$ mostrando i resti delle divisioni successive per $2$.",
                        "solution_sketch": "37 = 1·32 + 0·16 + 0·8 + 1·4 + 0·2 + 1·1 = 100101₂.",
                    }
                ],
                "reconstruction_notes": [
                    "Le formule sommatarie $N = \\sum c_k b^k$ e le regole di equivalenza simmetrica sintetizzano in linguaggio moderno i passaggi dalle fonti."
                ],
            }

        def fake_critic(prompt: str, schema: Mapping[str, Any]) -> Mapping[str, Any]:
            critic_calls.append(prompt)
            if len(critic_calls) == 1:
                return {
                    "approved": False,
                    "summary": "La prima bozza espone un codice interno ed è necessario completare la verifica esplicita sulla simmetria.",
                    "issues": [
                        {
                            "category": "logical_leap",
                            "severity": "major",
                            "excerpt": "L'uguaglianza istituisce una simmetria rigorosa",
                            "explanation": "Serve esplicitare l'invarianza quando si somma la medesima quantità ai due membri.",
                            "suggested_fix": "Aggiungere l'enunciato sull'invarianza dei due piatti della bilancia.",
                        }
                    ],
                }
            return {
                "approved": True,
                "summary": "Prosa adulta continua, formalismo completo, citazioni esatte e zero salti logici.",
                "issues": [],
            }

        res = generate_and_verify_chapter(
            spec,
            db_path=db_path,
            output_dir=tmp_dir / "out",
            assets_dir=tmp_dir / "assets",
            author_llm=fake_author,
            critic_llm=fake_critic,
            max_revisions=2,
        )

        assert res.attempts == 2
        assert res.status == "pubblicato"
        assert res.critique.approved is True
        assert res.footnotes_used == 3
        assert len(res.figures_included) >= 1
        assert "P0.5" in author_calls[1] or "Errori" in author_calls[1].upper() or "BLOCCANTI" in author_calls[1]
        assert res.chapter_path.exists()
        assert run_deterministic_chapter_audit(res.chapter_path, db_path=db_path) == []
        assert verifica_scheda(res.chapter_path, db_path=db_path) == []


@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_live_pilot_dossier_assembly_and_published_chapter_verification() -> None:
    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dossier = assemble_chapter_dossier(
                conn,
                PILOT_CHAPTER_SPEC,
                chapter_dir=Path(tmp) / "vol1",
                assets_dir=Path(tmp) / "assets",
                figures_root=DEFAULT_FIGURES_DIR,
            )
            assert len(dossier.quotes) >= 8
            assert len({q.book_pk for q in dossier.quotes}) >= 4
            assert len(dossier.sympy_drills) == 4
            assert dossier.figures and dossier.figures[0].path.exists()
    finally:
        conn.close()

    pilot_path = DEFAULT_BOOKS_DIR / "vol1_ofa" / "01_dall_ovvio_al_numero.md"
    if pilot_path.exists():
        assert verifica_scheda(pilot_path, db_path=DEFAULT_DB_PATH) == []
        assert run_deterministic_chapter_audit(pilot_path, db_path=DEFAULT_DB_PATH) == []


def test_catalog_full_dag_coverage_and_specific_sympy_drills() -> None:
    dag = load_unified_dag()
    non_g_nodes = {nid for nid, n in dag["nodes"].items() if n.get("layer", 3) < 3}
    covered = {nid for sp in (*VOL1_CHAPTER_SPECS, *VOL2_CHAPTER_SPECS) for nid in sp.node_ids}
    assert non_g_nodes - covered == set()

    for sp in (*VOL1_CHAPTER_SPECS, *VOL2_CHAPTER_SPECS):
        assert sp.svg_diagram_id in CONTROLLED_SVG_IDS
        assert sp.drill_keys

    # Verifica che ogni drill_key nel DAG produca esercizi specifici del proprio dominio (zero ripiego su equazione lineare)
    for nid, node in dag["nodes"].items():
        dk = node.get("drill_key")
        if not dk:
            continue
        drills = generate_drill_set(nid, dk, count=3, seed=42)
        assert len(drills) == 3
        for d in drills:
            assert grade_drill_answer(d["expected"], d["expected"])["is_correct"] is True
            if dk not in {"drill_equality_balance", "drill_linear_equation"}:
                assert "Isola x mantenendo in equilibrio" not in d["prompt"], (nid, dk, d["prompt"])


@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_volume1_all_11_published_chapters_and_30_ofa_questions() -> None:
    vol1_dir = DEFAULT_BOOKS_DIR / "vol1_ofa"
    for sp in VOL1_CHAPTER_SPECS:
        ch_path = vol1_dir / f"{sp.chapter_number:02d}_{sp.slug}.md"
        assert ch_path.exists(), f"Capitolo Volume I mancante: {ch_path}"
        meta, _ = leggi_scheda(ch_path)
        assert meta.get("stato") == "pubblicato", f"{ch_path.name} ha stato={meta.get('stato')!r}"
        assert verifica_scheda(ch_path, db_path=DEFAULT_DB_PATH) == []
        assert run_deterministic_chapter_audit(ch_path, db_path=DEFAULT_DB_PATH) == []

    ofa_path = vol1_dir / "ofa_30_quesiti_reali.json"
    assert ofa_path.exists()
    ofa_data = json.loads(ofa_path.read_text(encoding="utf-8"))
    assert ofa_data["count"] == 30
    assert len(ofa_data["questions"]) == 30

    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        for q in ofa_data["questions"]:
            row = conn.execute(
                "SELECT is_active, block_uid, norm_content FROM blocks WHERE block_pk = ?",
                (q["block_pk"],),
            ).fetchone()
            assert row is not None and int(row["is_active"]) == 1
            assert row["block_uid"] == q["block_uid"]
            assert normalize_for_match(q["question_excerpt"]) in row["norm_content"]
    finally:
        conn.close()


def test_open_access_ingest_append_only_idempotent_offline() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "corpus.db"
        conn = init_corpus_db(db_path)
        try:
            existing_pk, existing_uid = _seed_book_block(
                conn,
                title="Testo Storico Esistente",
                surface_domain="matematica",
                content=(
                    "Il principio di invarianza stabilisce che una relazione valida permane "
                    "sotto tutte le trasformazioni ammissibili del sistema fisico considerato."
                ),
                quote="una relazione valida permane sotto tutte le trasformazioni ammissibili del sistema fisico",
                stmt="Definizione storica di invarianza su trasformazioni ammissibili.",
                page=12,
            )
        finally:
            conn.close()

        sample_work = OpenAccessWorkDraft(
            book_uid="oa_test_append_only_work",
            title="Manuale Aperto di Sicurezza e Testing (€0)",
            author="Autori Open Access",
            year=2025,
            surface_domain="informatica",
            language="it",
            blocks=(
                OpenAccessBlockDraft(
                    page=1,
                    section_title="Principi di testing sistematico",
                    content=(
                        "Ogni suite di verifica automatica deve isolare i casi limite "
                        "e riprodurre deterministicamente le condizioni di errore senza effetti collaterali esterni."
                    ),
                ),
                OpenAccessBlockDraft(
                    page=2,
                    section_title="Validazione degli ingressi HTTP",
                    content=(
                        "Le query parametrizzate separano in modo netto la struttura sintattica del comando SQL "
                        "dai dati forniti dall'utente attraverso i moduli di rete."
                    ),
                ),
            ),
        )

        first = ingest_open_access_sources(
            db_path,
            preloaded_works=[sample_work],
            extract_v22=False,
        )
        assert first["works_processed"] == 1
        assert first["books_inserted"] == 1
        assert first["blocks_inserted"] == 2
        assert first["oa_blocks_total"] == 2
        assert first["oa_blocks_pending_v22"] == 2
        assert first["active_blocks_after"] == 3
        assert first["fts_rows_after"] == 3

        second = ingest_open_access_sources(
            db_path,
            preloaded_works=[sample_work],
            extract_v22=False,
        )
        assert second["books_inserted"] == 0
        assert second["blocks_inserted"] == 0
        assert second["oa_blocks_total"] == 2
        assert second["oa_blocks_pending_v22"] == 2
        assert second["active_blocks_after"] == 3
        assert second["fts_rows_after"] == 3

        check_conn = connect_corpus_db(db_path, read_only=True)
        try:
            orig = check_conn.execute(
                "SELECT block_pk, block_uid, source_origin, is_active FROM blocks WHERE block_pk = ?",
                (existing_pk,),
            ).fetchone()
            assert orig is not None
            assert int(orig["block_pk"]) == existing_pk
            assert orig["block_uid"] == existing_uid
            assert orig["source_origin"] == "test"
            assert int(orig["is_active"]) == 1

            oa_rows = check_conn.execute(
                "SELECT block_pk, source_origin FROM blocks WHERE source_origin = 'open_access_oa' ORDER BY block_pk"
            ).fetchall()
            assert len(oa_rows) == 2
            assert all(r["source_origin"] == "open_access_oa" for r in oa_rows)
        finally:
            check_conn.close()


@pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="pack_corpus.db non presente")
def test_volume2_all_9_published_chapters_and_open_access_indexed() -> None:
    vol2_dir = DEFAULT_BOOKS_DIR / "vol2_secai"
    for sp in VOL2_CHAPTER_SPECS:
        ch_path = vol2_dir / f"{sp.chapter_number:02d}_{sp.slug}.md"
        assert ch_path.exists(), f"Capitolo Volume II mancante: {ch_path}"
        meta, _ = leggi_scheda(ch_path)
        assert meta.get("stato") == "pubblicato", f"{ch_path.name} ha stato={meta.get('stato')!r}"
        assert verifica_scheda(ch_path, db_path=DEFAULT_DB_PATH) == []
        assert run_deterministic_chapter_audit(ch_path, db_path=DEFAULT_DB_PATH) == []

    conn = connect_corpus_db(DEFAULT_DB_PATH, read_only=True)
    try:
        assert len(ALL_OA_BOOK_UIDS) == 8
        for uid in ALL_OA_BOOK_UIDS:
            row = conn.execute(
                """
                SELECT bk.book_pk, bk.source_kind, bk.is_active,
                       COUNT(DISTINCT bl.block_pk) AS n_blocks,
                       COUNT(eu.unit_pk) AS n_units
                FROM books bk
                JOIN blocks bl ON bl.book_pk = bk.book_pk
                             AND bl.is_active = 1
                             AND bl.source_origin = 'open_access_oa'
                JOIN epistemic_units eu ON eu.block_pk = bl.block_pk
                WHERE bk.book_uid = ?
                  AND bk.is_active = 1
                  AND bk.source_kind = 'open_access'
                GROUP BY bk.book_pk
                """,
                (uid,),
            ).fetchone()
            assert row is not None, f"Opera Open-Access mancante o senza unità epistemiche: {uid}"
            assert int(row["n_blocks"]) >= 1
            assert int(row["n_units"]) >= 1
    finally:
        conn.close()
