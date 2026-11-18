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


def _build_single_drill(node_id: str, key: str, idx: int, rng: random.Random) -> dict[str, Any]:
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
