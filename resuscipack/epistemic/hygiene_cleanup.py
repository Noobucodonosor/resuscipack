"""Bonifica epistemica idempotente a €0 (ADR-0005, TASK-HYG-02).

1. Ripulisce `epistemic_units.actors_json` dai token spuri introdotti dal bug `w`
   (parole comuni minuscole, sigle tecniche, termini generici estratti dalla quote).
2. Popola `books.author` (e recupera titoli troncati con `…`) a partire da pattern
   deterministici di titolo/percorso e dai blocchi di frontespizio (pp. 1..3),
   preservando al 100% `block_pk`, `block_uid` e `blocks.content`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

from resuscipack.corpus.schema import DEFAULT_DB_PATH

_NOBLE_PARTICLES = frozenset(
    {
        "di", "de", "de'", "da", "dal", "dalla", "dallo", "del", "della", "dei", "degli",
        "du", "des", "dos", "das", "der", "den", "ten", "ter", "van", "von", "la", "le",
        "al", "el", "bin", "ibn",
    }
)
_ACTOR_GENERATIONAL_SUFFIXES = frozenset(
    {
        "junior", "senior", "jr", "jr.", "sr", "sr.",
        "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi",
    }
)

_KNOWN_SINGLE_ACTORS = frozenset(
    {
        "abel", "adleman", "al-khwarizmi", "ampere", "ampère", "archimede", "archita", "aristotele",
        "averroe", "averroè", "avicenna", "babbage", "bacon", "bacone", "banach", "barrow", "barto",
        "bayes", "beckford", "bellissima", "belloni", "bengio", "bentivoglio", "bernoulli", "bishop",
        "bohr", "bombelli", "boole", "boringhi", "brooks", "cantor", "cardano", "carnap", "cartesio",
        "casalegno", "cauchy", "cavalieri", "chebyshev", "chomsky", "cicerone", "clementi", "comte",
        "cook", "copernico", "cormen", "curie", "dalton", "darwin", "dedekind", "deitel", "democrito",
        "descartes", "diffie", "dijkstra", "diofanto", "dirac", "einstein", "eleati", "epicurei",
        "epicuro", "erone", "euclide", "eudemo", "eudosso", "euler", "eulero", "faraday", "fermat",
        "fermi", "feynman", "fibonacci", "formalisti", "fourier", "frajese", "frege", "frescobaldi",
        "galeno", "galilei", "galileo", "galois", "galvani", "gauss", "gemino", "geymonat", "godel",
        "gödel", "goldwasser", "goodfellow", "harvey", "hegel", "heisenberg", "hellman", "hermite",
        "hertz", "hilbert", "hinton", "hoare", "hobbes", "horowitz", "hume", "illuministi",
        "intuizionisti", "ipparco", "ippocrate", "jacobi", "joule", "kant", "karp", "kelvin",
        "keplero", "keyser", "knuth", "kolmogorov", "kripke", "kuhn", "lagrange", "lakatos",
        "lamport", "laplace", "lavoisier", "lebesgue", "lecun", "leibniz", "liapunov", "locke",
        "logicisti", "lolli", "lovelace", "lucrezio", "luzzaschi", "mach", "marcacci", "marconi",
        "marenzio", "mariani", "markov", "maxwell", "mazza", "mendel", "mendeleev", "micali",
        "murphy", "newton", "noether", "ohm", "oppenheim", "oresme", "ovidio", "owsinski", "pappo",
        "parnas", "pascal", "pasteur", "pauli", "peano", "pearl", "peripatetici", "pitagora",
        "pitagorici", "planck", "platone", "plinio", "poincare", "poincaré", "poisson", "popper",
        "positivisti", "proclo", "quine", "rialpo", "riemann", "rinuccini", "rivest", "ross",
        "runnels", "russell", "rutherford", "schafer", "schrodinger", "schrödinger", "sedgewick",
        "seneca", "shamir", "shannon", "sheldon", "sofisti", "spinoza", "stallings", "stoici",
        "sutton", "talete", "tanenbaum", "tarski", "tartaglia", "teeteto", "tolomeo", "torricelli",
        "turing", "vesalio", "vico", "vidolin", "viete", "viète", "volta", "wallis", "watt",
        "weierstrass", "wiener", "wirth", "wittgenstein", "zenone",
    }
)

_NON_ACTOR_STOPWORDS = frozenset(
    {
        "acqua", "acustica", "aereo", "algebra", "algoritmo", "alimentazione", "allarme", "ambiente",
        "amplificatore", "analisi", "anello", "animali", "antenna", "apparecchi", "apparecchio",
        "appendice", "arduino", "aria", "arte", "articolo", "assioma", "atomo", "attuatore",
        "audio", "autore", "autori", "autorita", "azienda", "base", "batteri", "bibliografia",
        "biologia", "browser", "bus", "cache", "calcolo", "calore", "campione", "campo",
        "capacita", "capitolo", "carica", "causa", "cavo", "cellula", "cellule", "chimica",
        "circuito", "classe", "client", "codice", "colore", "comitato", "commissione", "compilatore",
        "complessita", "composto", "concetti", "concetto", "condensatore", "condizione", "conoscenza",
        "conseguenza", "corollario", "corpo", "corrente", "costituzione", "criterio", "crittografia",
        "cultura", "curva", "dati", "database", "definizione", "densita", "derivata", "differenza",
        "differenziale", "dimostrazione", "diodo", "diritto", "dispositivo", "distribuzione",
        "docente", "domenica", "economia", "effetto", "elemento", "elettronica", "energia",
        "ente", "entropia", "enzima", "equazione", "equazioni", "errore", "esempio", "esercizio",
        "esperimento", "esponenziale", "europa", "fase", "fenomeno", "figura", "file", "filosofia",
        "filtro", "fisica", "flusso", "forma", "forza", "framework", "frase", "frequenza",
        "funzione", "fuoco", "fusibile", "gas", "gene", "generale", "generatore", "gennaio",
        "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
        "ottobre", "novembre", "dicembre", "geografia", "geometria", "giovedi", "governo", "grado",
        "grafo", "gruppo", "guida", "idea", "illuminazione", "immagine", "immagini", "impianto",
        "indice", "induttanza", "induttore", "informatica", "informazione", "informazioni",
        "ingegnere", "insieme", "integrale", "intelletto", "interfaccia", "internet", "interprete",
        "interruttore", "ipotesi", "istituto", "italia", "java", "latex", "lavoro", "legge",
        "leggi", "lemma", "lettore", "libreria", "limite", "linea", "linee", "lingua", "linguaggio",
        "linux", "lista", "logaritmo", "logica", "luce", "luna", "lunedi", "macchina", "martedi",
        "massa", "matematica", "materiale", "materiali", "matlab", "matrice", "matrici", "meccanica",
        "media", "memoria", "mente", "mercoledi", "metodo", "misura", "misure", "modello", "modulo",
        "momento", "mondo", "motore", "musica", "natura", "neutro", "nodo", "norma", "norme",
        "numero", "numeri", "oggetto", "onda", "onde", "ordine", "organismo", "organo", "origine",
        "oscillatore", "osservazione", "ottica", "pacchetto", "pagina", "parlamento", "parola",
        "parte", "pensiero", "persona", "persone", "piano", "piante", "pila", "porta", "postulato",
        "potenza", "potenziale", "potenze", "pressione", "principi", "principio", "probabilita",
        "problema", "processo", "prodotto", "programma", "programmazione", "proprietario",
        "proprieta", "proteina", "proteine", "protocollo", "punto", "python", "quantita",
        "quoziente", "rack", "radice", "radiosity", "ragione", "rapporto", "reazione", "registro",
        "regola", "regole", "relazione", "resistenza", "resistore", "responsabile", "rete", "reti",
        "retta", "ricerca", "risultato", "roma", "sabato", "schema", "scienza", "scuola", "segnale",
        "segnali", "sensore", "serie", "server", "sezione", "sicurezza", "sistema", "sistemi",
        "societa", "soggetto", "sole", "soluzione", "somma", "sommario", "sostanza", "spazio",
        "specie", "spettro", "statistica", "stato", "storia", "strumento", "struttura", "studente",
        "studi", "studio", "successione", "suono", "superficie", "tabella", "tecnica", "tecnologia",
        "temperatura", "tempo", "tensione", "teorema", "teoria", "teorie", "termodinamica", "terra",
        "tesi", "tessuto", "test", "testo", "thread", "transistor", "trasformata", "trasformatore",
        "trigonometria", "unita", "universita", "uomo", "utente", "valore", "varianza", "velocita",
        "venerdi", "vettore", "vettori", "video", "virus", "volume", "windows", "word", "excel",
    }
)

_ABSTRACT_COMMON_SUFFIXES = (
    "zione", "zioni", "mento", "menti", "aggio", "aggi", "ezza", "ezze", "anza", "anze",
    "enza", "enze", "ità", "età", "ismo", "ismi", "logia", "logie", "grafia", "metria",
)

_PLACE_PREFIXES = frozenset(
    {"santa", "san", "santo", "monte", "isola", "capo", "golfo", "stretto", "lago", "fiume", "piazza", "via"}
)


def _is_valid_name_word(w_clean: str, *, allow_initial: bool = False) -> bool:
    if not w_clean:
        return False
    if allow_initial and re.fullmatch(r"(?:[A-ZÀ-Ý]\.){1,4}", w_clean):
        return True
    w_core = w_clean.rstrip(".")
    if not w_core:
        return False
    # Gestisce apostrofi nobiliari/irlandesi: d'Este, O'Connor, l'Hôpital
    if "'" in w_core:
        head, tail = w_core.split("'", 1)
        if head.casefold() in {"d", "de", "l", "o"} and tail and tail[0].isupper():
            w_core = tail
    if w_core[0].isupper():
        if allow_initial and len(w_core) == 1:
            return True
        return len(w_core) >= 2 and not (w_core.isupper() and len(w_core) <= 5)
    return False


def is_plausible_actor_name(token: str) -> bool:
    """Restituisce True solo se `token` rappresenta un nome proprio di persona, autore o scuola."""
    tok = " ".join(str(token or "").replace("’", "'").split()).strip(" ,.;:()[]{}\"'")
    if not tok or len(tok) < 2 or len(tok) > 65:
        return False
    if any(ch.isdigit() for ch in tok):
        return False
    if "/" in tok or "\\" in tok or "=" in tok or "_" in tok or "&" in tok:
        return False
    if not tok[0].isupper():
        return False

    compact_alpha = re.sub(r"[.\-\s']", "", tok)
    if not compact_alpha:
        return False
    if tok.isupper() and len(compact_alpha) <= 8:
        return False

    low = tok.casefold()
    ascii_low = (
        low.replace("à", "a")
        .replace("è", "e")
        .replace("é", "e")
        .replace("ì", "i")
        .replace("ò", "o")
        .replace("ó", "o")
        .replace("ù", "u")
    )
    if low in _NON_ACTOR_STOPWORDS or ascii_low in _NON_ACTOR_STOPWORDS:
        return False

    words = tok.split()
    if len(words) == 1:
        if low in _KNOWN_SINGLE_ACTORS or ascii_low in _KNOWN_SINGLE_ACTORS:
            return True
        if low.endswith(_ABSTRACT_COMMON_SUFFIXES):
            return False
        if "." in tok:
            return False
        # Consente cognomi composti tipo McCormach, Al-Khuwarizmi, DeMorgan
        return len(tok) >= 3 and any(ch.islower() for ch in tok[1:])

    # Multi-parola: es. "Guglielmo Marconi", "Emilio de' Cavalieri", "Alfonso d'Este", "E. du Bois-Reymond"
    first_low = words[0].casefold()
    if first_low in _PLACE_PREFIXES:
        return False

    cap_words = 0
    for idx, w in enumerate(words):
        w_clean = w.strip(",()")
        if not w_clean:
            continue
        w_bare = w_clean.rstrip(".")
        w_low = w_clean.casefold()
        if idx > 0 and (
            w_low in _NOBLE_PARTICLES
            or w_bare.casefold() in _NOBLE_PARTICLES
            or w_low in _ACTOR_GENERATIONAL_SUFFIXES
            or w_bare.casefold() in _ACTOR_GENERATIONAL_SUFFIXES
        ):
            continue
        if not _is_valid_name_word(w_clean, allow_initial=("." in w_clean)):
            return False
        if w_bare.casefold() in _NON_ACTOR_STOPWORDS:
            return False
        cap_words += 1

    return cap_words >= 2


def clean_actor_list(raw_actors_json: Optional[str]) -> Tuple[List[str], bool]:
    """Pulisce un array JSON `actors_json`. Restituisce `(cleaned_list, changed)`."""
    if not raw_actors_json:
        return [], False
    try:
        parsed = json.loads(raw_actors_json)
    except json.JSONDecodeError:
        return [], True
    if not isinstance(parsed, list):
        return [], True

    cleaned: List[str] = []
    seen: set[str] = set()
    for item in parsed:
        tok = " ".join(str(item or "").split()).strip()
        if not is_plausible_actor_name(tok):
            continue
        key = tok.casefold()
        if key not in seen:
            seen.add(key)
            cleaned.append(tok)

    changed = cleaned != [str(x).strip() for x in parsed if isinstance(x, str)]
    if len(cleaned) != len(parsed):
        changed = True
    return cleaned, changed


_NOISE_AUTHOR_WORDS = frozenset(
    {
        "prima", "seconda", "terza", "quarta", "quinta", "scientifico", "tecnico", "triennio",
        "matematica", "informatica", "fisica", "biologia", "storia", "filosofia", "programma",
        "appunti", "brochure", "sintesi", "test", "sezione", "review", "introduzione", "indice",
        "sommario", "capitolo", "edizione", "edizioni", "universale", "classici", "bussole",
        "corso", "manuale", "dispensa", "guida", "architettura", "arte", "audio", "analisi",
        "fondamenti", "materiali", "elettrotecnica", "opere", "linguaggio", "microsoft", "word",
        "volume", "tomo", "parte", "libgen", "unknown", "sconosciuto", "anonimo", "autori",
        "enciclopedia", "encicilopedia", "italiana", "didattica", "apprendimento", "unita", "unità",
        "foglio", "elettronico", "lezione", "notebook", "panduan", "penggunaan", "pc",
        "phyla", "archaebacteria", "scuola", "istituto", "universita", "università", "dipartimento",
        "polito", "politecnico", "milano", "torino", "roma", "bologna", "padova", "napoli",
        "adobe", "cloud", "services", "server", "client", "software", "windows", "linux",
    }
)

_TAXON_SUFFIX_RE = re.compile(
    r"(?:ales|phyta|idae|aceae|bacteria|mycota|euroside|roside|asteride)$",
    re.IGNORECASE,
)


def _looks_like_person_author(candidate: str) -> bool:
    if "  " in candidate or "\t" in candidate:
        return False
    s = " ".join(candidate.split()).strip(" ,.-:;()[]")
    if not s or len(s) < 5 or len(s) > 80:
        return False
    if any(ch.isdigit() for ch in s):
        return False
    if s.isupper():
        return False
    parts = [p.strip(".,") for p in re.split(r"[\s]+", s) if p.strip(".,")]
    if len(parts) < 2 or len(parts) > 6:
        return False
    for p in parts:
        p_low = p.casefold()
        if p_low in _NOBLE_PARTICLES or p in {"&", "e", "and"}:
            continue
        if len(p) < 2 or not p[0].isupper() or p.isupper():
            return False
        if not any(ch.islower() for ch in p[1:]):
            return False
        if p_low in _NOISE_AUTHOR_WORDS or p_low in _NON_ACTOR_STOPWORDS:
            return False
        if _TAXON_SUFFIX_RE.search(p_low):
            return False
    return True


def _infer_author_from_frontmatter(blocks_texts: Sequence[str], title: str) -> Optional[str]:
    """Estrae l'autore dai blocchi di frontespizio/titolo usando pattern deterministici."""
    joined = "\n".join(blocks_texts[:3])
    head_lines = "\n".join((blocks_texts[0].splitlines()[:8] if blocks_texts else []))
    m_auth = re.search(r"(?:Author\(s\)|Autore|A cura di)\s*:\s*([A-ZÀ-Ý][^\n]{4,70})", head_lines)
    if m_auth:
        cand = " ".join(m_auth.group(1).split()).strip()
        if _looks_like_person_author(cand):
            return cand

    # Se il titolo inizia con `[Serie] Nome Cognome...`
    m_br = re.match(
        r"^\[[^\]]+\]\s+([A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+){1,4}(?:\s*,\s*[A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+){1,3})*)",
        title,
    )
    if m_br:
        raw_chunk = m_br.group(1)
        cand_words: List[str] = []
        for w in raw_chunk.split():
            if w.strip(",").casefold() in _NOISE_AUTHOR_WORDS:
                break
            cand_words.append(w)
        cand = " ".join(cand_words).strip(" ,")
        if "…" in title and cand_words:
            first_tok = cand_words[0]
            m_full = re.search(rf"\b({re.escape(first_tok)}\s+[A-ZÀ-Ý][a-zà-ÿ]+)\b", joined)
            if m_full and _looks_like_person_author(m_full.group(1)):
                return m_full.group(1)
        if _looks_like_person_author(cand):
            return cand

    # Pattern `"First Last, Book Title"` (es. `"Bobby Owsinski, The Mixing Engineer's Handbook"`)
    m_comma = re.match(r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+)\s*,\s+.{6,}$", title)
    if m_comma and _looks_like_person_author(m_comma.group(1)):
        return m_comma.group(1)

    # Pattern `"Autore - Titolo"`
    m_dash = re.match(r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ.'\-]+){1,3})\s+-\s+.{5,}$", title)
    if m_dash and _looks_like_person_author(m_dash.group(1)):
        return m_dash.group(1)

    # Cerca righe pulite di frontespizio (es. "Ludovico Geymonat", "Prof. Giuseppe Barberis")
    if blocks_texts:
        first_lines = [ln.strip() for ln in blocks_texts[0].splitlines() if ln.strip()][:14]
        for ln in first_lines:
            cleaned_ln = re.sub(r"^(?:Prof\.?\s+|Dott\.?\s+|Ing\.?\s+|by\s+|di\s+)", "", ln, flags=re.IGNORECASE).strip()
            if 5 <= len(cleaned_ln) <= 45 and _looks_like_person_author(cleaned_ln):
                return cleaned_ln
        m_di = re.search(
            r"(?:OPERE\s+SCELTE|OPERE|SAGGI|ELEMENTI|STORIA)[\s\S]{0,60}?\bdi\s+([A-ZÀ-Ý][a-zà-ÿ]+\s+[A-ZÀ-Ý][a-zà-ÿ]+)\b",
            blocks_texts[0],
        )
        if m_di and _looks_like_person_author(m_di.group(1)):
            return m_di.group(1)

    return None


def _recover_truncated_title(title: str, blocks_texts: Sequence[str]) -> Optional[str]:
    """Ripristina un titolo completo solo se `title` contiene `…` ed è recuperabile dal frontespizio."""
    if "…" not in title and not title.endswith("..."):
        return None
    joined = "\n".join(blocks_texts[:2])
    if "Review of Aegean Prehistory IV" in title and "Advent of the Neolithic" in joined:
        return "Review of Aegean Prehistory IV: The Stone Age of Greece from the Palaeolithic to the Advent of the Neolithic"
    if "Ludovico Ge" in title and "Storia e filosofia" in joined:
        return "[Universale Bollati Boringhieri, 573] Ludovico Geymonat - Storia e filosofia dell'analisi infinitesimale (2008, Bollati Boringhieri)"
    if "Paul J. Deitel" in title and "IL LINGUAGGIO C" in joined.upper():
        return "[Informatica] Paul J. Deitel, Harvey M. Deitel - Il linguaggio C. Fondamenti e tecniche di programmazione (2016, Pearson)"
    if "dani mazza" in title.lower() and "MATERIALI PER" in joined.upper():
        return "Daniele Mazza - Materiali per l'elettrotecnica (Politecnico di Torino)"
    return None


@dataclass
class HygieneReport:
    dry_run: bool
    units_scanned: int
    units_cleaned: int
    tokens_before: int
    tokens_after: int
    books_author_updated: int
    books_title_restored: int
    actor_samples: List[Dict[str, Any]]
    author_samples: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "units_scanned": self.units_scanned,
            "units_cleaned": self.units_cleaned,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "books_author_updated": self.books_author_updated,
            "books_title_restored": self.books_title_restored,
            "actor_samples": self.actor_samples,
            "author_samples": self.author_samples,
        }


def run_hygiene_cleanup(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    apply: bool = False,
    backup_path: Optional[Path | str] = None,
) -> HygieneReport:
    """Esegue `--dry-run` (default) o `--apply` su `pack_corpus.db` in modo idempotente."""
    db_p = Path(db_path)
    if apply and backup_path is not None:
        bak = Path(backup_path)
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_p, bak)

    uri = f"file:{db_p}?mode=ro" if not apply else str(db_p)
    conn = sqlite3.connect(uri, uri=not apply, timeout=30.0)
    conn.row_factory = sqlite3.Row

    try:
        unit_rows = conn.execute(
            "SELECT unit_pk, actors_json, stmt FROM epistemic_units WHERE actors_json IS NOT NULL AND actors_json != '[]'"
        ).fetchall()
        units_scanned = len(unit_rows)
        units_cleaned = 0
        tokens_before = 0
        tokens_after = 0
        actor_updates: List[Tuple[str, int]] = []
        actor_samples: List[Dict[str, Any]] = []

        for r in unit_rows:
            raw_json = str(r["actors_json"] or "[]")
            try:
                orig = json.loads(raw_json)
            except json.JSONDecodeError:
                orig = []
            if isinstance(orig, list):
                tokens_before += len(orig)
            cleaned, changed = clean_actor_list(raw_json)
            tokens_after += len(cleaned)
            if changed:
                units_cleaned += 1
                new_json = json.dumps(cleaned, ensure_ascii=False)
                actor_updates.append((new_json, int(r["unit_pk"])))
                if len(actor_samples) < 20:
                    actor_samples.append(
                        {
                            "unit_pk": int(r["unit_pk"]),
                            "before": orig,
                            "after": cleaned,
                            "stmt": str(r["stmt"] or "")[:90],
                        }
                    )

        book_rows = conn.execute(
            "SELECT book_pk, title, author FROM books WHERE is_active = 1 AND (author IS NULL OR title LIKE '%…%' OR title LIKE '%...')"
        ).fetchall()
        author_updates: List[Tuple[str, int]] = []
        title_updates: List[Tuple[str, int]] = []
        author_samples: List[Dict[str, Any]] = []

        for br in book_rows:
            bpk = int(br["book_pk"])
            btitle = str(br["title"] or "")
            fm_rows = conn.execute(
                "SELECT content FROM blocks WHERE book_pk = ? AND is_active = 1 ORDER BY page_start ASC, block_pk ASC LIMIT 3",
                (bpk,),
            ).fetchall()
            fm_texts = [str(fr["content"] or "") for fr in fm_rows]

            if br["author"] is None:
                inferred = _infer_author_from_frontmatter(fm_texts, btitle)
                if inferred:
                    author_updates.append((inferred, bpk))
                    if len(author_samples) < 20:
                        author_samples.append({"book_pk": bpk, "title": btitle, "author": inferred})

            restored_title = _recover_truncated_title(btitle, fm_texts)
            if restored_title and restored_title != btitle:
                title_updates.append((restored_title, bpk))

        if apply:
            with conn:
                if actor_updates:
                    conn.executemany(
                        "UPDATE epistemic_units SET actors_json = ? WHERE unit_pk = ?",
                        actor_updates,
                    )
                if author_updates:
                    conn.executemany(
                        "UPDATE books SET author = ? WHERE book_pk = ? AND author IS NULL",
                        author_updates,
                    )
                if title_updates:
                    conn.executemany(
                        "UPDATE books SET title = ? WHERE book_pk = ?",
                        title_updates,
                    )

        return HygieneReport(
            dry_run=not apply,
            units_scanned=units_scanned,
            units_cleaned=units_cleaned,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            books_author_updated=len(author_updates),
            books_title_restored=len(title_updates),
            actor_samples=actor_samples,
            author_samples=author_samples,
        )
    finally:
        conn.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bonifica deterministica €0 di actors_json e books.author.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Percorso di pack_corpus.db")
    parser.add_argument("--apply", action="store_true", help="Applica le modifiche su DB (default: --dry-run)")
    parser.add_argument("--backup", type=Path, default=None, help="Percorso di backup prima di --apply")
    args = parser.parse_args(argv)

    rep = run_hygiene_cleanup(args.db, apply=args.apply, backup_path=args.backup)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
