"""Motore di verifica attiva SecAI (ADR-0003, TASK-SECAI-02):
1. Fast-Forward Diagnostico parametrico corretto simbolicamente da `SymPy` (accetta `7/20` == `0.35`,
   espressioni algebriche equivalenti, derivate composte, intervalli con modulo, RSA, complemento a due);
2. Verificatore di 5 invarianti geometrici con `SymPy` + generazione curva SVG per grafici disegnati a mano (`P0.6`);
3. Rubrica booleana `Proof-Step Check` per le dimostrazioni scritte a libro chiuso (`sqrt(2)` irrazionale,
   principio di induzione, hash crittografico != cifratura).
"""

from __future__ import annotations

import math
import random
import re
from typing import Any

import sympy as sp

x_sym, y_sym, w_sym = sp.symbols("x y w", real=True)


def _sympy_equivalent(student_raw: str, expected_raw: str) -> tuple[bool, str]:
    """Verifica con SymPy se la risposta dello studente è matematicamente equivalente all'attesa
    (es. `7/20` == `0.35`, `(x-1)*(x+1)` == `x**2 - 1`, `2*sqrt(2)` == `sqrt(8)`)."""
    s_clean = str(student_raw or "").strip()
    if not s_clean:
        return False, "Risposta vuota."

    # Normalizzazioni sintattiche amichevoli per l'input studente italiano
    norm_s = (
        s_clean.replace(",", ".")
        .replace("^", "**")
        .replace("−", "-")
        .replace("×", "*")
        .replace("÷", "/")
    )
    norm_e = (
        str(expected_raw)
        .strip()
        .replace(",", ".")
        .replace("^", "**")
        .replace("−", "-")
    )

    # Caso risposte testuali/booleane esatte (es. "iniettiva", "vero", "no", intervallo "[95, 145]")
    if re.fullmatch(r"[A-Za-zÀ-ÿ_]+", norm_e):
        ok = norm_s.lower() == norm_e.lower()
        return ok, ("Corretto!" if ok else f"Atteso: {expected_raw}")

    if norm_e.startswith("[") and norm_e.endswith("]"):
        nums_s = re.findall(r"-?\d+(?:\.\d+)?(?:/\d+)?", norm_s)
        nums_e = re.findall(r"-?\d+(?:\.\d+)?(?:/\d+)?", norm_e)
        if len(nums_s) == len(nums_e) and len(nums_e) >= 2:
            ok = all(_sympy_scalar_eq(a, b) for a, b in zip(nums_s, nums_e))
            return ok, ("Intervallo/vettore equivalente verificato da SymPy!" if ok else f"Estremi attesi: {expected_raw}")
        return False, f"Formato atteso come coppia/vettore: {expected_raw}"

    ok = _sympy_scalar_eq(norm_s, norm_e)
    return ok, ("Equivalenza simbolica verificata da SymPy!" if ok else f"Non equivalente. Valore/forma corretta: {expected_raw}")


def _sympy_scalar_eq(s_expr_str: str, e_expr_str: str) -> bool:
    local_dict = {
        "x": x_sym,
        "y": y_sym,
        "w": w_sym,
        "pi": sp.pi,
        "e": sp.E,
        "I": sp.I,
        "i": sp.I,
        "sqrt": sp.sqrt,
        "log": sp.log,
        "ln": sp.log,
        "sin": sp.sin,
        "cos": sp.cos,
        "exp": sp.exp,
        "oo": sp.oo,
    }
    try:
        s_expr = sp.sympify(s_expr_str, locals=local_dict, convert_xor=True)
        e_expr = sp.sympify(e_expr_str, locals=local_dict, convert_xor=True)
    except Exception:
        return s_expr_str.strip().lower() == e_expr_str.strip().lower()

    try:
        diff = sp.simplify(sp.nsimplify(s_expr, rational=True) - sp.nsimplify(e_expr, rational=True))
        if diff == 0:
            return True
        if not s_expr.free_symbols and not e_expr.free_symbols:
            return abs(complex(sp.N(s_expr)) - complex(sp.N(e_expr))) < 1e-9
    except Exception:
        pass
    return False


def generate_drill_set(node_id: str, drill_key: str | None = None, count: int = 5, seed: int | None = None) -> list[dict[str, Any]]:
    """Genera `count` esercizi parametrici deterministici (calcolo + 'che cosa si rompe') per il nodo dato."""
    rng = random.Random(seed if seed is not None else sum(ord(c) for c in node_id) + 2026)
    key = drill_key or node_id
    items: list[dict[str, Any]] = []

    for i in range(count):
        item = _build_single_drill(node_id, key, i, rng)
        items.append(item)
    return items


def _build_arithmetic_drill(key: str, idx: int, rng: random.Random) -> dict[str, Any] | None:
    if key in {"drill_number_order", "numeri.ordine"}:
        if idx % 2 == 0:
            ans = "-3/4"
            prompt = "Tra i numeri razionali negativi -3/4 e -4/5, quale è il maggiore (più a destra sulla retta)?"
            why = "Poiché -3/4 = -0.75 > -0.80 = -4/5, -3/4 si trova più a destra di -4/5 sulla retta."
        else:
            p, q = rng.choice([(7, 12), (5, 8), (4, 9)])
            r, s = rng.choice([(1, 2), (2, 3), (3, 7)])
            diff = abs(sp.Rational(p, q) - sp.Rational(r, s))
            ans = str(diff)
            prompt = f"Calcola la distanza esatta sulla retta reale tra i razionali {p}/{q} e {r}/{s}."
            why = f"|{p}/{q} - {r}/{s}| = {diff} riducendo allo stesso denominatore."
    elif key in {"drill_addition_properties", "operazioni.addizione"}:
        a = rng.randint(14, 38)
        comp = rng.choice([100, 200])
        c = comp - a
        b = rng.randint(23, 79)
        ans = str(comp + b)
        prompt = f"Applica le proprietà commutativa e associativa per calcolare rapidamente ({a} + {b}) + {c}."
        why = f"Riordinando ({a} + {c}) + {b} si ottiene {comp} + {b} = {ans}."
    elif key in {"drill_column_carry", "operazioni.colonna"}:
        if idx % 2 == 0:
            a = rng.randint(240, 490)
            b = rng.randint(155, 389)
            ans = str(a + b)
            prompt = f"Esegui l'addizione posizionale con riporto in base 10: {a} + {b}."
            why = f"Sommando unità, decine e centinaia con riporto al decimo superiore si ottiene {a + b}."
        else:
            base = rng.choice([400, 500, 700])
            sub = rng.randint(127, 268)
            ans = str(base - sub)
            prompt = f"Calcola con prestito posizionale su zeri consecutivi: {base} - {sub}."
            why = f"Scomponendo le centinaia in decine e unità per il prestito: {base} - {sub} = {ans}."
    elif key in {"drill_multiplication_grid", "operazioni.moltiplicazione"}:
        r = rng.randint(6, 12)
        c = rng.randint(7, 14)
        if idx % 2 == 0:
            ans = str(r * c)
            prompt = f"Uno schieramento rettangolare ha {r} righe e {c} colonne: quanti elementi contiene?"
            why = f"La griglia di {r} righe per {c} colonne equivale a {r} · {c} = {r * c}."
        else:
            ans = str(c)
            prompt = f"[Che cosa si rompe] Se in uno schieramento {r} × {c} aggiungi una riga intera ottenendo ({r} + 1) × {c}, di quanto aumenta il totale?"
            why = f"({r}+1)·{c} - {r}·{c} = {c} per linearità della moltiplicazione."
    elif key in {"drill_euclidean_division", "operazioni.divisione"}:
        d = rng.choice([6, 7, 8, 9, 11])
        q = rng.randint(5, 11)
        r = rng.randint(1, d - 1)
        a = d * q + r
        if idx % 2 == 0:
            ans = f"[{q}, {r}]"
            prompt = f"Determina quoziente q e resto r della divisione euclidea di {a} per {d} (risposta come coppia [q, r] con 0 <= r < {d})."
            why = f"{a} = {d} · {q} + {r}, con 0 <= {r} < {d}."
        else:
            ans = str(r)
            prompt = f"Nella divisione euclidea di {a} per {d}, quale è il resto non negativo r ∈ [0, {d - 1}]?"
            why = f"Poiché {d} · {q} = {d * q} <= {a} < {d * (q + 1)}, il resto unico è {a} - {d * q} = {r}."
    else:
        return None
    return {"prompt": prompt, "expected": ans, "explanation": why}


def _build_fractions_divisibility_drill(key: str, idx: int, rng: random.Random) -> dict[str, Any] | None:
    if key in {"drill_fraction_meaning", "frazioni.significato"}:
        b = rng.choice([5, 7, 8, 9])
        a = rng.randint(2, b - 1)
        tot = b * rng.randint(4, 9)
        ans = str((tot * a) // b)
        prompt = f"Calcola i {a}/{b} dell'intero {tot}."
        why = f"Una parte unitaria vale {tot}/{b} = {tot // b}; prendendone {a} si ottiene {ans}."
    elif key in {"drill_fraction_equivalence", "frazioni.equivalenza"}:
        b = rng.choice([3, 4, 5, 7])
        a = rng.randint(1, b - 1)
        while math.gcd(a, b) != 1:
            a = rng.randint(1, b - 1)
        k = rng.randint(3, 8)
        ans = str(a * k)
        prompt = f"Trova il numeratore x che rende equivalenti le frazioni {a}/{b} = x/{b * k}."
        why = f"Moltiplicando numeratore e denominatore per lo stesso fattore {k} != 0 si ottiene x = {a} · {k} = {ans}."
    elif key in {"drill_fraction_mul_div", "frazioni.moltiplicazione-divisione"}:
        a, b = rng.choice([(2, 3), (3, 4), (4, 5), (5, 6)])
        c, d = rng.choice([(5, 7), (3, 8), (2, 9), (7, 10)])
        val = sp.Rational(a, b) / sp.Rational(c, d)
        ans = str(val)
        prompt = f"Calcola il quoziente ({a}/{b}) ÷ ({c}/{d}) moltiplicando per il reciproco (forma ridotta)."
        why = f"({a}/{b}) · ({d}/{c}) = {a * d}/{b * c} = {val}."
    elif key in {"drill_decimals", "numeri.decimali"}:
        pairs = [("0.125", sp.Rational(3, 8)), ("0.25", sp.Rational(3, 4)), ("0.625", sp.Rational(1, 8))]
        dec_str, frac = pairs[idx % len(pairs)]
        val = sp.Rational(dec_str) + frac
        ans = str(val)
        prompt = f"Calcola il valore esatto della somma {dec_str} + {frac} convertendo il decimale in frazione."
        why = f"{dec_str} = {sp.Rational(dec_str)}; sommando {frac} si ottiene {val}."
    elif key in {"drill_prime_factorization", "divisibilita.multipli-primi"}:
        exp2 = rng.randint(2, 5)
        odd = rng.choice([3, 5, 7, 9, 15])
        n = (2 ** exp2) * odd
        ans = str(exp2)
        prompt = f"Nella fattorizzazione unica in numeri primi di {n}, quale è l'esponente del fattore primo 2?"
        why = f"{n} = 2^{exp2} · {odd}: dividendo ripetutamente per 2 si estrae esattamente l'esponente {exp2}."
    elif key in {"drill_lcm", "divisibilita.mcm"}:
        a, b = [(12, 18), (15, 20), (14, 21), (18, 24)][idx % 4]
        val = math.lcm(a, b)
        ans = str(val)
        prompt = f"Calcola il minimo comune multiplo mcm({a}, {b}) tramite scomposizione in fattori primi."
        why = f"MCD({a}, {b}) = {math.gcd(a, b)}, dunque mcm({a}, {b}) = ({a} · {b}) / {math.gcd(a, b)} = {val}."
    elif key in {"drill_gcd", "divisibilita.mcd"}:
        a, b = [(84, 36), (96, 60), (105, 45), (126, 48)][idx % 4]
        val = math.gcd(a, b)
        ans = str(val)
        prompt = f"Applica l'algoritmo euclideo delle divisioni successive per trovare MCD({a}, {b})."
        why = f"Le divisioni successive mostrano che il massimo divisore comune di {a} e {b} è {val}."
    elif key in {"drill_signed_integers", "numeri.relativi"}:
        a = rng.randint(3, 8)
        b = rng.randint(2, 6)
        c = rng.randint(4, 12)
        val = (-a) * (-b) - c
        ans = str(val)
        prompt = f"Valuta l'espressione tra numeri interi relativi: (-{a}) · (-{b}) - {c}."
        why = f"Il prodotto di due negativi è positivo ({a * b}); sottraendo {c} si ottiene {val}."
    elif key in {"drill_exponent_rules", "operazioni.potenze-base"}:
        p = rng.randint(4, 7)
        q = rng.randint(2, 4)
        r = rng.randint(3, p + q - 2)
        val = 2 ** (p + q - r)
        ans = str(val)
        prompt = f"Semplifica applicando le proprietà delle potenze in base 2: (2^{p} · 2^{q}) / 2^{r}."
        why = f"2^({p} + {q} - {r}) = 2^{p + q - r} = {val}."
    elif key in {"drill_square_roots", "operazioni.radici-base"}:
        k = rng.randint(2, 5)
        m = rng.choice([2, 3, 5, 7])
        rad = k * k * m
        ans = f"{k}*sqrt({m})"
        prompt = f"Porta fuori dal segno di radice il fattore quadratico e semplifica sqrt({rad}) (usa la sintassi k*sqrt(m))."
        why = f"Poiché {rad} = {k}^2 · {m}, segue sqrt({rad}) = {k}*sqrt({m})."
    else:
        return None
    return {"prompt": prompt, "expected": ans, "explanation": why}


def _build_proportions_algebra_drill(key: str, idx: int, rng: random.Random) -> dict[str, Any] | None:
    if key in {"drill_proportions_percent", "rapporti.proporzioni-percentuali"}:
        if idx % 2 == 0:
            pct = rng.choice([10, 20, 30])
            ans = str(sp.Rational((100 + pct) * (100 - pct), 100))
            prompt = f"[Che cosa si rompe] Un prezzo di 100 euro subisce prima un aumento del {pct}% e poi uno sconto del {pct}%: quale è il prezzo finale?"
            why = f"100 · (1 + {pct}/100) · (1 - {pct}/100) = 100 · (1 - ({pct}/100)^2) = {ans} (non torna a 100!)."
        else:
            k = rng.randint(2, 5)
            a, b = rng.choice([(3, 4), (5, 6), (2, 7)])
            ans = str(a * k)
            prompt = f"Risolvi la proporzione {a} : {b} = x : {b * k} ricavando il termine incognito x."
            why = f"Per la proprietà fondamentale x = ({a} · {b * k}) / {b} = {ans}."
    elif key in {"drill_unit_measurement", "misure.confronto-unita"}:
        km = rng.choice([2, 3, 5])
        m = rng.choice([250, 500])
        val = sp.Rational(km * 1000, m)
        ans = str(val)
        prompt = f"Calcola il rapporto adimensionale tra due lunghezze esprimendole nella stessa unità: ({km} km) / ({m} m)."
        why = f"Convertendo {km} km = {km * 1000} m, il rapporto omogeneo è {km * 1000}/{m} = {val}."
    elif key in {"drill_metric_conversions", "misure.equivalenze-decimali"}:
        m2 = rng.choice([2, 3, 5])
        ans = str(m2 * 10000)
        prompt = f"Converti una superficie di {m2} m^2 in cm^2 ricordando che 1 m = 100 cm."
        why = f"Poiché (100 cm)^2 = 10000 cm^2, {m2} m^2 = {m2} · 10^4 = {ans} cm^2."
    elif key in {"drill_sequence_pattern", "relazioni.sequenze-regole"}:
        a0 = rng.randint(1, 3)
        a1 = 2 * a0 + 1
        a2 = 2 * a1 + 1
        a3 = 2 * a2 + 1
        ans = str(a3)
        prompt = f"Data la successione definita ricorsivamente da a_0 = {a0} e a_{{n+1}} = 2*a_n + 1, calcola il termine a_3."
        why = f"a_1 = {a1}, a_2 = {a2}, a_3 = 2·{a2} + 1 = {a3}."
    elif key in {"drill_literal_expressions", "relazioni.lettere-formule"}:
        a = rng.randint(2, 5)
        b = rng.randint(2, 6)
        c = rng.randint(1, a)
        d = rng.randint(1, 5)
        expr = sp.expand(a * (x_sym + b) - c * x_sym + d)
        ans = str(expr)
        prompt = f"Semplifica l'espressione letterale raccogliendo i termini simili: {a}*(x + {b}) - {c}*x + {d}."
        why = f"Distribuendo {a} e sommando i termini in x e le costanti si ottiene {expr}."
    elif key in {"drill_direct_inverse_prop", "relazioni.proporzionalita-diretta-inversa"}:
        x1 = rng.choice([3, 4, 6])
        y1 = rng.choice([8, 12, 10])
        k = x1 * y1
        x2 = rng.choice([2, 12])
        while k % x2 != 0:
            x2 += 1
        ans = str(k // x2)
        prompt = f"Due grandezze positive x e y sono inversamente proporzionali (x·y = k). Se x = {x1} dà y = {y1}, quanto vale y quando x = {x2}?"
        why = f"La costante invariante è k = {x1}·{y1} = {k}; dunque per x = {x2} si ha y = {k}/{x2} = {ans}."
    else:
        return None
    return {"prompt": prompt, "expected": ans, "explanation": why}


def _build_geometry_drill(key: str, idx: int, rng: random.Random) -> dict[str, Any] | None:
    if key in {"drill_segments_length", "geometria.punti-rette-segmenti"}:
        a = rng.randint(2, 8)
        b = rng.randint(a + 6, a + 18)
        mid = sp.Rational(a + b, 2)
        ans = str(mid)
        prompt = f"Su una retta orientata il segmento AB ha estremi x_A = {a} e x_B = {b}: qual è l'ascissa del punto medio M?"
        why = f"Il punto medio ha ascissa (x_A + x_B)/2 = ({a} + {b})/2 = {mid}."
    elif key in {"drill_angles_degrees", "geometria.angoli-rotazioni"}:
        if idx % 2 == 0:
            a1 = rng.randint(35, 65)
            a2 = rng.randint(40, 75)
            ans = str(180 - a1 - a2)
            prompt = f"Due angoli interni di un triangolo euclideo misurano {a1}° e {a2}°: quanti gradi misura il terzo angolo?"
            why = f"La somma degli angoli interni è 180°, quindi 180 - ({a1} + {a2}) = {ans}°."
        else:
            n = rng.choice([5, 6, 8])
            ans = str((n - 2) * 180)
            prompt = f"Quanti gradi misura la somma degli angoli interni di un poligono convesso di {n} lati?"
            why = f"Scomponendolo in ({n} - 2) triangoli da un vertice si ha ({n} - 2) · 180° = {ans}°."
    elif key in {"drill_perpendicular_angles", "geometria.parallelismo-perpendicolarita"}:
        alpha = rng.choice([38, 52, 64, 71])
        ans = str(180 - alpha)
        prompt = f"Due rette parallele sono tagliate da una trasversale formando un angolo acuto di {alpha}°: quanto misura ciascun angolo ottuso coniugato interno?"
        why = f"Gli angoli coniugati interni tra parallele sono supplementari: 180° - {alpha}° = {ans}°."
    elif key in {"drill_triangle_perimeter", "geometria.poligoni-perimetro"}:
        a = rng.randint(4, 7)
        b = rng.randint(6, 10)
        ans = str(a + b - 1)
        prompt = f"Due lati di un triangolo misurano {a} e {b}: qual è il massimo valore intero ammissibile per il terzo lato c (disuguaglianza triangolare)?"
        why = f"Deve valere c < a + b = {a + b}; dunque il massimo intero è {a + b - 1}."
    elif key in {"drill_rectangle_area", "geometria.area-rettangolo-schieramento"}:
        b = rng.randint(4, 9)
        h = rng.randint(3, 7)
        if idx % 2 == 0:
            ans = str(b * h)
            prompt = f"Un rettangolo ha base {b} e altezza {h}: qual è la sua area in unità quadrate?"
            why = f"Area = base · altezza = {b} · {h} = {b * h}."
        else:
            ans = "4"
            prompt = "[Che cosa si rompe] Se raddoppi entrambi i lati di un rettangolo, per quale fattore viene moltiplicata la sua area?"
            why = "Area(2b, 2h) = (2b)·(2h) = 4·(bh): la scala quadratrica moltiplica l'area per 2^2 = 4."
    elif key in {"drill_triangle_area", "geometria.area-triangolo-poligoni"}:
        b = rng.choice([6, 8, 10, 12])
        h = rng.randint(5, 9)
        ans = str((b * h) // 2)
        prompt = f"Calcola l'area di un triangolo di base b = {b} e altezza h = {h} tramite equiscomponibilità in metà rettangolo."
        why = f"Area = (b · h)/2 = ({b} · {h})/2 = {ans}."
    elif key in {"drill_translation_coords", "geometria.simmetrie-traslazioni"}:
        x0, y0 = rng.randint(1, 5), rng.randint(2, 6)
        dx, dy = rng.randint(3, 7), -rng.randint(1, 3)
        ans = f"[{x0 + dx}, {y0 + dy}]"
        prompt = f"Applica la traslazione di vettore v = ({dx}, {dy}) al punto P({x0}, {y0}): scrivi le coordinate immagine [x', y']."
        why = f"x' = {x0} + ({dx}) = {x0 + dx}, y' = {y0} + ({dy}) = {y0 + dy}."
    elif key in {"drill_circle_pi", "geometria.cerchio-pi-greco"}:
        r = rng.randint(3, 8)
        if idx % 2 == 0:
            ans = f"{2 * r}*pi"
            prompt = f"Esprimi la lunghezza esatta della circonferenza di raggio r = {r} in funzione simbolica di pi."
            why = f"C = 2 · pi · r = {2 * r}*pi."
        else:
            ans = f"{r * r}*pi"
            prompt = f"Esprimi l'area esatta del cerchio di raggio r = {r} in funzione simbolica di pi."
            why = f"A = pi · r^2 = {r * r}*pi."
    elif key in {"drill_similarity_scale", "geometria.similitudine-scala"}:
        s = rng.choice([2, 3, 5])
        a0 = rng.randint(4, 9)
        ans = str(a0 * s * s)
        prompt = f"Due poligoni simili hanno rapporto di similitudine lineare k = {s}. Se il più piccolo ha area {a0}, qual è l'area del più grande?"
        why = f"Le aree scalano come il quadrato del fattore lineare: {a0} · {s}^2 = {ans}."
    elif key in {"drill_volume_scaling", "geometria.solidi-volume"}:
        s = rng.choice([2, 3, 4])
        v0 = rng.randint(2, 6)
        ans = str(v0 * (s ** 3))
        prompt = f"Un solido di volume {v0} cm^3 viene ingrandito in scala moltiplicando ogni spigolo per {s}: qual è il nuovo volume?"
        why = f"I volumi scalano con il cubo della scala lineare: {v0} · {s}^3 = {ans}."
    elif key in {"drill_cartesian_points", "geometria.coordinate-griglia"}:
        dx, dy, dist = [(3, 4, 5), (6, 8, 10), (5, 12, 13)][idx % 3]
        x1, y1 = rng.randint(1, 4), rng.randint(1, 4)
        ans = str(dist)
        prompt = f"Calcola la distanza euclidea nel piano cartesiano tra A({x1}, {y1}) e B({x1 + dx}, {y1 + dy})."
        why = f"d(A, B) = sqrt(({dx})^2 + ({dy})^2) = {dist}."
    elif key in {"drill_euclid_similarity", "superiori.circonferenza-euclide-talete"}:
        p, q, h = [(4, 9, 6), (2, 8, 4), (3, 12, 6)][idx % 3]
        ans = str(h)
        prompt = f"In un triangolo rettangolo le proiezioni dei cateti sull'ipotenusa valgono p = {p} e q = {q}. Applica il 2° teorema di Euclide per trovare l'altezza h."
        why = f"Per il 2° teorema di Euclide h^2 = p · q = {p * q}, quindi h = sqrt({p * q}) = {h}."
    else:
        return None
    return {"prompt": prompt, "expected": ans, "explanation": why}


def _build_logic_sets_ofa_drill(key: str, idx: int, rng: random.Random) -> dict[str, Any] | None:
    if key in {"drill_set_classification", "logica.classificare-attributi"}:
        na = rng.randint(12, 20)
        nb = rng.randint(10, 18)
        ni = rng.randint(3, min(na, nb) - 2)
        ans = str(na + nb - ni)
        prompt = f"Se |A| = {na}, |B| = {nb} e la loro intersezione ha |A ∩ B| = {ni}, quanti elementi contiene l'unione A ∪ B?"
        why = f"Per inclusione-esclusione |A ∪ B| = {na} + {nb} - {ni} = {ans}."
    elif key in {"drill_boolean_basics", "logica.vero-falso-non-e-o"}:
        if idx % 2 == 0:
            ans = "1"
            prompt = "Valuta l'espressione booleana con A = 1 (vero), B = 0 (falso): (NOT B) AND (A OR B). Rispondi 1 o 0."
            why = "NOT 0 = 1 e (1 OR 0) = 1; dunque 1 AND 1 = 1."
        else:
            ans = "0"
            prompt = "Valuta l'espressione booleana con A = 1 (vero), B = 0 (falso): NOT (A OR B). Rispondi 1 o 0."
            why = "A OR B = 1, quindi la sua negazione NOT(1) vale 0."
    elif key in {"drill_counterexample", "logica.tutti-qualcuno-controesempio"}:
        if idx % 2 == 0:
            ans = "2"
            prompt = "Trova l'unico numero primo che funge da controesempio all'enunciato universale 'Tutti i numeri primi sono dispari'."
            why = "Il numero 2 è primo (divisibile solo per 1 e per se stesso) ma è pari: un solo controesempio basta a falsificare il quantificatore universale."
        else:
            ans = "9"
            prompt = "Trova il più piccolo intero positivo dispari e composto che funge da controesempio a 'Tutti i numeri dispari maggiori di 1 sono primi'."
            why = "3, 5, 7 sono primi, mentre 9 = 3 · 3 è dispari ma composto."
    elif key in {"drill_p0_logic_counterexample", "P0.1", "P6.1", "P6.2"}:
        n = rng.choice([2, 3, 4])
        ans = str(2 ** n if idx % 2 == 0 else 9)
        if idx % 2 == 0:
            prompt = f"Un enunciato composto contiene {n} variabili booleane indipendenti: quante righe ha la sua tavola di verità completa?"
            why = f"Ogni variabile può assumere 2 valori, quindi vi sono 2^{n} = {2 ** n} assegnazioni possibili."
        else:
            prompt = "Qual è il più piccolo intero dispari maggiore di 1 che falsifica la congettura 'Ogni dispari > 1 è primo'?"
            why = "9 = 3^2 non è primo."
    elif key in {"drill_p0_propositional", "P0.2"}:
        if idx % 2 == 0:
            ans = "0"
            prompt = "Considera l'implicazione logica P -> Q nel caso P = 1 (vero) e Q = 0 (falso): qual è il valore di verità di P -> Q (1 o 0)?"
            why = "L'unico caso in cui un'implicazione P -> Q è falsa (0) si verifica quando l'ipotesi P è vera e la tesi Q è falsa."
        else:
            n = rng.choice([3, 4])
            ans = str(2 ** n)
            prompt = f"Quante assegnazioni di verità distinte esistono per una formula proposizionale con {n} variabili atomiche?"
            why = f"2^{n} = {2 ** n} righe nella tavola di verità."
    elif key in {"drill_p0_sets_functions", "P0.3"}:
        if idx % 2 == 0:
            x0 = rng.randint(2, 5)
            fx = 2 * x0 + 1
            gfx = fx * fx - 1
            ans = str(gfx)
            prompt = f"Date f(x) = 2*x + 1 e g(y) = y^2 - 1, calcola il valore della funzione composta g(f({x0}))."
            why = f"f({x0}) = {fx}; poi g({fx}) = {fx}^2 - 1 = {gfx}."
        else:
            n = rng.choice([4, 5])
            ans = str(2 ** n)
            prompt = f"Se un insieme X ha cardinalità |X| = {n}, quanti sottoinsiemi contiene l'insieme delle parti Pow(X)?"
            why = f"|Pow(X)| = 2^{n} = {2 ** n}."
    elif key in {"drill_p0_radicals_powers", "P0.4"}:
        k = rng.choice([6, 10, 14])
        m = rng.choice([2, 3, 5])
        if k % m != 0:
            k = m * rng.randint(2, 4)
        ans = f"{k // m}*sqrt({m})"
        prompt = f"Razionalizza il denominatore della frazione {k} / sqrt({m}) (scrivi il risultato con sintassi c*sqrt(m))."
        why = f"{k}/sqrt({m}) = ({k}*sqrt({m}))/{m} = {k // m}*sqrt({m})."
    elif key in {"drill_p0_trigonometry", "P0.7"}:
        cases = [
            ("sin(pi/6) + cos(pi/3)", "1", "sin(pi/6) = 1/2 e cos(pi/3) = 1/2, quindi la somma vale 1."),
            ("sin(pi/4)^2 + cos(pi/4)^2", "1", "Per l'identità pitagorica fondamentale sin^2(alpha) + cos^2(alpha) = 1."),
            ("2*sin(pi/3)*cos(pi/6)", "3/2", "sin(pi/3) = sqrt(3)/2 e cos(pi/6) = sqrt(3)/2: 2 · (3/4) = 3/2."),
        ]
        expr_s, ans, why = cases[idx % len(cases)]
        prompt = f"Calcola il valore esatto in radianti dell'espressione goniometrica: {expr_s}."
    elif key in {"drill_goniometry_identities", "superiori.goniometria-formule-equazioni"}:
        if idx % 2 == 0:
            ans = "4/5"
            prompt = "Sapendo che sin(alpha) = 3/5 e che alpha appartiene al primo quadrante (0 < alpha < pi/2), calcola cos(alpha)."
            why = "Dall'identità fondamentale cos(alpha) = sqrt(1 - (3/5)^2) = sqrt(16/25) = 4/5."
        else:
            ans = "24/25"
            prompt = "Con sin(alpha) = 3/5 e cos(alpha) = 4/5 nel primo quadrante, calcola sin(2*alpha) tramite la formula di duplicazione."
            why = "sin(2*alpha) = 2*sin(alpha)*cos(alpha) = 2*(3/5)*(4/5) = 24/25."
    elif key in {"drill_cosine_law", "superiori.trigonometria-triangoli"}:
        # Triangoli con angolo 60° (cos = 1/2) o 120° (cos = -1/2) e lati esatti
        triples = [(5, 8, 60, 7), (3, 8, 60, 7), (3, 5, 120, 7), (7, 8, 120, 13)]
        a, b, deg, c = triples[idx % len(triples)]
        ans = str(c)
        prompt = f"In un triangolo due lati misurano a = {a} e b = {b} con angolo compreso gamma = {deg}°: calcola il terzo lato c con il teorema del coseno (Carnot)."
        why = f"c^2 = {a}^2 + {b}^2 - 2·{a}·{b}·cos({deg}°) = {c*c}, da cui c = {c}."
    elif key in {"drill_p0_fermi_logic", "P0.8"}:
        ops = rng.choice([4, 6])
        cult = rng.choice([9, 12])
        ans = str(ops * 2)
        prompt = f"Se {ops} operatori completano {cult} analisi in 20 minuti a ritmo lineare costante, quanti operatori occorrono per completare {10 * cult} analisi in 100 minuti?"
        why = f"Il carico cresce di 10 volte mentre il tempo disponibile cresce di 5 volte: servono (10/5)·{ops} = {ops * 2} operatori."
    elif key in {"drill_frequency_table", "dati.tabelle-grafici"}:
        f0, f1, f2 = rng.randint(4, 8), rng.randint(6, 12), rng.randint(3, 6)
        tot = f0 + f1 + f2
        ans = str(sp.Rational(f1, tot))
        prompt = f"In un campione statistico le frequenze assolute di tre classi sono ({f0}, {f1}, {f2}): qual è la frequenza relativa esatta della seconda classe?"
        why = f"La numerosità totale è {tot}, quindi la frequenza relativa vale {f1}/{tot} = {ans}."
    elif key in {"drill_mean_median_prob", "dati.media-frequenza-incertezza"}:
        n = 3
        m1 = 28
        next_v = rng.choice([20, 24])
        ans = str(sp.Rational(n * m1 + next_v, n + 1))
        prompt = f"Dopo {n} prove la media aritmetica dei voti è {m1}. Nella quarta prova lo studente ottiene {next_v}: qual è la nuova media aritmetica?"
        why = f"La somma precedente vale {n}·{m1} = {n * m1}; la nuova media è ({n * m1} + {next_v})/4 = {ans}."
    else:
        return None
    return {"prompt": prompt, "expected": ans, "explanation": why}


def _build_secai_vol2_drill(key: str, idx: int, rng: random.Random) -> dict[str, Any] | None:
    if key in {"drill_space_vectors", "superiori.geometria-spazio-vettori"}:
        u = [rng.randint(1, 4), rng.randint(-2, 3), rng.randint(1, 3)]
        v = [rng.randint(1, 3), rng.randint(1, 4), rng.randint(-2, 2)]
        dot = sum(a * b for a, b in zip(u, v))
        ans = str(dot)
        prompt = f"Calcola il prodotto scalare u · v nello spazio R^3 tra u = {tuple(u)} e v = {tuple(v)}."
        why = f"{u[0]}·{v[0]} + {u[1]}·{v[1]} + {u[2]}·{v[2]} = {dot}."
    elif key in {"drill_p1_cli_permissions", "P1.1"}:
        perms = [("rwxr-x---", "750"), ("rw-r--r--", "644"), ("rwx------", "700"), ("rwxr-xr-x", "755")]
        sym, oct_v = perms[idx % len(perms)]
        ans = oct_v
        prompt = f"Converti la stringa simbolica di permessi POSIX `{sym}` nel corrispondente codice ottale a tre cifre per chmod."
        why = f"Sommando r=4, w=2, x=1 per utente, gruppo e altri si ottiene {oct_v}."
    elif key in {"drill_p1_git_concepts", "P1.2"}:
        n_main = rng.randint(3, 5)
        n_feat = rng.randint(2, 4)
        ans = str(n_main + n_feat + 1)
        prompt = f"Un repository parte da 1 commit iniziale comune, poi sviluppa {n_main} nuovi commit su `main` e {n_feat} commit su un ramo `feature` prima di unirli in un merge commit: quanti commit distinti compongono la storia unificata?"
        why = f"I commit raggiungibili dal merge commit sono 1 + {n_main} + {n_feat} + 1 (il merge) = {ans}."
    elif key in {"drill_p2_induction", "P2.1"}:
        n = rng.randint(6, 12)
        if idx % 2 == 0:
            ans = str(n * (n + 1) // 2)
            prompt = f"Usa la formula dimostrata per induzione S(n) = n(n+1)/2 per calcolare la somma 1 + 2 + ... + {n}."
            why = f"S({n}) = {n}·({n}+1)/2 = {ans}."
        else:
            ans = str(n + 1)
            prompt = f"Nel passo induttivo per S(n) = 1 + 2 + ... + n, quale quantità esatta S(n+1) - S(n) si aggiunge all'ipotesi induttiva con n = {n}?"
            why = f"Passando da n={n} a n+1={n+1} si aggiunge esattamente l'ultimo addendo n+1 = {n+1}."
    elif key in {"drill_p2_discrete_combinatorics", "P2.2"}:
        if idx % 2 == 0:
            n = rng.choice([5, 6, 7])
            ans = str(n * (n - 1) // 2)
            prompt = f"Quanti spigoli possiede un grafo semplice completo K_{n} con {n} vertici?"
            why = f"Ogni coppia non ordinata di vertici definisce uno spigolo: C({n}, 2) = {n}·{n-1}/2 = {ans}."
        else:
            ans = "4"
            prompt = "Calcola il resto modulo 7 di 3^100 applicando il piccolo teorema di Fermat (3^6 ≡ 1 mod 7, 100 = 6·16 + 4)."
            why = "3^100 ≡ (3^6)^16 · 3^4 ≡ 3^4 = 81 ≡ 4 (mod 7)."
    elif key in {"drill_p3_linear_algebra", "P3.1"}:
        a, b = rng.randint(2, 5), rng.randint(1, 3)
        c, d = rng.randint(1, 3), rng.randint(2, 5)
        if idx % 2 == 0:
            det = a * d - b * c
            ans = str(det)
            prompt = f"Calcola il determinante det(A) della matrice 2×2 A = [[{a}, {b}], [{c}, {d}]]."
            why = f"det(A) = ({a})·({d}) - ({b})·({c}) = {det}."
        else:
            x0, y0 = rng.randint(1, 3), rng.randint(1, 3)
            u1, u2 = a * x0 + b * y0, c * x0 + d * y0
            ans = f"[{u1}, {u2}]"
            prompt = f"Calcola l'immagine A·v (in formato [y1, y2]) della matrice A = [[{a}, {b}], [{c}, {d}]] sul vettore v = [{x0}, {y0}]."
            why = f"y1 = {a}·{x0} + {b}·{y0} = {u1}, y2 = {c}·{x0} + {d}·{y0} = {u2}."
    elif key in {"drill_p3_least_squares", "P3.3"}:
        m, q = rng.randint(1, 3), rng.randint(0, 2)
        pts = [(0, q + 1), (1, m + q - 1), (2, 2 * m + q + 1)]
        rss = sum((y - (m * x + q)) ** 2 for x, y in pts)
        ans = str(rss)
        prompt = f"Data la retta modello y_hat = {m}*x + {q} e i punti osservati {pts}, calcola la somma dei quadrati dei residui ∑(y_i - y_hat_i)^2."
        why = f"I residui valgono (+1, -1, +1); elevando al quadrato e sommando si ottiene 1 + 1 + 1 = {rss}."
    elif key in {"drill_p5_complexity_invariants", "P5.1"}:
        p = rng.choice([7, 8, 10])
        n = 2 ** p
        ans = str(p + 1)
        prompt = f"Su un vettore ordinato di N = {n} elementi, quante iterazioni al caso peggiore esegue una ricerca binaria che dimezza l'intervallo ad ogni passo fino a 1 elemento?"
        why = f"Da 2^{p} a 2^0 servono {p} dimezzamenti più il controllo finale: {p + 1} iterazioni (O(log N))."
    elif key in {"drill_p5_testing_edge_cases", "P5.2"}:
        a = rng.randint(10, 20)
        b = a + rng.randint(5, 15)
        ans = str(b + 1)
        prompt = f"Per testare ai confini una funzione valida su interi x ∈ [{a}, {b}], qual è il più piccolo intero strettamente superiore al limite superiore da includere come test di rifiuto?"
        why = f"Nell'analisi dei valori ai confini, il primo intero fuori dal dominio superiore [{a}, {b}] è {b} + 1 = {b + 1}."
    elif key in {"drill_p5_http_sqli", "P5.3"}:
        if idx % 2 == 0:
            ans = "401"
            prompt = "Quale codice di stato HTTP identifica una richiesta priva di credenziali valide di autenticazione (Unauthorized)? Inserisci il codice numerico a 3 cifre."
            why = "HTTP 401 indica assenza o invalidità dell'autenticazione; HTTP 403 indica utente autenticato ma privo di autorizzazione."
        else:
            ans = "parametrizzazione"
            prompt = "Quale tecnica strutturale (una parola: 'concatenazione' o 'parametrizzazione') separa il codice SQL dai dati utente per prevenire SQL injection?"
            why = "La parametrizzazione (prepared statements) impedisce che i dati utente alterino l'albero sintattico della query."
    else:
        return None
    return {"prompt": prompt, "expected": ans, "explanation": why}


def _build_single_drill(node_id: str, key: str, idx: int, rng: random.Random) -> dict[str, Any]:
    for builder in (
        _build_arithmetic_drill,
        _build_fractions_divisibility_drill,
        _build_proportions_algebra_drill,
        _build_geometry_drill,
        _build_logic_sets_ofa_drill,
        _build_secai_vol2_drill,
    ):
        built = builder(key, idx, rng)
        if built is not None:
            return {
                "drill_id": f"{node_id}#q{idx + 1}",
                "node_id": node_id,
                **built,
            }

    if key in {"drill_counting_bijection", "numeri.quantita"}:
        if idx % 2 == 0:
            n = rng.choice([3, 4, 5])
            ans = str(math.factorial(n))
            prompt = f"Quante biiezioni diverse esistono tra un insieme di {n} oggetti distinti e l'insieme campione {{1, ..., {n}}}?"
            why = f"Il primo oggetto ha {n} scelte, il secondo {n-1}, ..., fino a {n}! = {ans}."
        else:
            m = rng.randint(5, 9)
            n = m - 1
            ans = "iniettiva"
            prompt = (
                f"[Che cosa si rompe] Tentando di accoppiare {m} oggetti con {n} sedie (f: I_{m} -> I_{n}), "
                f"quale proprietà tra 'iniettiva' e 'suriettiva' si rompe necessariamente per il principio dei cassetti?"
            )
            why = "Con più elementi in partenza che in arrivo, almeno due elementi finiscono sulla stessa immagine: cade l'iniettività."
    elif key in {"drill_fraction_addition", "frazioni.denominatore-comune"}:
        dens = [(4, 5), (3, 7), (5, 6), (3, 8), (2, 9)]
        b, d = dens[idx % len(dens)]
        a = rng.randint(1, b - 1)
        c = rng.randint(1, d - 1)
        if idx == count_mod(idx):
            # Domanda "che cosa si rompe" sulla regola falsa (a+c)/(b+d)
            val = sp.Rational(a, b) - sp.Rational(c, d) if a * d > c * b else sp.Rational(a, b) + sp.Rational(c, d)
            op = "-" if a * d > c * b else "+"
            ans = str(val)
            prompt = f"Calcola {a}/{b} {op} {c}/{d} riducendo allo stesso denominatore (accettata sia frazione sia decimale esatto se finito)."
            why = f"Portando al denominatore comune {math.lcm(b, d)} e applicando la distributiva si ottiene {val}."
        else:
            # Differenza tra frazione vera e mediante sbagliata
            true_sum = sp.Rational(1, 2) + sp.Rational(1, 3)
            fake_sum = sp.Rational(1 + 1, 2 + 3)
            diff = true_sum - fake_sum
            ans = str(diff)
            prompt = "[Che cosa si rompe] Di quanto differisce la somma vera (1/2 + 1/3) dal risultato della falsa regola (1+1)/(2+3)?"
            why = f"La somma vera vale 5/6 mentre la mediante vale 2/5: lo scarto d'errore è 5/6 - 2/5 = {diff}."
    elif key in {"drill_subtraction_inverse", "operazioni.sottrazione"}:
        a = rng.randint(12, 25)
        b = rng.randint(4, 9)
        c = rng.randint(1, b - 1)
        if idx % 2 == 0:
            diff = ((a - b) - c) - (a - (b - c))
            ans = str(abs(diff))
            prompt = f"[Che cosa si rompe] Calcola la distanza tra ({a} - {b}) - {c} e {a} - ({b} - {c}) per verificare il fallimento dell'associatività."
            why = f"({a}-{b})-{c} = {a-b-c}, mentre {a}-({b}-{c}) = {a-(b-c)}: differiscono di 2*{c} = {abs(diff)}."
        else:
            ans = str(a - b)
            prompt = f"Trova l'unico naturale c tale che {b} + c = {a}."
            why = f"Per definizione di sottrazione come inversa dell'addizione, c = {a} - {b} = {a - b}."
    elif key in {"drill_positional_value", "numeri.posizionale"}:
        n = rng.choice([13, 19, 22, 25, 29, 37])
        if idx % 2 == 0:
            ans = bin(n)[2:]
            # Trattiamo il binario come stringa intera cifre 0/1 confrontata al valore intero delle cifre scritte
            prompt = f"Scrivi il numero decimale {n} in base 2 (solo cifre 0 e 1, senza prefisso 0b)."
            why = f"Scomponendo {n} in potenze di 2 si ottiene ({ans})_2."
        else:
            b3, b1, b0 = rng.randint(2, 7), rng.randint(1, 8), rng.randint(1, 9)
            val = b3 * 1000 + b1 * 10 + b0
            ans = str(val - (b3 * 100 + b1 * 10 + b0))
            prompt = f"[Che cosa si rompe] Se nel numero {val} ometti lo zero segnaposto delle centinaia ottenendo {b3}{b1}{b0}, quanto valore perdi?"
            why = f"Senza lo zero il {b3} scivola dalle migliaia alle centinaia: perdi {b3}*1000 - {b3}*100 = {ans}."
    elif key in {"drill_distributive_law", "operazioni.distributiva"}:
        a = rng.randint(3, 7)
        b = rng.randint(4, 9)
        if idx % 2 == 0:
            ans = str(2 * a * b)
            prompt = f"[Che cosa si rompe] Di quanto sbaglia chi calcola ({a} + {b})^2 facendo {a}^2 + {b}^2?"
            why = f"Per la proprietà distributiva ({a}+{b})^2 = {a}^2 + 2·{a}·{b} + {b}^2: mancano i due rettangoli misti 2ab = {2*a*b}."
        else:
            ans = f"{a}*x + {a*b}"
            prompt = f"Applica la proprietà distributiva per espandere {a}* (x + {b})."
            why = f"Distribuendo il fattore {a} su ciascun addendo si ottiene {a}*x + {a*b}."
    elif key in {"drill_pythagoras", "geometria.pitagora"}:
        triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (9, 12, 15)]
        a, b, c = triples[idx % len(triples)]
        ans = str(c)
        prompt = f"In un triangolo rettangolo i cateti misurano {a} e {b}: quanto misura l'ipotenusa?"
        why = f"Per Pitagora sqrt({a}^2 + {b}^2) = sqrt({a*a + b*b}) = {c}."
    elif key in {"drill_p0_symbolic_inequalities", "P0.5"}:
        if idx % 2 == 0:
            x0 = rng.choice([100, 120, 150, 200])
            half_gap = rng.choice([15, 25, 30, 40])
            ans = f"[{x0 - half_gap}, {x0 + half_gap}]"
            prompt = (
                f"[Marconi nel Tigullio] L'asse del radio-faro è in x0 = {x0} m e le due boe distano {2 * half_gap} m "
                f"(tolleranza ±{half_gap} m, cioè |x - {x0}| <= {half_gap}). Scrivi l'intervallo [min, max] delle coordinate valide."
            )
            why = f"|x - {x0}| <= {half_gap} equivale a -{half_gap} <= x - {x0} <= {half_gap}, ossia [{x0 - half_gap}, {x0 + half_gap}]."
        else:
            r1 = rng.randint(1, 4)
            r2 = r1 + rng.randint(2, 4)
            expr = sp.expand((x_sym - r1) * (x_sym - r2))
            ans = f"({x_sym - r1})*({x_sym - r2})"
            prompt = f"Scomponi in fattori di primo grado il polinomio quadratico: {expr}"
            why = f"Le radici sono {r1} e {r2}, quindi {expr} = (x - {r1})(x - {r2})."
    elif key in {"drill_p0_functions_parabola", "P0.6"}:
        c_focus = sp.Rational(rng.choice([1, 2, 4]), 4)
        a_coeff = sp.Rational(1, 4 * c_focus)
        ans = f"{a_coeff}*x**2"
        prompt = f"Scrivi l'equazione y(x) della parabola con vertice nell'origine e fuoco in F(0, {c_focus}) sapendo che a = 1/(4c)."
        why = f"Con distanza focale c = {c_focus}, il coefficiente vale a = 1/(4·({c_focus})) = {a_coeff}, quindi y = {a_coeff}*x^2."
    elif key in {"drill_p2_calculus_chain", "P2.3"}:
        k = rng.randint(2, 5)
        b = rng.randint(1, 4)
        f_expr = (k * x_sym + b) ** 3
        deriv = sp.diff(f_expr, x_sym)
        ans = str(deriv)
        prompt = f"Calcola la derivata rispetto a x della funzione composta f(x) = ({k}*x + {b})**3 usando la regola della catena."
        why = f"Derivata esterna 3*({k}*x + {b})**2 moltiplicata per la derivata interna {k}: {deriv}."
    elif key in {"drill_p3_bayes", "P3.2"}:
        # Test diagnostico / IDS a bassa prevalenza
        prev = sp.Rational(1, 100)
        sens = sp.Rational(99, 100)
        fpr = sp.Rational(1, 100)
        post = (sens * prev) / (sens * prev + fpr * (1 - prev))
        ans = str(post)
        prompt = (
            "Un IDS segnala attacchi con sensibilità 99/100 e falsi positivi 1/100 su traffico dove solo 1 pacchetto su 100 è malevolo. "
            "Qual è la probabilità a posteriori (Bayes) che un allarme sia un vero attacco?"
        )
        why = f"P(A|+) = (0.99*0.01) / (0.99*0.01 + 0.01*0.99) = {post} (esattamente il 50% a causa del base rate 1/100!)."
    elif key in {"drill_p4_rsa_modular", "P4.1"}:
        p, q, e = 5, 11, 3
        phi = (p - 1) * (q - 1)
        d = pow(e, -1, phi)
        ans = str(d)
        prompt = f"In un mini-RSA con p={p}, q={q} ed esponente pubblico e={e}, calcola l'esponente privato d tale che e*d ≡ 1 (mod {(p-1)*(q-1)})."
        why = f"phi(55) = 4*10 = 40; poiché 3 * {d} = {3*d} = 2*40 + 1 ≡ 1 (mod 40), la chiave privata è d = {d}."
    elif key in {"drill_p4_twos_complement", "P4.2"}:
        k = rng.choice([5, 13, 27, 42])
        twos = 256 - k
        ans = str(twos)
        prompt = f"Qual è il valore intero senza segno (0..255) del byte che rappresenta -{k} in complemento a due su 8 bit?"
        why = f"Su 8 bit il complemento a due di -{k} vale 2^8 - {k} = 256 - {k} = {twos}."
    elif key in {"drill_polynomial_products", "superiori.polinomi-prodotti-notevoli"}:
        a = rng.randint(2, 4)
        b = rng.randint(2, 6)
        if idx % 2 == 0:
            ans = str(sp.expand((a * x_sym + b) ** 2))
            prompt = f"Usa il modello geometrico del quadrato scomposto per espandere ({a}*x + {b})^2 in forma polinomiale."
            why = f"({a}x + {b})^2 somma i due quadrati ({a}x)^2, {b}^2 e i due rettangoli misti 2·{a}·{b}·x: {ans}."
        else:
            ans = f"{2 * b}*x"
            prompt = (
                f"[Che cosa si rompe] Se espandi (x + {b})^2 dimenticando i due rettangoli misti e scrivendo x^2 + {b**2}, "
                f"quale termine algebrico (in x) stai perdendo?"
            )
            why = f"(x + {b})^2 = x^2 + {2*b}*x + {b**2}: la scorciatoia 'falso quadrato' perde 2·{b}·x = {ans}."
    elif key in {"drill_polynomial_ruffini", "superiori.fattorizzazione-frazioni-algebriche"}:
        r = rng.randint(2, 5)
        k = rng.randint(1, 4)
        rem = rng.choice([3, 5, 7, -4])
        if idx % 2 == 0:
            poly = sp.expand((x_sym - r) * (x_sym + k) + rem)
            ans = str(rem)
            prompt = f"Per il teorema del resto di Ruffini, qual è il resto della divisione di P(x) = {poly} per (x - {r})?"
            why = f"Valutando P({r}) al posto del divisore si isola direttamente il resto P({r}) = {rem}."
        else:
            ans = str(r)
            prompt = (
                f"[Che cosa si rompe] Nella frazione algebrica (x^2 - {r*r})/(x - {r}), dopo la semplificazione resta x + {r}: "
                f"quale valore x0 è comunque escluso dal dominio iniziale perché annulla il denominatore?"
            )
            why = f"Per x = {r} l'espressione originaria vale 0/0 (forma indeterminata), mai definita senza condizione x != {r}."
    elif key in {"drill_linear_systems_line", "superiori.sistemi-lineari-retta"}:
        if idx % 2 == 0:
            x_val = rng.randint(2, 7)
            y_val = rng.randint(1, 5)
            ans = f"[{x_val}, {y_val}]"
            prompt = (
                f"Trova il punto di intersezione [x, y] delle due rette del sistema lineare "
                f"x + y = {x_val + y_val} e x - y = {x_val - y_val}."
            )
            why = f"Sommando membro a membro 2x = {2*x_val} => x = {x_val} e y = {y_val}: punto [{x_val}, {y_val}]."
        else:
            m = rng.choice([2, 3, 4, 5])
            ans = str(-sp.Rational(1, m))
            prompt = (
                f"[Che cosa si rompe] Nel fascio improprio y = {m}*x + q, quanto vale il coefficiente angolare m' "
                f"di una retta perpendicolare (che rompe il parallelismo con m*m' = -1)?"
            )
            why = f"La condizione di ortogonalità nel piano cartesiano è m·m' = -1, quindi m' = -1/{m}."
    elif key in {"drill_quadratic_radicals", "superiori.radicali-equazioni-secondo-grado"}:
        r1 = rng.randint(2, 5)
        r2 = r1 + rng.randint(1, 4)
        if idx % 2 == 0:
            ans = str(r1 + r2)
            prompt = (
                f"Applicando le formule di Viète senza estrarre le radici, quanto vale la somma x_1 + x_2 delle soluzioni "
                f"di x^2 - {r1 + r2}*x + {r1 * r2} = 0?"
            )
            why = f"In x^2 - Sx + P = 0 la somma vale -b/a = {r1 + r2} (qui le radici sono {r1} e {r2})."
        else:
            a, b, c = rng.choice([(1, 4, 5), (2, 3, 4), (1, 2, 5)])
            ans = str(b * b - 4 * a * c)
            prompt = (
                f"[Che cosa si rompe nei reali] Calcola il discriminante Delta = b^2 - 4ac di {a}*x^2 + {b}*x + {c} = 0 "
                f"per verificare perché la parabola non tocca mai l'asse x."
            )
            why = f"Delta = {b}^2 - 4·{a}·{c} = {ans} < 0: nessuna soluzione reale finché restiamo in R."
    elif key in {"drill_conics_loci", "superiori.coniche-luoghi-geometrici"}:
        triples = [(5, 3, 4), (5, 4, 3), (13, 5, 12), (10, 6, 8)]
        a, b, c_foc = triples[idx % len(triples)]
        if idx % 2 == 0:
            ans = str(c_foc)
            prompt = f"L'ellisse x^2/{a*a} + y^2/{b*b} = 1 ha semiassi a={a} e b={b}: quanto vale la semidistanza focale c?"
            why = f"Per i fuochi dell'ellisse c = sqrt(a^2 - b^2) = sqrt({a*a} - {b*b}) = {c_foc}."
        else:
            p, q = rng.choice([(3, 2), (4, 3), (5, 2)])
            ans = str(sp.Rational(q, p))
            prompt = f"Nell'iperbole x^2/{p*p} - y^2/{q*q} = 1, quanto vale il coefficiente angolare positivo b/a dell'asintoto?"
            why = f"Gli asintoti soddisfano x^2/a^2 - y^2/b^2 = 0, ossia y = ±(b/a)x con b/a = {q}/{p}."
    elif key in {"drill_progressions_sum", "superiori.successioni-progressioni"}:
        if idx % 2 == 0:
            a1 = rng.randint(1, 4)
            d = rng.randint(2, 4)
            n = rng.choice([6, 8, 10])
            an = a1 + (n - 1) * d
            ans = str(n * (a1 + an) // 2)
            prompt = f"Calcola con la formula di Gauss la somma dei primi {n} termini della progressione aritmetica con a_1={a1} e ragione d={d}."
            why = f"a_{n} = {a1} + {n-1}·{d} = {an}; dunque S_{n} = {n}·({a1}+{an})/2 = {ans}."
        else:
            r = rng.choice([2, 3])
            k = rng.choice([3, 4])
            ans = str((r ** (k + 1) - 1) // (r - 1))
            prompt = f"Calcola la somma finita della progressione geometrica 1 + {r} + ... + {r}^{k} usando ({r}^({k}+1) - 1)/({r} - 1)."
            why = f"S = ({r}^{k+1} - 1)/({r} - 1) = {ans}."
    elif key in {"drill_logarithms_exp", "superiori.esponenziali-logaritmi"}:
        if idx % 2 == 0:
            base = rng.choice([2, 3])
            p1 = rng.randint(3, 5)
            p2 = rng.randint(1, 2)
            ans = str(p1 - p2)
            prompt = f"Calcola il valore esatto di log_{base}({base**p1}) - log_{base}({base**p2}) senza calcolatrice."
            why = f"Per la proprietà del quoziente vale log_{base}({base**p1}/{base**p2}) = log_{base}({base**(p1-p2)}) = {p1 - p2}."
        else:
            k = rng.choice([2, 4, 5])
            ans = str(sp.Rational(k + 1, 2))
            prompt = f"Risolvi l'equazione esponenziale 3^(2*x - 1) = 3^{k} sfruttando l'iniettività della base."
            why = f"Eguagliando gli esponenti: 2x - 1 = {k} => x = {ans}."
    elif key in {"drill_complex_numbers", "superiori.numeri-complessi-gauss"}:
        if idx % 2 == 0:
            a, b = rng.randint(1, 4), rng.randint(1, 3)
            c, d = rng.randint(1, 3), rng.randint(1, 4)
            prod = sp.expand((a + b * sp.I) * (c + d * sp.I))
            ans = str(prod)
            prompt = f"Nel piano di Gauss calcola il prodotto ({a} + {b}*i)*({c} + {d}*i) ricordando i^2 = -1 (usa i o I)."
            why = f"({a}·{c} - {b}·{d}) + ({a}·{d} + {b}·{c})*i = {prod}."
        else:
            k = rng.choice([1, 2, 3])
            ans = str(5 * k)
            prompt = f"Calcola il modulo euclideo |z| = sqrt(Re(z)^2 + Im(z)^2) del numero complesso z = {3*k} + {4*k}*i."
            why = f"|{3*k} + {4*k}*i| = sqrt({(3*k)**2} + {(4*k)**2}) = {5*k}."
    elif key in {"drill_combinatorics_binomial", "superiori.combinatoria-probabilita-composta"}:
        if idx % 2 == 0:
            n = rng.choice([5, 6, 7])
            k = rng.choice([2, 3])
            ans = str(math.comb(n, k))
            prompt = f"In quanti modi puoi estrarre un comitato non ordinato di {k} elementi da un insieme di {n} persone? Calcola C({n}, {k})."
            why = f"Le combinazioni semplici valgono {n}! / ({k}!·{n-k}!) = {ans}."
        else:
            a = rng.randint(2, 5)
            ans = str(3 * (a * a))
            prompt = f"[Binomio di Newton] Nello sviluppo completo di (x + {a})^3, quanto vale il coefficiente numerico di x?"
            why = f"Il termine lineare è C(3, 2)·{a}^2·x = 3·{a*a}·x = {ans}*x."
    elif key in {"drill_limits_continuity", "superiori.limiti-continuita-asintoti"}:
        if idx % 2 == 0:
            r = rng.randint(2, 6)
            ans = str(2 * r)
            prompt = f"Calcola lim_{{x -> {r}}} (x^2 - {r*r}) / (x - {r}) eliminando la forma indeterminata 0/0."
            why = f"Scomponendo x^2 - {r*r} = (x - {r})(x + {r}), per x != {r} vale x + {r} -> {2*r}."
        else:
            k = rng.choice([2, 3, 5])
            m = rng.choice([2, 3, 4])
            ans = str(sp.Rational(k, m))
            prompt = f"[Limite notevole] Quanto vale lim_{{x -> 0}} sin({k}*x) / ({m}*x)?"
            why = f"Riscrivendo come ({k}/{m})·sin({k}*x)/({k}*x) e applicando sin(u)/u -> 1 si ottiene {ans}."
    elif key in {"drill_derivatives_extrema", "superiori.derivata-studio-funzione"}:
        if idx % 2 == 0:
            a = rng.randint(1, 3)
            x0 = rng.randint(2, 6)
            c = rng.randint(1, 9)
            ans = str(x0)
            prompt = f"Trova l'ascissa x del punto di minimo di f(x) = {a}*x^2 - {2*a*x0}*x + {c} annullando la derivata prima f'(x) = 0."
            why = f"f'(x) = {2*a}*x - {2*a*x0} = 0 si annulla esattamente in x = {x0} (dove f'' > 0)."
        else:
            a = rng.randint(2, 4)
            n = rng.randint(3, 5)
            b = rng.randint(2, 5)
            deriv = sp.diff(a * x_sym**n + b * sp.sin(x_sym), x_sym)
            ans = str(deriv)
            prompt = f"Calcola la derivata prima f'(x) rispetto a x di f(x) = {a}*x^{n} + {b}*sin(x)."
            why = f"Derivando termine a termine: d/dx({a}x^{n}) + d/dx({b}sin(x)) = {deriv}."
    elif key in {"drill_definite_integrals", "superiori.integrali-teorema-fondamentale"}:
        if idx % 2 == 0:
            p = rng.choice([1, 2, 3])
            c = p + 1
            b = rng.randint(2, 4)
            val = sp.integrate(c * x_sym**p, (x_sym, 0, b))
            ans = str(val)
            prompt = f"Applica Torricelli-Barrow: calcola l'integrale definito da 0 a {b} di {c}*x^{p} dx."
            why = f"Una primitiva di {c}*x^{p} è x^{p+1}; valutata tra 0 e {b} dà {b}^{p+1} = {val}."
        else:
            p = rng.choice([3, 5])
            b = rng.randint(2, 5)
            ans = "0"
            prompt = (
                f"[Che cosa si rompe tra integrale e area] Quanto vale l'integrale definito di f(x) = x^{p} "
                f"sull'intervallo simmetrico [-{b}, {b}]?"
            )
            why = f"Essendo x^{p} dispari su dominio simmetrico [-{b}, {b}], l'area con segno negativo e quella positiva si elidono: 0."
    elif key in {"drill_ode_separable", "superiori.equazioni-differenziali-modelli"}:
        if idx % 2 == 0:
            k = rng.choice([2, 3, 4])
            y0 = rng.choice([2, 5, 7])
            ans = f"{y0}*exp({k}*x)"
            prompt = (
                f"Risolvi il problema di Cauchy y'(x) = {k}*y(x) con y(0) = {y0}: scrivi la soluzione y(x) "
                f"in funzione di x (usa exp(...) oppure e^(...))."
            )
            why = f"Separando dy/y = {k} dx si ha y(x) = C·exp({k}*x); imponendo y(0) = {y0} segue y(x) = {y0}*exp({k}*x)."
        else:
            a = rng.choice([6, 10, 15])
            b = rng.choice([2, 3, 5])
            ans = str(sp.Rational(a, b))
            prompt = f"Nel modello lineare y'(x) = {a} - {b}*y(x), quanto vale il livello di equilibrio stazionario y* (dove y' = 0)?"
            why = f"All'equilibrio il tasso di variazione si annulla: {a} - {b}·y* = 0 => y* = {ans}."
    else:
        # Generatore algebrico universale coerente col livello per tutti gli altri nodi del DAG
        m = rng.randint(2, 9)
        q = rng.randint(3, 12)
        target = m * rng.randint(2, 8) + q
        sol = sp.Rational(target - q, m)
        ans = str(sol)
        prompt = f"Isola x mantenendo in equilibrio i due membri dell'uguaglianza: {m}*x + {q} = {target}"
        why = f"Sottraendo {q} ad ambo i membri e dividendo per {m} si ottiene x = {sol}."

    return {
        "drill_id": f"{node_id}#q{idx + 1}",
        "node_id": node_id,
        "prompt": prompt,
        "expected": ans,
        "explanation": why,
    }


def count_mod(idx: int) -> int:
    return idx if idx % 2 == 0 else -1


def grade_drill_answer(expected: str, student_answer: str) -> dict[str, Any]:
    ok, msg = _sympy_equivalent(student_answer, expected)
    return {
        "is_correct": ok,
        "feedback": msg,
        "expected": expected,
        "student_answer": student_answer,
    }


def verify_graph_invariants(spec_id: str, answers: dict[str, Any]) -> dict[str, Any]:
    """Verifica con SymPy i 5 invarianti strutturali letti dal grafico disegnato su carta (Famiglia C, es. P0.6:
    `y = |log(x - 2)| + 1`) prima di sbloccare l'overlay SVG esatto."""
    if spec_id != "abs_shifted_log":
        raise ValueError(f"Specifica grafico non supportata: {spec_id!r}")

    # Derivazione esatta in SymPy: f(x) = Abs(log(x - 2)) + 1 per x > 2
    cusp_sol = sp.solve(sp.log(x_sym - 2), x_sym)[0]  # x = 3
    cusp_y = 1
    probe_x = 2 + sp.E
    probe_y = sp.Abs(sp.log(probe_x - 2)) + 1  # y = 2

    checks = {
        "domain_lower_bound": _sympy_scalar_eq(str(answers.get("domain_lower_bound", "")), "2"),
        "vertical_asymptote_x": _sympy_scalar_eq(str(answers.get("vertical_asymptote_x", "")), "2"),
        "cusp_x": _sympy_scalar_eq(str(answers.get("cusp_x", "")), str(cusp_sol)),
        "cusp_y": _sympy_scalar_eq(str(answers.get("cusp_y", "")), str(cusp_y)),
        "probe_y_at_2_plus_e": _sympy_scalar_eq(str(answers.get("probe_y_at_2_plus_e", "")), str(probe_y)),
        "monotonicity_split": (
            str(answers.get("left_branch", "")).strip().lower() in {"decrescente", "decreasing"}
            and str(answers.get("right_branch", "")).strip().lower() in {"crescente", "increasing"}
        ),
    }
    all_passed = all(checks.values())

    curve_points: list[dict[str, float]] = []
    if all_passed:
        for step in range(1, 65):
            xv = 2.08 + step * 0.11
            yv = abs(math.log(xv - 2.0)) + 1.0
            curve_points.append({"x": round(xv, 3), "y": round(yv, 3)})

    return {
        "spec_id": spec_id,
        "formula": "y = |ln(x - 2)| + 1",
        "checks": checks,
        "passed_count": sum(1 for v in checks.values() if v),
        "total_checks": len(checks),
        "all_passed": all_passed,
        "reference_curve_points": curve_points,
    }


PROOF_RUBRICS: dict[str, list[dict[str, Any]]] = {
    "sqrt2_irrational": [
        {
            "lemma_id": "L1_coprime_assumption",
            "label": "Assunzione per assurdo sqrt(2) = a/b ridotta ai minimi termini (MCD(a,b)=1 / coprimi)",
            "patterns": [r"assurdo", r"(?:mcd|coprim|irriducibil|minimi\s+termini|nessun\s+fattore\s+comune)"],
            "require_all": True,
            "missing_hint": "Hai dimenticato di dichiarare che la frazione a/b è ridotta ai minimi termini (MCD(a,b)=1): senza questo la contraddizione finale crolla!",
        },
        {
            "lemma_id": "L2_a_even",
            "label": "Elevamento a^2 = 2b^2 e deduzione che a^2 pari implica a pari",
            "patterns": [r"a\s*(?:\^|\*\*|²)?\s*2?\s*=\s*2\s*\*?\s*b", r"pari"],
            "require_all": True,
            "missing_hint": "Esplicita il passaggio a^2 = 2b^2 e il lemma per cui se a^2 è pari allora anche a deve essere pari (dispari^2 è dispari).",
        },
        {
            "lemma_id": "L3_b_even",
            "label": "Sostituzione a = 2k da cui 4k^2 = 2b^2 => b^2 = 2k^2 => b pari",
            "patterns": [r"2\s*\*?\s*k", r"b.*pari"],
            "require_all": True,
            "missing_hint": "Sostituisci a = 2k nell'uguaglianza per ricavare b^2 = 2k^2 e concludere che anche b è pari.",
        },
        {
            "lemma_id": "L4_contradiction",
            "label": "Contraddizione esplicita: a e b entrambi pari violano MCD(a,b)=1",
            "patterns": [r"(?:contraddizion|assurdo|impossibil|viola)"],
            "require_all": True,
            "missing_hint": "Chiudi la dimostrazione dichiarando che a e b entrambi divisibili per 2 contraddicono l'irriducibilità iniziale di a/b.",
        },
    ],
    "induction_sum_n": [
        {
            "lemma_id": "L1_base_case",
            "label": "Verifica esplicita del caso base (n = 0 oppure n = 1)",
            "patterns": [r"(?:caso\s+base|n\s*=\s*[01])"],
            "require_all": True,
            "missing_hint": "Manca la verifica esplicita del caso base (es. per n=1: 1 = 1(2)/2).",
        },
        {
            "lemma_id": "L2_inductive_hypothesis",
            "label": "Enunciazione dell'ipotesi induttiva per un generico n fissato",
            "patterns": [r"(?:ipotesi\s+induttiv|supponiamo.*n)"],
            "require_all": True,
            "missing_hint": "Dichiara chiaramente l'ipotesi induttiva su n prima di calcolare il passo n+1.",
        },
        {
            "lemma_id": "L3_inductive_step",
            "label": "Sviluppo algebrico per n+1 sommando (n+1) a n(n+1)/2 fino a (n+1)(n+2)/2",
            "patterns": [r"n\s*\+\s*1", r"n\s*\+\s*2"],
            "require_all": True,
            "missing_hint": "Mostra il raccoglimento n(n+1)/2 + (n+1) = (n+1)(n+2)/2 che chiude il passo induttivo.",
        },
    ],
    "hash_vs_encryption": [
        {
            "lemma_id": "L1_one_way",
            "label": "Unidirezionalità (assenza di chiave di decifratura / preimage resistance)",
            "patterns": [r"(?:unidirezional|non\s+invertibil|nessuna\s+chiave\s+di\s+decifra|preimmagin)"],
            "require_all": True,
            "missing_hint": "Spiega che un hash è unidirezionale (non esiste chiave per invertire H(m) -> m), mentre una cifratura deve essere invertibile col segreto.",
        },
        {
            "lemma_id": "L2_pigeonhole_compression",
            "label": "Compressione a taglia fissa e collisioni inevitabili per il principio dei cassetti",
            "patterns": [r"(?:lunghezza\s+fissa|256\s*bit|collision|cassetti|perdita)"],
            "require_all": True,
            "missing_hint": "Collega al principio dei cassetti (`numeri.quantita`): mappando messaggi di lunghezza arbitraria su n bit fissi, l'informazione non è biunivoca.",
        },
    ],
}


def evaluate_proof_rubric(rubric_id: str, student_proof_text: str) -> dict[str, Any]:
    """Valuta una dimostrazione scritta a libro chiuso contro i lemmi obbligatori (Famiglia D)."""
    if rubric_id not in PROOF_RUBRICS:
        raise ValueError(f"Rubrica dimostrativa sconosciuta: {rubric_id!r}")
    text = str(student_proof_text or "").strip()
    results = []
    for item in PROOF_RUBRICS[rubric_id]:
        matches = [re.search(pat, text, flags=re.IGNORECASE | re.DOTALL) for pat in item["patterns"]]
        present = all(m is not None for m in matches) if item["require_all"] else any(m is not None for m in matches)
        matched_span = next((m.group(0) for m in matches if m is not None), "")
        results.append(
            {
                "lemma_id": item["lemma_id"],
                "label": item["label"],
                "present": present,
                "student_quote": matched_span if present else "",
                "feedback": "Passaggio presente." if present else item["missing_hint"],
            }
        )
    all_passed = all(r["present"] for r in results)
    return {
        "rubric_id": rubric_id,
        "results": results,
        "passed_count": sum(1 for r in results if r["present"]),
        "total_lemmas": len(results),
        "all_passed": all_passed,
    }
