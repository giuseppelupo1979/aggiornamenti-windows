# Changelog

Tutte le modifiche rilevanti al progetto. Le versioni seguono il [versionamento semantico](https://semver.org/lang/it/).

## [0.4.0] - 2026-10-11

### Aggiunto
- Verifica della versione effettivamente installata dopo ogni installazione riuscita. Se non coincide con quella richiesta o non è leggibile, l'esito è **Da verificare**; i codici di riavvio di Windows/winget hanno uno stato dedicato, senza riavviare il PC automaticamente.
- **Solo con alimentazione di rete** ed **Evita connessioni a consumo** per gli aggiornamenti automatici, attivi per impostazione predefinita. Se le condizioni sono sconosciute o sfavorevoli, si riprova ogni cinque minuti entro la finestra notturna. La pagina mostra motivo dell'attesa e prossimo tentativo.
- **Rimanda per 24 ore**, **Per una settimana**, **Salta questa versione** e **Riprendi**. I rinvii persistono e valgono anche per la coda automatica; le esclusioni permanenti restano separate.
- Storico degli ultimi 300 tentativi con versione richiesta e rilevata, modalità, codice di uscita, dettagli persistenti e filtri per app ed esito. Esportazione JSON della diagnostica con oscuramento dei dati personali riconoscibili, senza invio automatico.
- Aspetto **Come Windows**, **Chiaro** o **Scuro**, salvato nelle impostazioni.

### Interfaccia
- Accento blu per azioni, selezioni e avanzamento; verde per successi e ambra per avvisi.
- Elenco e impostazioni in pannelli, versioni più leggibili e righe selezionate evidenziate.
- Caselle quadrate, azioni sempre visibili, focus da tastiera preservato nelle righe e supporto alla riduzione delle animazioni.
- Intestazione compatta che resta visibile durante lo scorrimento, pulsante **Aggiorna N app** e disposizione adattata alle finestre strette.

### Corretto
- Testi relativi a Windows, al risveglio entro cinque ore e all'avvio automatico.
- Finestre di aggiornamento che attraversano la mezzanotte, scrittura atomica delle nuove impostazioni e isolamento delle impostazioni predefinite.
- Notifiche automatiche distinguono gli errori dagli esiti che richiedono verifica o riavvio.

### Verifica
- 49 test automatici del server su verifica versioni, riavvii, rinvii, condizioni, API e oscuramento della diagnostica, oltre alle regressioni della 0.3.0.
- Verifica nel browser: temi chiaro/scuro, rinvio e ripresa, selezione da tastiera, aggiornamento simulato, filtri dello storico, esportazione diagnostica, intestazione fissa e assenza di overflow a 320/360 pixel.
- La prova end-to-end nella VM personale con installazioni reali resta da eseguire dopo l'aggiornamento dell'utente.

## [0.3.0] - 2026-10-09

Nata da una revisione indipendente del codice (16 prove riproducibili) e dai suggerimenti di un utente.

### Aggiunto
- **Interrompi**: durante un giro il pulsante "Aggiorna" diventa "Interrompi"; finisce l'installazione in corso e lascia le altre da fare.
- **Funzionamento solo manuale**: privilegi di amministratore e avvio all'accensione ora sono separati. Senza controlli pianificati il programma gira solo quando lo apri, e con Esci si chiude del tutto.
- **Forza chiusura / Rimanda** per i programmi che non si chiudono da soli; **Riprova** per quelli messi da parte; **Dettagli** separato dalla casella di selezione.
- **Storico** degli aggiornamenti, conservato tra un avvio e l'altro.
- Riquadro "Aggiornamenti è stato chiuso" quando la finestra perde il programma, e chiusura automatica della finestra con Esci.
- 22 test automatici eseguiti prima di ogni build; librerie della build con versioni fissate.

### Corretto
- Dopo 10 secondi un programma aperto veniva chiuso d'autorità anche con una domanda di salvataggio già aperta: ora **non si forza mai senza una scelta esplicita**, e di notte un programma aperto si rimanda sempre, controllandolo subito prima di ogni installazione.
- Un errore inatteso (per esempio un comando lento) lasciava il programma bloccato su "in corso" fino al riavvio: ora ogni errore chiude il proprio aggiornamento e libera il programma.
- Una scansione fallita diventava "Tutto aggiornato": ora l'errore viene mostrato, si tiene l'ultimo elenco valido e la notifica non parte. Lo stesso per Windows Update.
- L'auto-aggiornamento sostituiva l'exe senza verificarlo: ora controlla lo SHA-256 pubblicato, l'intestazione e la dimensione, e rimette al suo posto la versione in uso se qualcosa va storto. La nuova versione viene proposta solo quando i file sono davvero nella Release, e la Release diventa pubblica solo dopo il caricamento di entrambi gli exe.
- Esci dall'icona o una reinstallazione durante un aggiornamento lo interrompevano: ora si aspetta la fine.
- Si installa la versione mostrata (`--version`, `--source`), non una più nuova uscita nel frattempo.
- L'aggiornamento notturno poteva partire a mezzogiorno o saltare la giornata se il programma era occupato: ora parte solo tra l'orario scelto e 5 ore dopo, e riprova se era occupato.
- Tabelle di winget a 4 colonne e programmi con un nome che inizia con un numero venivano letti male.
- Un errore temporaneo escludeva un programma per sempre: ora scade dopo 7 giorni e c'è "Riprova".
- Dopo un errore la casella di selezione non funzionava più.
- Richieste API con dati non validi causavano un'eccezione invece di un errore chiaro; l'ultimo pezzo dell'output di un comando poteva andare perso; la rimozione dell'avvio automatico dichiarava successo anche quando Windows la rifiutava.
- Scritture concorrenti delle impostazioni potevano perdersi; il registro ora ruota a 1 MB.
- Il link "Cerca" cercava la versione **Mac** dei programmi.

## [0.2.2] - 2026-10-09

### Corretto
- I programmi aperti spesso non venivano chiusi e l'aggiornamento falliva con "è aperto: chiudilo e riprova". La chiusura veniva chiesta solo alla finestra principale, e un dialogo aperto (per esempio quello di aggiornamento interno di Notepad++) la bloccava. Ora la richiesta arriva a **tutte** le finestre del programma; se dopo 10 secondi è ancora aperto viene chiuso d'autorità, aggiornato e riaperto.
- Protezione dei documenti: il programma **non** viene chiuso d'autorità se un titolo di finestra indica un documento non salvato (asterisco o pallino) o se, alla richiesta di chiusura, compare una nuova finestra come "Vuoi salvare le modifiche?". In quel caso l'aggiornamento viene saltato con una spiegazione.

### Verificato sulla VM Windows 11
- Esci dal **vero menu** dell'icona vicino all'orologio e riapertura dal **vero collegamento del menu Start**: 2,8 s con privilegi; 6,9 s senza, con l'attività di avvio bloccata.
- Notepad++ aperto con il suo dialogo di aggiornamento: chiuso in 1 s, aggiornato, riaperto.
- Notepad++ con documento non salvato e salvataggio automatico attivo: chiuso, aggiornato, riaperto con il testo intatto.
- Notepad++ con documento non salvato che chiede di salvare: non chiuso, aggiornamento saltato con spiegazione.

## [0.2.1] - 2026-10-09

### Corretto
- Dopo **Esci** dall'icona vicino all'orologio il programma poteva non riaprirsi più. Le cause erano tre, tutte corrette:
  - il lanciatore controllava se il server era attivo con tentativi che su Windows durano circa 2 secondi l'uno: dopo Esci la finestra impiegava fino a due minuti e mezzo ad aprirsi, e se nel frattempo l'avvio non era riuscito si apriva su una pagina morta. Ora la verifica dura al massimo 0,3 secondi e le attese sono in tempo reale: la riapertura richiede circa 2 secondi;
  - se l'attività pianificata non partiva, il lanciatore non aveva alternative. Ora, se entro pochi secondi non compare il processo, avvia il programma direttamente (senza privilegi) in circa 7 secondi;
  - l'attività creata con `schtasks` non partiva **a batteria**, si fermava passando alla batteria e veniva chiusa **dopo 3 giorni**. Ora è registrata con le impostazioni giuste, e quelle create dalle versioni precedenti vengono corrette da sole al primo avvio con i privilegi.
- Se il programma non è in esecuzione, la finestra lo dice e spiega come riaprirlo, invece di mostrare dati vecchi.

## [0.2.0] - 2026-10-09

### Aggiunto
- Schermata di benvenuto al primo avvio con tre scelte: aggiornamenti senza domande (attiva i privilegi con una sola conferma di Windows), controllo ogni mattina, aggiornamento notturno.
- Icone vere dei programmi, estratte dai programmi installati.
- Icona vicino all'orologio con il numero di aggiornamenti disponibili (pallino sull'icona) e il menu Apri · Controlla ora · Esci.
- Chiusura e riapertura automatica dei programmi aperti durante l'aggiornamento: prima si chiude la finestra, i programmi che vivono solo nell'area di notifica vengono fermati, e dopo l'aggiornamento si riaprono senza privilegi di amministratore. Un programma con finestra che non si chiude (per esempio con un documento da salvare) non viene forzato. Di notte i programmi aperti vengono rimandati. *Ancora da verificare su un caso reale.*

### Corretto
- La modalità demo mostrava un finto avviso di nuova versione.

## [0.1.2] - 2026-10-09

### Migliorato
- Un'app che winget non può aggiornare non compare più come "Non riuscito" in rosso: la riga dice "Spostata tra le non controllate" e l'app passa subito in quella sezione con la spiegazione, senza aspettare il controllo successivo.
- Se l'installer fallisce perché il programma è aperto, il messaggio lo indica per nome (per esempio "Greenshot è aperto: chiudilo…").

### Corretto
- Aggiornamenti compariva tra le proprie app non controllate.

## [0.1.1] - 2026-10-09

### Corretto
- Reinstallando o aggiornando mentre il programma era aperto (anche in modalità demo) l'installazione falliva con "file utilizzato da un altro processo": ora tutte le copie in esecuzione vengono chiuse prima di sostituire l'exe.
- In caso di errore all'avvio compare un messaggio comprensibile invece della finestra tecnica di Python.
- Le app che winget non può aggiornare (installate con un sistema diverso, non trovate o non compatibili) dopo il primo tentativo passano in "Non controllate" con la spiegazione, e tornano tra gli aggiornamenti se la versione installata cambia.
- winget a volte elenca un aggiornamento e poi non trova l'app: si riprova una volta sulla sola sorgente winget.
- La stessa app elencata sia dal Microsoft Store sia da winget compare una volta sola.
- Quando un installer fallisce compare il suggerimento di chiudere il programma o accettare la richiesta di Windows.

## [0.1.0] - 2026-10-09

Prima versione, derivata da [Aggiornamenti per Mac](https://github.com/giuseppelupo1979/aggiornamenti-mac) 1.8.2.

### Aggiunto
- `Aggiornamenti.exe` in un unico file per x64 e ARM64, costruito da GitHub Actions a ogni versione con codice SHA-256 di controllo e una prova automatica di avvio.
- Installazione al primo avvio: copia nella cartella utente, collegamenti nel menu Start e sul Desktop, voce in Impostazioni → App con disinstallazione, nome e icona propri per le notifiche.
- Interfaccia nella finestra applicazione di Microsoft Edge, tema sempre scuro.
- Ricerca degli aggiornamenti con winget (repository winget e Microsoft Store), unendo i risultati delle due interrogazioni perché winget a volte omette pacchetti; identificativi completi letti da `winget export` quando la tabella li tronca.
- Aggiornamento silenzioso con barra di avanzamento e fasi (download, verifica, installazione).
- Privilegi di amministratore attivabili con una sola conferma di Windows, tramite un'attività pianificata che avvia il programma all'accesso: nessuna password salvata.
- Esclusioni, controllo giornaliero con notifica, aggiornamento notturno, pulizia degli installer scaricati, sezione delle app non controllate, avviso degli aggiornamenti di Windows, avviso e installazione delle nuove versioni del programma, modalità demo, italiano e inglese.

### Corretto durante le prove sulla VM Windows 11 ARM64
- Il server in background riusava la cartella temporanea del lanciatore e, chiuso il lanciatore, la pagina spariva.
- L'output di winget catturato arriva nella codifica OEM della console: lettere accentate e "…" degli identificativi troncati venivano storpiati.
- La finestra di benvenuto di Edge compariva usando un profilo separato.
- Microsoft Edge veniva proposto ma winget non può aggiornarlo (si aggiorna da solo): ora è escluso, e per gli altri casi simili compare una spiegazione comprensibile.
- La ricerca degli aggiornamenti di Windows falliva per un problema di virgolette.
