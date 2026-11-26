---
name: recupero-credito
description: Usa quando l'utente ha un credito da recuperare, una fattura non pagata o vuole procedere con decreto ingiuntivo — interessi di mora, rivalutazione ISTAT, decreto ingiuntivo e parcella avvocato.
tools: [decreto_ingiuntivo, interessi_legali, interessi_mora, modello_notula, rivalutazione_monetaria]
prompt: {"name": "recupero_credito", "description": "Workflow completo per recupero credito: interessi, rivalutazione, decreto ingiuntivo e parcella", "args": [{"name": "importo", "type": "float"}, {"name": "tipo_credito", "type": "str"}, {"name": "data_scadenza", "type": "str"}]}
---

# Recupero Credito

Workflow completo: interessi mora, rivalutazione, decreto ingiuntivo, parcella.

## Workflow

### 1. Interessi di mora

Chiama `interessi_mora` con capitale, data_inizio (data di scadenza del pagamento: gli interessi decorrono dal giorno successivo, art. 4, co. 1, D.Lgs. 231/2002) e data_fine (data di calcolo).

- **Commerciale** (imprese/PA): usa `interessi_mora` — tasso BCE + 8 punti (D.Lgs. 231/2002)
- **Privato** (crediti tra privati): usa `interessi_legali` — tasso legale art. 1284 c.c.
- **In esecuzione**: se il titolo giudiziale condanna genericamente agli «interessi legali», dopo la domanda giudiziale si applica il saggio dell'art. 1284, co. 1, c.c., non quello maggiorato del co. 4, salvo che il titolo, anche solo in motivazione, accerti la spettanza di quest'ultimo (Cass. SS.UU. n. 12449/2024). Nel ricorso chiedi espressamente gli interessi ex art. 1284, co. 4, dalla domanda.

### 2. Rivalutazione monetaria

Chiama `rivalutazione_monetaria` con l'importo del credito, dalla data di scadenza a oggi.

**Nota**: per un credito di denaro la rivalutazione non è automatica: è il maggior danno dell'art. 1224, co. 2, c.c., da chiedere e provare. Secondo Cass. SS.UU. n. 19499/2008 si presume quando, durante la mora, il rendimento netto dei titoli di Stato fino a 12 mesi ha superato il saggio legale (verificalo sui dati del periodo di mora: con un saggio legale basso, come l'1,60% del 2026 fissato dal DM MEF 10/12/2025, la presunzione può tornare a operare); per somme maggiori il creditore deve provarlo (l'imprenditore, ad esempio, con il costo del credito bancario o la redditività dell'impresa), e il debitore può provare che il denaro non avrebbe reso di più. Spetta solo per la parte che eccede gli interessi moratori: i due importi non si sommano. La rivalutazione ISTAT è una stima di confronto, non il criterio delle SS.UU.

### 3. Decreto ingiuntivo

Chiama `decreto_ingiuntivo` con l'importo del credito e, per un credito commerciale (imprese/PA, D.Lgs. 231/2002), `tipo_credito='commerciale'`: la bozza chiede allora gli interessi moratori dal giorno successivo alla scadenza, senza costituzione in mora (art. 4, co. 1). Verifica:

- Competenza — Giudice di Pace fino a € 10.000 per i procedimenti instaurati dal 28/2/2023 (riforma Cartabia, D.Lgs. 149/2022); fino a € 5.000 per quelli anteriori. Oltre la soglia, Tribunale.
- Contributo unificato dovuto
- Requisiti documentali (fatture, contratto, estratto autentico notarile)
- Possibilità di provvisoria esecutività (art. 642 c.p.c.)

### 4. Parcella

Chiama `modello_notula` con il `tipo_procedimento` del ricorso per decreto ingiuntivo, avvocato, cliente e `valore_causa` pari all'importo del credito: il monitorio si liquida sulla propria tabella del D.M. 55/2014, in fase unica, non con le fasi di un giudizio di cognizione (studio, introduttiva, istruttoria, decisionale). Indica il range compenso con `livello` min/medio/max. Nella tabella «Costi procedura» il compenso è `totale_onorari`: `totale_notula` comprende già contributo unificato e anticipazione forfettaria, da non contare due volte.

## Formato output

### Riepilogo Recupero Credito

| Voce | Importo |
|------|---------|
| Capitale | € `importo` |
| Interessi di mora (da `data_scadenza` a oggi) | € ... |
| Rivalutazione ISTAT (alternativa) | € ... |
| **Totale dovuto** | **€ ...** |

### Costi procedura

| Voce | Importo |
|------|---------|
| Contributo unificato | € ... |
| Marca da bollo | € 27,00 |
| Diritti di notifica | € ... |
| Compenso avvocato (medio) | € ... |
| **Costo totale procedura** | **€ ...** |

## Raccomandazioni

- Indicare se conviene la diffida stragiudiziale prima del ricorso
- Valutare la provvisoria esecutività
- Tempi medi della procedura
