# Materiale di origine dei file di contesto

Questi cinque file vengono da un altro progetto di agente personale (impianto
`AGENTS.md` / `SOUL.md` / `IDENTITY.md`) e sono stati usati come sorgente per costruire le
istruzioni di ernesto in `context/`. Sono conservati qui come riferimento: non vengono
letti da ernesto.

## Cosa e' stato preso

- `SOUL.md` → i principi di `context/soul.md`: utilita' sostanziale, avere opinioni, essere
  intraprendenti prima di chiedere, prudenza fuori e audacia dentro, il rispetto dovuto a
  chi ti da' accesso alle sue cose.
- `PREF.md` → la disciplina di codice di `context/agent.md` (pensa prima di scrivere, prima
  la semplicita', modifiche chirurgiche, obiettivi verificabili) e le preferenze di risposta
  di `context/soul.md`.
- `AGENTS.md` → la dottrina della memoria su file ("se vuoi ricordare qualcosa, scrivilo")
  e le regole di sicurezza (niente dati privati fuori, niente comandi distruttivi senza
  chiedere, meglio spostare che cancellare).
- `USER.md` → il profilo utente in `context/agent.md`, senza l'ID del bot Telegram: gli
  identificatori operativi stanno in `credentials.md` o nelle variabili d'ambiente, non nel
  system prompt.

## Cosa e' stato scartato, e perche'

`IDENTITY.md` per intero (descrive un'altra identita': ernesto resta ernesto) e circa meta'
di `AGENTS.md`: heartbeat, cron interni, chat di gruppo, regole per Discord e WhatsApp,
reazioni emoji, agente trascrittore e i rimandi a file che non esistono (`ROADMAP.md`,
`HEARTBEAT.md`, `TOOLS.md`, `BOOTSTRAP.md`, `avatars/`). Presuppongono un workspace che
ernesto non ha.

## Le quattro contraddizioni risolte

I file si contraddicevano su emoji, riassunto finale, lingua e commit automatici. In tutti
e quattro i casi ha vinto `PREF.md`, che descrive le preferenze reali e correnti: niente
emoji, niente riassunto finale, italiano, nessun commit per iniziativa dell'agente.
