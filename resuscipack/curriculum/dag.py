"""DAG Curricolare Unificato Aciclico a 4 Strati per SecAI (L-31, UniMi).

Unisce in un unico grafo aciclico verificato:
- Strato 0 (64 nodi): Fondamenta scolastiche 1ª elementare -> 5ª superiore ("Decisioni di Progetto" in 3 rami)
- Strato 1 (11 unità): Bonifica OFA & Pre-Immatricolazione (`P0.1..P0.8`, `P1.1..P1.2`, `P6.1`)
- Strato 2 (12 unità): Ponti Anti-Baratro per i 20 Shadow Gates (`P2..P5`, `P6.2`, incl. Prob/Stat 0 CFU)
- Strato 3 (21 gate): Esami e Attività Ufficiali SecAI (`G00..G20`, 180 CFU, Manifesto FAOof1_2027)
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

DEFAULT_CURRICULUM_DIR = Path(__file__).resolve().parents[2] / "data" / "curriculum"
DEFAULT_DAG_PATH = DEFAULT_CURRICULUM_DIR / "secai_unified_dag.json"
DEFAULT_OPEN_ACCESS_PATH = DEFAULT_CURRICULUM_DIR / "open_access_textbooks.json"

CANONICAL_OP_TAGS = {
    "BOUNDED_TOLERANCE",
    "SIGNED_DEVIATION_FEEDBACK",
    "LATENT_STATE_SENSING",
    "ANGULAR_GEOMETRY_PROJECTION",
    "SERIES_CONJUNCTION_GATE",
    "PARALLEL_DISJUNCTION_PATH",
    "VARIABLE_ISOLATION_CONTROL",
    "HIDDEN_CONFOUNDER",
    "COMBINATORIAL_GRID_PATTERN",
    "CONSTRAINED_SEARCH_DECODING",
    "ORDER_OF_MAGNITUDE_BOUND",
    "PROPORTIONAL_SCALING",
    "RATE_OF_CHANGE",
    "ACCUMULATION_INTEGRATION",
    "INVARIANT_PRESERVATION",
    "BIJECTION_EQUINUMEROSITY",
    "RECURSIVE_SELF_SIMILARITY",
    "CONTRADICTION_REDUCTIO",
    "MODULAR_PERIODICITY",
    "PROBABILITY_BAYESIAN_UPDATE",
    "SIGNAL_TRANSDUCTION_ECHO",
    "BOTTLENECK_CAPACITY",
    "ADVERSARIAL_DECEPTION",
    "THRESHOLD_PHASE_TRANSITION",
}


def _layer0_nodes() -> list[dict[str, Any]]:
    raw = [
        # --- RAMO 1: NUMERI E OPERAZIONI (21 nodi) ---
        (
            "numeri.quantita",
            "Contare e il numero come quantità",
            "numeri-e-operazioni",
            "1ª elementare",
            [],
            "Un numero indica quanti oggetti ci sono indipendentemente dall'ordine di conteggio (corrispondenza biunivoca).",
            ["BIJECTION_EQUINUMEROSITY", "INVARIANT_PRESERVATION"],
            "Stabilire se due collezioni finite hanno la stessa numerosità accoppiando elementi uno a uno senza contare.",
            "drill_counting_bijection",
        ),
        (
            "numeri.ordine",
            "Confrontare e ordinare i numeri",
            "numeri-e-operazioni",
            "1ª elementare",
            ["numeri.quantita"],
            "Ogni naturale ha un successivo e i numeri si dispongono in fila sulla retta: maggiore significa più a destra.",
            ["BIJECTION_EQUINUMEROSITY", "ORDER_OF_MAGNITUDE_BOUND"],
            "Ordinare grandezze lungo una successione discreta dotata di minimo e operatore successivo.",
            "drill_number_order",
        ),
        (
            "numeri.posizionale",
            "Sistema posizionale decimale e zero",
            "numeri-e-operazioni",
            "1ª-2ª elementare",
            ["numeri.quantita"],
            "Il valore di una cifra dipende dalla posizione (potenze di 10) e lo zero tiene il posto vuoto.",
            ["COMBINATORIAL_GRID_PATTERN", "ORDER_OF_MAGNITUDE_BOUND"],
            "Rappresentare quantità arbitrarie con un alfabeto finito di simboli usando pesi di posizione e segnaposto vuoto.",
            "drill_positional_value",
        ),
        (
            "operazioni.addizione",
            "Addizione come riunire",
            "numeri-e-operazioni",
            "1ª elementare",
            ["numeri.quantita", "numeri.ordine"],
            "Addizionare riunisce due insiemi disgiunti; ordine e raggruppamento non alterano la somma (commutativa, associativa, 0 neutro).",
            ["INVARIANT_PRESERVATION", "ACCUMULATION_INTEGRATION"],
            "Comporre due quantità prive di elementi comuni in modo indipendente dall'ordine di aggregazione.",
            "drill_addition_properties",
        ),
        (
            "operazioni.sottrazione",
            "Sottrazione come togliere e come differenza",
            "numeri-e-operazioni",
            "1ª elementare",
            ["operazioni.addizione"],
            "Sottrarre è l'operazione inversa dell'addizione (a - b = c sse c + b = a); in N richiede a >= b.",
            ["SIGNED_DEVIATION_FEEDBACK", "BOUNDED_TOLERANCE"],
            "Determinare lo scarto mancante per raggiungere un totale dato e riconoscere quando l'operazione esce dai naturali.",
            "drill_subtraction_inverse",
        ),
        (
            "operazioni.colonna",
            "Addizione e sottrazione in colonna",
            "numeri-e-operazioni",
            "2ª elementare",
            ["numeri.posizionale", "operazioni.addizione", "operazioni.sottrazione"],
            "Riporto e prestito discendono dal cambio 10 unità = 1 decina nel sistema posizionale.",
            ["INVARIANT_PRESERVATION", "MODULAR_PERIODICITY"],
            "Scomporre un calcolo globale in passi locali per colonna propagando il riporto alla posizione superiore.",
            "drill_column_carry",
        ),
        (
            "operazioni.moltiplicazione",
            "Moltiplicazione come addizione ripetuta e schieramento",
            "numeri-e-operazioni",
            "2ª elementare",
            ["operazioni.addizione"],
            "a × b conta uno schieramento rettangolare a per b: ruotandolo di 90° appare subito perché a × b = b × a.",
            ["COMBINATORIAL_GRID_PATTERN", "PROPORTIONAL_SCALING"],
            "Contare gli elementi di una griglia regolare bidimensionale tramite il prodotto di righe e colonne.",
            "drill_multiplication_grid",
        ),
        (
            "operazioni.distributiva",
            "Proprietà distributiva",
            "numeri-e-operazioni",
            "3ª elementare",
            ["operazioni.moltiplicazione", "operazioni.addizione"],
            "a × (b + c) = a × b + a × c: spezzare uno schieramento collega somma e prodotto e fonderà il calcolo letterale e le frazioni.",
            ["INVARIANT_PRESERVATION", "COMBINATORIAL_GRID_PATTERN"],
            "Spezzare un prodotto complesso nella somma di parti calcolabili separatamente conservando il totale.",
            "drill_distributive_law",
        ),
        (
            "operazioni.divisione",
            "Divisione come ripartire e contenere, e il resto",
            "numeri-e-operazioni",
            "3ª elementare",
            ["operazioni.moltiplicazione", "operazioni.sottrazione"],
            "a = b·q + r con 0 <= r < b (b != 0): la divisione euclidea separa la quota intera dal resto indivisibile in N.",
            ["MODULAR_PERIODICITY", "BOUNDED_TOLERANCE"],
            "Ripartire una quantità discreta in quote uguali isolando un resto strettamente minore del divisore.",
            "drill_euclidean_division",
        ),
        (
            "frazioni.significato",
            "La frazione come parti uguali di un intero",
            "numeri-e-operazioni",
            "3ª elementare",
            ["operazioni.divisione"],
            "m/n indica m copie dell'unità frazionaria 1/n ottenuta dividendo l'intero in n parti esattamente uguali.",
            ["PROPORTIONAL_SCALING", "INVARIANT_PRESERVATION"],
            "Suddividere un'unità continua in parti equipotenti per misurare grandezze non intere.",
            "drill_fraction_meaning",
        ),
        (
            "frazioni.equivalenza",
            "Frazioni equivalenti",
            "numeri-e-operazioni",
            "4ª elementare",
            ["frazioni.significato", "operazioni.moltiplicazione"],
            "(m·k)/(n·k) = m/n per k != 0: infiniti simboli diversi rappresentano lo stesso numero razionale.",
            ["INVARIANT_PRESERVATION", "PROPORTIONAL_SCALING"],
            "Raffinare la scala di suddivisione senza alterare la grandezza rappresentata.",
            "drill_fraction_equivalence",
        ),
        (
            "frazioni.denominatore-comune",
            "Somma di frazioni con il denominatore comune",
            "numeri-e-operazioni",
            "5ª elementare",
            ["frazioni.significato", "frazioni.equivalenza", "operazioni.distributiva"],
            "a/b + c/d = (ad + cb)/(bd): si sommano solo pezzi della stessa taglia per preservare la proprietà distributiva.",
            ["INVARIANT_PRESERVATION", "PROPORTIONAL_SCALING"],
            "Ridurre grandezze espresse in unità diverse a una sottomisura comune prima di sommarle.",
            "drill_fraction_addition",
        ),
        (
            "frazioni.moltiplicazione-divisione",
            "Moltiplicazione, reciproco e divisione tra frazioni",
            "numeri-e-operazioni",
            "1ª media",
            ["frazioni.equivalenza", "operazioni.divisione"],
            "(a/b)·(c/d) = (ac)/(bd) e dividere per c/d equivale a moltiplicare per il reciproco d/c (c != 0).",
            ["PROPORTIONAL_SCALING", "INVARIANT_PRESERVATION"],
            "Comporre due fattori di scala frazionari e invertire una trasformazione moltiplicativa tramite il reciproco.",
            "drill_fraction_mul_div",
        ),
        (
            "numeri.decimali",
            "Numeri decimali e approssimazione",
            "numeri-e-operazioni",
            "4ª-5ª elementare",
            ["numeri.posizionale", "operazioni.colonna", "frazioni.equivalenza"],
            "I decimali estendono i pesi posizionali a destra della virgola (1/10, 1/100...); non tutte le frazioni terminano in base 10.",
            ["BOUNDED_TOLERANCE", "ORDER_OF_MAGNITUDE_BOUND"],
            "Approssimare un rapporto razionale su griglia decimale controllando l'errore di troncamento.",
            "drill_decimals",
        ),
        (
            "divisibilita.multipli-primi",
            "Divisibilità, numeri primi e fattorizzazione unica",
            "numeri-e-operazioni",
            "1ª media",
            ["operazioni.moltiplicazione", "operazioni.divisione"],
            "Ogni intero > 1 si scompone in modo unico nel prodotto di numeri primi (mattoni moltiplicativi indivisibili).",
            ["CONSTRAINED_SEARCH_DECODING", "MODULAR_PERIODICITY"],
            "Scomporre un intero nei suoi fattori primi irriducibili verificando l'unicità della firma moltiplicativa.",
            "drill_prime_factorization",
        ),
        (
            "divisibilita.mcm",
            "Minimo comune multiplo (mcm)",
            "numeri-e-operazioni",
            "1ª media",
            ["divisibilita.multipli-primi"],
            "Il mcm sceglie la griglia comune più economica per sincronizzare cicli periodici o sommare frazioni.",
            ["MODULAR_PERIODICITY", "BOTTLENECK_CAPACITY"],
            "Trovare il primo istante di coincidenza tra due fenomeni periodici di periodo diverso.",
            "drill_lcm",
        ),
        (
            "divisibilita.mcd",
            "Massimo comune divisore (MCD) e frazioni irriducibili",
            "numeri-e-operazioni",
            "1ª media",
            ["divisibilita.multipli-primi"],
            "Il MCD (calcolabile anche coi resti di Euclide) dà il passo massimo comune e riduce a/b ai minimi termini.",
            ["MODULAR_PERIODICITY", "RECURSIVE_SELF_SIMILARITY"],
            "Determinare la massima unità di misura comune che divide esattamente due grandezze senza resto.",
            "drill_gcd",
        ),
        (
            "numeri.relativi",
            "Numeri interi relativi (Z) e regola dei segni",
            "numeri-e-operazioni",
            "3ª media",
            ["operazioni.sottrazione", "numeri.ordine"],
            "I negativi rendono sempre possibile la sottrazione; (-1)(-1) = +1 è imposto dal voler conservare la proprietà distributiva.",
            ["SIGNED_DEVIATION_FEEDBACK", "INVARIANT_PRESERVATION"],
            "Rappresentare scostamenti orientati rispetto a uno zero centrale preservando le leggi dell'algebra.",
            "drill_signed_integers",
        ),
        (
            "operazioni.potenze-base",
            "Potenze e proprietà degli esponenti",
            "numeri-e-operazioni",
            "1ª-3ª media",
            ["operazioni.moltiplicazione", "numeri.relativi"],
            "a^m · a^n = a^(m+n) trasforma prodotti in somme di esponenti, imponendo a^0 = 1 e a^(-n) = 1/a^n.",
            ["ORDER_OF_MAGNITUDE_BOUND", "PROPORTIONAL_SCALING"],
            "Modellare crescite moltiplicative ripetute e scale di grandezza tramite aritmetica sugli esponenti.",
            "drill_exponent_rules",
        ),
        (
            "operazioni.radici-base",
            "Radice quadrata ed estrazione inversa della potenza",
            "numeri-e-operazioni",
            "2ª media",
            ["operazioni.potenze-base", "frazioni.moltiplicazione-divisione"],
            "sqrt(a) (per a >= 0) è il lato positivo del quadrato di area a; per molti interi non è né intero né frazione.",
            ["CONTRADICTION_REDUCTIO", "BOUNDED_TOLERANCE"],
            "Risalire dal quadrato al lato accorgendosi che i razionali presentano buchi geometrici (incommensurabilità).",
            "drill_square_roots",
        ),
        (
            "rapporti.proporzioni-percentuali",
            "Rapporti, proporzioni e percentuali",
            "numeri-e-operazioni",
            "2ª media",
            ["frazioni.moltiplicazione-divisione", "numeri.decimali"],
            "a : b = c : d equivale a a·d = b·c: confronta grandezze per quoziente anziché per differenza assoluta.",
            ["PROPORTIONAL_SCALING", "INVARIANT_PRESERVATION"],
            "Mantenere invariato il rapporto relativo tra due grandezze al variare della scala assoluta.",
            "drill_proportions_percent",
        ),
        # --- RAMO 2: SPAZIO, MISURE E FIGURE (14 nodi) ---
        (
            "misure.confronto-unita",
            "Misurare: scegliere un'unità campione",
            "spazio-misure-figure",
            "1ª-2ª elementare",
            ["numeri.quantita", "numeri.ordine"],
            "Misurare traduce una grandezza continua in numero contando quante volte vi entra un campione scelto per convenzione.",
            ["PROPORTIONAL_SCALING", "BOUNDED_TOLERANCE"],
            "Rendere confrontabili grandezze fisiche continue riferendole a un campione riproducibile.",
            "drill_unit_measurement",
        ),
        (
            "misure.equivalenze-decimali",
            "Sistema metrico decimale ed equivalenze",
            "spazio-misure-figure",
            "4ª elementare",
            ["misure.confronto-unita", "numeri.decimali"],
            "Legare i multipli dell'unità alle potenze di 10 riduce i cambi di unità a semplici scorrimenti della virgola.",
            ["ORDER_OF_MAGNITUDE_BOUND", "PROPORTIONAL_SCALING"],
            "Convertire misure tra scale diverse moltiplicando o dividendo per potenze della base.",
            "drill_metric_conversions",
        ),
        (
            "geometria.punti-rette-segmenti",
            "Punti, rette, segmenti e distanza minima",
            "spazio-misure-figure",
            "2ª-3ª elementare",
            ["misure.confronto-unita"],
            "Il segmento formalizza il filo teso tra due punti (cammino di lunghezza minima nel piano euclideo).",
            ["ANGULAR_GEOMETRY_PROJECTION", "BOUNDED_TOLERANCE"],
            "Idealizzare traiettorie rettilinee e distanze tra posizioni prive di estensione.",
            "drill_segments_length",
        ),
        (
            "geometria.angoli-rotazioni",
            "Angolo come cambio di direzione e rotazione",
            "spazio-misure-figure",
            "3ª-4ª elementare",
            ["geometria.punti-rette-segmenti"],
            "L'angolo misura l'ampiezza di rotazione tra due semirette, non la lunghezza dei loro lati.",
            ["ANGULAR_GEOMETRY_PROJECTION", "MODULAR_PERIODICITY"],
            "Quantificare una deviazione direzionale periodica indipendentemente dalla distanza percorsa.",
            "drill_angles_degrees",
        ),
        (
            "geometria.parallelismo-perpendicolarita",
            "Rette parallele, perpendicolari e distanza punto-retta",
            "spazio-misure-figure",
            "4ª elementare",
            ["geometria.angoli-rotazioni"],
            "La distanza da una retta si misura lungo la perpendicolare (proiezione ortogonale = cammino più corto).",
            ["ANGULAR_GEOMETRY_PROJECTION", "INVARIANT_PRESERVATION"],
            "Proiettare ortogonalmente un punto su un asse per misurare lo scostamento trasversale minimo.",
            "drill_perpendicular_angles",
        ),
        (
            "geometria.poligoni-perimetro",
            "Poligoni, triangoli e disuguaglianza triangolare",
            "spazio-misure-figure",
            "3ª-4ª elementare",
            ["geometria.punti-rette-segmenti", "operazioni.addizione"],
            "Tre segmenti chiudono un triangolo solo se ciascuno è minore della somma degli altri due (a < b + c).",
            ["BOUNDED_TOLERANCE", "ANGULAR_GEOMETRY_PROJECTION"],
            "Verificare le condizioni di chiusura geometrica e rigidità di una figura piana a lati rettilinei.",
            "drill_triangle_perimeter",
        ),
        (
            "geometria.area-rettangolo-schieramento",
            "Area del rettangolo e unità quadrate",
            "spazio-misure-figure",
            "4ª elementare",
            ["geometria.poligoni-perimetro", "operazioni.moltiplicazione"],
            "Area = base × altezza estende lo schieramento discreto al continuo, separando superficie da contorno (perimetro).",
            ["ACCUMULATION_INTEGRATION", "COMBINATORIAL_GRID_PATTERN"],
            "Distinguere estensione superficiale ed estensione lineare mostrando rettangoli isoperimetrici di area diversa.",
            "drill_rectangle_area",
        ),
        (
            "geometria.area-triangolo-poligoni",
            "Equiscomponibilità e area di triangoli e poligoni",
            "spazio-misure-figure",
            "5ª elementare",
            ["geometria.area-rettangolo-schieramento", "frazioni.significato"],
            "Ogni triangolo è metà di un parallelogramma di uguale base e altezza: A = (b · h) / 2 per taglio e ricomposizione.",
            ["INVARIANT_PRESERVATION", "ACCUMULATION_INTEGRATION"],
            "Ricondurre una figura ignota a una nota per dissezione conservando l'area totale.",
            "drill_triangle_area",
        ),
        (
            "geometria.simmetrie-traslazioni",
            "Isometrie: traslazioni, rotazioni e simmetrie",
            "spazio-misure-figure",
            "4ª-5ª elementare",
            ["geometria.parallelismo-perpendicolarita"],
            "Due figure sono congruenti se un movimento rigido (che conserva distanze e angoli) sovrappone l'una all'altra.",
            ["INVARIANT_PRESERVATION", "ANGULAR_GEOMETRY_PROJECTION"],
            "Riconoscere quali proprietà restano invarianti quando un oggetto viene spostato o ribaltato nello spazio.",
            "drill_translation_coords",
        ),
        (
            "geometria.pitagora",
            "Teorema di Pitagora e distanza euclidea",
            "spazio-misure-figure",
            "2ª media",
            ["geometria.area-triangolo-poligoni", "operazioni.radici-base"],
            "a^2 + b^2 = c^2 vale se e solo se il triangolo è rettangolo: lega angolo retto e calcolo delle distanze (es. orizzonte ottico).",
            ["ANGULAR_GEOMETRY_PROJECTION", "INVARIANT_PRESERVATION"],
            "Calcolare una distanza obliqua inaccessibile componendo due spostamenti ortogonali misurabili.",
            "drill_pythagoras",
        ),
        (
            "geometria.cerchio-pi-greco",
            "Circonferenza, cerchio e la costante pi greco",
            "spazio-misure-figure",
            "5ª elem - 3ª media",
            ["geometria.poligoni-perimetro", "rapporti.proporzioni-percentuali"],
            "Il rapporto C / d = π è costante per tutti i cerchi; l'area πr^2 emerge affettando il cerchio in settori sempre più fini.",
            ["PROPORTIONAL_SCALING", "ACCUMULATION_INTEGRATION"],
            "Approssimare curve continue tramite poligoni inscritti e circoscritti scoprendo un rapporto universale.",
            "drill_circle_pi",
        ),
        (
            "geometria.similitudine-scala",
            "Figure simili, riduzioni in scala e teorema di Talete",
            "spazio-misure-figure",
            "2ª media",
            ["geometria.angoli-rotazioni", "rapporti.proporzioni-percentuali"],
            "Scalare i lati di un fattore k lascia invariati gli angoli ma moltiplica le aree per k^2 (seme della trigonometria).",
            ["PROPORTIONAL_SCALING", "ANGULAR_GEOMETRY_PROJECTION"],
            "Misurare indirettamente altezze o distanze lontane sfruttando triangoli con gli stessi angoli.",
            "drill_similarity_scale",
        ),
        (
            "geometria.solidi-volume",
            "Solidi nello spazio, volume e principio delle fette",
            "spazio-misure-figure",
            "3ª media",
            ["geometria.area-rettangolo-schieramento", "operazioni.potenze-base"],
            "Volume = Area_base × altezza; scalare le lunghezze di k moltiplica i volumi per k^3 (ponte verso gli indivisibili di Cavalieri).",
            ["ACCUMULATION_INTEGRATION", "PROPORTIONAL_SCALING"],
            "Calcolare la capacità tridimensionale impilando sezioni piane parallele.",
            "drill_volume_scaling",
        ),
        (
            "geometria.coordinate-griglia",
            "Piano cartesiano: punti e distanze come coppie di numeri",
            "spazio-misure-figure",
            "5ª elem - 3ª media",
            ["numeri.relativi", "geometria.parallelismo-perpendicolarita"],
            "Fissati due assi orientati ortogonali, ogni punto diventa una coppia ordinata (x, y): la geometria diventa algebra.",
            ["ANGULAR_GEOMETRY_PROJECTION", "COMBINATORIAL_GRID_PATTERN"],
            "Localizzare univocamente posizioni e traiettorie nel piano tramite due scostamenti con segno dagli assi.",
            "drill_cartesian_points",
        ),
        # --- RAMO 3: RELAZIONI, LOGICA E DATI (10 nodi) ---
        (
            "logica.classificare-attributi",
            "Classificare oggetti per attributi (insiemi intuitivi)",
            "relazioni-logica-dati",
            "1ª elementare",
            ["numeri.quantita"],
            "Un insieme ben definito richiede un criterio oggettivo che decida senza ambiguità se un oggetto appartiene o no.",
            ["VARIABLE_ISOLATION_CONTROL", "THRESHOLD_PHASE_TRANSITION"],
            "Ripartire elementi in classi disgiunte o sovrapposte in base a proprietà osservabili verificabili.",
            "drill_set_classification",
        ),
        (
            "logica.vero-falso-non-e-o",
            "Enunciati vero/falso e connettivi NON, E, O",
            "relazioni-logica-dati",
            "2ª-3ª elementare",
            ["logica.classificare-attributi"],
            "In matematica 'O' (OR) significa 'almeno uno dei due' (inclusivo), mentre 'E' (AND) richiede entrambe le condizioni vere.",
            ["SERIES_CONJUNCTION_GATE", "PARALLEL_DISJUNCTION_PATH"],
            "Combinare condizioni elementari binarie in catene in serie (AND) o in parallelo (OR).",
            "drill_boolean_basics",
        ),
        (
            "logica.tutti-qualcuno-controesempio",
            "Tutti, esiste almeno uno, e la forza del controesempio",
            "relazioni-logica-dati",
            "4ª-5ª elementare",
            ["logica.vero-falso-non-e-o"],
            "Mille esempi favorevoli non dimostrano 'per ogni', ma basta UN solo controesempio per demolirlo.",
            ["CONTRADICTION_REDUCTIO", "CONSTRAINED_SEARCH_DECODING"],
            "Confutare una regola universale esibendo un singolo caso che rispetta l'ipotesi ma viola la tesi.",
            "drill_counterexample",
        ),
        (
            "relazioni.uguaglianza-bilancia",
            "Il segno '=' come equilibrio di bilancia (non 'fa')",
            "relazioni-logica-dati",
            "1ª-2ª elementare",
            ["operazioni.addizione", "operazioni.sottrazione"],
            "'=' non significa 'premi invio e scrivi il risultato', ma che i due lati pesano uguale e restano uguali operando allo stesso modo su entrambi.",
            ["INVARIANT_PRESERVATION", "SIGNED_DEVIATION_FEEDBACK"],
            "Conservare un'uguaglianza applicando trasformazioni identiche e invertibili ad ambo i membri.",
            "drill_equality_balance",
        ),
        (
            "relazioni.sequenze-regole",
            "Sequenze, regolarità e passi ricorsivi",
            "relazioni-logica-dati",
            "2ª-3ª elementare",
            ["numeri.ordine", "operazioni.addizione"],
            "Una successione può essere descritta passo-passo (da un termine al successivo) oppure con una formula chiusa sul posto n.",
            ["RECURSIVE_SELF_SIMILARITY", "RATE_OF_CHANGE"],
            "Individuare la legge d'invarianza che genera una sequenza e prevedere il termine n-esimo.",
            "drill_sequence_pattern",
        ),
        (
            "relazioni.lettere-formule",
            "Dalle parole alle lettere: variabili ed espressioni letterali",
            "relazioni-logica-dati",
            "1ª-3ª media",
            ["relazioni.uguaglianza-bilancia", "operazioni.distributiva"],
            "Una lettera tiene il posto di un numero generico: permette di dimostrare proprietà per infiniti numeri in un colpo solo.",
            ["INVARIANT_PRESERVATION", "PROPORTIONAL_SCALING"],
            "Tradurre una procedura verbale in espressione simbolica semplificabile con le stesse leggi dell'aritmetica.",
            "drill_literal_expressions",
        ),
        (
            "relazioni.proporzionalita-diretta-inversa",
            "Leggi di proporzionalità diretta (y = kx) e inversa (x·y = k)",
            "relazioni-logica-dati",
            "2ª-3ª media",
            ["rapporti.proporzioni-percentuali", "geometria.coordinate-griglia"],
            "y = kx dà una retta per l'origine (tasso costante); x·y = k dà un ramo di iperbole (prodotto costante).",
            ["PROPORTIONAL_SCALING", "RATE_OF_CHANGE"],
            "Distinguere leggi lineari da leggi inverse osservando come varia il rapporto o il prodotto delle coppie.",
            "drill_direct_inverse_prop",
        ),
        (
            "relazioni.equazione-primo-grado-base",
            "Equazioni lineari: isolare l'incognita disfacendo le operazioni",
            "relazioni-logica-dati",
            "3ª media",
            ["relazioni.lettere-formule", "numeri.relativi"],
            "'Portare di là cambiando segno' non è magia: è sommare l'opposto a entrambi i piatti della bilancia (ax + b = 0 -> x = -b/a per a != 0).",
            ["INVARIANT_PRESERVATION", "CONSTRAINED_SEARCH_DECODING"],
            "Isolare un'incognita invertendo in ordine opposto la catena di operazioni che agisce su di essa.",
            "drill_linear_equation",
        ),
        (
            "dati.tabelle-grafici",
            "Raccogliere dati, frequenze e rappresentazioni grafiche",
            "relazioni-logica-dati",
            "3ª-5ª elementare",
            ["numeri.ordine", "geometria.coordinate-griglia"],
            "Una tabella di frequenze comprime osservazioni grezze rendendo visibili distribuzioni e anomalie.",
            ["VARIABLE_ISOLATION_CONTROL", "ORDER_OF_MAGNITUDE_BOUND"],
            "Organizzare osservazioni empiriche in conteggi assoluti e frequenze relative verificando che sommino a 1.",
            "drill_frequency_table",
        ),
        (
            "dati.media-frequenza-incertezza",
            "Media, moda, mediana e primi passi nell'incertezza",
            "relazioni-logica-dati",
            "5ª elem - 3ª media",
            ["dati.tabelle-grafici", "rapporti.proporzioni-percentuali"],
            "La media è il baricentro (sensibile ai valori estremi), la mediana divide a metà; la probabilità classica conta favorevoli/possibili equiprobabili.",
            ["PROBABILITY_BAYESIAN_UPDATE", "HIDDEN_CONFOUNDER"],
            "Sintetizzare una distribuzione di misure scegliendo un indice robusto agli outlier e stimando casi favorevoli.",
            "drill_mean_median_prob",
        ),
    ]

    nodes = []
    for (
        nid,
        title,
        branch,
        school_grade,
        prereqs,
        decision,
        op_tags,
        archetype,
        drill_key,
    ) in raw:
        nodes.append(
            {
                "id": nid,
                "title": title,
                "layer": 0,
                "layer_label": "Strato 0 · Fondamenta Scolastiche (1ª Elementare → 5ª Superiore)",
                "branch": branch,
                "school_grade": school_grade,
                "estimated_hours": 1.5,
                "prerequisites": prereqs,
                "decision": decision,
                "target_op_tags": op_tags,
                "generator_archetype": archetype,
                "drill_key": drill_key,
                "canonical_domains": ["matematica"],
            }
        )

    high_school_raw = [
        (
            "superiori.polinomi-prodotti-notevoli",
            "Polinomi e prodotti notevoli (geometria dell'algebra)",
            "numeri-e-operazioni",
            "1ª superiore",
            ["relazioni.lettere-formule", "operazioni.potenze-base", "geometria.area-rettangolo-schieramento"],
            "Ogni prodotto notevole — (a+b)^2 = a^2 + 2ab + b^2, a^2 - b^2 = (a-b)(a+b) — è l'identità geometrica di un rettangolo o cubo scomposto per la legge distributiva.",
            ["COMBINATORIAL_GRID_PATTERN", "INVARIANT_PRESERVATION"],
            "Calcolare prodotti e scomposizioni simboliche conservando i termini misti e le aree rettangolari composte.",
            "drill_polynomial_products",
            3.0,
        ),
        (
            "superiori.fattorizzazione-frazioni-algebriche",
            "Scomposizione di polinomi, Ruffini e frazioni algebriche",
            "numeri-e-operazioni",
            "1ª superiore",
            ["superiori.polinomi-prodotti-notevoli", "operazioni.divisione", "frazioni.denominatore-comune"],
            "Un polinomio P(x) è divisibile per (x - r) sse P(r) = 0 (teorema del resto di Ruffini): scomporre trasforma equazioni opache in fattori annullabili sotto condizioni di esistenza esplicite.",
            ["INVARIANT_PRESERVATION", "CONSTRAINED_SEARCH_DECODING"],
            "Dividere ed estrarre radici razionali di polinomi imponendo le condizioni di non annullamento dei denominatori.",
            "drill_polynomial_ruffini",
            3.5,
        ),
        (
            "superiori.geometria-sintetica-congruenza",
            "Geometria euclidea assiomatica: congruenza dei triangoli e rette parallele",
            "spazio-misure-figure",
            "1ª superiore",
            ["geometria.parallelismo-perpendicolarita", "geometria.poligoni-perimetro", "logica.tutti-qualcuno-controesempio"],
            "Dedurre le proprietà delle figure (criteri di congruenza, somma degli angoli = 180°, parallelogrammi) a partire da un nucleo minimo di definizioni e postulati.",
            ["INVARIANT_PRESERVATION", "CONTRADICTION_REDUCTIO"],
            "Catene deduttive su angoli formati da trasversali e criteri minimi di rigidità dei triangoli.",
            "drill_perpendicular_angles",
            3.0,
        ),
        (
            "superiori.sistemi-lineari-retta",
            "Sistemi lineari e retta nel piano cartesiano",
            "relazioni-logica-dati",
            "2ª superiore",
            ["relazioni.equazione-primo-grado-base", "geometria.coordinate-griglia"],
            "Un sistema lineare 2×2 è l'intersezione geometrica di due rette (y = mx + q): determinante != 0 significa incidenza unica, 0 significa parallelismo o coincidenza.",
            ["ANGULAR_GEOMETRY_PROJECTION", "VARIABLE_ISOLATION_CONTROL"],
            "Risolvere sistemi lineari (sostituzione, riduzione, Cramer) traducendo pendenza, ortogonalità e incidenza.",
            "drill_linear_systems_line",
            3.5,
        ),
        (
            "superiori.radicali-equazioni-secondo-grado",
            "Radicali, razionalizzazione ed equazioni di secondo grado",
            "numeri-e-operazioni",
            "2ª superiore",
            ["operazioni.radici-base", "superiori.fattorizzazione-frazioni-algebriche", "superiori.sistemi-lineari-retta"],
            "Completare il quadrato riduce ax^2 + bx + c = 0 a uno scostamento puro (x + b/2a)^2 = Delta/(4a^2); il discriminante decide il numero di intersezioni reali con l'asse x.",
            ["INVARIANT_PRESERVATION", "BOUNDED_TOLERANCE"],
            "Semplificare radicali su dominio lecito, completare il quadrato e applicare le formule di Viète (somma/prodotto radici).",
            "drill_quadratic_radicals",
            4.0,
        ),
        (
            "superiori.circonferenza-euclide-talete",
            "Circonferenza, teoremi di Euclide e similitudine di Talete",
            "spazio-misure-figure",
            "2ª superiore",
            ["superiori.geometria-sintetica-congruenza", "geometria.pitagora", "geometria.similitudine-scala", "geometria.cerchio-pi-greco"],
            "La proiezione ortogonale genera triangoli simili dentro il triangolo rettangolo (1° e 2° teorema di Euclide) e lega angoli al centro, alla circonferenza e rette tangenti.",
            ["PROPORTIONAL_SCALING", "ANGULAR_GEOMETRY_PROJECTION"],
            "Usare fasci paralleli e medie geometriche per calcolare corde, tangenti e segmenti inaccessibili.",
            "drill_euclid_similarity",
            3.5,
        ),
        (
            "superiori.equazioni-fratte-irrazionali-modulo",
            "Disequazioni fratte, sistemi di disequazioni, irrazionali e moduli",
            "numeri-e-operazioni",
            "3ª superiore",
            ["superiori.radicali-equazioni-secondo-grado"],
            "Non moltiplicare mai per un denominatore di segno ignoto e non elevare al quadrato senza concordanza di segno: lo studio del segno e delle condizioni di accettabilità previene soluzioni fantasma.",
            ["BOUNDED_TOLERANCE", "SIGNED_DEVIATION_FEEDBACK"],
            "Discutere sistemi equivalenti per disequazioni fratte, valori assoluti e radici di indice pari/dispari.",
            "drill_p0_symbolic_inequalities",
            4.0,
        ),
        (
            "superiori.coniche-luoghi-geometrici",
            "Coniche come luoghi geometrici ed equazioni (parabola, ellisse, iperbole)",
            "spazio-misure-figure",
            "3ª superiore",
            ["superiori.sistemi-lineari-retta", "superiori.radicali-equazioni-secondo-grado", "superiori.circonferenza-euclide-talete"],
            "Circonferenza, ellisse, parabola e iperbole uniscono la sezione del cono (Apollonio), proprietà focali fisiche e quadratica algebrica nel piano cartesiano.",
            ["ANGULAR_GEOMETRY_PROJECTION", "INVARIANT_PRESERVATION"],
            "Passare dalla definizione come luogo di distanze all'equazione canonica di fuochi, direttrici, assi e asintoti.",
            "drill_conics_loci",
            4.0,
        ),
        (
            "superiori.successioni-progressioni",
            "Successioni numeriche, progressioni aritmetiche e geometriche",
            "numeri-e-operazioni",
            "3ª superiore",
            ["relazioni.sequenze-regole", "superiori.radicali-equazioni-secondo-grado"],
            "Sottrarre una somma da se stessa spostata (Gauss) chiude le somme aritmetiche e geometriche S_n = a_1 (1 - q^n)/(1 - q), anticipando le serie e l'induzione.",
            ["RECURSIVE_SELF_SIMILARITY", "ACCUMULATION_INTEGRATION"],
            "Calcolare termini generali e somme parziali chiuse distinguendo crescita lineare (differenza costante) da moltiplicativa (ragione costante).",
            "drill_progressions_sum",
            3.0,
        ),
        (
            "superiori.goniometria-formule-equazioni",
            "Funzioni goniometriche, formule di addizione ed equazioni periodiche",
            "spazio-misure-figure",
            "3ª superiore",
            ["superiori.circonferenza-euclide-talete", "superiori.coniche-luoghi-geometrici"],
            "Tutte le identità di addizione, duplicazione e bisezione scendono da una rotazione unitaria sulla circonferenza (o dalla distanza tra due punti su essa), riducendo le equazioni goniometriche a sistemi sulla circonferenza.",
            ["ANGULAR_GEOMETRY_PROJECTION", "MODULAR_PERIODICITY"],
            "Manipolare identità di seno/coseno/tangente e risolvere equazioni e disequazioni periodiche in modulo 2π.",
            "drill_goniometry_identities",
            4.0,
        ),
        (
            "superiori.trigonometria-triangoli",
            "Trigonometria piana e risoluzione di triangoli qualunque",
            "spazio-misure-figure",
            "4ª superiore",
            ["superiori.goniometria-formule-equazioni"],
            "I teoremi dei seni e di Carnot (c^2 = a^2 + b^2 - 2ab cos γ) generalizzano Pitagora a qualunque angolo, sbloccando navigazione, geodesia e meccanica.",
            ["ANGULAR_GEOMETRY_PROJECTION", "PROPORTIONAL_SCALING"],
            "Ricostruire lati e angoli inaccessibili da rilievi angolari parziali.",
            "drill_cosine_law",
            3.0,
        ),
        (
            "superiori.esponenziali-logaritmi",
            "Funzioni esponenziali, logaritmi e scale multiplicativo-additive",
            "relazioni-logica-dati",
            "4ª superiore",
            ["operazioni.potenze-base", "superiori.successioni-progressioni", "superiori.equazioni-fratte-irrazionali-modulo"],
            "Il logaritmo log_a(y) trasforma prodotti in somme e potenze in moltiplicazioni (inverso continuo dell'esponenziale a^x), rendendo lineari scale fisiche di molti ordini di grandezza.",
            ["ORDER_OF_MAGNITUDE_BOUND", "RATE_OF_CHANGE"],
            "Risolvere equazioni e disequazioni esponenziali/logaritmiche con cambio di base e vincoli sull'argomento (> 0).",
            "drill_logarithms_exp",
            4.0,
        ),
        (
            "superiori.numeri-complessi-gauss",
            "Numeri complessi, piano di Gauss, De Moivre e radici n-esime",
            "numeri-e-operazioni",
            "4ª superiore",
            ["superiori.goniometria-formule-equazioni", "superiori.radicali-equazioni-secondo-grado"],
            "Introdurre i con i^2 = -1 significa interpretare il prodotto come scalatura + rotazione nel piano (De Moivre), chiudendo l'algebra polinomiale sui poligoni regolari delle radici n-esime.",
            ["ANGULAR_GEOMETRY_PROJECTION", "MODULAR_PERIODICITY"],
            "Convertire tra forma algebrica (a + ib) e polare/trigonometrica ed estrarre radici n-esime.",
            "drill_complex_numbers",
            3.5,
        ),
        (
            "superiori.combinatoria-probabilita-composta",
            "Calcolo combinatorio, binomio di Newton e probabilità composta/Bayes",
            "relazioni-logica-dati",
            "4ª superiore",
            ["dati.media-frequenza-incertezza", "superiori.polinomi-prodotti-notevoli"],
            "Separare l'importanza dell'ordine (disposizioni vs combinazioni C(n,k)) spiega insieme i coefficienti di (a+b)^n e il conteggio esatto delle probabilità condizionate.",
            ["COMBINATORIAL_GRID_PATTERN", "PROBABILITY_BAYESIAN_UPDATE"],
            "Contare disposizioni, permutazioni, combinazioni ed eventi dipendenti condizionati.",
            "drill_combinatorics_binomial",
            3.5,
        ),
        (
            "superiori.geometria-spazio-vettori",
            "Vettori, matrici 2×2/3×3 e geometria analitica nello spazio 3D",
            "spazio-misure-figure",
            "4ª superiore",
            ["geometria.solidi-volume", "superiori.sistemi-lineari-retta", "superiori.trigonometria-triangoli"],
            "Un vettore normale (a, b, c) identifica un piano ax + by + cz + d = 0 nello spazio 3D, unificando distanza, ortogonalità (prodotto scalare = 0) e determinanti.",
            ["ANGULAR_GEOMETRY_PROJECTION", "INVARIANT_PRESERVATION"],
            "Operare su vettori in R^2/R^3, prodotti scalari e intersezioni/distanze tra rette e piani nello spazio.",
            "drill_space_vectors",
            3.5,
        ),
        (
            "superiori.limiti-continuita-asintoti",
            "Limiti, continuità, asintoti e teoremi globali (Weierstrass, valori intermedi)",
            "relazioni-logica-dati",
            "5ª superiore",
            ["superiori.equazioni-fratte-irrazionali-modulo", "superiori.esponenziali-logaritmi", "superiori.goniometria-formule-equazioni"],
            "Il limite (ε-δ) fissa una tolleranza arbitraria sull'uscita e trova un corridoio attorno a x_0 in cui la funzione non scappa (localizzazione rigorosa dell'infinito e delle discontinuità).",
            ["BOUNDED_TOLERANCE", "THRESHOLD_PHASE_TRANSITION"],
            "Calcolare limiti con forme indeterminate, limiti notevoli e classificare discontinuità e asintoti.",
            "drill_limits_continuity",
            4.5,
        ),
        (
            "superiori.derivata-studio-funzione",
            "Derivata, teoremi del calcolo differenziale (Rolle/Lagrange) e studio di funzione",
            "relazioni-logica-dati",
            "5ª superiore",
            ["superiori.limiti-continuita-asintoti"],
            "La derivata f'(x_0) è la migliore approssimazione lineare locale (pendenza tangente e velocità istantanea); azzerarla isola massimi, minimi e punti di svolta fisici ed economici.",
            ["RATE_OF_CHANGE", "SIGNED_DEVIATION_FEEDBACK"],
            "Calcolare derivate di funzioni composte e ricostruire il grafico qualitativo completo tramite f' e f''.",
            "drill_derivatives_extrema",
            5.0,
        ),
        (
            "superiori.integrali-teorema-fondamentale",
            "Integrali indefiniti/definiti e Teorema Fondamentale del Calcolo",
            "relazioni-logica-dati",
            "5ª superiore",
            ["superiori.derivata-studio-funzione", "geometria.area-triangolo-poligoni"],
            "L'accumulazione continua di rettangoli infinitesimi (integrale di Riemann) è l'operazione inversa del tasso istantaneo (Torricelli-Barrow): F'(x) = f(x) lega aree e derivate.",
            ["ACCUMULATION_INTEGRATION", "INVARIANT_PRESERVATION"],
            "Integrare per scomposizione, sostituzione e parti per calcolare aree e volumi esatti.",
            "drill_definite_integrals",
            5.0,
        ),
        (
            "superiori.equazioni-differenziali-modelli",
            "Equazioni differenziali del 1° e 2° ordine e modelli dinamici",
            "relazioni-logica-dati",
            "5ª superiore",
            ["superiori.integrali-teorema-fondamentale"],
            "In fisica, biologia e ingegneria non conosciamo subito lo stato y(t), ma la legge locale y' = F(t, y) che ne regola il tasso di cambiamento; integrarla genera l'intera traiettoria.",
            ["RATE_OF_CHANGE", "ACCUMULATION_INTEGRATION"],
            "Separare le variabili e risolvere equazioni differenziali lineari con condizioni iniziali (Cauchy).",
            "drill_ode_separable",
            3.5,
        ),
    ]
    for (
        nid,
        title,
        branch,
        school_grade,
        prereqs,
        decision,
        op_tags,
        archetype,
        drill_key,
        est_hours,
    ) in high_school_raw:
        nodes.append(
            {
                "id": nid,
                "title": title,
                "layer": 0,
                "layer_label": "Strato 0 · Fondamenta Scolastiche (1ª Elementare → 5ª Superiore)",
                "branch": branch,
                "school_grade": school_grade,
                "estimated_hours": est_hours,
                "prerequisites": prereqs,
                "decision": decision,
                "target_op_tags": op_tags,
                "generator_archetype": archetype,
                "drill_key": drill_key,
                "canonical_domains": ["matematica"],
            }
        )
    return nodes


def _layer1_and_2_units() -> list[dict[str, Any]]:
    units = [
        # --- STRATO 1: BONIFICA OFA & PRE-IMMATRICOLAZIONE (11 unità) ---
        {
            "id": "P6.1",
            "title": "Storia della matematica come percorso di apprendimento",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "contesto-e-metodo",
            "program": "P6 · Contesto e metodo (trasversale)",
            "estimated_hours": 0,
            "prerequisites": [],
            "decision": "Usare il problema storico generatore (incommensurabili, indivisibili, flussioni, dicotomia booleana) per sciogliere la compressione manualistica.",
            "objective": "Ricostruire il problema originario che ha reso necessaria ogni definizione formale dei programmi P0-P3.",
            "hero_proof": "Una pagina per unità P0-P3 che ricostruisce il problema storico generatore con citazioni primarie dal corpus.",
            "proof_family": "rubric_proof",
            "target_op_tags": ["CONTRADICTION_REDUCTIO", "ACCUMULATION_INTEGRATION"],
            "generator_archetype": "Risalire dalla regola formale compressa alla controversia o anomalia sperimentale che l'ha generata.",
            "drill_key": "drill_p0_logic_counterexample",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "storia della scienza"],
        },
        {
            "id": "P0.1",
            "title": "Che cosa è una dimostrazione",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 8,
            "prerequisites": [
                "logica.tutti-qualcuno-controesempio",
                "geometria.pitagora",
                "superiori.geometria-sintetica-congruenza",
                "P6.1",
            ],
            "decision": "Separare ipotesi, tesi, assiomi e regole deduttive (diretta, per assurdo, controesempio) per arrestare il regresso infinito delle giustificazioni.",
            "objective": "Distinguere un'affermazione dimostrata da una plausibile; separare ipotesi e tesi e produrre controesempi.",
            "hero_proof": "Riscrivere l'enunciato del teorema di Pitagora separando ipotesi e tesi; produrre un controesempio a 'ogni numero primo è dispari'.",
            "proof_family": "rubric_proof",
            "target_op_tags": ["CONTRADICTION_REDUCTIO", "INVARIANT_PRESERVATION"],
            "generator_archetype": "Costringere un'ipotesi rivale all'autocontraddizione o esibire un singolo caso che smentisce una legge universale.",
            "drill_key": "drill_p0_logic_counterexample",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "logica"],
        },
        {
            "id": "P0.2",
            "title": "Logica proposizionale e dei predicati",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 10,
            "prerequisites": ["P0.1", "logica.vero-falso-non-e-o"],
            "decision": "Algebrizzare il ragionamento su {0, 1} (Boole: x(1-x)=0) e formalizzare l'ordine dei quantificatori ∀ ed ∃ e la loro negazione (De Morgan).",
            "objective": "Tradurre una frase italiana in formula logica e negare correttamente enunciati con quantificatori annidati.",
            "hero_proof": "Negare 'per ogni x esiste y tale che y > x' e scrivere la tavola di verità della contronominale (A -> B) <-> (~B -> ~A).",
            "proof_family": "sympy_and_rubric",
            "target_op_tags": ["SERIES_CONJUNCTION_GATE", "PARALLEL_DISJUNCTION_PATH", "CONTRADICTION_REDUCTIO"],
            "generator_archetype": "Verificare se un effetto binario dipende dalla continuità simultanea di tutti gli anelli in serie o da almeno un ramo attivo.",
            "drill_key": "drill_p0_propositional",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "logica", "informatica"],
        },
        {
            "id": "P0.3",
            "title": "Insiemi, relazioni, funzioni come oggetti",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 8,
            "prerequisites": ["P0.2", "numeri.quantita", "logica.classificare-attributi"],
            "decision": "Definire una funzione come sottoinsieme univoco del prodotto cartesiano A × B, distinguendo iniettività, suriettività e biiettività.",
            "objective": "Usare il linguaggio insiemistico per definire oggetti matematici e dimostrare proprietà di funzioni e relazioni.",
            "hero_proof": "Definire formalmente 'valore assoluto' come funzione e dimostrare che la composizione di due funzioni iniettive è iniettiva.",
            "proof_family": "rubric_proof",
            "target_op_tags": ["BIJECTION_EQUINUMEROSITY", "BOUNDED_TOLERANCE", "INVARIANT_PRESERVATION"],
            "generator_archetype": "Accoppiare elementi di un dominio a un codominio garantendo assenza di collisioni (iniettività) o copertura totale (suriettività).",
            "drill_key": "drill_p0_sets_functions",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "logica"],
        },
        {
            "id": "P0.4",
            "title": "Numeri: dagli interi ai reali",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 10,
            "prerequisites": [
                "P0.3",
                "divisibilita.mcd",
                "divisibilita.mcm",
                "operazioni.radici-base",
                "rapporti.proporzioni-percentuali",
                "superiori.radicali-equazioni-secondo-grado",
            ],
            "decision": "Estendere N -> Z -> Q -> R a ogni operazione che si rompe (sottrazione, divisione, diagonale incommensurabile sqrt(2)).",
            "objective": "Manipolare senza errori potenze razionali/negative, radicali, frazioni, valore assoluto e ordini di grandezza.",
            "hero_proof": "Semplificare a mano un'espressione con potenze frazionarie annidate e dimostrare a libro chiuso l'irrazionalità di sqrt(2).",
            "proof_family": "sympy_and_rubric",
            "rubric_id": "sqrt2_irrational",
            "target_op_tags": ["CONTRADICTION_REDUCTIO", "ORDER_OF_MAGNITUDE_BOUND", "PROPORTIONAL_SCALING"],
            "generator_archetype": "Scoprire l'impossibilità di esprimere una lunghezza geometrica continua tramite il rapporto di due interi coprimi.",
            "drill_key": "drill_p0_radicals_powers",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P0.5",
            "title": "Calcolo simbolico: equazioni e disequazioni",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 14,
            "prerequisites": [
                "P0.4",
                "frazioni.denominatore-comune",
                "relazioni.equazione-primo-grado-base",
                "operazioni.distributiva",
                "superiori.fattorizzazione-frazioni-algebriche",
                "superiori.equazioni-fratte-irrazionali-modulo",
            ],
            "decision": "Ricondurre equazioni e disequazioni (1°/2° grado, fratte, con valore assoluto |x - x0| < δ e radicali) a fattorizzazione e studio del segno.",
            "objective": "Risolvere senza esitazione equazioni e disequazioni con frazioni, moduli e radicali, controllando il risultato per sostituzione.",
            "hero_proof": "Risolvere e rappresentare sull'asse reale una disequazione frazionaria e una con valore assoluto, verificando per sostituzione.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["BOUNDED_TOLERANCE", "SIGNED_DEVIATION_FEEDBACK", "LATENT_STATE_SENSING"],
            "generator_archetype": "Mantenere un mobile o una misura entro un margine massimo di tolleranza attorno a un asse centrale usando uno scostamento con segno.",
            "drill_key": "drill_p0_symbolic_inequalities",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P0.6",
            "title": "Funzioni elementari e loro grafici",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 12,
            "prerequisites": [
                "P0.5",
                "geometria.coordinate-griglia",
                "geometria.simmetrie-traslazioni",
                "relazioni.proporzionalita-diretta-inversa",
                "superiori.coniche-luoghi-geometrici",
                "superiori.esponenziali-logaritmi",
            ],
            "decision": "Fondere algebra e geometria (Cartesio): leggere rette, parabole, esponenziali e logaritmi tramite trasformazioni geometriche anziché tabelle di punti.",
            "objective": "Disegnare a mano, senza tabelle di valori, il grafico di una funzione elementare e delle sue trasformazioni.",
            "hero_proof": "Da f(x) = log(x) ricavare a mano il grafico di y = |log(x - 2)| + 1 indicando dominio, asintoto, cuspide e monotonia.",
            "proof_family": "graph_invariants",
            "graph_spec_id": "abs_shifted_log",
            "target_op_tags": ["ANGULAR_GEOMETRY_PROJECTION", "SIGNAL_TRANSDUCTION_ECHO", "PROPORTIONAL_SCALING"],
            "generator_archetype": "Concentrare onde o raggi paralleli in un unico punto focale tramite una superficie curva e leggere spostamenti come traslazioni d'assi.",
            "drill_key": "drill_p0_functions_parabola",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P0.7",
            "title": "Trigonometria essenziale",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 8,
            "prerequisites": [
                "P0.6",
                "geometria.cerchio-pi-greco",
                "geometria.similitudine-scala",
                "geometria.pitagora",
                "superiori.goniometria-formule-equazioni",
                "superiori.trigonometria-triangoli",
            ],
            "decision": "Definire seno e coseno come coordinate sulla circonferenza unitaria in radianti per modellare rotazioni, proiezioni d'angolo e fenomeni periodici.",
            "objective": "Usare seno, coseno e tangente come funzioni periodiche e proiezioni geometriche senza memorizzare tabelle cieche.",
            "hero_proof": "Giustificare sin^2(x) + cos^2(x) = 1 sulla circonferenza goniometrica e risolvere sin(2x) = 1/2 in [0, 2π].",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["ANGULAR_GEOMETRY_PROJECTION", "MODULAR_PERIODICITY"],
            "generator_archetype": "Calcolare il cono angolare sotteso da un varco di larghezza fissa a distanza variabile e scomporre vettori lungo assi ortogonali.",
            "drill_key": "drill_p0_trigonometry",
            "corpus_coverage": "partial",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P0.8",
            "title": "Logica elementare applicata: problemi e stime a tempo",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "linguaggio-matematico",
            "program": "P0 · Il linguaggio (pre-iscrizione)",
            "estimated_hours": 6,
            "prerequisites": [
                "P0.2",
                "P0.5",
                "dati.media-frequenza-incertezza",
                "misure.equivalenze-decimali",
            ],
            "decision": "Smascherare fallacie tipiche (inversione dell'implicazione, base-rate neglect) e stimare ordini di grandezza a mente sotto vincolo di tempo.",
            "objective": "Affrontare quesiti stile test d'accesso (Testmatbasesol / CISIA) in tempo limitato e produrre stime alla Fermi.",
            "hero_proof": "Sessione cronometrata su quesiti ufficiali (deduzione, percentuali, stime di potenza/ordine di grandezza) con diagnosi errori.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["ORDER_OF_MAGNITUDE_BOUND", "PROBABILITY_BAYESIAN_UPDATE", "CONTRADICTION_REDUCTIO"],
            "generator_archetype": "Demolire un'affermazione implausibile calcolando in due righe il limite fisico di potenza o densità energetica a distanza data.",
            "drill_key": "drill_p0_fermi_logic",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "logica"],
        },
        {
            "id": "P1.1",
            "title": "Ambiente di lavoro e riga di comando",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "alfabetizzazione-operativa",
            "program": "P1 · Alfabetizzazione operativa (pre-iscrizione)",
            "estimated_hours": 6,
            "prerequisites": ["relazioni.sequenze-regole"],
            "decision": "Padroneggiare shell POSIX, permessi, ambienti virtuali Python isolati e lettura degli stack trace prima di scrivere algoritmi.",
            "objective": "Muoversi nel filesystem, isolare dipendenze e diagnosticare un errore da terminale senza dipendere da IDE opachi.",
            "hero_proof": "Creare un ambiente Python isolato, eseguire uno script di lettura file e verificare exit code e permessi.",
            "proof_family": "lab_executable",
            "target_op_tags": ["VARIABLE_ISOLATION_CONTROL", "BOTTLENECK_CAPACITY"],
            "generator_archetype": "Isolare un ambiente esecutivo riproducibile separando configurazione, permessi e canali di input/output.",
            "drill_key": "drill_p1_cli_permissions",
            "corpus_coverage": "covered",
            "canonical_domains": ["informatica"],
        },
        {
            "id": "P1.2",
            "title": "Versionamento e riproducibilità (Git)",
            "layer": 1,
            "layer_label": "Strato 1 · Gate OFA & Pre-Immatricolazione",
            "branch": "alfabetizzazione-operativa",
            "program": "P1 · Alfabetizzazione operativa (pre-iscrizione)",
            "estimated_hours": 6,
            "prerequisites": ["P1.1"],
            "decision": "Modellare la storia del codice come grafo aciclico di snapshot immutabili (commit SHA) per riprodurre ogni esperimento.",
            "objective": "Gestire commit atomici, branch, merge e dipendenze dichiarate per rendere riproducibile un progetto.",
            "hero_proof": "Ricostruire un esperimento in un repository con storia leggibile, branch di feature e dipendenze bloccate.",
            "proof_family": "lab_executable",
            "target_op_tags": ["INVARIANT_PRESERVATION", "VARIABLE_ISOLATION_CONTROL"],
            "generator_archetype": "Tracciare modifiche incrementali reversibili garantendo il ritorno immediato a una baseline funzionante.",
            "drill_key": "drill_p1_git_concepts",
            "corpus_coverage": "open_access_dropin",
            "open_access_ids": ["OA-01-PRO-GIT"],
            "canonical_domains": ["informatica"],
        },
        # --- STRATO 2: PONTI ANTI-BARATRO PER I 20 SHADOW GATES (12 unità) ---
        {
            "id": "P2.1",
            "title": "Induzione e ricorsione",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "consolidamento-q1-q2",
            "program": "P2 · Consolidamento in corso (Q1→Q2, 1° anno)",
            "estimated_hours": 10,
            "prerequisites": ["P0.3", "superiori.successioni-progressioni", "G02"],
            "decision": "Induzione matematica (base + passo n -> n+1) e ricorsione ben fondata nel codice sono la medesima struttura vista da due lati.",
            "objective": "Dimostrare per induzione e garantire la terminazione e correttezza di funzioni ricorsive.",
            "hero_proof": "Dimostrare per induzione la somma dei primi n interi n(n+1)/2 e verificare una funzione ricorsiva equivalente.",
            "proof_family": "sympy_and_rubric",
            "rubric_id": "induction_sum_n",
            "target_op_tags": ["RECURSIVE_SELF_SIMILARITY", "INVARIANT_PRESERVATION"],
            "generator_archetype": "Ridurre un problema di taglia n a un sottoproblema identico di taglia minore ancorato a un caso base elementare.",
            "drill_key": "drill_p2_induction",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "informatica"],
        },
        {
            "id": "P2.2",
            "title": "Matematica del discreto",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "consolidamento-q1-q2",
            "program": "P2 · Consolidamento in corso (Q1→Q2, 1° anno)",
            "estimated_hours": 14,
            "prerequisites": ["P2.1", "superiori.combinatoria-probabilita-composta", "G00"],
            "decision": "Contare configurazioni finite (combinatoria, pigeonhole), modellare reti come grafi e calcolare nei resti modulari Z_n.",
            "objective": "Contare spazi di chiavi/password, usare aritmetica modulare e stimare la complessità asintotica O(f(n)).",
            "hero_proof": "Contare le password di lunghezza 8 con almeno una cifra e stimare la complessità di cicli annidati.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["COMBINATORIAL_GRID_PATTERN", "MODULAR_PERIODICITY", "CONSTRAINED_SEARCH_DECODING"],
            "generator_archetype": "Generare trame regolari su griglia discreta ed enumerare sistematicamente configurazioni ammissibili potando i tentativi ciechi.",
            "drill_key": "drill_p2_discrete_combinatorics",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica", "informatica"],
        },
        {
            "id": "P2.3",
            "title": "Analisi: quel tanto che serve (Limiti, Derivate, Catena, Integrali)",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "consolidamento-q1-q2",
            "program": "P2 · Consolidamento in corso (Q1→Q2, 1° anno)",
            "estimated_hours": 16,
            "prerequisites": [
                "P0.6",
                "geometria.solidi-volume",
                "superiori.limiti-continuita-asintoti",
                "superiori.derivata-studio-funzione",
                "superiori.integrali-teorema-fondamentale",
                "superiori.equazioni-differenziali-modelli",
                "G01",
            ],
            "decision": "Leggere la derivata come tasso istantaneo di variazione (Newton) e la regola della catena come propagazione della sensibilità lungo strati composti.",
            "objective": "Derivare composizioni multistrato (backpropagation in miniatura), trovare minimi e interpretare l'integrale come accumulazione.",
            "hero_proof": "Derivare analiticamente una composizione a tre livelli (mini-rete a due strati) e calcolare il minimo di una loss quadratica.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["RATE_OF_CHANGE", "ACCUMULATION_INTEGRATION", "SIGNED_DEVIATION_FEEDBACK"],
            "generator_archetype": "Guidare l'ottimizzazione verso il minimo di errore seguendo la pendenza locale e accumulare fette infinitesime.",
            "drill_key": "drill_p2_calculus_chain",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P3.1",
            "title": "Algebra lineare operativa",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "ponte-ai-q2-q3",
            "program": "P3 · Ponte matematico per l'AI (Q2→Q3, finestra critica)",
            "estimated_hours": 18,
            "prerequisites": [
                "P0.6",
                "superiori.sistemi-lineari-retta",
                "superiori.numeri-complessi-gauss",
                "superiori.geometria-spazio-vettori",
                "G00",
            ],
            "decision": "Vedere matrici come trasformazioni geometriche dello spazio, prodotti scalari come proiezioni di similarità e autovettori come direzioni invarianti.",
            "objective": "Calcolare a mano prodotti matrice-vettore, rango, eliminazione di Gauss, determinanti e autovalori interpretandoli geometricamente.",
            "hero_proof": "Calcolare a mano prodotto matrice-vettore 3×3, rango e autovalori, spiegando la deformazione geometrica prodotta.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["ANGULAR_GEOMETRY_PROJECTION", "COMBINATORIAL_GRID_PATTERN", "INVARIANT_PRESERVATION"],
            "generator_archetype": "Rappresentare deformazioni lineari dello spazio indipendentemente dal sistema di riferimento scelto.",
            "drill_key": "drill_p3_linear_algebra",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P3.2",
            "title": "Probabilità (Colma lacuna 0 CFU prima di Machine Learning)",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "ponte-ai-q2-q3",
            "program": "P3 · Ponte matematico per l'AI (Q2→Q3, finestra critica)",
            "estimated_hours": 14,
            "prerequisites": ["P0.3", "P0.4", "superiori.combinatoria-probabilita-composta", "P2.3"],
            "decision": "Formalizzare l'incertezza con gli assiomi di Kolmogorov e l'aggiornamento razionale delle credenze col teorema di Bayes.",
            "objective": "Calcolare probabilità condizionate, Bayes (falsi positivi con bassa prevalenza), valore atteso e varianza.",
            "hero_proof": "Risolvere il problema del test diagnostico / IDS a bassa prevalenza spiegando con Bayes l'errore dell'intuizione ingenua.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["PROBABILITY_BAYESIAN_UPDATE", "LATENT_STATE_SENSING"],
            "generator_archetype": "Aggiornare la credenza su una causa nascosta alla luce di un segnale rumoroso tenendo conto della rarità a priori.",
            "drill_key": "drill_p3_bayes",
            "corpus_coverage": "covered",
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P3.3",
            "title": "Statistica e analisi dei dati (Colma lacuna 0 CFU)",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "ponte-ai-q2-q3",
            "program": "P3 · Ponte matematico per l'AI (Q2→Q3, finestra critica)",
            "estimated_hours": 12,
            "prerequisites": ["P3.2"],
            "decision": "Distinguere correlazione empirica, artefatti da variabili confondenti e inferenza causale controllata (minimi quadrati e limiti del p-value).",
            "objective": "Stimare parametri con incertezza, adattare una retta ai minimi quadrati a mano e in Python e isolare variabili confondenti.",
            "hero_proof": "Calcolare la retta ai minimi quadrati su 5 punti a mano e riprodurre la stima e i residui in uno script Python verificato.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["HIDDEN_CONFOUNDER", "VARIABLE_ISOLATION_CONTROL", "PROBABILITY_BAYESIAN_UPDATE"],
            "generator_archetype": "Isolare se un effetto osservato dipenda dall'ipotesi testata o da un confondente fisico nascosto tramite controlli incrociati.",
            "drill_key": "drill_p3_least_squares",
            "corpus_coverage": "open_access_dropin",
            "open_access_ids": ["OA-04-OPENINTRO-STATS"],
            "canonical_domains": ["matematica"],
        },
        {
            "id": "P4.1",
            "title": "Crittografia di base",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "fondamenti-sicurezza",
            "program": "P4 · Fondamenti tecnici per la sicurezza (estate 1°→2° anno)",
            "estimated_hours": 12,
            "prerequisites": ["P2.2", "G03", "G04"],
            "decision": "Separare integrità unidirezionale (hash), confidenzialità simmetrica (AES) e asimmetrica/autenticazione su problemi matematici asimmetrici (RSA, DH).",
            "objective": "Distinguere hash, cifratura simmetrica, chiave pubblica e firma digitale, eseguendo RSA su numeri piccoli.",
            "hero_proof": "Eseguire RSA a mano con numeri primi piccoli e dimostrare formalmente perché un hash crittografico non è una cifratura.",
            "proof_family": "sympy_and_rubric",
            "rubric_id": "hash_vs_encryption",
            "target_op_tags": ["CONSTRAINED_SEARCH_DECODING", "MODULAR_PERIODICITY", "ADVERSARIAL_DECEPTION"],
            "generator_archetype": "Decodificare una scrittura velata sfruttando regolarità strutturali oppure impedire l'inversione senza chiave segreta.",
            "drill_key": "drill_p4_rsa_modular",
            "corpus_coverage": "open_access_dropin",
            "open_access_ids": ["OA-02-BONEH-SHOUP"],
            "canonical_domains": ["informatica"],
        },
        {
            "id": "P4.2",
            "title": "Macchina, memoria, rete",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "fondamenti-sicurezza",
            "program": "P4 · Fondamenti tecnici per la sicurezza (estate 1°→2° anno)",
            "estimated_hours": 14,
            "prerequisites": ["G03", "G04"],
            "decision": "Leggere cosa accade fisicamente ai bit (complemento a due, stack frame C, indirizzamento IP/CIDR) quando un programma esegue o corrompe memoria.",
            "objective": "Sommare in complemento a due, tracciare lo stack frame di una chiamata e calcolare subnetting IPv4.",
            "hero_proof": "Convertire e sommare in complemento a due su 8 bit, tracciare uno stack frame e risolvere un piano di subnetting CIDR.",
            "proof_family": "sympy_deterministic",
            "target_op_tags": ["BOTTLENECK_CAPACITY", "SERIES_CONJUNCTION_GATE", "SIGNAL_TRANSDUCTION_ECHO"],
            "generator_archetype": " Seguire la trasduzione fisica di un segnale attraverso livelli di astrazione finiti soggetti a overflow e rumore.",
            "drill_key": "drill_p4_twos_complement",
            "corpus_coverage": "covered",
            "canonical_domains": ["informatica"],
        },
        {
            "id": "P5.1",
            "title": "Programmare bene, non solo far funzionare",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "pratica-del-software",
            "program": "P5 · Pratica del software (2° anno)",
            "estimated_hours": 12,
            "prerequisites": ["G07"],
            "decision": "Esplicitare invarianti, tipi e contratti (pre/post-condizioni alla Hoare) per governare la complessità e prevenire stati illegali.",
            "objective": "Scomporre funzioni monolitiche in moduli coesi dotati di invarianti verificabili.",
            "hero_proof": "Rifattorizzare una funzione monolitica di 60 righe in tre funzioni pure con invarianti dichiarati e asserzioni.",
            "proof_family": "lab_executable",
            "target_op_tags": ["INVARIANT_PRESERVATION", "VARIABLE_ISOLATION_CONTROL"],
            "generator_archetype": "Isolare responsabilità e mantenere veri gli invarianti di stato attraverso ogni transizione ammessa.",
            "drill_key": "drill_p5_complexity_invariants",
            "corpus_coverage": "covered",
            "canonical_domains": ["informatica"],
        },
        {
            "id": "P5.2",
            "title": "Testing, versionamento, revisione",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "pratica-del-software",
            "program": "P5 · Pratica del software (2° anno)",
            "estimated_hours": 12,
            "prerequisites": ["P5.1", "P1.2"],
            "decision": "Usare suite di test deterministici sui casi limite come rete di sicurezza oggettiva prima di qualsiasi refactoring.",
            "objective": "Scrivere unit test che coprano i casi limite e rifattorizzare a regressioni zero.",
            "hero_proof": "Portare ai casi limite la suite pytest di un modulo reale e rifattorizzarlo mantenendo 100% pass.",
            "proof_family": "lab_executable",
            "target_op_tags": ["VARIABLE_ISOLATION_CONTROL", "BOUNDED_TOLERANCE"],
            "generator_archetype": "Ripristinare la baseline funzionante e isolare un guasto sostituendo un singolo componente per volta con controlli positivi e negativi.",
            "drill_key": "drill_p5_testing_edge_cases",
            "corpus_coverage": "open_access_dropin",
            "open_access_ids": ["OA-03-SWE-OWASP"],
            "canonical_domains": ["informatica"],
        },
        {
            "id": "P5.3",
            "title": "Stack web e mobile",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "pratica-del-software",
            "program": "P5 · Pratica del software (2° anno)",
            "estimated_hours": 12,
            "prerequisites": ["G04", "G10"],
            "decision": "Comprendere come nasce lo stato di sessione sopra HTTP stateless e dove l'iniezione di input non fidato rompe il confine dati/codice (SQLi, XSS).",
            "objective": "Tracciare il ciclo HTTP request-response, cookie/token di sessione, query parametrizzate SQL e permessi mobile.",
            "hero_proof": "Tracciare il flusso completo di un login HTTP individuando e mitigando tre vettori di attacco (SQLi, session hijacking, CSRF).",
            "proof_family": "lab_executable",
            "target_op_tags": ["ADVERSARIAL_DECEPTION", "VARIABLE_ISOLATION_CONTROL"],
            "generator_archetype": "Impedire che dati forniti da un avversario vengano interpretati come istruzioni esecutive dal parser ricevente.",
            "drill_key": "drill_p5_http_sqli",
            "corpus_coverage": "open_access_dropin",
            "open_access_ids": ["OA-03-SWE-OWASP"],
            "canonical_domains": ["informatica"],
        },
        {
            "id": "P6.2",
            "title": "Scrittura tecnica e uso delle fonti",
            "layer": 2,
            "layer_label": "Strato 2 · Ponti Shadow Gates (1°–2° Anno)",
            "branch": "contesto-e-metodo",
            "program": "P6 · Contesto e metodo (verso Tirocinio e Tesi)",
            "estimated_hours": 8,
            "prerequisites": ["G19"],
            "decision": "Distinguere rigorosamente dato misurato, citazione primaria e ipotesi interpretativa in un elaborato scientifico riproducibile.",
            "objective": "Redigere un abstract tecnico strutturato con fonti verificate secondo standard IEEE/ACM.",
            "hero_proof": "Scrivere un abstract strutturato di 250 parole su un esperimento di sicurezza/AI con 5 fonti primarie verificate.",
            "proof_family": "rubric_proof",
            "target_op_tags": ["INVARIANT_PRESERVATION", "VARIABLE_ISOLATION_CONTROL"],
            "generator_archetype": "Documentare metodo, prove e limiti in modo che un terzo indipendente possa verificare o falsificare il risultato.",
            "drill_key": "drill_p0_logic_counterexample",
            "corpus_coverage": "partial",
            "canonical_domains": ["informatica", "filosofia"],
        },
    ]
    return units


def _layer3_gates() -> list[dict[str, Any]]:
    gates_raw = [
        ("G00", "Matematica I", "formal_ofa", 1, 1, 6, ["P0.1", "P0.2", "P0.3", "P0.4", "P0.5", "P0.8"], "Entro 12 mesi dall'immatricolazione (pena blocco totale esami 2° e 3° anno)", "20 item: manipolazione simbolica, disequazioni, logica elementare"),
        ("G01", "Matematica II", "internal", 1, 1, 6, ["P0.6", "P0.7", "G00"], "Prima dell'appello Q1 (co-erogato con Matematica I)", "10 item su grafici di funzioni, trasformazioni e trigonometria"),
        ("G02", "Programmazione e Algoritmi I", "external", 1, 1, 9, ["P1.1", "P1.2"], "Prime 3 settimane del Q1", "Creare, eseguire e correggere un programma con cicli e condizioni in ambiente isolato"),
        ("G03", "Computing Systems", "internal", 1, 2, 9, ["G00", "G02"], "Fine Q1 / inizio Q2", "Conversioni di base, complemento a due, tabelle di verità e porte logiche"),
        ("G04", "Reti e Cloud", "internal", 1, 2, 9, ["G03"], "Prime 2 settimane del Q2", "Subnetting IPv4/CIDR e tracciamento richiesta HTTP lungo i livelli"),
        ("G05", "Machine Learning", "structural", 1, 3, 9, ["G01", "P2.3", "P3.1", "P3.2", "P3.3"], "Tra fine Q2 e inizio Q3 — finestra più critica del 1° anno (Prob/Stat a 0 CFU nel piano!)", "Prodotto matrice-vettore, gradiente quadratica, teorema di Bayes e minimi quadrati"),
        ("G06", "Analisi e Visualizzazione dei Dati", "structural", 1, 3, 6, ["G02", "P3.3"], "Inizio Q3", "Statistiche descrittive, interpretazione boxplot e regressione in Python"),
        ("G07", "Programmazione e Algoritmi II", "internal", 1, 3, 9, ["G02", "P2.1", "P2.2"], "Fine Q2", "Traccia di ricorsione su alberi/grafi e stima asintotica O-grande"),
        ("G08", "Aspetti penali ed etici della AI e della sicurezza", "external", 2, 1, 6, ["G00"], "Q3 del 1° anno", "Individuazione norma applicabile (CP / GDPR / AI Act) in un caso di data breach"),
        ("G09", "Defensive Security", "structural", 2, 1, 9, ["G04", "P4.1", "P4.2"], "Estate tra 1° e 2° anno (Crittografia senza modulo dedicato nel piano)", "Regole di filtraggio e distinzione formale tra hash, cifratura simmetrica e asimmetrica"),
        ("G10", "Database", "internal", 2, 1, 9, ["G00", "G07"], "Q3 del 1° anno", "Traduzione di interrogazioni con quantificatori in algebra relazionale e SQL"),
        ("G11", "Deep Learning", "internal", 2, 2, 6, ["G05", "P2.3", "P3.1"], "Q1 del 2° anno", "Derivazione analitica della regola della catena (backpropagation) su rete a due strati"),
        ("G12", "Offensive Security", "structural", 2, 2, 9, ["G09", "P4.2"], "Q1 del 2° anno (Linguaggio C e modello memoria assenti dal piano)", "Lettura di uno stack frame C e analisi di buffer overflow in ambiente isolato"),
        ("G13", "Laboratorio AI", "external", 2, 2, 6, ["G05", "G11", "P1.2"], "Q1 del 2° anno", "Riproduzione completa di un training ML a partire da un repository versionato"),
        ("G14", "Generative AI", "internal", 2, 3, 9, ["G11", "P3.1", "P3.2"], "Q2 del 2° anno", "Calcolo del meccanismo di self-attention da prodotti scalari QKV normalizzati"),
        ("G15", "Sicurezza e AI", "integration", 2, 3, 9, ["G11", "G12", "P3.2"], "Q2 del 2° anno (integrazione filiere AI + Security)", "Modellazione di un attacco data poisoning o FGSM evasion su un classificatore"),
        ("G16", "Progettazione di software sicuro", "structural", 3, 1, 6, ["G07", "P5.1", "P5.2"], "2° anno in parallelo ai lab (Ingegneria del Software assente dal piano!)", "Scrittura unit test con copertura casi limite e refactoring verificato"),
        ("G17", "Laboratorio Cybersecurity", "external", 3, 1, 6, ["G09", "G12"], "Estate tra 2° e 3° anno", "Allestimento lab virtualizzato isolato e report tecnico di vulnerability assessment"),
        ("G18", "Sicurezza nei sistemi web e mobili", "structural", 3, 1, 6, ["G04", "G10", "P5.3"], "Estate tra 2° e 3° anno (Sviluppo web/mobile assente dal piano)", "Analisi ciclo sessione HTTP e mitigazione SQL injection / XSS / permessi Android"),
        ("G19", "Tirocinio", "external", 3, 2, 18, ["G15", "G16", "G17", "G18"], "Fine 2° anno / inizio 3° anno", "Progetto applicativo autonomo documentato in repository riproducibile"),
        ("G20", "Prova finale", "external", 3, 3, 3, ["G19", "P6.2"], "3° anno prima del deposito tesi", "Stesura elaborato finale con abstract strutturato e fonti primarie verificate"),
    ]
    nodes = []
    for gid, title, gate_type, year, quarter, cfu, prereqs, window, diag in gates_raw:
        extra_oa = ["OA-05-ARXIV-GENAI-ADVML"] if gid in {"G14", "G15"} else []
        nodes.append(
            {
                "id": gid,
                "title": f"{gid} · {title}",
                "module_name": title,
                "layer": 3,
                "layer_label": f"Strato 3 · Esami & Gate SecAI ({year}° Anno, Q{quarter})",
                "branch": "esami-secai-l31",
                "gate_type": gate_type,
                "year": year,
                "quadrimestre": quarter,
                "cfu": cfu,
                "estimated_hours": cfu * 8,
                "prerequisites": prereqs,
                "window": window,
                "diagnostic_prompt": diag,
                "decision": f"Traguardo curricolare ufficiale SecAI ({cfu} CFU, tipo gate: {gate_type}). Finestra critica: {window}.",
                "target_op_tags": ["INVARIANT_PRESERVATION"],
                "open_access_ids": extra_oa,
                "canonical_domains": ["informatica", "matematica"],
            }
        )
    return nodes


def build_unified_dag_payload() -> dict[str, Any]:
    """Costruisce il payload JSON completo del DAG Unificato a 4 Strati e ne verifica l'aciclicità."""
    all_nodes_list = _layer0_nodes() + _layer1_and_2_units() + _layer3_gates()
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[list[str]] = []

    for node in all_nodes_list:
        nid = node["id"]
        if nid in nodes_by_id:
            raise ValueError(f"ID nodo duplicato nel DAG: {nid}")
        for tag in node.get("target_op_tags", []):
            if tag not in CANONICAL_OP_TAGS:
                raise ValueError(f"op_tag non canonico {tag!r} sul nodo {nid}")
        nodes_by_id[nid] = node

    for nid, node in nodes_by_id.items():
        for prereq in node["prerequisites"]:
            if prereq not in nodes_by_id:
                raise ValueError(f"Prerequisito inesistente {prereq!r} richiesto da {nid}")
            edges.append([prereq, nid])

    topo_order = topological_sort(nodes_by_id)
    # Calcola per ciascun nodo la Bussola dell'Hero (catena minima verso un Gate e verso G00 se applicabile)
    children_map: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
    for src, dst in edges:
        children_map[src].append(dst)

    for nid, node in nodes_by_id.items():
        compass = _compute_hero_compass(nid, nodes_by_id, children_map)
        node["hero_compass"] = compass

    payload = {
        "schema_version": "secai-unified-dag.v1",
        "metadata": {
            "title": "SecAI Unified 4-Layer Curricular Spine (1ª Elementare → 5ª Superiore → OFA → L-31 UniMi)",
            "degree": "Sicurezza Informatica e Intelligenza Artificiale (L-31, Università degli Studi di Milano)",
            "regulatory_baseline": "Manifesto degli Studi FAOof1_2027",
            "total_nodes": len(nodes_by_id),
            "layer_counts": {
                "layer_0_foundations": sum(1 for n in all_nodes_list if n["layer"] == 0),
                "layer_1_ofa_pre": sum(1 for n in all_nodes_list if n["layer"] == 1),
                "layer_2_shadow_bridges": sum(1 for n in all_nodes_list if n["layer"] == 2),
                "layer_3_secai_gates": sum(1 for n in all_nodes_list if n["layer"] == 3),
            },
            "total_edges": len(edges),
            "acyclic": True,
            "topological_order": topo_order,
        },
        "hero_profile": {
            "actor": "Studente adulto con formazione filosofica, esperienza software ed esperienza nautica nel Tigullio",
            "mission": "Azzerare l'effetto sudoku partendo dalle decisioni di progetto elementari, liquidare il GATE-OFA-MATH entro 12 mesi e arrivare a tutti i 20 Shadow Gates SecAI con prerequisiti dimostrati.",
            "formal_ofa_gate": "G00",
            "critical_zero_cfu_bridge": ["P3.1", "P3.2", "P3.3"],
        },
        "nodes": nodes_by_id,
        "edges": edges,
    }
    return payload


def topological_sort(nodes_by_id: dict[str, dict[str, Any]]) -> list[str]:
    """Esegue l'ordinamento topologico di Kahn; solleva ValueError se esiste anche un solo ciclo."""
    in_degree: dict[str, int] = {nid: 0 for nid in nodes_by_id}
    children: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
    for nid, node in nodes_by_id.items():
        for prereq in node.get("prerequisites", []):
            in_degree[nid] += 1
            children[prereq].append(nid)

    queue = deque(
        sorted(
            [nid for nid, deg in in_degree.items() if deg == 0],
            key=lambda k: (nodes_by_id[k]["layer"], k),
        )
    )
    order: list[str] = []
    while queue:
        curr = queue.popleft()
        order.append(curr)
        newly_ready = []
        for nxt in children[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                newly_ready.append(nxt)
        for nxt in sorted(newly_ready, key=lambda k: (nodes_by_id[k]["layer"], k)):
            queue.append(nxt)

    if len(order) != len(nodes_by_id):
        cycling = sorted(set(nodes_by_id) - set(order))
        raise ValueError(f"Ciclo rilevato nel DAG curricolare sui nodi: {cycling}")
    return order


def _shortest_path_to_targets(
    start_id: str,
    target_predicate: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    children_map: dict[str, list[str]],
) -> list[str]:
    if target_predicate(nodes_by_id[start_id]):
        return [start_id]
    visited = {start_id}
    queue: deque[list[str]] = deque([[start_id]])
    while queue:
        path = queue.popleft()
        curr = path[-1]
        for nxt in children_map.get(curr, []):
            if nxt in visited:
                continue
            new_path = path + [nxt]
            if target_predicate(nodes_by_id[nxt]):
                return new_path
            visited.add(nxt)
            queue.append(new_path)
    return []


def _reachable_gates(
    start_id: str,
    nodes_by_id: dict[str, dict[str, Any]],
    children_map: dict[str, list[str]],
) -> list[str]:
    visited = set()
    queue = deque([start_id])
    gates = []
    while queue:
        curr = queue.popleft()
        for nxt in children_map.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                if nodes_by_id[nxt]["layer"] == 3:
                    gates.append(nxt)
                queue.append(nxt)
    if nodes_by_id[start_id]["layer"] == 3:
        gates.insert(0, start_id)
    return sorted(set(gates))


def _compute_hero_compass(
    node_id: str,
    nodes_by_id: dict[str, dict[str, Any]],
    children_map: dict[str, list[str]],
) -> dict[str, Any]:
    path_to_ofa = _shortest_path_to_targets(
        node_id,
        lambda n: n["id"] == "G00",
        nodes_by_id,
        children_map,
    )
    path_to_any_gate = _shortest_path_to_targets(
        node_id,
        lambda n: n["layer"] == 3,
        nodes_by_id,
        children_map,
    )
    primary_path = path_to_ofa or path_to_any_gate
    gates_unlocked = _reachable_gates(node_id, nodes_by_id, children_map)
    if not gates_unlocked:
        raise ValueError(f"Il nodo {node_id} è un vicolo cieco: non sblocca alcun Gate SecAI!")

    chain_display = [
        {"id": pid, "title": nodes_by_id[pid]["title"], "layer": nodes_by_id[pid]["layer"]}
        for pid in primary_path
    ]
    target_gate = nodes_by_id[primary_path[-1]]
    return {
        "primary_path_ids": primary_path,
        "chain": chain_display,
        "target_gate_id": target_gate["id"],
        "target_gate_title": target_gate["title"],
        "target_gate_window": target_gate.get("window", ""),
        "serves_ofa_formal": "G00" in gates_unlocked,
        "gates_unlocked": gates_unlocked,
        "gates_unlocked_count": len(gates_unlocked),
    }


def save_unified_dag_json(dest_path: Path | str = DEFAULT_DAG_PATH) -> dict[str, Any]:
    payload = build_unified_dag_payload()
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_unified_dag(dag_path: Path | str = DEFAULT_DAG_PATH) -> dict[str, Any]:
    path = Path(dag_path)
    if not path.exists():
        return save_unified_dag_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    topological_sort(payload["nodes"])
    return payload


def load_open_access_registry(path: Path | str = DEFAULT_OPEN_ACCESS_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"reclassified_as_covered_in_wave0": [], "open_access_acquisitions": []}
    return json.loads(p.read_text(encoding="utf-8"))


def compute_frontier_nodes(
    dag_payload: dict[str, Any],
    mastered_ids: set[str],
    failed_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Individua i 'Nodi Frontiera' dello studente:
    1) tutti i nodi con almeno un tentativo fallito i cui prerequisiti sono soddisfatti;
    2) i primi nodi in ordine topologico non ancora superati i cui prerequisiti sono tutti soddisfatti.
    """
    failed = failed_ids or set()
    nodes = dag_payload["nodes"]
    topo = dag_payload["metadata"]["topological_order"]
    frontier: list[dict[str, Any]] = []
    for nid in topo:
        if nid in mastered_ids:
            continue
        node = nodes[nid]
        prereqs = node.get("prerequisites", [])
        if all(p in mastered_ids for p in prereqs):
            entry = dict(node)
            entry["frontier_reason"] = (
                "punto_debole_rilevato" if nid in failed else "prossimo_mattone_sbloccato"
            )
            frontier.append(entry)
    frontier.sort(key=lambda item: (0 if item["frontier_reason"] == "punto_debole_rilevato" else 1, item["layer"], item["id"]))
    return frontier


if __name__ == "__main__":
    data = save_unified_dag_json()
    print(
        f"Saved DAG with {data['metadata']['total_nodes']} nodes and "
        f"{data['metadata']['total_edges']} edges (acyclic={data['metadata']['acyclic']})."
    )
