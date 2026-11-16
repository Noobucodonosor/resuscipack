---
id: operazioni.sottrazione
titolo: Sottrazione come togliere e come differenza
livello: elementari
prerequisiti:
  - operazioni.addizione
stato: validata_auto
aggiornato: '2026-11-16'
fonti:
  - block_pk: 13636
    block_uid: blk_b083ca8e9fa024dc9719
    citazione: "è maggiore del sottraendo (numero che si sottrae) o tutt'al più ad esso uguale, la sottrazione è possibile"
  - block_pk: 53594
    block_uid: blk_3a701adb097a696d6fe6
    citazione: "Per poter eseguire ogni possibile sottrazione tra i numeri naturali è necessario"
---

**Prerequisiti:** `operazioni.addizione` (verso `numeri.relativi` → `P0.4` Interi $\mathbb{Z}$ → `P4.2` Complemento a due e underflow)

## Contesto
Sia quando si «toglie» una parte da un gruppo ($5$ mele meno $3$), sia quando si «confronta» quanto manca a $3$ per raggiungere $5$, si cerca lo stesso oggetto: l'addendo mancante $c$ tale che $b + c = a$. Nei numeri naturali, però, questa operazione inversa incontra un muro appena il sottraendo supera il minuendo [^1], creando la spinta progettuale che porterà a inventare i numeri negativi [^2].

## Concetti
### Intuitivo
Se sul conto ci sono $5$ euro e ne spendi $3$, restano $2$ euro perché $3 + 2 = 5$. Se provi a spenderne $8$ usando solo quantità naturali senza debiti, l'operazione si blocca. Inoltre nell'ordine delle operazioni conta chi sta davanti: togliere $3$ da $5$ non equivale a togliere $5$ da $3$.

### Formale
Dati $a, b \in \mathbb{N}$, la differenza $a - b$ è definita (quando esiste) come l'unico $c \in \mathbb{N}$ tale che:
$$b + c = a$$
Per la definizione d'ordine su $\mathbb{N}$ (`numeri.ordine`), un tale $c \in \mathbb{N}$ esiste se e solo se $a \ge b$ [^1].

### Termini
- **minuendo ($a$)**: quantità iniziale da cui si sottrae.
- **sottraendo ($b$)**: quantità sottratta; la condizione di esistenza in $\mathbb{N}$ è $a \ge b$.
- **operazione parziale**: operazione non definita su tutte le coppie dell'insieme (a differenza di $+$ che è totale su $\mathbb{N} \times \mathbb{N}$).

## Enunciati
- **[Definizione]** Per $a, b \in \mathbb{N}$, $a - b = c$ significa che $c \in \mathbb{N}$ soddisfa $b + c = a$. — *Giustificazione:* Definisce la sottrazione come inversione esatta dell'addizione, unificando il significato di «resto» e quello di «differenza».
- **[Teorema]** Esistenza e unicità in $\mathbb{N}$: la differenza $a - b$ esiste in $\mathbb{N}$ se e solo se $a \ge b$ [^1], ed è unica. — *Giustificazione:* Per definizione $b \le a \iff \exists c \in \mathbb{N}: b + c = a$; l'unicità segue dalla legge di cancellazione dell'addizione ($b + c_1 = b + c_2 \implies c_1 = c_2$).
- **[Teorema]** La sottrazione non è né commutativa né associativa. — *Giustificazione:* Basta un controesempio verificabile (`P0.1`): per $5$ e $3$, $5 - 3 = 2$ mentre $3 - 5$ non esiste in $\mathbb{N}$ (e in $\mathbb{Z}$ vale $-2 \neq 2$); per l'associatività, $(9 - 4) - 2 = 3 \neq 7 = 9 - (4 - 2)$.
- **[Convenzione]** In assenza di parentesi, una catena di sottrazioni si valuta da sinistra a destra: $a - b - c := (a - b) - c$. — *Giustificazione:* Poiché la sottrazione non è associativa, senza questa convenzione sintattica la scrittura $9 - 4 - 2$ sarebbe ambigua tra $3$ e $7$.

## Decisione
Definire $a - b$ in $\mathbb{N}$ tramite l'equazione $b + c = a$ accettando che sia parziale per $a < b$, anziché forzare un risultato artificiale che distrugga l'inversione della somma.

## Alternative
- **A.** Sottrazione saturata a zero: porre $a - b = 0$ ogni volta che $a < b$.
- **B.** Distanza senza segno: porre $a \ominus b = |a - b|$ (sempre positivo).
- **C.** Ampliare l'insieme numerico da $\mathbb{N}$ agli interi relativi $\mathbb{Z}$ [^2].

## Conseguenze
Con **A** si ha sia $3 - 5 = 0$ sia $4 - 5 = 0$, perdendo l'invertibilità $(a - b) + b = a$ (in informatica esiste nei registri *saturating arithmetic*, mentre negli interi *unsigned* C `3u - 5u` provoca un pericoloso *integer underflow* studiato in `P4.2` e `G12 Offensive Security`!). Con **B** si perde il verso dello scarto. La via maestra algebrica sarà **C** (`numeri.relativi`).

## Lacune
- La costruzione formale di $\mathbb{Z}$ come classi di equivalenza di coppie $(a, b) \in \mathbb{N} \times \mathbb{N}$ verrà introdotta tra `P0.3` e `P0.4`.

## Esercizio "che cosa si rompe"
1. Calcola $(15 - 6) - 2$ e $15 - (6 - 2)$: di quanto differiscono e perché?
2. Con la regola saturata **A**, verifica che $(3 - 5) + 5 \neq 3$: quale enunciato si rompe?
3. Su un contatore binario senza segno a 8 bit (`0..255`), cosa succede fisicamente quando calcoli `3 - 5` se non c'è saturazione?

## Note
[^1]: [block_pk=13636 | block_uid=blk_b083ca8e9fa024dc9719] «è maggiore del sottraendo (numero che si sottrae) o tutt'al più ad esso uguale, la sottrazione è possibile» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 161)
[^2]: [block_pk=53594 | block_uid=blk_3a701adb097a696d6fe6] «Per poter eseguire ogni possibile sottrazione tra i numeri naturali è necessario» — Nella Dodero, Paolo Baroncini, Dante Trezzi, Nuovi elementi di matematica Vol. 1 (p. 155)
