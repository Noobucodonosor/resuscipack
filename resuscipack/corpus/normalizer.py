"""Normalizzazione deterministica del testo, pulizia artefatti OCR, hashing content-addressed
e classificazione disciplinare/paratestuale per il corpus di `resuscipack`."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

HYPHEN_BREAK_RE = re.compile(r"([a-zA-ZÀ-ÿ]{2,})-\s*\n\s*([a-zA-ZÀ-ÿ]{2,})")
DET_BLOCK_RE = re.compile(r"<\|det\|>([^<\s]+)(?:\s*\[+[^\]]*\]+)?\s*<\|/det\|>(.*)", re.DOTALL)
DET_TAG_RE = re.compile(r"<\|/?det\|>|<\|/?ref\|>|\[\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\]")
WATERMARK_LINE_RE = re.compile(
    r"^(?:Cultura[_\s]+in[_\s]+Ita\d*\s*|"
    r"(?:https?://)?(?:www\.)?scribd\.com/Cultura_in_Ita\d*\S*\s*|"
    r"(?:https?://)?(?:www\.)?scribd\.com/\S+\s*|"
    r"r?t+r?ee?cc?ani(?:,\s*il\s*portale\s*del\s*sapere|\.it)\s*|"
    r"https?://www\.t+r?ee?cc?ani\.it/\S+\s*|"
    r"Dizionario\s+Biografico\s+degli\s+Italiani\s*-\s*stampa\s*|"
    r"<!--\s*Pagina\s+vuota\s*-->\s*)$",
    re.IGNORECASE,
)

# Codici dei manuali utente ASUS Notebook PC multilingua e documenti amministrativi da escludere
ASUS_MULTILANG_CODES = {
    "0402", "0404", "0405", "0406", "0407", "0408", "0409", "040b",
    "040c", "040e", "0410", "0412", "0413", "0414", "0415", "0416",
    "0418", "0419", "041b", "041d", "041f", "0422", "0424", "0804",
    "0816", "081a", "0c0a",
}

ADMIN_NOISE_PATTERNS = (
    "allegato orario serale",
    "visura berretti",
    "welcome aboard 2018",
    "attestato formazione generale",
    "med certificate",
    "griglia 1^prova",
    "modulo assegni",
    "temp_curriculum",
)

# Cloni noti generati dal vecchio bug `.split('.')[0]` o test OCR
KNOWN_DUPLICATE_TITLES = {
    "(Classici UTET) Kelvin (William Thomson), Enrico Bellone (ed",
    "(Classici UTET) Kelvin (William Thomson), Enrico Bellone (ed_searchable",
    "Sheldon M",
    "Campionamento.key",
}


def normalize_for_match(text: str) -> str:
    """Normalizzazione canonica identica a `verifica_citazioni`: NFKC, rimozione soft-hyphen,
    ricucitura sillabazione a fine riga, unificazione apostrofi/virgolette/trattini, lowercase."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\u00ad", "")
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)
    for src, dst in (
        ("’", "'"),
        ("‘", "'"),
        ("«", '"'),
        ("»", '"'),
        ("“", '"'),
        ("”", '"'),
        ("–", "-"),
        ("—", "-"),
    ):
        t = t.replace(src, dst)
    return " ".join(t.lower().split())


def clean_ocr_markdown(raw: str) -> str:
    """Pulisce tag `<|det|>` Baidu Unlimited-OCR, righe di sola filigrana (`Cultura_in_Ita5`, Scribd)
    e ricuce le sillabazioni spezzate a fine riga preservando paragrafi e formule LaTeX."""
    if not raw:
        return ""
    lines_out: list[str] = []
    for raw_line in raw.splitlines():
        s = raw_line.rstrip()
        if not s:
            lines_out.append("")
            continue
        if s.strip() == "<PAGE>":
            continue
        m = DET_BLOCK_RE.match(s)
        if m:
            cat, body = m.group(1).strip().lower(), m.group(2).strip()
            if cat == "image":
                continue
            s = body
        else:
            s = DET_TAG_RE.sub("", s)
        stripped = s.strip()
        if not stripped:
            continue
        if WATERMARK_LINE_RE.match(stripped):
            continue
        lines_out.append(s)

    joined = "\n".join(lines_out)
    joined = HYPHEN_BREAK_RE.sub(r"\1\2", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def make_book_uid(canonical_key: str, source_kind: str) -> str:
    """Genera un `book_uid` deterministico (`bk_<16hex>`)."""
    norm_key = unicodedata.normalize("NFC", canonical_key).strip().lower()
    digest = hashlib.sha256(f"{source_kind}:{norm_key}".encode("utf-8")).hexdigest()[:16]
    return f"bk_{digest}"


def make_block_uid(book_uid: str, page_start: int | None, page_end: int | None, norm_content: str) -> str:
    """Genera un `block_uid` content-addressed deterministico (`blk_<20hex>`)."""
    p_s = page_start if page_start is not None else 0
    p_e = page_end if page_end is not None else p_s
    payload = f"{book_uid}:{p_s}-{p_e}:{norm_content}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"blk_{digest}"


def estimate_bpe_tokens(text: str) -> int:
    """Stima accurata dei token BPE su italiano/inglese/LaTeX (~3.65 caratteri per token)."""
    if not text:
        return 0
    return max(1, int(round(len(text) / 3.65)))


def is_excluded_noise_title(title: str) -> bool:
    """Restituisce True per i 52 manuali ASUS/documenti amministrativi e i 4 cloni `.split('.')[0]`."""
    t_nfc = unicodedata.normalize("NFC", title).strip()
    if t_nfc in KNOWN_DUPLICATE_TITLES:
        return True
    tl = t_nfc.lower()
    if tl in ASUS_MULTILANG_CODES:
        return True
    if tl.startswith(("test_page", "demo_cpu", "demo_mps", "cavalieri_page120_test")):
        return True
    if any(pat in tl for pat in ADMIN_NOISE_PATTERNS):
        return True
    return False


def classify_block_role(content: str, section_title: str = "") -> str:
    """Distingue deterministicamente `'paratext'` (indici analitici, sommari puntinati, colophon),
    `'footnote'` (apparato di note) e `'body'` (testo sostantivo)."""
    sec_low = (section_title or "").strip().lower()
    if any(
        sec_low == k or sec_low.startswith(k + " ")
        for k in ("indice analitico", "indice dei nomi", "bibliografia", "table of contents", "index")
    ):
        return "paratext"

    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not lines:
        return "paratext"

    # Indice con righe di puntini "... 142" o elenchi di numeri di pagina (es. indice dei nomi Geymonat)
    dotted_toc = sum(1 for ln in lines if re.search(r"\.{4,}\s*\d+\s*$", ln))
    index_entries = sum(
        1 for ln in lines if re.search(r",\s*\d+(?:\s*[-–,]\s*\d+){2,}\.?\s*$", ln)
    )
    if len(lines) >= 4 and (dotted_toc / len(lines) >= 0.45 or index_entries / len(lines) >= 0.45):
        return "paratext"

    if len(content) < 90 and any(
        k in content.lower() for k in ("tutti i diritti riservati", "isbn ", "finito di stampare", "copyright ©")
    ):
        return "paratext"

    first_line = lines[0]
    if re.match(r"^(?:\[\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+|\\\(\s*\^\{\s*\d+\s*\}\s*\\\))\s+\S", first_line) and len(content) < 1800:
        return "footnote"

    return "body"


def parse_author_year(title: str) -> tuple[str | None, int | None]:
    """Estrae autore e anno di pubblicazione dal nome standard dei file della biblioteca."""
    t = unicodedata.normalize("NFC", title).strip()
    year_match = re.search(r"\b(1[5-9]\d{2}|20[0-2]\d)\b", t)
    year = int(year_match.group(1)) if year_match else None

    cleaned = re.sub(r"^[\[\(][^\]\)]+[\]\)]\s*", "", t)
    if " - " in cleaned:
        author_part = cleaned.split(" - ", 1)[0].strip()
        if 2 <= len(author_part) <= 90 and not author_part.isdigit():
            return author_part, year
    return None, year


def classify_surface_domain(title: str, sample_text: str = "") -> str:
    """Classifica la disciplina dichiarata del volume (`surface_domain`) per l'inversione del Libro Sbagliato."""
    tl = unicodedata.normalize("NFC", title).lower()
    st = (sample_text or "")[:2500].lower()

    # Storia della scienza / Biografie scientifiche (es. Masini - Marconi, Geymonat)
    if any(k in tl for k in ("marconi", "storia della scienza", "storia della matematica", "storia e filosofia", "histories of the electron", "galileo matematico", "attraverso la storia")):
        return "storia_della_scienza"
    if any(k in tl for k in ("galvani", "medicin", "anatom", "fisiolog", "istolog", "citolog", "vaccin", "primo soccorso", "salute")):
        return "medicina_biologia"
    if any(k in tl for k in ("micolog", "lichen", "piante", "botanic", "angiosperm", "roside", "asterid", "monocotiledon", "pteridophyt", "procariot", "glaucophyt", "spermatophyt", "coniferophyt", "eudicotiledon")):
        return "botanica_scienze_naturali"
    if any(k in tl for k in ("frescobaldi", "rinuccini", "clementi", "madrigal", "music", "sinfonia", "beethoven", "vidolin", "armonia")):
        return "musica_acustica"
    if any(k in tl for k in ("winckelmann", "winklemann", "durer", "dürer", "architettur", "fotografia", "cavaliere inesistente", "favola moderna", "tucidide", "antico elladico", "cicladi", "minoico", "micenei")):
        return "arte_letteratura_antichita"
    if any(k in tl for k in ("descartes", "cartesio", "wittgenstein", "abbagnano", "kant", "aristotel", "platone", "rawls", "hayek", "berlin", "etica", "filosof", "gnoseolog", "scienze umanistiche")):
        return "filosofia_scienze_umane"
    if any(k in tl for k in ("informatic", "python", "java", "programmazione", "algoritm", "calcolatori", "linux", "android", "sql", "database", "network", "security", "sicurezza", "hacker", "cybercrime", "blockchain", "crittograf", "software", "c++", "linguaggio c", "machine learning", "big data", "visual basic", "php", "excel", "arduino")):
        return "informatica"
    if any(k in tl for k in ("matematic", "algebr", "analisi", "calcolo", "geometri", "aritmetic", "cavalieri", "euclid", "insiemi", "probabilit", "statistic", "logica", "boole", "frajese", "dodero", "prodi", "apostol", "amerio", "berzolari", "ross", "lipschutz")):
        return "matematica"
    if any(k in tl for k in ("fisic", "termodinamic", "meccanic", "ottica", "elettro", "kelvin", "maxwell", "volta", "amper", "ampère", "torricelli", "fermi", "boltzmann", "boyle", "laplace", "copernico", "newton", "schwinger", "franceschetti", "ravalico", "amplificator", "impianti", "circuit", "luce", "radio")):
        return "fisica_ingegneria"

    # Fallback su campione testuale
    if any(k in st for k in ("teorema", "dimostrazione", "insieme", "equazione")):
        return "matematica"
    if any(k in st for k in ("algoritmo", "compilatore", "sistema operativo", "codice sorgente")):
        return "informatica"
    if any(k in st for k in ("tensione", "corrente elettrica", "energia cinetica", "campo magnetico")):
        return "fisica_ingegneria"
    if any(k in st for k in ("filosofia", "metafisica", "epistemologia")):
        return "filosofia_scienze_umane"
    return "miscellanea_tecnica"


def detect_language(sample_text: str) -> str:
    """Rileva la lingua prevalente ('it', 'en', 'fr', 'de', 'other') tramite stopword ad alta frequenza."""
    words = re.findall(r"[a-zà-ÿ]+", (sample_text or "")[:4000].lower())
    if not words:
        return "other"
    it_sw = {"della", "delle", "degli", "questo", "questa", "sono", "essere", "anche", "nella", "dalla", "quindi"}
    en_sw = {"the", "and", "that", "with", "from", "this", "which", "their", "have", "been", "between"}
    fr_sw = {"dans", "pour", "avec", "plus", "sont", "cette", "comme", "tout", "mais", "nous"}
    de_sw = {"der", "die", "und", "nicht", "sich", "mit", "auch", "auf", "eine"}

    scores = {
        "it": sum(1 for w in words if w in it_sw),
        "en": sum(1 for w in words if w in en_sw),
        "fr": sum(1 for w in words if w in fr_sw),
        "de": sum(1 for w in words if w in de_sw),
    }
    best_lang, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_lang if best_score >= 2 else "it"


def canonical_stem_key(raw_name: str) -> str:
    """Chiave canonica NFC senza suffissi `- libgen.lc` per il matching inter-sorgente."""
    s = unicodedata.normalize("NFC", Path(raw_name).stem if raw_name.endswith((".pdf", ".md", ".epub", ".djvu")) else raw_name)
    s = re.sub(r"\s*-\s*libgen\.\w+$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+libgen$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[_—–-]+", " ", s)
    return " ".join(s.lower().split())
