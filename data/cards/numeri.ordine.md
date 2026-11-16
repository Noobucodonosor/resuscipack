---
id: numeri.ordine
titolo: Confrontare e ordinare i numeri
livello: elementari
prerequisiti:
  - numeri.quantita
stato: validata_auto
aggiornato: '2026-11-16'
fonti:
  - block_pk: 13586
    block_uid: blk_d7e812c2ff3c4e8f8db2
    citazione: "B può mettersi in corrispondenza biunivoca con una parte (propria) di A"
  - block_pk: 28506
    block_uid: blk_b6649475b70a00c35b46
    citazione: "Si deve a G. Peano una presentazione assiomatica degli interi naturali basata sulle nozioni primitive di “numero”, “zero” e “successivo”"
---

**Prerequisiti:** `numeri.quantita` (verso `P0.3` Relazioni d'ordine → `G07 Programmazione II` Ordinamento e alberi di ricerca)

## Contesto
Stabilito quando due insiemi hanno la stessa quantità, occorre decidere quale di due gruppi diversi ne ha «di più». Attilio Frajese mostra che anche la disuguaglianza nasce dall'accoppiamento senza bisogno di contare: un insieme $A$ prevale su $B$ quando $B$ si accoppia biunivocamente solo con una parte propria di $A$ [^1]. Parallelamente, Giuseppe Peano fonda l'intera catena dei naturali sull'operazione di passaggio al «successivo» a partire dallo zero [^2].

## Concetti
### Intuitivo
Se in una sala ogni ospite occupa una sedia e restano ancora sedie libere, le sedie sono più degli ospiti senza dover contare né gli uni né le altre. Disponendo i numeri in fila da sinistra a destra ($0, 1, 2, 3, \dots$), fare un passo a destra significa passare al successivo $n + 1$: «minore» diventa geometricamente «più a sinistra».

### Formale
Siano $A, B$ insiemi finiti con $a = \operatorname{card}(A)$ e $b = \operatorname{card}(B)$:
- Si scrive $b < a$ se esiste un sottoinsieme proprio $A' \subsetneq A$ tale che $B \sim A'$ [^1] (per gli insiemi finiti il principio dei cassetti vieta che sia contemporaneamente $A \sim B$).
- Nell'assiomatica di Peano [^2], $\mathbb{N}$ è generato da $0$ e da una funzione iniettiva $s: \mathbb{N} \to \mathbb{N} \setminus \{0\}$ (successivo), e si definisce $b \le a \iff \exists k \in \mathbb{N}: b + k = a$.

### Termini
- **sottoinsieme proprio ($A' \subsetneq A$)**: parte di $A$ a cui manca almeno un elemento di $A$.
- **successivo ($s(n)$ o $n+1$)**: il numero immediatamente seguente nella catena di Peano.
- **ordine totale (tricotomia)**: per ogni coppia $a, b \in \mathbb{N}$ vale esattamente una tra $a < b$, $a = b$, $a > b$.

## Enunciati
- **[Definizione]** Per insiemi finiti $A, B$ di cardinalità $a, b$, si pone $b < a$ se $B$ è equipotente a una parte propria di $A$ [^1]. — *Giustificazione:* Riduce il confronto «minore di» alla sola nozione di biiezione introdotta in `numeri.quantita`.
- **[Assioma]** Assiomi di Peano sul successivo: $0$ non è successivo di alcun naturale, e numeri distinti hanno successivi distinti ($m \neq n \implies s(m) \neq s(n)$) [^2]. — *Giustificazione:* Impedisce che la catena dei naturali si richiuda ad anello come le ore di un orologio.
- **[Teorema]** Antisimmetria e transitività dell'ordine su $\mathbb{N}$: non può essere insieme $a < b$ e $b < a$; se $a < b$ e $b < c$ allora $a < c$. — *Giustificazione:* Se per assurdo $a < b$ e $b < a$, componendo le inclusioni proprie si avrebbe una biiezione tra un insieme finito e una sua parte propria, vietata dal principio dei cassetti.
- **[Convenzione]** Sulla retta orientata i numeri crescono da sinistra verso destra ($a < b \iff a$ sta a sinistra di $b$). — *Giustificazione:* Fissa un riferimento visivo uniforme che resterà identico per negativi (`numeri.relativi`) e reali (`P0.4`, `P0.5`).

## Decisione
Ordinare i numeri naturali in una successione lineare illimitata dotata di minimo ($0$) e funzione successivo iniettiva, equivalente al confronto per inclusione propria tra insiemi finiti.

## Alternative
- **A.** Ordine ciclico finito (come l'orologio modulo 12).
- **B.** Ordine lessicografico carattere per carattere (come le stringhe ASCII nei programmi).

## Conseguenze
Con **A** si rompe la transitività: sull'orologio 11 precede 12 e 12 precede 1, ma 1 non è maggiore di 11 (nasce l'aritmetica modulare di `P2.2`/`P4.1`, priva però di ordine compatibile con la somma). Con **B** `"10" < "9"` perché il carattere `'1'` precede `'9'`: bug classico di programmazione quando si ordinano stringhe invece di interi.

## Lacune
- La distinzione formale tra buon ordinamento (ogni sottoinsieme non vuoto di $\mathbb{N}$ ha minimo) e principio di induzione verrà completata in `P2.1`.

## Esercizio "che cosa si rompe"
1. Ordina `9`, `10`, `100`, `25` come stringhe ASCII e come numeri naturali: mostra quale coppia inverte l'ordine.
2. Verifica sull'orologio a 12 ore perché non può esistere una relazione `<` transitiva invariante per rotazione.
3. Dato $A = \{a, b, c, d\}$ e $B = \{1, 2\}$, elenca due parti proprie distinte di $A$ equipotenti a $B$.

## Note
[^1]: [block_pk=13586 | block_uid=blk_d7e812c2ff3c4e8f8db2] «B può mettersi in corrispondenza biunivoca con una parte (propria) di A» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 110)
[^2]: [block_pk=28506 | block_uid=blk_b6649475b70a00c35b46] «Si deve a G. Peano una presentazione assiomatica degli interi naturali basata sulle nozioni primitive di “numero”, “zero” e “successivo”» — Giovanni Prodi, Analisi Matematica (p. 47)
