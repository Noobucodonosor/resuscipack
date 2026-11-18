"""Validazione rigorosa e persistenza dello schema polimorfico `BlockExtraction v2.1`.

Garantisce:
1. Copertura sia dell'80% di trattati/manuali/controversie (`sig=None` ammesso: Diritto al Silenzio)
   sia del ~20-35% di episodi/esperimenti/pratiche con `sig` strutturale.
2. Risoluzione delle deissi editoriali su `stmt` e verifica verbatim deterministica di `quote`
   contro il testo del blocco (`norm_content`).
3. Regola `domain_stripping` su `sig.mech` + Enum chiuso `OpTag` (zero leakage).
4. Gate anti-template sul batch (rifiuto di prefissi stereotipati ripetuti o bassa entropia).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .op_tags import OpTag, find_forbidden_surface_terms, validate_op_tags

SCHEMA_VERSION = "block-extraction.v2.1"
SCHEMA_VERSION_V22 = "block-extraction.v2.2"


class MacroDiscipline(str, Enum):
    """Tassonomia chiusa delle 22 macro-discipline universali per lo Spettro Percentuale per Libro (v2.2)."""

    MATEMATICA = "matematica"
    LOGICA = "logica"
    INFORMATICA = "informatica"
    CRITTOGRAFIA_SICUREZZA = "crittografia_sicurezza"
    FISICA = "fisica"
    ASTRONOMIA_COSMOLOGIA = "astronomia_cosmologia"
    CHIMICA_MATERIALI = "chimica_materiali"
    BIOLOGIA_FISIOLOGIA_MEDICINA = "biologia_fisiologia_medicina"
    GEOGRAFIA_CARTOGRAFIA_TERRITORIO = "geografia_cartografia_territorio"
    NAUTICA_NAVIGAZIONE_METEO = "nautica_navigazione_meteo"
    INGEGNERIA_MECCANICA_ELETTRONICA = "ingegneria_meccanica_elettronica"
    TELECOMUNICAZIONI_SEGNALI = "telecomunicazioni_segnali"
    STORIA_POLITICA_MILITARE = "storia_politica_militare"
    ECONOMIA_COMMERCIO_ASSICURAZIONI = "economia_commercio_assicurazioni"
    DIRITTO_ISTITUZIONI = "diritto_istituzioni"
    FILOSOFIA_EPISTEMOLOGIA = "filosofia_epistemologia"
    LETTERATURA_RETORICA_FILOLOGIA = "letteratura_retorica_filologia"
    MUSICA_ACUSTICA = "musica_acustica"
    ARTE_ARCHITETTURA_DISEGNO = "arte_architettura_disegno"
    PSICOLOGIA_PEDAGOGIA_SOCIETA = "psicologia_pedagogia_societa"
    AGRONOMIA_SCIENZE_NATURALI_CIBO = "agronomia_scienze_naturali_cibo"
    ARTI_PRATICHE_ARTIGIANATO = "arti_pratiche_artigianato"


ALL_MACRO_DISCIPLINES = frozenset(d.value for d in MacroDiscipline)


class BlockYield(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW_OR_PARATEXT = "low_or_paratext"


class UnitKind(str, Enum):
    DEF = "def"
    THM = "thm"
    PROOF_IDEA = "proof_idea"
    PROC = "proc"
    EXP = "exp"
    DISPUTE = "dispute"
    CLAIM = "claim"
    COUNTEREX = "counterex"


class UnitMode(str, Enum):
    DEFINES = "defines"
    PROVES = "proves"
    APPLIES = "applies"
    CRITIQUES = "critiques"
    EXTENDS = "extends"
    PRESUPPOSES = "presupposes"
    NARRATES = "narrates"


class AntiSudokuRole(str, Enum):
    GENESIS_PROBLEM = "genesis_problem"
    EMBODIED_INTUITION = "embodied_intuition"
    FERTILE_ERROR = "fertile_error"
    HIDDEN_ASSUMPTION = "hidden_assumption"
    FEASIBILITY_BOUND = "feasibility_bound"


# Espressioni deittiche opache vietate in `stmt` (proposizione atomica autocontenuta)
_DANGLING_DEIXIS_RE = re.compile(
    r"(?:^\s*(?:egli|ella|esso|essa|essi|esse|costui|ciò)\b"
    r"|\b(?:il nostro|suddetto autore|questo paragrafo parla|questa pagina tratta"
    r"|ivi|ibidem|op\.\s*cit\.)\b)",
    flags=re.IGNORECASE,
)

# Formule inventate di leakage vietate in `sig.mech` quando assenti dal testo originale
_LEAKAGE_FORMULA_RE = re.compile(r"\|\s*[a-zA-Z]\s*-\s*[a-zA-Z0-9_]+\s*\|\s*[<>≤≥]")


def normalizza_testo(testo: str) -> str:
    """Normalizzazione canonica identica per citazioni, blocchi e verificatore schede."""
    t = unicodedata.normalize("NFKC", str(testo or ""))
    t = t.replace("\u00ad", "")  # soft hyphen
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)  # sillabazione a fine riga
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


_ALNUM_TOKEN_RE = re.compile(r"[a-z0-9à-ÿ\u0370-\u03ff]+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9à-ÿ\u0370-\u03ff]+")

_GREEK_LATEX_MAP: Mapping[str, str] = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "vartheta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "omicron": "ο",
    "pi": "π",
    "varpi": "π",
    "rho": "ρ",
    "varrho": "ρ",
    "sigma": "σ",
    "varsigma": "σ",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "varphi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "γ",
    "Delta": "δ",
    "Theta": "θ",
    "Lambda": "λ",
    "Xi": "ξ",
    "Pi": "π",
    "Sigma": "σ",
    "Upsilon": "υ",
    "Phi": "φ",
    "Psi": "ψ",
    "Omega": "ω",
    "quad": " ",
    "qquad": " ",
}
_LATEX_CMD_RE = re.compile(r"\\([A-Za-z]+)")
_QUOTE_ELLIPSIS_SPLIT_RE = re.compile(r"(?:\[\.\.\.\]|\[…\]|\.\.\.|…)")


def _strip_accents_nfd(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def _normalize_ocr_and_latex(testo: str) -> str:
    """Converte comandi greci LaTeX (`\\pi`, `\\epsilon`) in Unicode e rimuove diacritici NFD
    per il confronto rigoroso contro blocchi matematici OCR storici."""
    raw = str(testo or "")
    raw = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?", " ", raw)
    raw = re.sub(r"([A-Za-z0-9])_\{([A-Za-z0-9]+)\}", r"\1\2", raw)
    raw = re.sub(r"([A-Za-z0-9])_([A-Za-z0-9])\b", r"\1\2", raw)
    raw = re.sub(r"\\(?:left|right)\s*(?:\\[{}]|[.()\[\]|])?", " ", raw)
    raw = re.sub(r"\\[{}\[\]()\\,;!:]+", " ", raw)
    expanded = _LATEX_CMD_RE.sub(lambda m: _GREEK_LATEX_MAP.get(m.group(1), " "), raw)
    expanded = expanded.replace("$", " ").replace("{", "").replace("}", "").replace("ς", "σ")
    base = normalizza_testo(expanded)
    stripped = _strip_accents_nfd(base)
    return " ".join(stripped.split())


def _single_span_ocr_match(norm_q: str, norm_b: str) -> bool:
    if not norm_q or not norm_b:
        return False
    if norm_q in norm_b:
        return True

    skel_q = _NON_ALNUM_RE.sub("", norm_q)
    skel_b = _NON_ALNUM_RE.sub("", norm_b)
    if len(skel_q) >= 16 and skel_q in skel_b:
        return True

    q_toks = _ALNUM_TOKEN_RE.findall(norm_q)
    b_toks = _ALNUM_TOKEN_RE.findall(norm_b)
    m = len(q_toks)
    if m < 4 or len(b_toks) < m:
        return False
    for start in range(len(b_toks) - m + 1):
        window = b_toks[start : start + m]
        mismatch_indices = [idx for idx, (qt, bt) in enumerate(zip(q_toks, window)) if qt != bt]
        if not mismatch_indices:
            return True
        if len(mismatch_indices) == 1:
            mi = mismatch_indices[0]
            qt, bt = q_toks[mi], window[mi]
            if len(qt) >= 3 and len(bt) >= 3 and _levenshtein_le_1(qt, bt):
                return True
            if m >= 6 and max(len(qt), len(bt)) <= 3:
                return True
    return False

_MODE_TO_DEFAULT_KIND = {
    "defines": "def",
    "proves": "proof_idea",
    "applies": "proc",
    "critiques": "dispute",
    "extends": "claim",
    "presupposes": "claim",
    "narrates": "claim",
}
_VALID_UNIT_MODE_VALUES = {m.value for m in UnitMode}
_VALID_UNIT_KIND_VALUES = {k.value for k in UnitKind}


def _levenshtein_le_1(a: str, b: str) -> bool:
    """Restituisce True sse la distanza di edit tra `a` e `b` è al più 1."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = sum(1 for ca, cb in zip(a, b) if ca != cb)
        return diffs <= 1
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def quote_matches_block_ocr_tolerant(quote: str, block_content: str) -> bool:
    """Verifica verbatim della citazione tollerando spaziature tipografiche, un singolo refuso OCR
    (o 1 token <=3 char su finestra >=6 parole), diacritici/greco LaTeX e un taglio `[...]` ordinato."""
    norm_quote = normalizza_testo(quote)
    norm_block = normalizza_testo(block_content)
    if _single_span_ocr_match(norm_quote, norm_block):
        return True

    latex_quote = _normalize_ocr_and_latex(quote)
    latex_block = _normalize_ocr_and_latex(block_content)
    if _single_span_ocr_match(latex_quote, latex_block):
        return True

    if _QUOTE_ELLIPSIS_SPLIT_RE.search(quote):
        parts = [p.strip() for p in _QUOTE_ELLIPSIS_SPLIT_RE.split(quote) if p.strip()]
        if len(parts) == 2 and all(len(p.split()) >= 3 for p in parts):
            n1 = _normalize_ocr_and_latex(parts[0])
            n2 = _normalize_ocr_and_latex(parts[1])
            idx1 = latex_block.find(n1)
            if idx1 >= 0:
                idx2 = latex_block.find(n2, idx1 + len(n1))
                if idx2 >= 0 and (idx2 - (idx1 + len(n1))) <= 350:
                    return True
    return False


def make_unit_uid(block_uid: str, kind: str, stmt: str, quote: str) -> str:
    payload = f"{block_uid}\x1f{kind}\x1f{normalizza_testo(stmt)}\x1f{normalizza_testo(quote)}"
    return "eu_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class AtomicEpistemicUnit:
    kind: UnitKind
    mode: UnitMode
    stmt: str
    quote: str
    who: Tuple[str, ...] = ()
    vs: Optional[str] = None
    concepts: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "mode": self.mode.value,
            "stmt": self.stmt,
            "quote": self.quote,
            "who": list(self.who),
            "vs": self.vs,
            "concepts": list(self.concepts),
        }


@dataclass(frozen=True)
class StructuralSignature:
    op_tags: Tuple[OpTag, ...]
    role: AntiSudokuRole
    mech: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_tags": [t.value for t in self.op_tags],
            "role": self.role.value,
            "mech": self.mech,
        }


@dataclass(frozen=True)
class BlockExtractionV21:
    block_yield: BlockYield
    units: Tuple[AtomicEpistemicUnit, ...] = field(default_factory=tuple)
    sig: Optional[StructuralSignature] = None
    macro_disciplines: Tuple[MacroDiscipline, ...] = field(default_factory=tuple)
    topics: Tuple[str, ...] = field(default_factory=tuple)
    places: Tuple[str, ...] = field(default_factory=tuple)
    years: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "yield": self.block_yield.value,
            "units": [u.to_dict() for u in self.units],
            "sig": self.sig.to_dict() if self.sig is not None else None,
        }
        if self.macro_disciplines or self.topics or self.places or self.years:
            out["macro_disciplines"] = [d.value for d in self.macro_disciplines]
            out["topics"] = list(self.topics)
            out["places"] = list(self.places)
            out["years"] = list(self.years)
        return out

    def compact_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


class SchemaValidationError(ValueError):
    """Errore sollevato quando un payload `BlockExtraction v2.1` viola gli invarianti."""


def _clean_str_list(raw: Any, field_name: str, *, min_len: int = 0, max_len: int = 10) -> Tuple[str, ...]:
    if raw is None:
        raw = []
    if not isinstance(raw, (list, tuple)):
        raise SchemaValidationError(f"{field_name} deve essere una lista di stringhe")
    out: List[str] = []
    seen = set()
    for item in raw:
        val = " ".join(str(item or "").split()).strip()
        if val and val.casefold() not in seen:
            seen.add(val.casefold())
            out.append(val)
    if len(out) < min_len or len(out) > max_len:
        raise SchemaValidationError(
            f"{field_name} richiede tra {min_len} e {max_len} elementi validi (trovati {len(out)})"
        )
    return tuple(out)


def _validate_macro_disciplines(
    raw: Any,
    *,
    min_len: int,
    max_len: int = 4,
) -> Tuple[MacroDiscipline, ...]:
    if raw is None:
        raw = []
    if not isinstance(raw, (list, tuple)):
        raise SchemaValidationError("macro_disciplines deve essere una lista di stringhe")
    out: List[MacroDiscipline] = []
    seen = set()
    for item in raw:
        val = str(item or "").strip().lower()
        if not val:
            continue
        try:
            disc = MacroDiscipline(val)
        except ValueError as exc:
            raise SchemaValidationError(
                f"macro_disciplines contiene voce fuori dall'Enum delle 22 macro-discipline: {val!r}"
            ) from exc
        if disc not in seen:
            seen.add(disc)
            out.append(disc)
    if len(out) < min_len or len(out) > max_len:
        raise SchemaValidationError(
            f"macro_disciplines richiede tra {min_len} e {max_len} voci valide (trovate {len(out)})"
        )
    return tuple(out)


def validate_block_extraction(
    payload: Mapping[str, Any],
    *,
    block_content: str,
    extra_forbidden_nouns: Iterable[str] = (),
    require_v22_metadata: bool = False,
) -> BlockExtractionV21:
    """Valida un dizionario `BlockExtraction v2.1 / v2.2` contro il testo sorgente reale del blocco."""
    if not isinstance(payload, Mapping):
        raise SchemaValidationError("Il payload di BlockExtraction deve essere un oggetto JSON")

    allowed_keys = {"yield", "units", "sig", "macro_disciplines", "topics", "places", "years"}
    extra_keys = set(payload.keys()) - allowed_keys
    if extra_keys:
        raise SchemaValidationError(f"Campi sconosciuti non ammessi nello schema: {sorted(extra_keys)}")

    try:
        byield = BlockYield(str(payload.get("yield", "")).strip())
    except ValueError as exc:
        raise SchemaValidationError(f"Valore 'yield' invalido: {payload.get('yield')!r}") from exc

    raw_units = payload.get("units")
    if not isinstance(raw_units, list):
        raise SchemaValidationError("Il campo 'units' deve essere una lista")

    raw_sig = payload.get("sig")

    if byield is BlockYield.LOW_OR_PARATEXT:
        if raw_units:
            raise SchemaValidationError("Con yield='low_or_paratext', 'units' deve essere vuoto ([]).")
        if raw_sig is not None:
            raise SchemaValidationError("Con yield='low_or_paratext', 'sig' deve essere null.")
        return BlockExtractionV21(
            block_yield=byield,
            units=(),
            sig=None,
            macro_disciplines=(),
            topics=(),
            places=(),
            years=(),
        )

    if not (1 <= len(raw_units) <= 8):
        raise SchemaValidationError(
            f"Blocco sostantivo ({byield.value}) richiede da 1 a 8 unità atomiche (trovate {len(raw_units)})"
        )

    norm_block = normalizza_testo(block_content)
    if not norm_block:
        raise SchemaValidationError("block_content vuoto: impossibile verificare le ancore verbatim")

    v22_present = any(k in payload for k in ("macro_disciplines", "topics", "places", "years"))
    min_disc = 1 if (require_v22_metadata or "macro_disciplines" in payload) else 0
    min_top = 1 if (require_v22_metadata or "topics" in payload) else 0
    macro_disciplines = (
        _validate_macro_disciplines(payload.get("macro_disciplines"), min_len=min_disc, max_len=4)
        if (require_v22_metadata or v22_present)
        else ()
    )
    topics = (
        _clean_str_list(payload.get("topics"), "topics", min_len=min_top, max_len=6)
        if (require_v22_metadata or "topics" in payload)
        else ()
    )
    places = (
        _clean_str_list(payload.get("places"), "places", min_len=0, max_len=24)
        if "places" in payload
        else ()
    )
    years = (
        _clean_str_list(payload.get("years"), "years", min_len=0, max_len=16)
        if "years" in payload
        else ()
    )

    validated_units: List[AtomicEpistemicUnit] = []
    for idx, raw_u in enumerate(raw_units, start=1):
        if not isinstance(raw_u, Mapping):
            raise SchemaValidationError(f"units[{idx}] deve essere un oggetto")
        u_extra = set(raw_u.keys()) - {"kind", "mode", "stmt", "quote", "who", "vs", "concepts"}
        if u_extra:
            raise SchemaValidationError(f"units[{idx}] contiene campi non ammessi: {sorted(u_extra)}")

        raw_kind_str = str(raw_u.get("kind", "")).strip().lower()
        raw_mode_str = str(raw_u.get("mode", "")).strip().lower()
        if raw_kind_str not in _VALID_UNIT_KIND_VALUES and raw_kind_str in _MODE_TO_DEFAULT_KIND:
            if raw_mode_str not in _VALID_UNIT_MODE_VALUES:
                raw_mode_str = raw_kind_str
            if raw_kind_str == "critiques":
                raw_kind_str = "dispute" if str(raw_u.get("vs") or "").strip() else "claim"
            else:
                raw_kind_str = _MODE_TO_DEFAULT_KIND[raw_kind_str]

        try:
            kind = UnitKind(raw_kind_str)
        except ValueError as exc:
            raise SchemaValidationError(f"units[{idx}].kind invalido: {raw_u.get('kind')!r}") from exc

        try:
            mode = UnitMode(raw_mode_str)
        except ValueError as exc:
            raise SchemaValidationError(f"units[{idx}].mode invalido: {raw_u.get('mode')!r}") from exc

        stmt = " ".join(str(raw_u.get("stmt", "")).split()).strip()
        if len(stmt) < 25:
            raise SchemaValidationError(f"units[{idx}].stmt troppo corta (<25 char): {stmt!r}")
        if _DANGLING_DEIXIS_RE.search(stmt):
            raise SchemaValidationError(
                f"units[{idx}].stmt contiene deissi non risolta o rinvio cieco: {stmt!r}"
            )

        quote = str(raw_u.get("quote", "")).strip()
        quote_words = quote.split()
        if not (3 <= len(quote_words) <= 75):
            raise SchemaValidationError(
                f"units[{idx}].quote deve avere tra 3 e 75 parole (trovate {len(quote_words)})"
            )
        if not quote_matches_block_ocr_tolerant(quote, block_content):
            raise SchemaValidationError(
                f"units[{idx}].quote non trovata verbatim nel blocco sorgente: {quote!r}"
            )

        who = _clean_str_list(raw_u.get("who"), f"units[{idx}].who", min_len=0, max_len=8)
        raw_vs = raw_u.get("vs")
        vs: Optional[str] = None
        if raw_vs is not None:
            vs_clean = " ".join(str(raw_vs).split()).strip()
            vs = vs_clean if vs_clean else None
        if kind is UnitKind.DISPUTE and not vs:
            raise SchemaValidationError(
                f"units[{idx}] ha kind='dispute' ma il campo 'vs' (Con chi in disaccordo) è nullo"
            )

        concepts = _clean_str_list(
            raw_u.get("concepts"), f"units[{idx}].concepts", min_len=1, max_len=5
        )
        validated_units.append(
            AtomicEpistemicUnit(
                kind=kind,
                mode=mode,
                stmt=stmt,
                quote=quote,
                who=who,
                vs=vs,
                concepts=concepts,
            )
        )

    validated_sig: Optional[StructuralSignature] = None
    if raw_sig is not None:
        if not isinstance(raw_sig, Mapping):
            raise SchemaValidationError("Il campo 'sig' deve essere un oggetto oppure null")
        sig_extra = set(raw_sig.keys()) - {"op_tags", "role", "mech"}
        if sig_extra:
            raise SchemaValidationError(f"sig contiene campi non ammessi: {sorted(sig_extra)}")
        try:
            op_tags = tuple(validate_op_tags(raw_sig.get("op_tags", [])))
        except ValueError as exc:
            raise SchemaValidationError(str(exc)) from exc
        try:
            role = AntiSudokuRole(str(raw_sig.get("role", "")).strip())
        except ValueError as exc:
            raise SchemaValidationError(f"sig.role invalido: {raw_sig.get('role')!r}") from exc

        mech = " ".join(str(raw_sig.get("mech", "")).split()).strip()
        if len(mech) < 30 or len(mech) > 650:
            raise SchemaValidationError(
                f"sig.mech deve avere tra 30 e 650 caratteri (trovati {len(mech)})"
            )
        forbidden_hits = find_forbidden_surface_terms(mech, extra_forbidden=extra_forbidden_nouns)
        if forbidden_hits:
            raise SchemaValidationError(
                f"Violazione domain_stripping in sig.mech (sostantivi di superficie vietati): {forbidden_hits}"
            )
        if _LEAKAGE_FORMULA_RE.search(mech) and not _LEAKAGE_FORMULA_RE.search(block_content):
            raise SchemaValidationError(
                f"Violazione zero-leakage: formula con modulo iniettata in sig.mech assente dal testo: {mech!r}"
            )
        validated_sig = StructuralSignature(op_tags=op_tags, role=role, mech=mech)

    return BlockExtractionV21(
        block_yield=byield,
        units=tuple(validated_units),
        sig=validated_sig,
        macro_disciplines=macro_disciplines,
        topics=topics,
        places=places,
        years=years,
    )


def _shannon_token_entropy(texts: Sequence[str]) -> float:
    tokens: List[str] = []
    for txt in texts:
        tokens.extend(re.findall(r"[a-zà-öø-ÿ0-9]{3,}", txt.casefold()))
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def validate_batch_anti_template(
    extractions: Sequence[BlockExtractionV21],
    *,
    max_shared_prefix_ratio: float = 0.20,
    min_entropy_bits: float = 3.5,
) -> None:
    """Rifiuta lotti affetti da collasso template (stile 83k `giustificazioni/` legacy)."""
    mechs = [ext.sig.mech for ext in extractions if ext.sig is not None]
    if len(mechs) < 5:
        return

    prefixes = [" ".join(m.casefold().split()[:4]) for m in mechs]
    most_common_prefix, count = Counter(prefixes).most_common(1)[0]
    ratio = count / len(mechs)
    if count >= 3 and ratio > max_shared_prefix_ratio:
        raise SchemaValidationError(
            f"Gate Anti-Template fallito: prefisso '{most_common_prefix}' ripetuto nel {ratio:.0%} delle sig.mech"
        )

    entropy = _shannon_token_entropy(mechs)
    if entropy < min_entropy_bits:
        raise SchemaValidationError(
            f"Gate Anti-Template fallito: entropia lessicale troppo bassa ({entropy:.2f} bit < {min_entropy_bits})"
        )


def persist_block_extraction(
    conn: sqlite3.Connection,
    *,
    block_pk: int,
    block_uid: str,
    extraction: BlockExtractionV21,
) -> int:
    """Salva idempotentemente `units[]` e `sig` (se presente) nelle tabelle canoniche di `pack_corpus.db`."""
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted_units = 0

    for u in extraction.units:
        u_uid = make_unit_uid(block_uid, u.kind.value, u.stmt, u.quote)
        conn.execute(
            """
            INSERT INTO epistemic_units (
                unit_uid, block_pk, kind, mode, stmt, verbatim_quote,
                actors_json, vs_dispute, concepts_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_uid) DO UPDATE SET
                kind = excluded.kind,
                mode = excluded.mode,
                stmt = excluded.stmt,
                verbatim_quote = excluded.verbatim_quote,
                actors_json = excluded.actors_json,
                vs_dispute = excluded.vs_dispute,
                concepts_json = excluded.concepts_json
            """,
            (
                u_uid,
                block_pk,
                u.kind.value,
                u.mode.value,
                u.stmt,
                u.quote,
                json.dumps(list(u.who), ensure_ascii=False),
                u.vs,
                json.dumps(list(u.concepts), ensure_ascii=False),
                now_iso,
            ),
        )
        inserted_units += 1

    if extraction.sig is not None:
        conn.execute(
            """
            INSERT INTO structural_signatures (
                block_pk, mech, op_tags_json, anti_sudoku_role, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(block_pk) DO UPDATE SET
                mech = excluded.mech,
                op_tags_json = excluded.op_tags_json,
                anti_sudoku_role = excluded.anti_sudoku_role
            """,
            (
                block_pk,
                extraction.sig.mech,
                json.dumps([t.value for t in extraction.sig.op_tags], ensure_ascii=False),
                extraction.sig.role.value,
                now_iso,
            ),
        )
    else:
        if extraction.block_yield is BlockYield.LOW_OR_PARATEXT:
            conn.execute(
                "DELETE FROM structural_signatures WHERE block_pk = ? "
                "AND NOT EXISTS (SELECT 1 FROM curiosity_bridges cb WHERE cb.block_pk = structural_signatures.block_pk)",
                (block_pk,),
            )

    _upsert_block_metadata_v22(
        conn,
        block_pk=block_pk,
        block_yield=extraction.block_yield,
        macro_disciplines=extraction.macro_disciplines,
        topics=extraction.topics,
        places=extraction.places,
        years=extraction.years,
        now_iso=now_iso,
    )
    return inserted_units


def _upsert_block_metadata_v22(
    conn: sqlite3.Connection,
    *,
    block_pk: int,
    block_yield: BlockYield,
    macro_disciplines: Sequence[MacroDiscipline],
    topics: Sequence[str],
    places: Sequence[str],
    years: Sequence[str],
    now_iso: str,
) -> bool:
    has_v22_table = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='block_metadata_v22'"
        ).fetchone()
        is not None
    )
    if not has_v22_table:
        return False
    if block_yield is BlockYield.LOW_OR_PARATEXT:
        conn.execute("DELETE FROM block_metadata_v22 WHERE block_pk = ?", (block_pk,))
        return False
    if not (macro_disciplines or topics or places or years):
        return False
    conn.execute(
        """
        INSERT INTO block_metadata_v22 (
            block_pk, macro_disciplines_json, emergent_topics_json,
            places_json, historical_years_json, schema_version, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(block_pk) DO UPDATE SET
            macro_disciplines_json = excluded.macro_disciplines_json,
            emergent_topics_json = excluded.emergent_topics_json,
            places_json = excluded.places_json,
            historical_years_json = excluded.historical_years_json,
            schema_version = excluded.schema_version,
            updated_at = excluded.updated_at
        """,
        (
            block_pk,
            json.dumps([d.value for d in macro_disciplines], ensure_ascii=False),
            json.dumps(list(topics), ensure_ascii=False),
            json.dumps(list(places), ensure_ascii=False),
            json.dumps(list(years), ensure_ascii=False),
            SCHEMA_VERSION_V22,
            now_iso,
        ),
    )
    return True


def validate_v22_metadata_only(payload: Mapping[str, Any]) -> BlockExtractionV21:
    """Valida il solo strato `v2.2` (spettro macro-disciplinare, temi, luoghi, anni) senza `units[]`."""
    if not isinstance(payload, Mapping):
        raise SchemaValidationError("Il payload metadata-only v2.2 deve essere un oggetto JSON")
    try:
        byield = BlockYield(str(payload.get("yield", "")).strip())
    except ValueError as exc:
        raise SchemaValidationError(f"Campo 'yield' invalido: {payload.get('yield')!r}") from exc
    if byield is BlockYield.LOW_OR_PARATEXT:
        return BlockExtractionV21(block_yield=byield)
    macro_disciplines = _validate_macro_disciplines(payload.get("macro_disciplines"), min_len=1, max_len=4)
    topics = _clean_str_list(payload.get("topics"), "topics", min_len=1, max_len=6)
    places = _clean_str_list(payload.get("places"), "places", min_len=0, max_len=24)
    years = _clean_str_list(payload.get("years"), "years", min_len=0, max_len=16)
    return BlockExtractionV21(
        block_yield=byield,
        units=(),
        sig=None,
        macro_disciplines=macro_disciplines,
        topics=topics,
        places=places,
        years=years,
    )


def persist_v22_metadata_only(
    conn: sqlite3.Connection,
    *,
    block_pk: int,
    payload: Mapping[str, Any] | BlockExtractionV21,
) -> bool:
    """Aggiorna idempotentemente `block_metadata_v22` senza alterare `epistemic_units` o `structural_signatures`."""
    ext = payload if isinstance(payload, BlockExtractionV21) else validate_v22_metadata_only(payload)
    now_iso = datetime.now(timezone.utc).isoformat()
    return _upsert_block_metadata_v22(
        conn,
        block_pk=block_pk,
        block_yield=ext.block_yield,
        macro_disciplines=ext.macro_disciplines,
        topics=ext.topics,
        places=ext.places,
        years=ext.years,
        now_iso=now_iso,
    )
