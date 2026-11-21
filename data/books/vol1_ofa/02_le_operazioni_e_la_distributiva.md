---
tipo: capitolo_libro
id: vol1_ofa.cap02
volume: vol1_ofa
capitolo: 2
titolo: Le operazioni fondamentali, il resto euclideo e la proprietà distributiva
sottotitolo: Dal riunire e sottrarre alla geometria delle aree e alla divisione con
  resto
nodi_coperti:
- operazioni.addizione
- operazioni.sottrazione
- operazioni.colonna
- operazioni.moltiplicazione
- operazioni.distributiva
- operazioni.divisione
drill_keys:
- drill_addition_properties
- drill_subtraction_inverse
- drill_column_carry
- drill_multiplication_grid
- drill_distributive_law
- drill_euclidean_division
stato: pubblicato
aggiornato: '2026-11-19'
fonti:
- block_pk: 13525
  block_uid: blk_bb0b6b4d1825d067e884
  citazione: La proprietà distributiva della moltiplicazione rispetto all' addizione
    verrà di nuovo ricordata
- block_pk: 58978
  block_uid: blk_9078349b6485924ef13e
  citazione: 'La sottrazione coincide con la somma con l''opposto: -j- - = (-j)- Per
    la divisione, si ha -j-l-j = H numero è'
- block_pk: 2884
  block_uid: blk_d222e8181ad20381892c
  citazione: Boole perviene così a determinare le tre seguenti proprietà di quelli
    che chiama "simboli elettivi"
- block_pk: 117557
  block_uid: blk_3485a4d803af2164fb1f
  citazione: Se si divide a caso una linea retta, il quadrato di tutta la retta e
    quello di una delle parti, presi ambedue
- block_pk: 53504
  block_uid: blk_47815d84a11ecefdc0af
  citazione: Moltiplicando (o dividendo) i due termini della divisione per uno stesso
    numero diverso da zero, il quoziente non muta
---

# Capitolo 2 — Le operazioni fondamentali, il resto euclideo e la proprietà distributiva

*Dal riunire e sottrarre alla geometria delle aree e alla divisione con resto*

> *«La proprietà distributiva della moltiplicazione rispetto all' addizione verrà di nuovo ricordata»* — Attilio Frajese, Introduzione elementare alla matematica moderna (1968, Le Monnier) (p. 49) [^1]

## L'addizione, la sottrazione e l'asimmetria del calcolo

L'atto originario del pensiero matematico risiede nel riunire collezioni di oggetti discreti, un'operazione fisica che l'aritmetica astrae nel concetto di addizione. Quando sommiamo due quantità naturali, stiamo postulando l'esistenza di un'operazione binaria che gode di simmetrie profonde. La proprietà commutativa, $a + b = b + a$, garantisce che l'ordine in cui i gruppi vengono fusi non altera il totale. La proprietà associativa, $(a + b) + c = a + (b + c)$, assicura che le aggregazioni intermedie sono ininfluenti sul risultato finale. Queste due leggi, apparentemente ovvie nell'esperienza quotidiana, costituiscono l'ossatura formale su cui si regge l'intera algebra elementare.

La sottrazione nasce come processo inverso: sottrarre significa determinare quale quantità deve essere aggiunta a una parte per ricostruire il tutto. Tuttavia, a differenza dell'addizione, la sottrazione è un'operazione intrinsecamente asimmetrica e priva di associatività. Se consideriamo l'espressione $(12 - 8) - 5$, il risultato è $-1$; se invece calcoliamo $12 - (8 - 5)$, otteniamo $9$. La differenza tra i due risultati evidenzia come la posizione delle parentesi alteri radicalmente il valore dell'espressione. Per ricondurre questa operazione ribelle all'interno di un quadro algebrico coerente, è necessario un salto concettuale verso i numeri relativi. Come osserva Fabio Bellissima nei suoi fondamenti, la sottrazione coincide strutturalmente con la somma con l'opposto, potendosi formalizzare come $a - b = a + (-b)$, mentre per la divisione vale un principio analogo moltiplicando per il reciproco [^2]. Questa riformulazione elimina l'asimmetria, permettendo di applicare le rassicuranti proprietà dell'addizione anche quando si calcolano le differenze.

## La moltiplicazione e la geometria delle aree

Se l'addizione modella l'unione di insiemi disgiunti, la moltiplicazione nei numeri naturali nasce come addizione ripetuta, ma trova la sua espressione più potente e visiva nella geometria delle aree. Moltiplicare $m$ per $n$ equivale a contare gli elementi di uno schieramento rettangolare composto da $m$ righe e $n$ colonne. Questa interpretazione bidimensionale rende immediatamente evidente la proprietà commutativa della moltiplicazione: ruotando il rettangolo di novanta gradi, le righe diventano colonne e viceversa, ma il numero totale di elementi, l'area, rimane invariato, per cui $m \cdot n = n \cdot m$.

Il ponte cruciale tra l'addizione e la moltiplicazione è fornito dalla proprietà distributiva. Geometricamente, calcolare $a(b + c)$ significa determinare l'area di un rettangolo di altezza $a$ e base $(b + c)$. Tagliando verticalmente questo rettangolo in corrispondenza della giunzione tra i segmenti $b$ e $c$, si ottengono due rettangoli più piccoli di aree $ab$ e $ac$. L'equivalenza $a(b + c) = ab + ac$ non è dunque un mero artificio simbolico, ma la traduzione algebrica del principio di additività delle aree. Attilio Frajese sottolinea come la proprietà distributiva della moltiplicazione rispetto all'addizione sia un cardine teorico che verrà costantemente richiamato nell'estensione del concetto di numero e nella costruzione delle strutture algebriche superiori [^1].

L'importanza di questa legge trascende l'aritmetica elementare per diventare un assioma fondativo in contesti formali astratti. Quando George Boole gettò le basi dell'algebra della logica, individuò proprio nella proprietà distributiva, espressa nella forma $x(u + v) = xu + xv$, una delle tre leggi fondamentali per i suoi simboli elettivi, dimostrando come le regole del calcolo quantitativo potessero governare anche le operazioni sui concetti e sugli insiemi [^3].

![Interpretazione geometrica della proprietà distributiva a(b + c) = ab + ac come scomposizione di rettangoli.](../assets/vol1_ofa_02_area_distributive_grid.svg)
*Interpretazione geometrica della proprietà distributiva a(b + c) = ab + ac come scomposizione di rettangoli.*

## Il quadrato del binomio e l'eredità di Euclide

L'applicazione iterata della proprietà distributiva permette di risolvere il problema della moltiplicazione di due somme, e in particolare il calcolo del quadrato di un binomio, $(a + b)^2$. Un errore cognitivo frequente consiste nel distribuire l'esponente sui singoli addendi, assumendo erroneamente che $(a + b)^2$ equivalga ad $a^2 + b^2$. Per comprendere la fallacia di questo ragionamento, è sufficiente ricorrere a un controesempio numerico: se poniamo $a = 7$ e $b = 7$, il quadrato della somma è $(7 + 7)^2 = 14^2 = 196$. Calcolando invece la somma dei quadrati, otteniamo $7^2 + 7^2 = 49 + 49 = 98$. La differenza tra il risultato corretto e quello errato è esattamente $98$.

Da dove deriva questa differenza? Sviluppando rigorosamente il prodotto $(a + b)(a + b)$ tramite la legge distributiva, si ottiene $a(a + b) + b(a + b) = a^2 + ab + ba + b^2$. Poiché la moltiplicazione è commutativa, $ab = ba$, da cui la formula finale $a^2 + 2ab + b^2$. Il termine $2ab$ rappresenta esattamente la quantità mancante nel calcolo errato precedente: nel caso di $a = 7$ e $b = 7$, il doppio prodotto è $2 \cdot 7 \cdot 7 = 98$.

Questa identità algebrica ha radici antiche e profondamente geometriche. Nel Libro II degli Elementi, Euclide formula le identità algebriche in termini di equivalenza tra aree di quadrati e rettangoli. La Proposizione 7 stabilisce esplicitamente che, dividendo una linea retta in due parti, il quadrato costruito sull'intera retta e quello costruito su una delle parti sono equivalenti al doppio del rettangolo compreso dalla retta intera e dalla parte, unito al quadrato della parte rimanente [^4]. Sebbene il linguaggio euclideo appaia distante dalla notazione simbolica moderna, il rigore logico sottostante è identico: l'algebra moderna non fa che condensare in simboli ciò che i matematici greci dimostravano tracciando figure nella sabbia.

## La divisione euclidea e la proprietà invariantiva

Mentre l'addizione e la moltiplicazione sono operazioni interne all'insieme dei numeri naturali, la sottrazione e la divisione pongono problemi di chiusura. Non sempre è possibile dividere un numero intero per un altro ottenendo un quoziente intero. Per gestire questa limitazione senza uscire dal dominio dei numeri discreti, si introduce la divisione euclidea, o divisione con resto. Dati due numeri naturali $a$ (dividendo) e $b$ (divisore, con $b > 0$), esistono e sono unici due numeri naturali $q$ (quoziente) ed $r$ (resto) tali che $a = bq + r$, con la condizione fondamentale che $0 \le r < b$.

Ad esempio, se vogliamo dividere $63$ per $8$, cerchiamo il massimo multiplo di $8$ che non superi $63$. Poiché $8 \cdot 7 = 56$ e $8 \cdot 8 = 64$, il quoziente è $q = 7$. Il resto si ottiene per sottrazione: $r = 63 - 56 = 7$. La relazione si scrive dunque $63 = 8 \cdot 7 + 7$. La condizione $r < b$ (in questo caso $7 < 8$) garantisce l'unicità della scomposizione, impedendo di fermare il processo di divisione prematuramente.

Quando il resto è pari a zero, la divisione si dice esatta e si entra nel dominio delle frazioni e dei numeri razionali. In questo contesto continuo, emerge una proprietà fondamentale che semplifica enormemente il calcolo algebrico: la proprietà invariantiva. Come precisato nei testi di didattica formale, moltiplicando o dividendo entrambi i termini della divisione per uno stesso numero rigorosamente diverso da zero, il quoziente rimane inalterato [^5]. Questa legge giustifica la semplificazione delle frazioni e la risoluzione delle equazioni di primo grado, confermando ancora una volta come le regole dell'aritmetica elementare costituiscano il substrato logico ineludibile per l'intera architettura matematica.

## Dal ragionamento al simbolo: esempi e verifiche

### Fallimento della proprietà associativa nella sottrazione

Dimostrare, tramite un controesempio numerico, che la sottrazione non gode della proprietà associativa, calcolando la differenza tra le espressioni $(12 - 8) - 5$ e $12 - (8 - 5)$.
1. Calcoliamo la prima espressione risolvendo prima la parentesi tonda: $(12 - 8) = 4$.
2. Sottraiamo il termine esterno: $4 - 5 = -1$.
3. Calcoliamo la seconda espressione risolvendo la sua parentesi tonda: $(8 - 5) = 3$.
4. Sottraiamo questo risultato dal termine iniziale: $12 - 3 = 9$.
5. Confrontiamo i risultati: $-1 \neq 9$. La differenza assoluta tra i due valori è $|-1 - 9| = 10$.

**Conclusione.** L'ordine di esecuzione delle sottrazioni altera il risultato finale. La sottrazione non è associativa.

### Calcolo del quadrato di un binomio e verifica dell'errore di linearità

Calcolare il valore esatto di $(7 + 7)^2$ utilizzando la proprietà distributiva e determinare l'entità dell'errore commesso se si calcolasse erroneamente $7^2 + 7^2$.
1. Calcoliamo il valore esatto sommando prima i termini: $(7 + 7)^2 = 14^2 = 196$.
2. Calcoliamo il valore dell'espressione errata: $7^2 + 7^2 = 49 + 49 = 98$.
3. Calcoliamo la differenza tra il valore esatto e quello errato: $196 - 98 = 98$.
4. Verifichiamo analiticamente l'errore: lo sviluppo corretto è $(a + b)^2 = a^2 + 2ab + b^2$. L'errore corrisponde al termine mancante $2ab$.
5. Sostituendo $a = 7$ e $b = 7$ nel doppio prodotto: $2 \cdot 7 \cdot 7 = 2 \cdot 49 = 98$.

**Conclusione.** L'errore commesso ignorando il doppio prodotto ammonta esattamente a 98, confermando che l'elevamento a potenza non è distributivo rispetto all'addizione.

### Determinazione di quoziente e resto nella divisione euclidea

Determinare il quoziente $q$ e il resto $r$ della divisione euclidea di $63$ per $8$, verificando le condizioni di esistenza.
1. Impostiamo l'equazione della divisione euclidea: $63 = 8 \cdot q + r$, con la condizione $0 \le r < 8$.
2. Cerchiamo il massimo intero $q$ tale che $8 \cdot q \le 63$.
3. Sappiamo che $8 \cdot 7 = 56$ e $8 \cdot 8 = 64$. Pertanto, il quoziente corretto è $q = 7$.
4. Calcoliamo il resto sottraendo il prodotto dal dividendo: $r = 63 - 56 = 7$.
5. Verifichiamo la condizione sul resto: $0 \le 7 < 8$, che risulta soddisfatta.

**Conclusione.** La divisione euclidea di 63 per 8 produce un quoziente di 7 e un resto di 7, esprimibile come la coppia [7, 7].

### Esercizi di verifica attiva
1. Applica le proprietà commutativa e associativa dell'addizione per calcolare mentalmente e in modo rapido la somma $(32 + 59) + 68$.
2. Di quanto sbaglia chi calcola $(7 + 7)^2$ facendo $7^2 + 7^2$? Giustifica il risultato geometricamente.
3. Determina quoziente $q$ e resto $r$ della divisione euclidea di $63$ per $8$, esprimendo il risultato come coppia $[q, r]$.
4. Calcola la distanza assoluta tra i risultati delle espressioni $(12 - 8) - 5$ e $12 - (8 - 5)$ per verificare il fallimento dell'associatività della sottrazione.

## Apparato delle fonti

### [Verificato sul testo]
[^1]: [block_pk=13525 | block_uid=blk_bb0b6b4d1825d067e884] «La proprietà distributiva della moltiplicazione rispetto all' addizione verrà di nuovo ricordata» — Attilio Frajese, Introduzione elementare alla matematica moderna (1968, Le Monnier) (p. 49)
[^2]: [block_pk=58978 | block_uid=blk_9078349b6485924ef13e] «La sottrazione coincide con la somma con l'opposto: -j- - = (-j)- Per la divisione, si ha -j-l-j = H numero è» — Fabio Bellissima, Fondamenti di matematica (2008, Carocci) (p. 7)
[^3]: [block_pk=2884 | block_uid=blk_d222e8181ad20381892c] «Boole perviene così a determinare le tre seguenti proprietà di quelli che chiama "simboli elettivi"» — George Boole, (Universale Bollati Boringhieri, Serie scientifica, 262) George Boole - L'analisi matematica della logica-Bollati Boringhieri (1993) (p. 25)
[^4]: [block_pk=117557 | block_uid=blk_3485a4d803af2164fb1f] «Se si divide a caso una linea retta, il quadrato di tutta la retta e quello di una delle parti, presi ambedue» — Euclide, a cura di Attilio Frajese e Lamberto Maccioni, Elementi (1970, UTET) (p. 173)
[^5]: [block_pk=53504 | block_uid=blk_47815d84a11ecefdc0af] «Moltiplicando (o dividendo) i due termini della divisione per uno stesso numero diverso da zero, il quoziente non muta» — Nella Dodero, Paolo Baroncini, Dante Trezzi, Nuovi elementi di matematica. Vol. 1 1(1996, Ghisetti e Corvi) (p. 65)

### [Ricostruzione matematica / addestramento]
- La citazione di Bellissima (Fonte Q4) presentava gravi difetti di riconoscimento ottico dei caratteri (OCR) nel testo originale del dossier. Per mantenere il rigore formale richiesto da un testo universitario, i glifi corrotti sono stati parafrasati e tradotti nella notazione algebrica standard a - b = a + (-b), preservando fedelmente il significato matematico dell'autore senza introdurre stringhe prive di senso.
- Per garantire la massima coerenza interna tra la teoria esposta e la pratica attiva, i valori numerici utilizzati nell'esempio del quadrato del binomio sono stati uniformati a a=7 e b=7. Questo allinea perfettamente il testo discorsivo con l'esercizio di verifica corrispondente, eliminando le discrepanze numeriche segnalate in fase di revisione.
- L'interpretazione geometrica della proprietà distributiva è stata esplicitamente collegata alla Proposizione 7 del Libro II degli Elementi di Euclide, per mostrare la continuità storica tra l'algebra geometrica antica e il calcolo simbolico moderno, evitando salti logici nella derivazione delle formule.
- Diagramma geometrico-simbolico controllato (`area_distributive_grid`): Interpretazione geometrica della proprietà distributiva a(b + c) = ab + ac come scomposizione di rettangoli.

### [Esercizi originali]
- Applica le proprietà commutativa e associativa dell'addizione per calcolare mentalmente e in modo rapido la somma $(32 + 59) + 68$. — *Traccia di verifica:* Riordinando i termini tramite la proprietà commutativa si ottiene $(32 + 68) + 59$. La somma in parentesi dà $100$, a cui si aggiunge $59$ per un totale di $159$.
- Di quanto sbaglia chi calcola $(7 + 7)^2$ facendo $7^2 + 7^2$? Giustifica il risultato geometricamente. — *Traccia di verifica:* Il calcolo errato dà $98$, mentre quello corretto dà $196$. L'errore è di $98$, che geometricamente corrisponde all'area dei due rettangoli misti di lati $7$ e $7$ (il doppio prodotto $2ab$) omessi nel calcolo.
- Determina quoziente $q$ e resto $r$ della divisione euclidea di $63$ per $8$, esprimendo il risultato come coppia $[q, r]$. — *Traccia di verifica:* Poiché $63 = 8 \cdot 7 + 7$ e il resto $7$ è strettamente minore del divisore $8$, la coppia cercata è $[7, 7]$.
- Calcola la distanza assoluta tra i risultati delle espressioni $(12 - 8) - 5$ e $12 - (8 - 5)$ per verificare il fallimento dell'associatività della sottrazione. — *Traccia di verifica:* La prima espressione vale $4 - 5 = -1$. La seconda vale $12 - 3 = 9$. La distanza assoluta tra $-1$ e $9$ è $10$.
- **Palestra simbolica (`drill_addition_properties`):** Applica le proprietà commutativa e associativa per calcolare rapidamente (32 + 59) + 68. *(Risposta verificata: `159`)*
- **Palestra simbolica (`drill_subtraction_inverse`):** [Che cosa si rompe] Calcola la distanza tra (12 - 8) - 5 e 12 - (8 - 5) per verificare il fallimento dell'associatività. *(Risposta verificata: `10`)*
- **Palestra simbolica (`drill_column_carry`):** Esegui l'addizione posizionale con riporto in base 10: 480 + 372. *(Risposta verificata: `852`)*
- **Palestra simbolica (`drill_multiplication_grid`):** Uno schieramento rettangolare ha 10 righe e 11 colonne: quanti elementi contiene? *(Risposta verificata: `110`)*
- **Palestra simbolica (`drill_distributive_law`):** [Che cosa si rompe] Di quanto sbaglia chi calcola (7 + 7)^2 facendo 7^2 + 7^2? *(Risposta verificata: `98`)*
- **Palestra simbolica (`drill_euclidean_division`):** Determina quoziente q e resto r della divisione euclidea di 63 per 8 (risposta come coppia [q, r] con 0 <= r < 8). *(Risposta verificata: `[7, 7]`)*
