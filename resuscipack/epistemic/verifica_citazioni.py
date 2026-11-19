#!/usr/bin/env python3
"""Validatore deterministico v3 a 6 Gate per le schede studio (`data/cards/*.md`) contro `pack_corpus.db`.

I 6 Gate obbligatori (ADR-0002, TASK-EPIST-02):
  Gate 1 (`block_identity`): ogni fonte referenziata ha `block_pk` e `block_uid` esistenti
      e attivi (`is_active=1`) in `pack_corpus.db` (aperto sempre in URI `mode=ro`).
  Gate 2 (`verbatim_span`): ogni citazione ha tra 4 e 25 parole e compare testualmente
      (dopo normalizzazione NFKC/sillabazione/virgolette/spazi) in `blocks.norm_content`.
  Gate 3 (`no_orphan_footnotes`): corrispondenza biunivoca esatta tra rimandi `[^n]` nel
      corpo e note `[^n]:` definite (zero note orfane, zero rimandi rotti).
  Gate 4 (`labeled_enunciati`): sezione `## Enunciati` presente e 100% delle sue voci `- `
      etichettate `[Definizione|Assioma|Teorema|Convenzione]` con `*Giustificazione:*` non vuota.
  Gate 5 (`zero_dangling_deixis`): zero rinvii ciechi o deissi pendenti nelle ancore e negli
      enunciati (`ivi`, `ibidem`, `op. cit.`, `il Nostro`, `suddetto autore`, ecc.).
  Gate 6 (`wrong_book_bridge_rigor`): se la scheda include un ponte "Libro Sbagliato"
      (in YAML o sezione Markdown), esige mappatura 1-a-1 di almeno 2 grandezze (`↔` / `<->`)
      e catena inferenziale di almeno 3 passi con rimando `[^n]` valido.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from .schema_v21 import normalizza_testo

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pack_corpus.db"
DEFAULT_CARDS_DIR = Path(__file__).resolve().parents[2] / "data" / "cards"

MIN_PAROLE = 4
MAX_PAROLE = 25

# Rimandi nel testo (applicato dopo la rimozione delle righe di definizione `^\[\^\d+\]:`):
# riconosce `[^1]` ovunque nel corpo (anche prima di `:` a fine frase, es. `nel varco [^2]:`)
# oppure `[1]` non seguito da `:` o `(`.
_FOOTNOTE_REF_RE = re.compile(r"\[\^(\d+)\]|(?<!\^)\[(\d+)\](?!:|\()")

# Formato contrattuale della riga nota:
# [^1]: [block_pk=12345 | block_uid=blk_...] «citazione esatta 4-25 parole» — Autore, Titolo (p. N)
_NOTE_DEF_LINE_RE = re.compile(r"^\[\^(\d+)\]:\s*(.+)$", flags=re.MULTILINE)
_CONTRACT_TAG_RE = re.compile(
    r"\[\s*block_pk\s*=\s*(\d+)\s*\|\s*block_uid\s*=\s*([A-Za-z0-9_:-]+)\s*\]"
)
# Estrae la citazione racchiusa tra «...» (gestendo eventuali «...» annidati) o "..." prima di ` — `
_GUILLEMET_QUOTE_RE = re.compile(r"«(.+)»(?=\s*(?:—|--|-|\(|\[|$))")
_STRAIGHT_QUOTE_RE = re.compile(r'"([^"]{10,})"(?=\s*(?:—|--|-|\(|\[|$))')

_ENUNCIATO_RE = re.compile(
    r"^-\s+\*\*\[(Definizione|Assioma|Teorema|Convenzione)\]\*\*\s+.+?"
    r"(?:—|--|-|\n)\s*(?:\*+Giustificazione:\*+|\*Giustificazione\*:\s*)\s*\S",
    flags=re.DOTALL,
)

_BLIND_CITATION_DEIXIS_RE = re.compile(
    r"\b(?:ivi|ibidem|op\.\s*cit\.|loc\.\s*cit\.|vedi\s+sopra|vedi\s+sotto|cfr\.\s+pag)\b",
    flags=re.IGNORECASE,
)
_EDITORIAL_DEIXIS_RE = re.compile(
    r"(?:^\s*-\s*\*\*\[[^\]]+\]\*\*\s*(?:egli|ella|costui)\b"
    r"|\b(?:il nostro|suddetto autore|questo documento parla|questa scheda dice"
    r"|ivi|ibidem|op\.\s*cit\.)\b)",
    flags=re.IGNORECASE | re.MULTILINE,
)

_MAPPING_ARROW_RE = re.compile(r"(?:↔|<->|↦|<==>|—>|->)")

_BOOK_DEBUG_JARGON_RE = re.compile(
    r"(?:\bblock_pk\s*=|\bblock_uid\s*=|\bStrato\s+[0-3]\b|\bGate\s+[1-6]\b"
    r"|\bP[0-6]\.\d+\b|\bG[0-2]\d\b|\bscore\s*[:=]?\s*0\.\d+|\bop_tags?\b|\bTASK-[A-Z]+-\d+\b)",
    flags=re.IGNORECASE,
)
_BOOK_CARD_HEADING_RE = re.compile(
    r"^##\s+(?:Contesto|Concetti|Enunciati|Decisione|Alternative|Conseguenze)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LATEX_FORMULA_RE = re.compile(r"\$\$[^$]+\$\$|(?<!\$)\$(?!\$)[^\$\n]+?(?<!\$)\$(?!\$)", flags=re.DOTALL)


def _strip_code_and_images_for_refs(text: str) -> str:
    cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned)
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", cleaned)
    return cleaned


def normalizza(testo: str) -> str:
    """Alias retrocompatibile della normalizzazione canonica."""
    return normalizza_testo(testo)


@dataclass
class CitationRef:
    note_num: int
    block_pk: Optional[int]
    block_uid: Optional[str]
    quote: str


@dataclass
class ValidationReport:
    card_path: Path
    gate_errors: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "gate1_block_identity": [],
            "gate2_verbatim_span": [],
            "gate3_no_orphan_footnotes": [],
            "gate4_labeled_enunciati": [],
            "gate5_zero_dangling_deixis": [],
            "gate6_wrong_book_bridge_rigor": [],
        }
    )

    @property
    def ok(self) -> bool:
        return all(not errs for errs in self.gate_errors.values())

    @property
    def all_errors(self) -> List[str]:
        out: List[str] = []
        for gate, errs in self.gate_errors.items():
            for e in errs:
                out.append(f"[{gate}] {e}")
        return out


def _open_ro_db(db_path: Path | str) -> sqlite3.Connection:
    p = Path(db_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Database corpus non trovato: {p}")
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def leggi_scheda(path: Path | str) -> Tuple[Dict[str, Any], str]:
    """Legge una scheda Markdown con o senza frontmatter YAML."""
    testo = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", testo, flags=re.DOTALL)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            raise ValueError("Il frontmatter YAML deve essere una mappa chiave-valore")
        return meta, m.group(2)
    return {}, testo


def _extract_quote_from_note_line(rest: str) -> str:
    m_g = _GUILLEMET_QUOTE_RE.search(rest)
    if m_g:
        return m_g.group(1).strip()
    m_s = _STRAIGHT_QUOTE_RE.search(rest)
    if m_s:
        return m_s.group(1).strip()
    return ""


def _parse_citations(meta: Mapping[str, Any], corpo: str) -> Tuple[List[CitationRef], Dict[int, str], List[str]]:
    """Estrae l'elenco unificato di citazioni da `[^n]: ...` e dall'eventuale YAML `fonti:`."""
    parse_errors: List[str] = []
    note_defs: Dict[int, str] = {}
    for m in _NOTE_DEF_LINE_RE.finditer(corpo):
        num = int(m.group(1))
        if num in note_defs:
            parse_errors.append(f"nota [^{num}] definita più di una volta")
        note_defs[num] = m.group(2).strip()

    yaml_fonti = meta.get("fonti")
    refs: List[CitationRef] = []

    if isinstance(yaml_fonti, list) and yaml_fonti:
        for idx, item in enumerate(yaml_fonti, start=1):
            if not isinstance(item, Mapping):
                parse_errors.append(f"fonte YAML [{idx}] non è un dizionario")
                continue
            b_pk_raw = item.get("block_pk")
            b_uid_raw = item.get("block_uid")
            quote_raw = str(item.get("citazione") or item.get("quote") or "").strip()

            # Integra da riga nota `[^idx]: [block_pk=... | block_uid=...] «...»` se presente
            note_line = note_defs.get(idx, "")
            m_tag = _CONTRACT_TAG_RE.search(note_line)
            if m_tag:
                tag_pk = int(m_tag.group(1))
                tag_uid = m_tag.group(2).strip()
                if b_pk_raw is not None and int(b_pk_raw) != tag_pk:
                    parse_errors.append(
                        f"fonte [{idx}]: conflitto block_pk tra YAML ({b_pk_raw}) e nota [^{idx}] ({tag_pk})"
                    )
                if b_uid_raw and str(b_uid_raw).strip() != tag_uid:
                    parse_errors.append(
                        f"fonte [{idx}]: conflitto block_uid tra YAML ({b_uid_raw}) e nota [^{idx}] ({tag_uid})"
                    )
                b_pk_raw = b_pk_raw if b_pk_raw is not None else tag_pk
                b_uid_raw = b_uid_raw or tag_uid
            if not quote_raw and note_line:
                quote_raw = _extract_quote_from_note_line(note_line)

            try:
                b_pk = int(b_pk_raw) if b_pk_raw is not None else None
            except (TypeError, ValueError):
                b_pk = None
            b_uid = str(b_uid_raw).strip() if b_uid_raw else None
            refs.append(CitationRef(note_num=idx, block_pk=b_pk, block_uid=b_uid, quote=quote_raw))
    else:
        for num in sorted(note_defs):
            line = note_defs[num]
            m_tag = _CONTRACT_TAG_RE.search(line)
            b_pk = int(m_tag.group(1)) if m_tag else None
            b_uid = m_tag.group(2).strip() if m_tag else None
            quote = _extract_quote_from_note_line(line)
            refs.append(CitationRef(note_num=num, block_pk=b_pk, block_uid=b_uid, quote=quote))

    return refs, note_defs, parse_errors


def _sezione(corpo: str, titolo_regex: str, level: str = "##") -> Optional[str]:
    pattern = rf"^{re.escape(level)}\s+(?:{titolo_regex})[ \t]*\n(.*?)(?=^{re.escape(level)}\s+|\Z)"
    m = re.search(pattern, corpo, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else None


def _strip_note_definitions(corpo: str) -> str:
    return re.sub(r"^\[\^\d+\]:.*$", "", corpo, flags=re.MULTILINE)


def verifica_scheda_report(
    path: Path | str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> ValidationReport:
    """Esegue i 6 Gate deterministici sulla scheda `path` contro `db_path` in sola lettura."""
    card_path = Path(path)
    report = ValidationReport(card_path=card_path)

    try:
        meta, corpo = leggi_scheda(card_path)
    except Exception as exc:
        report.gate_errors["gate1_block_identity"].append(f"Errore parsing scheda: {exc}")
        return report

    refs, note_defs, parse_errs = _parse_citations(meta, corpo)
    report.gate_errors["gate1_block_identity"].extend(parse_errs)

    if not refs:
        report.gate_errors["gate1_block_identity"].append(
            "Nessuna fonte/nota citazionale trovata nella scheda"
        )

    # Gate 1 & Gate 2: Identità block_pk/block_uid attivo + match verbatim 4-25 parole
    try:
        conn = _open_ro_db(db_path)
    except Exception as exc:
        report.gate_errors["gate1_block_identity"].append(str(exc))
        conn = None

    try:
        for ref in refs:
            label = f"[^{ref.note_num}]"
            if ref.block_pk is None or not ref.block_uid:
                report.gate_errors["gate1_block_identity"].append(
                    f"{label}: block_pk o block_uid mancante (richiesto formato [block_pk=... | block_uid=...])"
                )
            if not ref.quote:
                report.gate_errors["gate2_verbatim_span"].append(
                    f"{label}: citazione verbatim tra «...» mancante"
                )
            else:
                words = ref.quote.split()
                if not (MIN_PAROLE <= len(words) <= MAX_PAROLE):
                    report.gate_errors["gate2_verbatim_span"].append(
                        f"{label}: citazione di {len(words)} parole (ammesse {MIN_PAROLE}–{MAX_PAROLE})"
                    )
                if _BLIND_CITATION_DEIXIS_RE.search(ref.quote):
                    report.gate_errors["gate5_zero_dangling_deixis"].append(
                        f"{label}: citazione contiene rinvio bibliografico opaco: {ref.quote!r}"
                    )

            if conn is not None and ref.block_pk is not None:
                row = conn.execute(
                    "SELECT block_pk, block_uid, is_active, content, norm_content FROM blocks WHERE block_pk = ?",
                    (ref.block_pk,),
                ).fetchone()
                if row is None:
                    report.gate_errors["gate1_block_identity"].append(
                        f"{label}: block_pk={ref.block_pk} inesistente in pack_corpus.db"
                    )
                else:
                    if int(row["is_active"]) != 1:
                        report.gate_errors["gate1_block_identity"].append(
                            f"{label}: block_pk={ref.block_pk} non è attivo (is_active={row['is_active']})"
                        )
                    if ref.block_uid and str(row["block_uid"]) != ref.block_uid:
                        report.gate_errors["gate1_block_identity"].append(
                            f"{label}: block_uid={ref.block_uid!r} non coincide con DB ({row['block_uid']!r})"
                        )
                    if ref.quote:
                        norm_q = normalizza_testo(ref.quote)
                        haystack = row["norm_content"] or normalizza_testo(row["content"])
                        if norm_q not in haystack:
                            report.gate_errors["gate2_verbatim_span"].append(
                                f"{label}: citazione non trovata verbatim in block_pk={ref.block_pk}: {ref.quote!r}"
                            )
    finally:
        if conn is not None:
            conn.close()

    # Gate 3: Zero note orfane e zero rimandi pendenti
    corpo_senza_def = _strip_note_definitions(corpo)
    corpo_refs_scan = _strip_code_and_images_for_refs(corpo_senza_def)
    used_nums = {
        int(m.group(1) or m.group(2)) for m in _FOOTNOTE_REF_RE.finditer(corpo_refs_scan)
    }
    defined_nums = set(note_defs.keys()) | {r.note_num for r in refs}

    for r in refs:
        if r.note_num not in note_defs:
            report.gate_errors["gate3_no_orphan_footnotes"].append(
                f"fonte [{r.note_num}] priva di riga definizione [^{r.note_num}]: nella sezione Note/Apparato"
            )
    for n in sorted(used_nums - defined_nums):
        report.gate_errors["gate3_no_orphan_footnotes"].append(
            f"rimando [^{n}] nel testo senza nota [^{n}]: definita"
        )
    for n in sorted(defined_nums - used_nums):
        report.gate_errors["gate3_no_orphan_footnotes"].append(
            f"nota [^{n}]: definita ma orfana (mai richiamata nel corpo)"
        )

    is_book_chapter = str(meta.get("tipo", "")).strip().lower() == "capitolo_libro"

    if is_book_chapter:
        # Modalità Capitolo Continuo (TASK-BOOK-01): apparato a 3 colori, formalismo LaTeX, zero gergo interno, figure valide
        sez_apparato = _sezione(corpo, r"Apparato\s+delle\s+fonti", level="##")
        if sez_apparato is None:
            report.gate_errors["gate4_labeled_enunciati"].append(
                "Sezione '## Apparato delle fonti' mancante nel capitolo libro"
            )
        else:
            required_colors = (
                (r"\[\s*Verificato\s+sul\s+testo\s*\]", "### [Verificato sul testo]"),
                (
                    r"\[\s*Ricostruzione\s+matematica(?:\s*/\s*addestramento)?\s*\]",
                    "### [Ricostruzione matematica / addestramento]",
                ),
                (r"\[\s*Esercizi\s+originali\s*\]", "### [Esercizi originali]"),
            )
            for pat_col, label_col in required_colors:
                sub = _sezione(sez_apparato, pat_col, level="###")
                if sub is None or not sub.strip():
                    report.gate_errors["gate4_labeled_enunciati"].append(
                        f"Sottosezione mancante o vuota in Apparato delle fonti: '{label_col}'"
                    )

        prose_before_app = re.split(
            r"^##\s+Apparato\s+delle\s+fonti\b",
            corpo_senza_def,
            maxsplit=1,
            flags=re.IGNORECASE | re.MULTILINE,
        )[0]
        if not _LATEX_FORMULA_RE.search(prose_before_app):
            report.gate_errors["gate4_labeled_enunciati"].append(
                "Capitolo libro privo di sviluppo simbolico/formale LaTeX ($...$ o $$...$$)"
            )
        m_jargon = _BOOK_DEBUG_JARGON_RE.search(prose_before_app)
        if m_jargon:
            report.gate_errors["gate4_labeled_enunciati"].append(
                f"Gergo interno da sviluppatore rilevato nella prosa per il lettore: {m_jargon.group(0)!r}"
            )
        m_card_h = _BOOK_CARD_HEADING_RE.search(prose_before_app)
        if m_card_h:
            report.gate_errors["gate4_labeled_enunciati"].append(
                f"Intestazione rigida da scheda legacy non ammessa nei capitoli continui: {m_card_h.group(0)!r}"
            )

        repo_root = Path(__file__).resolve().parents[2]
        for m_img in _MD_IMAGE_RE.finditer(corpo):
            raw_target = m_img.group(1).strip()
            if raw_target.startswith(("http://", "https://", "data:")):
                continue
            cand_rel = (card_path.parent / raw_target).resolve()
            cand_root = (repo_root / raw_target).resolve()
            if not cand_rel.exists() and not cand_root.exists():
                report.gate_errors["gate4_labeled_enunciati"].append(
                    f"Immagine/figura locale mancante su disco: {raw_target!r}"
                )

        if _EDITORIAL_DEIXIS_RE.search(corpo_refs_scan):
            report.gate_errors["gate5_zero_dangling_deixis"].append(
                "Il capitolo contiene deissi editoriali opache ('il Nostro', 'suddetto autore', 'ivi', 'ibidem')"
            )
    else:
        # Gate 4 legacy (data/cards/*.md): 100% voci in `## Enunciati` etichettate + giustificate
        sez_enunciati = _sezione(corpo, r"Enunciati")
        if sez_enunciati is None:
            report.gate_errors["gate4_labeled_enunciati"].append("Sezione '## Enunciati' mancante")
        else:
            voci = [v.strip() for v in re.split(r"\n(?=-\s+)", sez_enunciati.strip()) if v.strip().startswith("-")]
            if not voci:
                report.gate_errors["gate4_labeled_enunciati"].append("Sezione '## Enunciati' priva di voci '- '")
            for idx, voce in enumerate(voci, start=1):
                if not _ENUNCIATO_RE.match(voce):
                    preview = " ".join(voce.split())[:80]
                    report.gate_errors["gate4_labeled_enunciati"].append(
                        f"Enunciato #{idx} privo di etichetta [Definizione|Assioma|Teorema|Convenzione] "
                        f"o di '*Giustificazione:*' non vuota: {preview!r}"
                    )

        # Gate 5 legacy: Zero deissi pendenti nel testo degli enunciati e delle sintesi
        if sez_enunciati and _EDITORIAL_DEIXIS_RE.search(sez_enunciati):
            report.gate_errors["gate5_zero_dangling_deixis"].append(
                "Sezione '## Enunciati' contiene deissi editoriali opache o rinvii ciechi (es. 'il Nostro', 'ivi', 'ibidem')"
            )
        if _EDITORIAL_DEIXIS_RE.search(corpo_senza_def):
            report.gate_errors["gate5_zero_dangling_deixis"].append(
                "Il corpo della scheda contiene deissi editoriali opache ('il Nostro', 'suddetto autore', 'ivi', 'ibidem')"
            )

    # Gate 6: Rigore Ponte "Libro Sbagliato" (se presente in YAML o in sezione Markdown)
    wb_yaml = meta.get("libro_sbagliato") or meta.get("wrong_book")
    wb_md = _sezione(corpo, r"[^\n]*Libro Sbagliato[^\n]*", level="##") or _sezione(
        corpo, r"[^\n]*Libro Sbagliato[^\n]*", level="###"
    )

    if wb_yaml is not None or wb_md is not None:
        # Verifica mappatura 1-a-1 (>= 2 coppie) e catena inferenziale (>= 3 passi)
        mappings_count = 0
        steps_count = 0
        has_citation_anchor = False

        if isinstance(wb_yaml, Mapping):
            raw_map = wb_yaml.get("mappatura") or wb_yaml.get("mapping") or {}
            if isinstance(raw_map, Mapping):
                mappings_count = max(mappings_count, sum(1 for k, v in raw_map.items() if str(k).strip() and str(v).strip()))
            elif isinstance(raw_map, list):
                mappings_count = max(mappings_count, len(raw_map))
            raw_steps = wb_yaml.get("catena_inferenziale") or wb_yaml.get("chain_steps") or []
            if isinstance(raw_steps, list):
                steps_count = max(steps_count, sum(1 for s in raw_steps if len(str(s).strip()) >= 10))
            if wb_yaml.get("block_pk") or wb_yaml.get("nota"):
                has_citation_anchor = True

        if wb_md:
            arrow_lines = [
                ln for ln in wb_md.splitlines() if _MAPPING_ARROW_RE.search(ln)
            ]
            mappings_count = max(mappings_count, len(arrow_lines))
            numbered_steps = re.findall(
                r"^\s*(?:\d+[\.\)]|-\s+\*\*Passo\s+\d+)\s+\S+", wb_md, flags=re.MULTILINE
            )
            steps_count = max(steps_count, len(numbered_steps))
            if _FOOTNOTE_REF_RE.search(wb_md):
                has_citation_anchor = True

        if mappings_count < 2:
            report.gate_errors["gate6_wrong_book_bridge_rigor"].append(
                f"Sezione Libro Sbagliato richiede mappatura 1-a-1 di almeno 2 grandezze con '↔' (trovate {mappings_count})"
            )
        if steps_count < 3:
            report.gate_errors["gate6_wrong_book_bridge_rigor"].append(
                f"Sezione Libro Sbagliato richiede catena inferenziale di almeno 3 passi numerati (trovati {steps_count})"
            )
        if not has_citation_anchor:
            report.gate_errors["gate6_wrong_book_bridge_rigor"].append(
                "Sezione Libro Sbagliato priva di rimando citazionale [^n] al blocco sorgente"
            )

    return report


def verifica_scheda(path: Path | str, *, db_path: Path | str = DEFAULT_DB_PATH) -> List[str]:
    """Restituisce la lista piatta degli errori dei 6 Gate (lista vuota = 100% PASS)."""
    return verifica_scheda_report(path, db_path=db_path).all_errors


def _discover_cards(targets: Sequence[str]) -> List[Path]:
    if targets:
        out: List[Path] = []
        for raw in targets:
            p = Path(raw)
            if p.is_dir():
                out.extend(sorted(f for f in p.rglob("*.md") if not f.name.startswith("_")))
            else:
                out.append(p)
        return out
    if not DEFAULT_CARDS_DIR.exists():
        return []
    return sorted(f for f in DEFAULT_CARDS_DIR.rglob("*.md") if not f.name.startswith("_"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validatore deterministico v3 a 6 Gate per le schede studio di resuscipack."
    )
    parser.add_argument("paths", nargs="*", help="File o cartelle di schede .md (default: data/cards)")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Percorso di pack_corpus.db (aperto in sola lettura mode=ro)",
    )
    args = parser.parse_args(argv)

    cards = _discover_cards(args.paths)
    if not cards:
        print("Nessuna scheda .md trovata da verificare.")
        return 0

    total_errors = 0
    for card in cards:
        rep = verifica_scheda_report(card, db_path=args.db)
        errs = rep.all_errors
        total_errors += len(errs)
        status = "OK " if rep.ok else "ERR"
        print(f"{status} {card}")
        for err in errs:
            print(f"    - {err}")

    print(f"\n{len(cards)} schede verificate, {total_errors} errori totali.")
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
