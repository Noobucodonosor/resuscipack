"""Motore di Audit Deterministico e Rilettura Critica Avversaria per i *Nuovi Libri* (ADR-0004, TASK-BOOK-01).

Combina due barriere indipendenti prima della promozione di un capitolo:
1. Audit deterministico (`run_deterministic_chapter_audit`):
   - `verifica_scheda_report` (tutti i 6 Gate in modalità `capitolo_libro`: citazioni verbatim, 3 colori,
     zero gergo di debug, zero note orfane, figure esistenti su disco, ponte Libro Sbagliato);
   - controllo anti-poltrona: densità di prosa continua (`>= 500` parole, `>= 4` paragrafi continui),
     presenza di formule simboliche e verifica eseguibile `SymPy` di ogni `drill_key` dichiarato.
2. Revisore critico avversario separato (`run_adversarial_llm_critique`):
   - agente distinto dall'autore incaricato di cercare salti logici, errori di conto, distorsioni delle
     citazioni, deissi pendenti o toni da sussidiario prima di approvare il capitolo.
"""

from __future__ import annotations

import json
import os
import re
import time
import random
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..curriculum.dag import DEFAULT_DAG_PATH, load_unified_dag
from ..curriculum.drills_sympy import generate_drill_set, grade_drill_answer
from ..epistemic.batch_cli import (
    DEFAULT_GCP_PROJECT,
    DEFAULT_VERTEX_MODEL,
    _ONLINE_LOCATIONS,
    _VERTEX_TOKEN_CACHE,
    _decode_json_tolerant,
    _resolve_api_key,
)
from ..epistemic.verifica_citazioni import (
    DEFAULT_DB_PATH,
    leggi_scheda,
    verifica_scheda_report,
)

# Tipo del callable JSON iniettabile nei test: (prompt, response_schema) -> dict JSON
JsonLlmCallable = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]

ADVERSARIAL_CRITIQUE_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "OBJECT",
    "required": ["approved", "summary", "issues"],
    "properties": {
        "approved": {"type": "BOOLEAN"},
        "summary": {"type": "STRING"},
        "issues": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["category", "severity", "excerpt", "explanation", "suggested_fix"],
                "properties": {
                    "category": {
                        "type": "STRING",
                        "enum": [
                            "logical_leap",
                            "calculation_error",
                            "dangling_deixis",
                            "tone_violation",
                            "citation_misrepresentation",
                            "anti_poltrona",
                        ],
                    },
                    "severity": {"type": "STRING", "enum": ["critical", "major", "minor"]},
                    "excerpt": {"type": "STRING"},
                    "explanation": {"type": "STRING"},
                    "suggested_fix": {"type": "STRING"},
                },
            },
        },
    },
}


@dataclass(frozen=True)
class CritiqueIssue:
    """Singolo rilievo deterministico o critico-avversario emerso nella rilettura del capitolo."""

    layer: str  # "deterministic" | "adversarial_llm"
    category: str
    severity: str  # "critical" | "major" | "minor"
    excerpt: str
    explanation: str
    suggested_fix: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer": self.layer,
            "category": self.category,
            "severity": self.severity,
            "excerpt": self.excerpt,
            "explanation": self.explanation,
            "suggested_fix": self.suggested_fix,
        }


@dataclass(frozen=True)
class CritiqueReport:
    """Esito complessivo della doppia barriera (audit deterministico + revisore avversario)."""

    approved: bool
    deterministic_errors: Tuple[str, ...]
    adversarial_issues: Tuple[CritiqueIssue, ...]
    verifier_report_ok: bool
    summary: str
    reviewer_model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "deterministic_errors": list(self.deterministic_errors),
            "adversarial_issues": [i.to_dict() for i in self.adversarial_issues],
            "verifier_report_ok": self.verifier_report_ok,
            "summary": self.summary,
            "reviewer_model": self.reviewer_model,
        }

    def blocking_feedback_text(self) -> str:
        lines: List[str] = []
        if self.deterministic_errors:
            lines.append("ERRORI DETERMINISTICI BLOCCANTI:")
            for err in self.deterministic_errors:
                lines.append(f"- {err}")
        blocking_adv = [i for i in self.adversarial_issues if i.severity in {"critical", "major"}]
        if blocking_adv:
            lines.append("RILIEVI DEL REVISORE CRITICO AVVERSARIO:")
            for iss in blocking_adv:
                lines.append(
                    f"- [{iss.severity.upper()} | {iss.category}] {iss.explanation} "
                    f"(Estratto: {iss.excerpt!r} -> Correzione: {iss.suggested_fix})"
                )
        return "\n".join(lines).strip()


def call_editorial_json_llm(
    prompt: str,
    response_schema: Mapping[str, Any],
    *,
    provider: str = "vertex",
    model: Optional[str] = None,
    project_id: Optional[str] = None,
    thinking_budget: int = 1024,
    max_output_tokens: int = 4096,
    temperature: float = 0.2,
    timeout_seconds: int = 120,
) -> Tuple[Mapping[str, Any], str]:
    """Invoca il modello cloud in modalità JSON rigorosa (`fail-honest`, zero fallback mock)."""
    prov = str(provider or "vertex").strip().lower()
    if prov == "vertex":
        proj = project_id or os.environ.get("GCP_PROJECT_ID", DEFAULT_GCP_PROJECT)
        mdl = model or os.environ.get("VERTEX_GEMINI_MODEL", DEFAULT_VERTEX_MODEL)
        thinking_cfg: Dict[str, Any]
        if mdl.startswith("gemini-3"):
            tb = int(thinking_budget)
            level = "LOW" if tb <= 1024 else ("MEDIUM" if tb <= 3072 else "HIGH")
            thinking_cfg = {"thinkingLevel": level}
        else:
            thinking_cfg = {"thinkingBudget": int(thinking_budget)}

        gen_cfg: Dict[str, Any] = {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_output_tokens),
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
            "thinkingConfig": thinking_cfg,
        }
        body = json.dumps(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": gen_cfg,
            }
        ).encode("utf-8")

        locations: Tuple[str, ...] = (
            ("global",) if (mdl.startswith("gemini-3") or "-preview" in mdl) else _ONLINE_LOCATIONS
        )
        backoffs = (4.0, 12.0, 28.0, 55.0)
        last_err: Optional[Exception] = None
        for attempt in range(len(backoffs) + 1):
            loc = locations[attempt % len(locations)]
            host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
            url = (
                f"https://{host}/v1/projects/{proj}"
                f"/locations/{loc}/publishers/google/models/{mdl}:generateContent"
            )
            token = _VERTEX_TOKEN_CACHE.get_token(
                force_refresh=(
                    attempt > 0
                    and isinstance(last_err, urllib.error.HTTPError)
                    and last_err.code == 401
                )
            )
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "x-goog-user-project": proj,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=int(timeout_seconds)) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                cand0 = raw["candidates"][0]
                parts = cand0["content"]["parts"]
                text_parts = [
                    p["text"]
                    for p in parts
                    if isinstance(p, dict) and not p.get("thought") and "text" in p
                ]
                txt = "\n".join(text_parts) if text_parts else parts[0]["text"]
                try:
                    return _decode_json_tolerant(txt), mdl
                except json.JSONDecodeError as exc:
                    finish_reason = cand0.get("finishReason", "UNKNOWN")
                    raise RuntimeError(
                        f"JSON incompleto da Vertex AI ({mdl}, finishReason={finish_reason}, "
                        f"chars={len(txt)}): {exc}"
                    ) from exc
            except urllib.error.HTTPError as exc:
                last_err = exc
                if exc.code == 401 and attempt == 0:
                    _VERTEX_TOKEN_CACHE.invalidate()
                    continue
                if exc.code == 404 and loc != "global" and "global" in locations and attempt < len(backoffs):
                    continue
                if exc.code in {429, 500, 503} and attempt < len(backoffs):
                    time.sleep(backoffs[attempt] + random.uniform(0.0, 2.5))
                    continue
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="ignore")[:260]
                except Exception:
                    pass
                raise RuntimeError(f"Vertex AI HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_err = exc
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt] + random.uniform(0.0, 2.5))
                    continue
                raise RuntimeError(f"Errore di rete Vertex AI ({mdl}): {exc}") from exc
        raise RuntimeError(f"Vertex AI fallito dopo retry ({mdl}): {last_err}")

    if prov == "gemini":
        api_key = _resolve_api_key("gemini")
        mdl = model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": float(temperature),
                "maxOutputTokens": int(max_output_tokens),
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=int(timeout_seconds)) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        txt = raw["candidates"][0]["content"]["parts"][0]["text"]
        return _decode_json_tolerant(txt), mdl

    if prov == "deepseek":
        api_key = _resolve_api_key("deepseek")
        mdl = model or "deepseek-chat"
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(
                {
                    "model": mdl,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_tokens": int(max_output_tokens),
                    "temperature": float(temperature),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=int(timeout_seconds)) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        txt = raw["choices"][0]["message"]["content"]
        return _decode_json_tolerant(txt), mdl

    raise ValueError(f"Provider non supportato: {provider!r}")


def _extract_prose_before_apparatus(body: str) -> str:
    without_defs = re.sub(r"^\[\^\d+\]:.*$", "", body, flags=re.MULTILINE)
    return re.split(
        r"^##\s+Apparato\s+delle\s+fonti\b",
        without_defs,
        maxsplit=1,
        flags=re.IGNORECASE | re.MULTILINE,
    )[0]


def _count_prose_words(text: str) -> int:
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    cleaned = re.sub(r"\[\^\d+\]", " ", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+.*$", " ", cleaned, flags=re.MULTILINE)
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", cleaned)
    return len(words)


def _count_continuous_paragraphs(prose: str) -> int:
    blocks = re.split(r"\n\s*\n", prose.strip())
    continuous = 0
    for blk in blocks:
        s = blk.strip()
        if not s:
            continue
        if s.startswith(("#", "-", "*", "![", ">", "|", "$$")):
            continue
        if re.match(r"^\d+[\.\)]\s+", s):
            continue
        if len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", s)) >= 30:
            continuous += 1
    return continuous


def run_deterministic_chapter_audit(
    chapter_path: Path | str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    dag_path: Path | str = DEFAULT_DAG_PATH,
    min_prose_words: int = 500,
    min_continuous_paragraphs: int = 4,
) -> List[str]:
    """Verifica deterministica completa: 6 Gate di `verifica_citazioni` + prosa continua + figure + SymPy."""
    path = Path(chapter_path)
    errors: List[str] = []

    try:
        meta, corpo = leggi_scheda(path)
    except Exception as exc:
        return [f"[parse] Errore lettura capitolo {path}: {exc}"]

    if str(meta.get("tipo", "")).strip().lower() != "capitolo_libro":
        errors.append("Il frontmatter YAML deve dichiarare `tipo: capitolo_libro`.")

    v_rep = verifica_scheda_report(path, db_path=db_path)
    errors.extend(v_rep.all_errors)

    prose = _extract_prose_before_apparatus(corpo)
    word_count = _count_prose_words(prose)
    if word_count < int(min_prose_words):
        errors.append(
            f"[anti_poltrona] Prosa continua troppo breve ({word_count} parole; richieste >= {min_prose_words})."
        )

    para_count = _count_continuous_paragraphs(prose)
    if para_count < int(min_continuous_paragraphs):
        errors.append(
            f"[anti_poltrona] Pochi paragrafi narrativi continui da >=30 parole ({para_count}; richiesti >= {min_continuous_paragraphs})."
        )

    if not re.search(r"!\[[^\]]*\]\([^)]+\)", corpo):
        errors.append("[broken_asset] Il capitolo deve includere almeno una figura reale o un diagramma SVG.")

    # Verifica `drill_keys` contro il DAG unificato e `SymPy`
    drill_keys = list(meta.get("drill_keys") or [])
    if not drill_keys:
        errors.append("[sympy_drill] Nessun `drill_key` dichiarato nel frontmatter.")
    else:
        known_dag_keys: Optional[set[str]] = None
        if Path(dag_path).exists():
            dag = load_unified_dag(dag_path)
            known_dag_keys = {
                str(n["drill_key"]) for n in dag["nodes"].values() if n.get("drill_key")
            }
        for dk in drill_keys:
            if known_dag_keys is not None and str(dk) not in known_dag_keys:
                errors.append(f"[sympy_drill] drill_key sconosciuto nel DAG: {dk!r}")
                continue
            drills = generate_drill_set("audit", str(dk), count=2, seed=42)
            if len(drills) < 2:
                errors.append(f"[sympy_drill] drill_key {dk!r} ha prodotto meno di 2 esercizi.")
                continue
            for idx, dr in enumerate(drills, start=1):
                res = grade_drill_answer(dr["expected"], dr["expected"])
                if not res.get("is_correct"):
                    errors.append(
                        f"[sympy_drill] Auto-verifica SymPy fallita per {dk!r} #{idx}: {res}"
                    )

    return errors


def build_adversarial_critique_prompt(
    chapter_markdown: str,
    dossier_sources_summary: Sequence[Dict[str, Any]],
) -> str:
    """Costruisce il prompt separato del Revisore Critico Avversario (zero indulgenza editorial)."""
    sources_lines = []
    for src in dossier_sources_summary:
        line = (
            f"- Fonte block #{src.get('block_pk')} | {src.get('book_title')} (p. {src.get('page', '?')}): "
            f"citazione «{src.get('quote', '')}»"
        )
        if src.get("stmt"):
            line += f" | Contesto verificato del blocco: {src['stmt']}"
        if src.get("vs_dispute"):
            line += f" | Controversia (`vs`): {src['vs_dispute']}"
        sources_lines.append(line)
    sources_block = "\n".join(sources_lines) if sources_lines else "(nessuna fonte nel dossier)"

    return (
        "Sei il REVISORE CRITICO AVVERSARIO di una casa editrice scientifica di alto livello.\n"
        "Un autore ha appena scritto questo capitolo di un nuovo libro matematico-culturale per studenti universitari.\n"
        "Il tuo compito NON è lodare il testo, ma CERCARE DIFETTI REALI e segnalare tutto ciò che indebolisce rigore o leggibilità.\n\n"
        "CHECKLIST SEVERA (marca `approved: false` se trovi almeno un problema `critical` o `major`):\n"
        "1. `logical_leap`: salti logici nella parte formale o nelle dimostrazioni (es. affermare una proprietà senza averla giustificata).\n"
        "2. `calculation_error`: errori di calcolo numerico/algebrico, soluzioni sbagliate negli esempi svolti o negli esercizi, formule LaTeX incoerenti.\n"
        "3. `citation_misrepresentation`: la prosa attribuisce a un autore (Euclide, Galileo, Cantor, Marconi, Wittgenstein...) un concetto che la sua citazione verbatim e il suo contesto verificato (`stmt`) non sostengono.\n"
        "4. `dangling_deixis`: riferimenti opachi ('il Nostro', 'vedi sopra', 'la figura successiva' quando la figura non è lì, pronome ambiguo). Nota: i percorsi relativi come `![...](../assets/*.svg)` sono figure reali già verificate su disco dall'audit deterministico: segnala `dangling_deixis` solo se la prosa rinvia a una figura assente o ne contraddice la didascalia.\n"
        "5. `tone_violation`: tono da sussidiario elementare/infantile, frasi vuote da AI ('In un mondo sempre più...', 'Scopriamo insieme'), oppure gergo burocratico da scheda.\n"
        "6. `anti_poltrona`: esempi o esercizi troppo passivi o privi di verifica/calcolo effettivo.\n\n"
        "FONTI VERIFICATE DISPONIBILI NEL DOSSIER:\n"
        f"{sources_block}\n\n"
        "CAPITOLO DA REVISIONARE:\n"
        "<<<CAPITOLO>>>\n"
        f"{chapter_markdown}\n"
        "<<<FINE_CAPITOLO>>>\n\n"
        "Restituisci SOLO JSON valido conforme allo schema (`approved`, `summary`, `issues[]`).\n"
        "Segnala al massimo i 6 rilievi più importanti, mantenendo `excerpt` (<= 20 parole), `explanation` e `suggested_fix` sintetici e precisi.\n"
        "Se il capitolo è davvero rigoroso, adulto, fedele alle citazioni e privo di errori di conto o salti logici, "
        "imposta `approved: true` (puoi comunque segnalare eventuali piccoli ritocchi `minor`)."
    )


def run_adversarial_llm_critique(
    chapter_markdown: str,
    dossier_sources_summary: Sequence[Dict[str, Any]],
    *,
    provider: str = "vertex",
    model: str = "gemini-3-flash-preview",
    critic_llm: Optional[JsonLlmCallable] = None,
    thinking_budget: int = 1024,
) -> Tuple[Tuple[CritiqueIssue, ...], str, Optional[str]]:
    """Esegue la rilettura critica avversaria tramite revisore separato (reale o callable iniettato nei test)."""
    prompt = build_adversarial_critique_prompt(chapter_markdown, dossier_sources_summary)
    if critic_llm is not None:
        raw_payload = critic_llm(prompt, ADVERSARIAL_CRITIQUE_RESPONSE_SCHEMA)
        used_model: Optional[str] = "injected-critic-llm"
    else:
        raw_payload, used_model = call_editorial_json_llm(
            prompt,
            ADVERSARIAL_CRITIQUE_RESPONSE_SCHEMA,
            provider=provider,
            model=model,
            thinking_budget=thinking_budget,
            max_output_tokens=16384,
            temperature=0.1,
            timeout_seconds=120,
        )

    issues_out: List[CritiqueIssue] = []
    for item in raw_payload.get("issues") or []:
        if not isinstance(item, Mapping):
            continue
        issues_out.append(
            CritiqueIssue(
                layer="adversarial_llm",
                category=str(item.get("category") or "logical_leap"),
                severity=str(item.get("severity") or "major").lower(),
                excerpt=str(item.get("excerpt") or "").strip(),
                explanation=str(item.get("explanation") or "").strip(),
                suggested_fix=str(item.get("suggested_fix") or "").strip(),
            )
        )

    summary = str(raw_payload.get("summary") or "").strip() or "Rilettura critica completata."
    # Se il modello ha dichiarato approved=false senza elencare issue critical/major, esplicita il blocco
    if raw_payload.get("approved") is False and not any(
        i.severity in {"critical", "major"} for i in issues_out
    ):
        issues_out.append(
            CritiqueIssue(
                layer="adversarial_llm",
                category="logical_leap",
                severity="major",
                excerpt="",
                explanation=summary,
                suggested_fix="Rafforzare i passaggi segnalati dal revisore critico.",
            )
        )

    return tuple(issues_out), summary, used_model


def audit_and_critique_chapter(
    chapter_path: Path | str,
    dossier_sources_summary: Sequence[Dict[str, Any]],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    dag_path: Path | str = DEFAULT_DAG_PATH,
    provider: str = "vertex",
    critic_model: str = "gemini-3-flash-preview",
    critic_llm: Optional[JsonLlmCallable] = None,
    min_prose_words: int = 500,
    min_continuous_paragraphs: int = 4,
) -> CritiqueReport:
    """Combina audit deterministico e rilettura critica avversaria per decidere la promozione del capitolo."""
    path = Path(chapter_path)
    det_errors = tuple(
        run_deterministic_chapter_audit(
            path,
            db_path=db_path,
            dag_path=dag_path,
            min_prose_words=min_prose_words,
            min_continuous_paragraphs=min_continuous_paragraphs,
        )
    )
    verifier_ok = len(verifica_scheda_report(path, db_path=db_path).all_errors) == 0
    chapter_text = path.read_text(encoding="utf-8")

    adv_issues, summary, used_model = run_adversarial_llm_critique(
        chapter_text,
        dossier_sources_summary,
        provider=provider,
        model=critic_model,
        critic_llm=critic_llm,
    )

    has_blocking_adv = any(i.severity in {"critical", "major"} for i in adv_issues)
    approved = (len(det_errors) == 0) and (not has_blocking_adv)
    return CritiqueReport(
        approved=approved,
        deterministic_errors=det_errors,
        adversarial_issues=adv_issues,
        verifier_report_ok=verifier_ok,
        summary=summary,
        reviewer_model=used_model,
    )


__all__ = [
    "ADVERSARIAL_CRITIQUE_RESPONSE_SCHEMA",
    "CritiqueIssue",
    "CritiqueReport",
    "JsonLlmCallable",
    "audit_and_critique_chapter",
    "build_adversarial_critique_prompt",
    "call_editorial_json_llm",
    "run_adversarial_llm_critique",
    "run_deterministic_chapter_audit",
]
