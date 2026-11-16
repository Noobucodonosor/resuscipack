---
id: operazioni.addizione
titolo: Addizione come riunire
livello: elementari
prerequisiti:
  - numeri.quantita
  - numeri.ordine
stato: validata_auto
aggiornato: '2026-11-16'
fonti:
  - block_pk: 13401
    block_uid: blk_54b1d80e96f4d15f1788
    citazione: "dà lo stesso risultato se s’inverte l'ordine dei termini stessi"
  - block_pk: 13604
    block_uid: blk_a7503139086c7573d860
    citazione: "la somma resta la stessa se si scambiano i termini tra loro"
  - block_pk: 13509
    block_uid: blk_28381db92423d6bbfb27
    citazione: "si possono associare gli addendi come si vuole, perchè il risultato è sempre lo stesso"
  - block_pk: 13795
    block_uid: blk_61f37ff5165663c9d789
    citazione: "detta addizione speciale gode della proprietà associativa e di quella commutativa"
---

**Prerequisiti:** `numeri.quantita`, `numeri.ordine` (verso `P0.5` Calcolo algebrico → `P2.2` Aritmetica modulare → `P4.1` Crittografia)

## Contesto
Riunire 3 mele e 2 mele in uno stesso cesto produce 5 mele qualunque sia il gruppo versato per primo. Attilio Frajese osserva che l'invarianza rispetto all'inversione dei termini è un'evidenza empirica immediata [^1], ma in matematica va fondata rigorosamente per capire *perché* vale e *quando* continua a valere anche fuori dal conteggio ordinario (come nelle aritmetiche finite ad orologio [^4]).

## Concetti
### Intuitivo
Metti sul tavolo due gruppi separati di gettoni (senza gettoni in comune) e spingili in un unico mucchio: non hai né creato né distrutto gettoni. Se hai tre gruppi $A, B, C$, puoi unire prima $A$ con $B$ e poi aggiungere $C$, oppure unire prima $B$ con $C$ e poi $A$: sul tavolo finiscono esattamente gli stessi gettoni.

### Formale
- **Approccio cardinale:** dati due numeri naturali $a, b$, si scelgono due insiemi finiti **disgiunti** ($A \cap B = \emptyset$) con $\operatorname{card}(A) = a$ e $\operatorname{card}(B) = b$, e si definisce $a + b = \operatorname{card}(A \cup B)$.
- **Perché servono le parentesi:** il simbolo $+$ è un'**operazione binaria**, cioè una funzione $+ : \mathbb{N} \times \mathbb{N} \to \mathbb{N}$ che accetta *esattamente due* argomenti per volta. La scrittura $a + b + c$ da sola sarebbe sintatticamente incompleta: le parentesi in $(a + b) + c$ prescrivono quale coppia binaria viene valutata per prima. Solo dopo aver dimostrato l'associatività diventa lecito omettere le parentesi.

### Termini
- **insiemi disgiunti ($A \cap B = \emptyset$)**: insiemi privi di elementi in comune.
- **operazione binaria**: legge che combina una coppia ordinata $(a, b)$ in un unico risultato.
- **elemento neutro additivo**: numero $e$ tale che $a + e = e + a = a$ per ogni $a$ (in $\mathbb{N}$ è $0$).

## Enunciati
- **[Definizione]** Siano $A, B$ insiemi finiti disgiunti ($A \cap B = \emptyset$) con $\operatorname{card}(A) = a$ e $\operatorname{card}(B) = b$; si definisce somma $a + b = \operatorname{card}(A \cup B)$. — *Giustificazione:* Il vincolo $A \cap B = \emptyset$ impedisce che uno stesso elemento venga contato due volte; la buona definizione non dipende dalla scelta dei rappresentanti perché biiezioni su $A$ e $B$ disgiunti si incollano in un'unica biiezione su $A \cup B$.
- **[Convenzione]** Le parentesi tonde in un'espressione come $(a + b) + c$ indicano l'ordine di valutazione di un'operazione binaria (albero sintattico): si calcola prima il valore della sotto-espressione racchiusa e lo si passa come singolo operando all'operazione esterna. — *Giustificazione:* Poiché $+$ è definita su coppie e non su triple, raggruppare con le parentesi è l'unico modo formale per ridurre tre o più termini a una catena di operazioni binarie successive.
- **[Teorema]** Proprietà commutativa: per ogni $a, b \in \mathbb{N}$, $a + b = b + a$ [^2]. — *Giustificazione:* Per definizione d'unione insiemistica $A \cup B = B \cup A$ (appartenere ad $A$ *o* a $B$ equivale ad appartenere a $B$ *o* ad $A$), dunque i due insiemi coincidono ed hanno identica cardinalità.
- **[Teorema]** Proprietà associativa: per ogni $a, b, c \in \mathbb{N}$, $(a + b) + c = a + (b + c)$ [^3]. — *Giustificazione:* Scelti $A, B, C$ a due a due disgiunti, vale l'identità insiemistica $(A \cup B) \cup C = A \cup (B \cup C)$; ciò autorizza a scrivere $a + b + c$ senza ambiguità.
- **[Teorema]** Esistenza e unicità dell'elemento neutro additivo: $0$ soddisfa $a + 0 = 0 + a = a$ per ogni $a \in \mathbb{N}$. — *Giustificazione:* Poiché $\operatorname{card}(\emptyset) = 0$, $A \cap \emptyset = \emptyset$ e $A \cup \emptyset = A$, segue $\operatorname{card}(A \cup \emptyset) = \operatorname{card}(A) = a$. Se esistesse un altro neutro $0'$, si avrebbe $0 = 0 + 0' = 0'$.

## Decisione
Definire $a + b$ come cardinalità dell'unione di due rappresentanti **disgiunti**, ottenendo un'operazione binaria commutativa, associativa e dotata di elemento neutro $0$.

## Alternative
- **A.** Unire insiemi qualsiasi senza richiedere che siano disgiunti ($A \cap B \neq \emptyset$).
- **B.** Addizione modulare su un insieme finito ciclico (es. aritmetica dell'orologio o su $\{0, 1\}$, che conserva associatività e commutatività [^4]).
- **C.** Concatenazione ordinata di sequenze/stringhe (`"porta" + "chiavi"`).

## Conseguenze
Con **A**, unendo $\{\text{Anna}, \text{Bruno}\}$ e $\{\text{Bruno}, \text{Carla}\}$ si ottengono 3 persone anziché $2 + 2 = 4$: il risultato non dipenderebbe più solo dalle cardinalità $a, b$ (servirà il principio di inclusione-esclusione $\operatorname{card}(A \cup B) = a + b - \operatorname{card}(A \cap B)$ in `P2.2`). Con **B** ($9 + 5 \equiv 2 \pmod{12}$) la somma non misura più quantità crescenti ma rotazioni cicliche (fondamentali per XOR e RSA in `P4.1`). Con **C** cade la commutatività (`"chiaviporta" != "portachiavi"`).

## Lacune
- La costruzione alternativa dell'addizione per ricorsione sugli assiomi di Peano ($a + 0 = a$, $a + s(b) = s(a + b)$) verrà affrontata in `P2.1` (*Induzione e ricorsione*).

## Esercizio "che cosa si rompe"
1. Calcola `(38 + 7) + 2` raggruppando invece come `38 + (7 + 2)` + scambio: dichiara a ogni passo quale teorema (commutativo o associativo) stai usando.
2. Dati $A = \{1, 2, 3\}$ e $B = \{3, 4\}$, calcola $\operatorname{card}(A \cup B)$ e spiega quale ipotesi della definizione di somma è stata violata.
3. Nell'addizione binaria modulo 2 su $\{0, 1\}$ (porta XOR: $1 \oplus 1 = 0$), verifica che $0$ è ancora l'elemento neutro ma che $1 + 1 > 1$ si rompe.

## Note
[^1]: [block_pk=13401 | block_uid=blk_54b1d80e96f4d15f1788] «dà lo stesso risultato se s’inverte l'ordine dei termini stessi» — Attilio Frajese, Introduzione alla matematica (p. 71)
[^2]: [block_pk=13604 | block_uid=blk_a7503139086c7573d860] «la somma resta la stessa se si scambiano i termini tra loro» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 129)
[^3]: [block_pk=13509 | block_uid=blk_28381db92423d6bbfb27] «si possono associare gli addendi come si vuole, perchè il risultato è sempre lo stesso» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 33)
[^4]: [block_pk=13795 | block_uid=blk_61f37ff5165663c9d789] «detta addizione speciale gode della proprietà associativa e di quella commutativa» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 320)
