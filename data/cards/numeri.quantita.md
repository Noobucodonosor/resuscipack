---
id: numeri.quantita
titolo: Contare e il numero come quantità
livello: elementari
prerequisiti: []
stato: validata_auto
aggiornato: '2026-11-16'
fonti:
  - block_pk: 13581
    block_uid: blk_a96a0243502d4911da96
    citazione: "una corrispondenza biunivoca tra gli elementi di due insiemi finiti può aversi SE E SOLTANTO SE i due insiemi hanno lo stesso numero di elementi"
  - block_pk: 60835
    block_uid: blk_9b590aa35c56ecad2cb8
    citazione: "con gli elementi in corrispondenza biunivoca, due insiemi cioè «egualmente numerosi»"
  - block_pk: 60835
    block_uid: blk_9b590aa35c56ecad2cb8
    citazione: "Definisce poi come potenza di un insieme M la proprieta comune ad esso e agli insiemi equipotenti a M"
  - block_pk: 41511
    block_uid: blk_07cf62094c2a30e86fcf
    citazione: "i numeri naturali svolgono, rispetto agli insiemi finiti, un doppio ruolo: da un lato ne caratterizzano la cardinalità"
  - block_pk: 41511
    block_uid: blk_07cf62094c2a30e86fcf
    citazione: "quando dagli insiemi finiti si passa a quelli infiniti, questi due ruoli devono essere separati"
  - block_pk: 28506
    block_uid: blk_b6649475b70a00c35b46
    citazione: "Si deve a G. Peano una presentazione assiomatica degli interi naturali basata sulle nozioni primitive di “numero”, “zero” e “successivo”"
  - block_pk: 13566
    block_uid: blk_272f532d1899e1322a58
    citazione: "Eppure AB è di lunghezza doppia di DE"
---

**Prerequisiti:** nessuno (punto di partenza della Spina Dorsale verso `P0.3` → `G00 Matematica I` → `P4.1 Crittografia`)

## Contesto
Per sapere se ci sono abbastanza sedie per gli ospiti non serve contare: basta far sedere ciascuno. Se nessuno resta in piedi e nessuna sedia resta vuota, i due gruppi sono «tanti quanti». È un confronto che si può fare prima ancora di avere i numeri, e la matematica moderna lo mette alla base: due insiemi finiti si possono accoppiare uno a uno esattamente quando hanno lo stesso numero di elementi [^1].

Georg Cantor trasformò questo confronto in una definizione rigorosa: chiamò equipotenti due insiemi i cui elementi si possono accoppiare uno a uno, «egualmente numerosi» nel linguaggio di Gottlob Frege [^2], e chiamò potenza di un insieme ciò che esso ha in comune con tutti gli insiemi equipotenti [^3]. Il numero, in questa impostazione, non viene prima del confronto: nasce da esso.

## Concetti
### Intuitivo
Attilio Frajese accoppia i quattro punti cardinali con i numeri da 1 a 4 [^1]. Ricostruito in tabella:

| nord | est | sud | ovest |
|---|---|---|---|
| 1 | 2 | 3 | 4 |

Ogni punto cardinale ha il suo numero, ogni numero il suo punto, nessuno resta fuori. Con $\{1, 2, 3, 4, 5\}$ invece è impossibile: comunque si accoppi, un numero resta senza compagno.

Contare è costruire proprio un accoppiamento così, tra gli oggetti e le parole «uno, due, tre…», con tre regole: ogni oggetto si tocca una sola volta, ogni parola si usa una sola volta, non si salta nessuna parola. L'ultima parola detta è la quantità.

### Formale
Siano $A$ e $B$ due insiemi.

- Una funzione $f: A \to B$ è **iniettiva** se manda elementi diversi in elementi diversi ($x \neq y \implies f(x) \neq f(y)$), **suriettiva** se ogni elemento di $B$ è immagine di qualche elemento di $A$, **biiettiva** (corrispondenza biunivoca) se è entrambe le cose.
- $A$ e $B$ sono **equipotenti**, e si scrive $A \sim B$, se esiste una biiezione da $A$ a $B$.
- Per ogni naturale $n$ sia $I_n = \{1, 2, \dots, n\}$, con $I_0 = \emptyset$ (insieme vuoto).
- $A$ ha $n$ elementi, e si scrive $\operatorname{card}(A) = n$, se $A \sim I_n$.

Dall'intuitivo al formale: «accoppiare» è una funzione; «nessuna sedia ha due persone» è l'iniettività; «nessuno resta in piedi» è la suriettività. Contare un insieme $A$ è costruire passo per passo una biiezione da $I_n$ ad $A$.

### Termini
- **corrispondenza biunivoca (biiezione)**: accoppiamento uno a uno tra due insiemi, senza ripetizioni e senza elementi esclusi.
- **iniettiva**: funzione che non manda mai due input distinti nello stesso output (assenza di collisioni, concetto chiave poi per gli hash in `P4.1`).
- **suriettiva**: funzione che copre l'intero insieme di arrivo.
- **equipotenti**: insiemi tra cui esiste una biiezione.
- **cardinalità**: quantità di elementi di un insieme, invariante per equipotenza.

## Enunciati
- **[Definizione]** Una biiezione è una funzione simultaneamente iniettiva e suriettiva. — *Giustificazione:* Traduce senza ambiguità l'accoppiamento uno a uno dell'esempio delle sedie: l'iniettività vieta due ospiti sulla stessa sedia, la suriettività vieta sedie vuote.
- **[Definizione]** Due insiemi $A$ e $B$ sono equipotenti ($A \sim B$) se esiste almeno una biiezione $f: A \to B$. — *Giustificazione:* È la scelta fondativa di Cantor [^2], che permette di definire l'uguaglianza numerica senza presupporre già l'operazione di conteggio.
- **[Teorema]** L'equipotenza è una relazione di equivalenza (riflessiva, simmetrica, transitiva). — *Giustificazione:* L'identità $\operatorname{id}_A$ è biiettiva; l'inversa $f^{-1}$ di una biiezione è biiettiva; la composizione $g \circ f$ di due biiezioni è biiettiva. Garantisce che «avere la stessa quantità» goda delle proprietà formali dell'uguaglianza.
- **[Definizione]** Si pone $\operatorname{card}(A) = n$ se $A \sim I_n$, dove $I_n = \{1, \dots, n\}$ e $I_0 = \emptyset$. — *Giustificazione:* Usa $I_n$ come insieme campione canonico per la «potenza» di Cantor [^3].
- **[Teorema]** Principio dei cassetti (unicità della cardinalità finita): se $A \sim I_n$ e $A \sim I_m$, allora $n = m$. — *Giustificazione:* Per induzione su $n$ si mostra che l'esistenza di una funzione iniettiva $f: I_m \to I_n$ implica $m \le n$. Componendo le due biiezioni tra $I_m$ e $I_n$ si ottiene sia $m \le n$ sia $n \le m$, dunque $n = m$. In informatica (`P4.1`), lo stesso teorema dimostra che una funzione hash da messaggi lunghi a 256 bit deve necessariamente ammettere collisioni.
- **[Teorema]** La quantità ottenuta contando un insieme finito $A$ non dipende dall'ordine in cui si toccano gli oggetti. — *Giustificazione:* Due conteggi in ordine diverso sono due biiezioni $f: I_n \to A$ e $g: I_m \to A$; per il principio dei cassetti segue necessariamente $n = m$.
- **[Convenzione]** Nel conteggio concreto si parte da «uno», mentre all'insieme vuoto si assegna cardinalità $0$ ($I_0 = \emptyset$). — *Giustificazione:* Giuseppe Peano pone lo zero tra gli enti primitivi dei naturali [^6]; partire da 1 sui campioni $I_n$ fa coincidere l'ultimo numerale pronunciato con la cardinalità totale.

## Decisione
Fondare il numero naturale sulla quantità (cardinalità via biiezione) anziché sull'ordine di scorrimento: contare diventa costruire una biiezione con l'insieme campione $\{1, \dots, n\}$.

## Alternative
- **A.** Fondare il numero sull'ordine anziché sulla quantità (primo, secondo, terzo…): è l'assiomatica di Giuseppe Peano basata su numero, zero e successivo [^6]. Negli insiemi finiti i due ruoli coincidono [^4], mentre negli insiemi infiniti cardinali e ordinali divergono [^5].
- **B.** Usare parole-numero diverse a seconda della natura fisica degli oggetti contati.
- **C.** Affidarsi alla sola percezione qualitativa («uno, due, molti»).

## Conseguenze
Con **B** sparisce l'astrazione aritmetica universale; con **C** diventa impossibile verificare scarti minimi (es. 12 contro 13). Il prezzo concettuale della scelta cantoriana emerge sugli insiemi infiniti: i punti di un segmento $AB$ si mettono in biiezione con quelli di un segmento $DE$ lungo la metà, eppure «AB è di lunghezza doppia di DE» [^7]. Un insieme infinito può essere equipotente a una sua parte propria, violando l'intuizione finita del principio dei cassetti.

## Lacune
- La dimostrazione completa per induzione del lemma iniettivo $I_m \to I_n$ è ricostruita nella scheda perché Frajese la assume intuitivamente; verrà ripresa formalmente in `P2.1` (*Induzione e ricorsione*).
- Manca nel corpus l'opera primaria di Gottlob Frege (*I fondamenti dell'aritmetica*, 1884), citata indirettamente tramite Ludovico Geymonat [^2].

## Esercizio "che cosa si rompe"
1. Costruisci due biiezioni distinte tra $\{\text{nord}, \text{est}, \text{sud}, \text{ovest}\}$ e $\{1, 2, 3, 4\}$ e calcola quante ne esistono in tutto.
2. Spiega quale condizione tra iniettività e suriettività si rompe necessariamente tentando una funzione da $\{1, 2, 3, 4, 5\}$ a $\{\text{nord}, \text{est}, \text{sud}, \text{ovest}\}$.
3. «Conta» 5 monete toccandone una due volte: scrivi la mappa da $\{1, \dots, 6\}$ alle monete e indica quale enunciato della scheda ti avverte che il conteggio è invalido.
4. Esibisci una biiezione esplicita tra $\mathbb{N} = \{0, 1, 2, \dots\}$ e i numeri pari $\{0, 2, 4, \dots\}$.

## Note
[^1]: [block_pk=13581 | block_uid=blk_a96a0243502d4911da96] «una corrispondenza biunivoca tra gli elementi di due insiemi finiti può aversi SE E SOLTANTO SE i due insiemi hanno lo stesso numero di elementi» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 105)
[^2]: [block_pk=60835 | block_uid=blk_9b590aa35c56ecad2cb8] «con gli elementi in corrispondenza biunivoca, due insiemi cioè «egualmente numerosi»» — Ludovico Geymonat, Storia e filosofia dell'analisi infinitesimale (p. 104)
[^3]: [block_pk=60835 | block_uid=blk_9b590aa35c56ecad2cb8] «Definisce poi come potenza di un insieme M la proprieta comune ad esso e agli insiemi equipotenti a M» — Ludovico Geymonat, Storia e filosofia dell'analisi infinitesimale (p. 104)
[^4]: [block_pk=41511 | block_uid=blk_07cf62094c2a30e86fcf] «i numeri naturali svolgono, rispetto agli insiemi finiti, un doppio ruolo: da un lato ne caratterizzano la cardinalità» — Paolo Casalegno, Mauro Mariani, Teoria degli insiemi (p. 98)
[^5]: [block_pk=41511 | block_uid=blk_07cf62094c2a30e86fcf] «quando dagli insiemi finiti si passa a quelli infiniti, questi due ruoli devono essere separati» — Paolo Casalegno, Mauro Mariani, Teoria degli insiemi (p. 98)
[^6]: [block_pk=28506 | block_uid=blk_b6649475b70a00c35b46] «Si deve a G. Peano una presentazione assiomatica degli interi naturali basata sulle nozioni primitive di “numero”, “zero” e “successivo”» — Giovanni Prodi, Analisi Matematica (p. 47)
[^7]: [block_pk=13566 | block_uid=blk_272f532d1899e1322a58] «Eppure AB è di lunghezza doppia di DE» — Attilio Frajese, Introduzione elementare alla matematica moderna (p. 90)
