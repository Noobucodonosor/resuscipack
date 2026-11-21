"""Test unitari per la pipeline lossless PDF -> Markdown (ADR-0006, TASK-PDFMD-01)."""

from __future__ import annotations

from resuscipack.corpus.pdf_md_pipeline import (
    RESUSCIPACK_MD_PAGE_SCHEMA,
    assemble_canonical_markdown,
    evaluate_page_quality_gate,
)


def test_assemble_canonical_markdown_preserves_all_layers_and_passes_gate() -> None:
    assert "body_markdown" in RESUSCIPACK_MD_PAGE_SCHEMA["properties"]
    assert "footnotes" in RESUSCIPACK_MD_PAGE_SCHEMA["properties"]
    assert "marginalia" in RESUSCIPACK_MD_PAGE_SCHEMA["properties"]
    assert "figures" in RESUSCIPACK_MD_PAGE_SCHEMA["properties"]

    payload = {
        "printed_page": "42",
        "running_header": "CAP. I — STORIA DELLA MATEMATICA GRECA",
        "section_title": "1. Sguardo generale",
        "block_role": "body",
        "body_markdown": (
            "Secondo Proclo[^1], l'espressione $a_n^2 + b_n^2 = c_n^2$ compare già nei testi più antichi "
            "sul rapporto tra *λόγος* e numero.\n\n$$\\sum_{k=1}^{n} k = \\frac{n(n+1)}{2} \\tag{1.4}$$"
        ),
        "footnotes": [
            {"id": "1", "text": "PROCLO, In primum Euclidis Elementorum librum commentarii, p. 65 Friedlein."}
        ],
        "marginalia": ["Cfr. Eudemo, Storia della geometria, fr. 133 Wehrli."],
        "boxes": [{"title": "Nota critica", "body": "L'edizione Frajese conserva la lezione del codice P."}],
        "figures": [
            {
                "label": "Fig. 1.2",
                "caption": "Schema dell'applicazione delle aree.",
                "internal_labels": ["AB", "CD", "triangolo rettangolo"],
            }
        ],
        "tables_html": [],
        "continues_on_next_page": True,
    }

    md = assemble_canonical_markdown(payload, figure_urls=["/corpus-figures/bk_demo/page_0042_0.jpg"])
    assert "<!-- p. 42 | header: CAP. I — STORIA DELLA MATEMATICA GRECA -->" in md
    assert "[^p42-1]" in md
    assert "[^p42-1]: PROCLO" in md
    assert "> [!margin] Cfr. Eudemo" in md
    assert "> [!box] **Nota critica**" in md
    assert "![Fig. 1.2: Schema dell'applicazione delle aree.](/corpus-figures/bk_demo/page_0042_0.jpg)" in md
    assert "*Etichette interne figura:* AB, CD, triangolo rettangolo" in md
    assert "<!-- continues_on_next_page: true -->" in md

    gate = evaluate_page_quality_gate(md, expected_figure_count=1)
    assert gate["passed"] is True
    assert gate["route"] == "accept"


def test_quality_gate_rejects_broken_latex_orphan_footnotes_garbled_and_2up_mix() -> None:
    g_empty = evaluate_page_quality_gate("   ")
    assert g_empty["passed"] is False
    assert g_empty["route"] == "escalate_vision"

    g_latex = evaluate_page_quality_gate("Testo abbastanza lungo per superare il limite minimo ma con $$x^2 + 1 rotto.")
    assert "latex_display_non_bilanciato" in g_latex["issues"]

    g_fn = evaluate_page_quality_gate(
        "Un testo con richiamo sospeso[^p9-2] ma senza la nota corrispondente in fondo alla pagina."
    )
    assert any(x.startswith("note_senza_definizione:") for x in g_fn["issues"])

    g_garbled = evaluate_page_quality_gate("Testo con carattere corrotto \ufffd che rovina la formula matematica.")
    assert "caratteri_corrotti_o_controllo" in g_garbled["issues"]

    g_fig = evaluate_page_quality_gate(
        "Pagina che cita una figura ma l'estrazione immagine e didascalia non compaiono nel testo finale.",
        expected_figure_count=2,
    )
    assert "figure_mancanti:0/2" in g_fig["issues"]

    g_2up = evaluate_page_quality_gate(
        "\n".join(
            [
                "Colonna sinistra mescolata        Colonna destra mescolata sulla stessa riga",
                "Altra frase a sinistra           Altra frase a destra senza separazione",
                "Terza riga sinistra              Terza riga destra",
                "Quarta riga sinistra             Quarta riga destra",
                "Quinta riga sinistra             Quinta riga destra",
                "Sesta riga sinistra              Sesta riga destra",
            ]
        )
    )
    assert "possibile_mescolamento_colonne_2up" in g_2up["issues"]
