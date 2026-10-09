# Aggiornamenti per Windows

**Tiene aggiornati con un clic i programmi del tuo PC che winget conosce, cioè la grande maggioranza.** Apri Aggiornamenti, vedi quali programmi hanno una versione nuova e li aggiorni tutti insieme, senza dover aprire i siti dei produttori uno per uno. È gratuito, senza pubblicità e senza account.

[English version →](README.en.md)

<img src="docs/finestra.png" alt="La finestra di Aggiornamenti" width="600">

---

## Installazione (3 minuti)

### 1. Scarica il programma

👉 **[Scarica Aggiornamenti](https://github.com/giuseppelupo1979/aggiornamenti-windows/releases/latest/download/Aggiornamenti-x64.exe)**: va bene per quasi tutti i PC.

Solo se il tuo PC ha un processore ARM (per esempio Surface Pro X o i portatili Copilot+ con Snapdragon) usa invece **[questa versione](https://github.com/giuseppelupo1979/aggiornamenti-windows/releases/latest/download/Aggiornamenti-arm64.exe)**. Se non sai quale hai: *Start → Impostazioni → Sistema → Informazioni → Tipo di sistema*. Se c'è scritto "x64", usa il primo link.

### 2. Apri il file scaricato

Apri **Aggiornamenti** dalla cartella Download (o dalla barra di download del browser).

La prima volta Windows mostra quasi sicuramente una schermata blu **"PC protetto da Windows"**. È normale: compare con tutti i programmi nuovi che non sono firmati da un'azienda con un certificato a pagamento. Per proseguire:

1. clicca la scritta **Ulteriori informazioni**;
2. in basso compare un nuovo pulsante, **Esegui comunque**: cliccalo.

<img src="docs/smartscreen.png" alt="Avviso PC protetto da Windows: clicca Ulteriori informazioni, poi Esegui comunque" width="420">

### 3. Tre scelte e sei pronto

Si apre la finestra di **benvenuto**. Lascia spuntato **Aggiornamenti senza domande**, premi **Inizia** e rispondi **Sì** alla richiesta di Windows: è l'unica volta che te lo chiede. Da quel momento i programmi si aggiornano in silenzio e Aggiornamenti parte da solo all'accensione del PC.

Il programma si è già installato da solo: lo ritrovi nel **menu Start**, sul **Desktop** e come icona vicino all'orologio. Puoi cancellare il file dalla cartella Download.

Hai saltato la scelta o vuoi cambiarla? In fondo alla finestra trovi **Privilegi di amministratore** e **Controllo automatico**.

---

## Come si usa

- **Clicca sui programmi** da aggiornare, oppure su **Seleziona tutto**, poi premi **Aggiorna**. Una barra mostra cosa sta succedendo per ogni programma. Durante il giro il pulsante diventa **Interrompi**: finisce l'installazione in corso e lascia le altre per dopo.
- Viene installata **esattamente la versione che vedi** nell'elenco, non una più nuova uscita nel frattempo.
- I programmi segnati **versione maggiore** (un grande salto di versione) non vengono selezionati da soli: aggiornali solo se sai che ti serve.
- **Escludi**, accanto a ogni programma, lo toglie dall'elenco **per sempre**: non viene più proposto né aggiornato di notte. Lo ritrovi in fondo, nella sezione *Escluse*, dove **Includi** lo rimette in elenco.
- In **Controllo automatico** puoi farti avvisare ogni giorno con una notifica, oppure lasciare che aggiorni da solo di notte (tra le 3 e le 8: se il PC è spento, si riprova la notte dopo). Puoi anche spegnere tutto: con **Avvia all'accensione** disattivato Aggiornamenti funziona **solo quando lo apri tu**, e con *Esci* si chiude del tutto.
- Se un programma da aggiornare è aperto, Aggiornamenti gli chiede di chiudersi, lo aggiorna e lo riapre. Se non si chiude da solo (per esempio perché chiede di salvare), **non lo forza**: la riga mostra **Forza chiusura** e **Rimanda**, e decidi tu. Di notte un programma aperto non viene mai chiuso: si rimanda.
- L'**icona vicino all'orologio** mostra un pallino quando ci sono aggiornamenti; cliccala per aprire la finestra o per controllare subito.
- Quando esce una nuova versione di Aggiornamenti stesso, compare un riquadro in alto con il pulsante **Installa**.

---

## Domande frequenti

**È sicuro?**
Il programma usa **winget**, lo strumento ufficiale di Microsoft già incluso in Windows 11, che scarica ogni aggiornamento dal sito del produttore e ne verifica l'integrità. Il codice di Aggiornamenti è pubblico in questa pagina e il file che scarichi viene costruito direttamente da GitHub a partire da questo codice.

**Perché Windows mostra "PC protetto da Windows"?**
Perché il programma è nuovo e non è firmato con un certificato a pagamento. Non significa che sia pericoloso: Windows avvisa per ogni programma che non conosce ancora. L'avviso diminuisce man mano che il programma viene scaricato da più persone.

**L'antivirus lo segnala.**
Alcuni antivirus segnalano per errore i programmi creati con lo strumento usato qui (PyInstaller). Se succede, puoi verificare che il file sia quello originale confrontando il codice SHA-256 pubblicato nella pagina della [versione](https://github.com/giuseppelupo1979/aggiornamenti-windows/releases/latest).

**Manda dati a qualcuno?**
No. Tutto funziona sul tuo PC. Le uniche connessioni sono quelle necessarie per controllare e scaricare gli aggiornamenti (i server di Microsoft e dei produttori) e, ogni sei ore, una richiesta a GitHub per sapere se esiste una nuova versione di Aggiornamenti. Niente account, niente pubblicità, niente statistiche.

**Alcuni programmi non compaiono.**
Aggiornamenti vede i programmi che winget conosce, cioè la grande maggioranza. Quelli che non riesce a controllare sono elencati in fondo, in *Non controllate*: per quelli usa l'aggiornamento interno del programma. Microsoft Edge non compare perché si aggiorna già da solo.

**Un aggiornamento è "Non riuscito".**
Clicca **Dettagli** accanto per vedere il motivo. I casi più comuni: hai risposto *No* alla richiesta di Windows, oppure il programma era aperto. Chiudilo e riprova. I programmi che winget non riesce ad aggiornare passano in *Non controllate*, con il pulsante **Riprova**.

**In Gestione attività vedo due "Aggiornamenti.exe".**
È normale: è un solo programma, che all'avvio si scompatta in due processi. Se li chiudi da lì il programma si ferma davvero; la finestra resta aperta ma lo dice ("Aggiornamenti è stato chiuso") e si può chiudere. Per riaprirlo usa il menu Start o il Desktop. Il modo normale per chiuderlo è **Esci** dall'icona vicino all'orologio: chiude anche la finestra, e se un aggiornamento è in corso aspetta che finisca.

**Il controllo dice che non è riuscito.**
Se winget o Windows Update non rispondono, Aggiornamenti lo scrive e mostra l'ultimo elenco valido invece di dire che è tutto a posto. Di solito basta riprovare più tardi con **Controlla**.

**Funziona su Windows 10?**
È provato su Windows 11. Su Windows 10 funziona se è installato *Programma di installazione app* (winget) dal Microsoft Store.

**Come lo disinstallo?**
*Start → Impostazioni → App → App installate → Aggiornamenti → Disinstalla*.

---

## Per chi vuole saperne di più

Aggiornamenti è un piccolo server locale (Python, solo libreria standard) che usa winget per trovare e installare gli aggiornamenti, con un'interfaccia web mostrata in una finestra di Microsoft Edge in modalità applicazione. Ascolta solo su `127.0.0.1` e rifiuta richieste da altri siti. Gli exe per x64 e ARM64 sono costruiti da [GitHub Actions](.github/workflows/build.yml) a ogni versione.

Avvio dal sorgente, senza exe:

```powershell
git clone https://github.com/giuseppelupo1979/aggiornamenti-windows.git
cd aggiornamenti-windows
.\installa.ps1
```

Esiste anche la versione per Mac: [aggiornamenti-mac](https://github.com/giuseppelupo1979/aggiornamenti-mac). Le novità di ogni versione sono in [CHANGELOG.md](CHANGELOG.md).

## Licenza

[MIT](LICENSE): libero da usare, modificare e condividere. Il software è fornito **senza garanzia**: installa e aggiorna programmi sul tuo PC, quindi lo usi a tuo rischio, come qualsiasi strumento di sistema.

Realizzato da Giuseppe Lupo con Claude (Anthropic).
