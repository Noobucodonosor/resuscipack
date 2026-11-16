---
id: numeri.posizionale
titolo: Sistema posizionale decimale e zero
livello: elementari
prerequisiti:
  - numeri.quantita
stato: validata_auto
aggiornato: '2026-11-16'
fonti:
  - block_pk: 39085
    block_uid: blk_a366f03bf4bf8aa2e912
    citazione: "la posizione di una cifra all'interno di un numero ne stabilisce il valore"
  - block_pk: 39085
    block_uid: blk_a366f03bf4bf8aa2e912
    citazione: "La notazione posizionale fu una grande invenzione (probabilmente fu inventato in India e arrivò in Europa attraverso gli arabi)"
  - block_pk: 54017
    block_uid: blk_fd054ff99c5d6501da5f
    citazione: "le norme per eseguire le operazioni aritmetiche con i numeri decimali scritti mediante le cifre arabe"
---

**Prerequisiti:** `numeri.quantita` (verso `operazioni.colonna` → `P4.2` Binario/Esadecimale → `G03 Computing Systems`)

## Contesto
Rappresentare quantità con una tacca per ogni unità diventa illeggibile già oltre qualche decina; inventare un simbolo nuovo per ogni ordine di grandezza costringe a memorizzare infiniti segni. La svolta indiano-araba [^2], diffusa in Europa insieme agli algoritmi di calcolo di al-Khwarizmi e Fibonacci [^3], risolve il problema facendo dipendere il peso di una cifra dalla sua posizione [^1] e introducendo lo zero per marcare una colonna vuota.

## Concetti
### Intuitivo
Nel numero `5605` compaiono due `5`: il primo conta 5 gruppi da mille, l'ultimo 5 unità singole, mentre lo `0` avverte che non ci sono centinaia sciolte. Cambiare base (es. base 2 nei calcolatori) significa semplicemente cambiare la taglia dei pacchetti da 10 a 2.

### Formale
Fissata una base intera $b \ge 2$ e l'alfabeto di cifre $D_b = \{0, 1, \dots, b-1\}$, la stringa posizionale $(c_k c_{k-1} \dots c_1 c_0)_b$ denota il numero naturale:
$$N = \sum_{i=0}^{k} c_i \cdot b^i = c_k b^k + \dots + c_1 b^1 + c_0 b^0$$
Per $b = 10$ si ottiene la scrittura decimale ordinaria; la cifra $0$ moltiplica la rispettiva potenza $b^i$ annullandone il contributo ma preservando gli indici $j > i$ delle cifre a sinistra.

### Termini
- **base di numerazione ($b$)**: numero di unità di un ordine necessarie per formare 1 unità dell'ordine immediatamente a sinistra.
- **valore posizionale**: peso $b^i$ associato all'indice di colonna $i \ge 0$ contato da destra.
- **zero segnaposto**: cifra che indica cardinalità nulla in una specifica posizione evitando lo slittamento degli ordini superiori.

## Enunciati
- **[Definizione]** In base $b \ge 2$, la scrittura $(c_k \dots c_0)_b$ con $c_i \in \{0, \dots, b-1\}$ vale $\sum_{i=0}^k c_i b^i$ [^1]. — *Giustificazione:* Associa a sequenze finite su un alfabeto ridotto quantità arbitrariamente grandi con crescita esponenziale nella lunghezza $k+1$.
- **[Teorema]** Teorema di rappresentazione in base $b$: ogni naturale $N \ge 1$ si scrive in modo unico come $\sum_{i=0}^k c_i b^i$ con $0 \le c_i < b$ e $c_k \neq 0$. — *Giustificazione:* Dividendo ripetutamente $N$ per $b$ con resto euclideo (`operazioni.divisione`), il resto $N \bmod b$ fissa univocamente $c_0$ e il quoziente $\lfloor N/b \rfloor < N$ determina ricorsivamente le cifre successive.
- **[Convenzione]** La base canonica quotidiana è $b = 10$ con le dieci cifre indo-arabe `0..9` [^2], mentre in architettura dei calcolatori (`G03`) si adottano $b = 2$ e $b = 16$. — *Giustificazione:* Il dieci riflette l'anatomia delle dieci dita umane, non una necessità matematica; il due riflette i due stati fisici stabili di un transistor [^3].

## Decisione
Usare un alfabeto finito di $b$ cifre (incluso lo `0` segnaposto) in cui ogni spostamento di una posizione a sinistra moltiplica il valore per la base $b$.

## Alternative
- **A.** Sistema additivo puro o misto senza zero (es. numerazione romana `MMDCCCLXXXVIII`).
- **B.** Sistema posizionale con spazio bianco al posto dello zero (tavolette babilonesi arcaiche).

## Conseguenze
Con **A** i simboli non sono allineati per ordini omogenei, rendendo impraticabili gli algoritmi meccanici in colonna (`operazioni.colonna`). Con **B** le scritture `37`, `307` e `3070` diventano indistinguibili su carta. Con la notazione posizionale, rappresentare $N$ richiede appena $\lfloor \log_b N \rfloor + 1$ cifre (complessità spaziale logaritmica in `P2.2`).

## Lacune
- I passaggi estratti sintetizzano la trasmissione indo-araba senza riportare il testo integrale del *Liber Abaci* di Leonardo Pisano; per l'aritmetica binaria su parola fissa e overflow si rimanda a `P4.2`.

## Esercizio "che cosa si rompe"
1. Prova a sommare in colonna `MCMXCIX + XXVII` senza convertire in cifre indo-arabe: quale proprietà posizionale ti viene a mancare?
2. Quanti numeri distinti minori di $10\,000$ collassano nella scrittura ambigua `4  2` se si abolisce la cifra `0`?
3. Scrivi `29` in base $2$ esplicitando la somma di potenze $2^i$.

## Note
[^1]: [block_pk=39085 | block_uid=blk_a366f03bf4bf8aa2e912] «la posizione di una cifra all'interno di un numero ne stabilisce il valore» — Dispensa ITS, Numerazioni e logica di base (p. 1)
[^2]: [block_pk=39085 | block_uid=blk_a366f03bf4bf8aa2e912] «La notazione posizionale fu una grande invenzione (probabilmente fu inventato in India e arrivò in Europa attraverso gli arabi)» — Dispensa ITS, Numerazioni e logica di base (p. 1)
[^3]: [block_pk=54017 | block_uid=blk_fd054ff99c5d6501da5f] «le norme per eseguire le operazioni aritmetiche con i numeri decimali scritti mediante le cifre arabe» — Nella Dodero, Paolo Baroncini, Dante Trezzi, Nuovi elementi di matematica Vol. 1 (p. 578)
