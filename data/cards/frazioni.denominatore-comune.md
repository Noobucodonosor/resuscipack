---
id: frazioni.denominatore-comune
titolo: Somma di frazioni con il denominatore comune
livello: elementari
prerequisiti:
  - frazioni.significato
  - frazioni.equivalenza
  - operazioni.distributiva
stato: validata_auto
aggiornato: '2026-11-16'
fonti:
  - block_pk: 13624
    block_uid: blk_cf2bf5d58638e88d9709
    citazione: "supponiamo che per la moltiplicazione e l'addizione dei numeri razionali debba valere la proprietà distributiva"
  - block_pk: 13624
    block_uid: blk_cf2bf5d58638e88d9709
    citazione: "si addizionano i numeratori, lasciando invariato il denominatore"
  - block_pk: 13624
    block_uid: blk_cf2bf5d58638e88d9709
    citazione: "Se poi le frazioni non hanno lo stesso denominatore si riducono ad averlo"
  - block_pk: 13623
    block_uid: blk_b745da3a725ca7c69582
    citazione: "Proviamo a moltiplicare quella somma per 7 (denominatore comune delle due frazioni)"
  - block_pk: 53739
    block_uid: blk_04649d3b923e115ce9ff
    citazione: "per eseguire la somma di più frazioni algebriche occorre, per prima cosa, ridurle allo stesso denominatore"
---

**Prerequisiti:** `frazioni.significato`, `frazioni.equivalenza`, `operazioni.distributiva` (verso `P0.4` Razionali $\mathbb{Q}$ → `P0.5` Disequazioni fratte → `G00 Matematica I`)

## Contesto
La regola $\frac{a}{b} + \frac{c}{d} = \frac{ad + cb}{bd}$ è l'esempio archetipico dell'«effetto sudoku» scolastico: imparata a memoria sembra un rituale arbitrario, mentre molti studenti tentano spontaneamente $\frac{a+c}{b+d}$. Attilio Frajese mostra invece che la regola non è un dogma calato dall'alto, bensì l'**unica conseguenza possibile** se vogliamo che per i numeri razionali continui a valere la proprietà distributiva degli interi [^1].

## Concetti
### Intuitivo
$\frac{2}{7}$ sono due fette di taglia «un settimo» e $\frac{3}{7}$ sono tre fette della stessa taglia: messe insieme danno cinque settimi [^2]. Se invece hai quarti e quinti ($\frac{3}{4} + \frac{2}{5}$), le fette hanno taglia diversa: prima le tagli in ventesimi ($\frac{15}{20}$ e $\frac{8}{20}$) così contano la stessa unità frazionaria [^3].

### Formale
Seguendo la derivazione costruttiva di Frajese [^4]: vogliamo determinare $S = \frac{a}{n} + \frac{b}{n}$ ($n \neq 0$) imponendo che $\frac{a}{n} \cdot n = a$ e che valga la proprietà distributiva [^1]:
$$S \cdot n = \left(\frac{a}{n} + \frac{b}{n}\right) \cdot n = \frac{a}{n}\cdot n + \frac{b}{n}\cdot n = a + b \implies S = \frac{a + b}{n}$$
Per denominatori diversi $b, d \neq 0$, per equivalenza (`frazioni.equivalenza`) $\frac{a}{b} = \frac{ad}{bd}$ e $\frac{c}{d} = \frac{cb}{bd}$, da cui $\frac{a}{b} + \frac{c}{d} = \frac{ad + cb}{bd}$, identica regola che varrà per le frazioni algebriche coi polinomi in `P0.5` [^5].

### Termini
- **denominatore comune**: multiplo comune di $b$ e $d$ (il prodotto $bd$ o il minimo comune multiplo $\operatorname{mcm}(b, d)$) scelto come nuova unità frazionaria condivisa.
- **operazione ben definita**: operazione il cui risultato non cambia se si sostituiscono gli operandi con frazioni ad essi equivalenti ($\frac{1}{2}$ vs $\frac{2}{4}$).
- **mediante di Farey**: il rapporto $\frac{a+c}{b+d}$, sempre compreso tra $\frac{a}{b}$ e $\frac{c}{d}$, utile in teoria dei numeri ma incompatibile con la somma di quantità.

## Enunciati
- **[Assioma]** Principio di permanenza delle proprietà formali: nell'estendere $+, \cdot$ da $\mathbb{Z}$ a $\mathbb{Q}$ si richiede che continuino a valere associatività, commutatività e proprietà distributiva $x(y + z) = xy + xz$ [^1]. — *Giustificazione:* È il requisito progettuale che evita di dover cambiare le regole del calcolo algebrico ogni volta che si allarga l'insieme numerico.
- **[Teorema]** Somma con uguale denominatore: per ogni $a, b \in \mathbb{Z}$ e $n \neq 0$, il principio di permanenza impone $\frac{a}{n} + \frac{b}{n} = \frac{a + b}{n}$ [^2]. — *Giustificazione:* Moltiplicando la somma incognita per $n$ [^4] e distribuendo si ottiene necessariamente $a + b$; poiché la divisione per $n \neq 0$ ha soluzione unica in $\mathbb{Q}$, la somma non può avere altro valore.
- **[Teorema]** Somma con denominatori qualsiasi e buona definizione: per $b, d \neq 0$, $\frac{a}{b} + \frac{c}{d} = \frac{ad + cb}{bd}$ [^3], e il risultato è invariante sostituendo $\frac{a}{b}$ con $\frac{ka}{kb}$ ($k \neq 0$). — *Giustificazione:* Sostituendo $a \mapsto ka, b \mapsto kb$ si ottiene $\frac{(ka)d + c(kb)}{(kb)d} = \frac{k(ad + cb)}{k(bd)} = \frac{ad + cb}{bd}$.
- **[Convenzione]** Nei calcoli manuali e sulle frazioni algebriche [^5] si preferisce come denominatore comune $\operatorname{mcm}(b, d)$ anziché $bd$. — *Giustificazione:* Non cambia il valore razionale finale, ma minimizza la grandezza dei coefficienti intermedi prima della semplificazione.

## Decisione
Ridurre sempre le frazioni a uno stesso denominatore comune prima di sommare i numeratori, così da preservare la proprietà distributiva e la buona definizione sulle classi di frazioni equivalenti.

## Alternative
- **A.** Sommare numeratori tra loro e denominatori tra loro: $\frac{a}{b} \oplus \frac{c}{d} = \frac{a+c}{b+d}$.
- **B.** Convertire preventivamente ogni frazione in numero decimale finito troncato.

## Conseguenze
Con **A** esplodono due contraddizioni fatali: (1) $\frac{1}{2} \oplus \frac{1}{2} = \frac{2}{4} = \frac{1}{2}$ (mezza torta più mezza torta farebbe mezza torta!); (2) sostituendo $\frac{1}{2}$ con la frazione equivalente $\frac{2}{4}$, $\frac{1}{2} \oplus \frac{1}{3} = \frac{2}{5} = 0{,}4$ mentre $\frac{2}{4} \oplus \frac{1}{3} = \frac{3}{7} \approx 0{,}428$: **lo stesso numero scritto in due modi dà risultati diversi** (operazione mal definita!). Con **B** frazioni periodiche come $\frac{1}{3} = 0{,}333\dots$ introducono errori di arrotondamento cumulativi ($\frac{1}{3} + \frac{1}{3} + \frac{1}{3} = 0{,}99 \neq 1$).

## Lacune
- L'estensione formale ai polinomi $\frac{P(x)}{Q(x)}$ con condizione di esistenza $Q(x) \neq 0$ è sviluppata nel nodo `P0.5`.

## Esercizio "che cosa si rompe"
1. Applica la falsa regola **A** a $\frac{1}{3} + \frac{1}{6}$ e poi a $\frac{2}{6} + \frac{1}{6}$: mostra che ottieni due numeri diversi pur partendo dalle stesse quantità.
2. Ricava quanto vale $\frac{2}{9} + \frac{5}{9}$ col metodo di Frajese: chiama $S$ la somma, moltiplicala per $9$ usando la distributiva e isola $S$.
3. Somma $\frac{3}{4} - \frac{2}{5}$ sia usando il prodotto dei denominatori sia usando il $\operatorname{mcm}$ e verifica che coincidono.

## Note
[^1]: [block_pk=13624 | block_uid=blk_cf2bf5d58638e88d9709] «supponiamo che per la moltiplicazione e l'addizione dei numeri razionali debba valere la proprietà distributiva» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 149)
[^2]: [block_pk=13624 | block_uid=blk_cf2bf5d58638e88d9709] «si addizionano i numeratori, lasciando invariato il denominatore» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 149)
[^3]: [block_pk=13624 | block_uid=blk_cf2bf5d58638e88d9709] «Se poi le frazioni non hanno lo stesso denominatore si riducono ad averlo» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 149)
[^4]: [block_pk=13623 | block_uid=blk_b745da3a725ca7c69582] «Proviamo a moltiplicare quella somma per 7 (denominatore comune delle due frazioni)» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 148)
[^5]: [block_pk=53739 | block_uid=blk_04649d3b923e115ce9ff] «per eseguire la somma di più frazioni algebriche occorre, per prima cosa, ridurle allo stesso denominatore» — Nella Dodero, Paolo Baroncini, Dante Trezzi, Nuovi elementi di matematica Vol. 1 (p. 300)
