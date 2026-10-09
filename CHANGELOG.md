# Changelog

Tutte le modifiche rilevanti al progetto. Le versioni seguono il [versionamento semantico](https://semver.org/lang/it/).

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
