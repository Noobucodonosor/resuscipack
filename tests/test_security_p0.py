"""Test di sicurezza P0 e portabilità CI (ADR-0005: TASK-SEC-01, TASK-SEC-02, TASK-QA-01)."""

from __future__ import annotations

from pathlib import Path
import time

from resuscipack.corpus.schema import init_corpus_db
from resuscipack.curriculum.drills_sympy import grade_drill_answer
from resuscipack.workbench.app import create_app


def test_sympy_parser_blocks_rce_and_dos() -> None:
    malicious_payloads = [
        "__import__('os').system('echo pwn')",
        "().__class__.__mro__[1].__subclasses__()",
        "eval('1+1')",
        "open('/etc/passwd').read()",
        "9**9**9**9",
        "factorial(10**9)",
        "x" * 300,
    ]
    t0 = time.monotonic()
    for payload in malicious_payloads:
        res = grade_drill_answer(payload, "42")
        assert res["is_correct"] is False
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"Troppo lento sui payload DoS: {elapsed:.2f}s"

    # Verifica che la matematica legittima continui a funzionare
    assert grade_drill_answer("7/20", "0.35")["is_correct"] is True
    assert grade_drill_answer("(x-1)*(x+1)", "x^2 - 1")["is_correct"] is True


def test_api_search_escapes_stored_xss_in_snippet(tmp_path: Path) -> None:
    db_path = tmp_path / "xss_corpus.db"
    conn = init_corpus_db(db_path)
    conn.execute(
        """
        INSERT INTO books (
            book_uid, title, author, year, surface_domain, source_kind, source_path, is_active
        ) VALUES ('bk_xss', 'Test XSS Book', 'Autore Test', 2024, 'informatica', 'epub', '/tmp/x.epub', 1)
        """
    )
    book_pk = conn.execute("SELECT book_pk FROM books WHERE book_uid = 'bk_xss'").fetchone()[0]
    content = 'Testo sicuro con teorema <script>alert("xss")</script> e <img src=x onerror=alert(1)>.'
    conn.execute(
        """
        INSERT INTO blocks (
            block_uid, book_pk, book_title, source_origin, page_start, page_end,
            section_title, content, norm_content, char_count, est_tokens, block_role, is_active
        ) VALUES (
            'blk_xss_1', ?, 'Test XSS Book', 'from_epub', 1, 1,
            'Sezione Sicurezza', ?, ?, ?, 15, 'body', 1
        )
        """,
        (book_pk, content, content.lower(), len(content)),
    )
    conn.commit()
    conn.close()

    app = create_app(corpus_db_path=db_path, state_db_path=tmp_path / "state.db")
    client = app.test_client()
    resp = client.get("/api/search?q=teorema")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    snip = data["results"][0]["snippet_html"]
    assert "<mark>teorema</mark>" in snip
    assert "<script>" not in snip
    assert "&lt;script&gt;" in snip
    assert "<img " not in snip
    assert "&lt;img " in snip
