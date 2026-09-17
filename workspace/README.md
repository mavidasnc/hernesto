# workspace

La cartella di lavoro di ernesto: appunti, bozze, output intermedi e tutto cio' che
l'agente produce per conto suo, invece di sparpagliarlo nella radice del progetto.

- `projects/` — i progetti nuovi. Quando chiedi «voglio creare un progetto pippo»,
  ernesto crea `workspace/projects/pippo/` e lavora li' dentro.

Il contenuto non e' versionato: in git resta solo questo file, per documentare la
struttura. `install-context.py` ricrea le cartelle dopo un clone.
