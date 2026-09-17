"""Interfaccia a riga di comando di ernesto: avvio (typer), REPL e comandi slash."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import questionary
import typer
from openai import OpenAI

from . import __version__
from .agent import run_turn
from .config import (
    COMPACT_KEEP_RECENT,
    COMPACT_SUMMARY_MODEL,
    COMPACT_THRESHOLD_TOKENS,
    MEMORY_DIR,
    OPENROUTER_BASE,
    config_dir,
    config_section,
    load_env_file,
)
from .context import (
    Context,
    extract_env_vars,
    load_context,
    summary_line,
    system_prompt_parts,
    verify_env_vars,
)
from .mcp_client import load_mcp_tools
from .models import DEFAULT_MODEL, MODELS, find_model, load_pricing
from .session import (
    SessionLogger,
    SessionState,
    compact_tool_results,
    estimate_tokens,
    fmt_cost,
    fmt_tokens,
    prompt_indicator,
    session_snapshot,
    summarize_with_llm,
    validate_snapshot,
)
from .tools import (
    LEVEL_DESTRUCTIVE,
    LEVEL_EXTERNAL,
    LEVEL_WARNING,
    ConfirmFn,
    Tool,
    build_native_tools,
)

REASONING_LEVELS = ("low", "medium", "high", "xhigh")

CREDENTIALS_TEMPLATE = """# Credenziali — progetto

## OPENROUTER_API_KEY
- A cosa serve: routing verso i modelli LLM (obbligatoria).
- Dove vive: variabile d'ambiente; esportala in ~/.bashrc o usa un file .env.
- Come ottenerla: https://openrouter.ai/keys
- Regole per l'agente: non stamparla mai, non copiarla in file committati.

## BRAVE_API_KEY
- A cosa serve: ricerca web (opzionale, abilita lo strumento brave_search).

## RESEND_API_KEY
- A cosa serve: invio email (opzionale, abilita lo strumento send_email).

## RESEND_FROM
- Indirizzo mittente per Resend, es. `Nome <mail@example.com>`.
"""

COMANDI = (
    "/context · /clear · /compact · /model · /tools · /reasoning · /yolo · /log · /cost · "
    "/save · /load · exit/quit · Ctrl+C interrompe il turno (al prompt: esce)"
)


def _configure_console() -> None:
    """Evita crash su console Windows non-UTF8 con i caratteri ✓/✗/·."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")


def _clear_screen() -> None:
    """Pulisce il terminale (solo se TTY: in pipe/non interattivo non tocca nulla)."""
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="", flush=True)


def _box_lines(lines: list[str], width: int) -> list[str]:
    """Incornicia le righe in un box Unicode largo `width` colonne."""
    inner = width - 4  # bordi + spazi
    boxed = ["┌" + "─" * (width - 2) + "┐"]
    for line in lines:
        if line == "":
            boxed.append("│" + " " * (width - 2) + "│")
        else:
            boxed.append("│  " + line[:inner].ljust(inner) + "│")
    boxed.append("└" + "─" * (width - 2) + "┘")
    return boxed


def _print_banner(state: SessionState, logger: SessionLogger) -> None:
    """Intestazione stile CLI agentica: identita', modello, contesto, comandi."""
    contesto = summary_line(state.context).replace("Contesto: ", "")
    lines = [
        f"ernesto v{__version__} — agente da terminale (OpenRouter)",
        "",
        f"modello:   {state.model.label} ({state.model.id})",
        f"reasoning: {state.reasoning_effort} · workdir: {state.workdir}",
        f"contesto:  {contesto}",
        f"log:       {logger.path}",
        "",
        f"comandi: {COMANDI}",
    ]
    if not sys.stdout.isatty():
        print("\n".join(line for line in lines if line))
        return
    width = min(max(shutil.get_terminal_size().columns, 50), 100)
    print("\033[36m" + "\n".join(_box_lines(lines, width)) + "\033[0m")


def _prompt_rule() -> None:
    """Riga di separazione sopra la zona di input (la chat scorre sopra, il prompt resta in basso)."""
    if sys.stdout.isatty():
        width = min(shutil.get_terminal_size().columns, 100)
        print("\033[2m" + "─" * width + "\033[0m")


# Etichette delle conferme per livello di gravita': solo ASCII, perche' la resa dei simboli
# non e' garantita su tutti i terminali. Il colore segue la convenzione del banner: si
# applica solo quando stdout e' un terminale.
LEVEL_BADGES: dict[str, tuple[str, str]] = {
    LEVEL_DESTRUCTIVE: ("[!] DISTRUTTIVO", "31"),  # rosso
    LEVEL_EXTERNAL: ("[>] ESTERNO", "33"),         # giallo
    LEVEL_WARNING: ("[?] ATTENZIONE", "36"),       # ciano, come il banner
}


def _badge(level: str) -> str:
    """Etichetta colorata del livello di conferma (senza colore fuori dal terminale)."""
    label, color = LEVEL_BADGES.get(level, ("[ ] CONFERMA", "36"))
    return f"\033[{color}m{label}\033[0m" if sys.stdout.isatty() else label


def make_confirm_fn(state: SessionState) -> ConfirmFn:
    """Callback di conferma: questionary se TTY; se stdin non e' un TTY, default False."""

    def confirm(message: str, preview: str | None = None, level: str = LEVEL_WARNING) -> bool:
        if state.yolo:
            return True
        print(f"\n{_badge(level)} {message}")
        if preview:
            print(f"---\n{preview}\n---")
        if not sys.stdin.isatty():
            print(f"[conferma richiesta] {message} → no (stdin non interattivo)")
            return False
        try:
            answer = questionary.confirm(message, default=False).ask()
        except (KeyboardInterrupt, EOFError):
            return False
        return bool(answer)

    return confirm


# ---------------------------------------------------------------------------
# Comandi slash
# ---------------------------------------------------------------------------


def cmd_model(state: SessionState) -> None:
    """Cambia il modello attivo (menu questionary) e azzera la conversazione."""
    choices = []
    for m in MODELS:
        if m.price_prompt == 0 and m.price_completion == 0:
            price_str = "gratuito"
        else:
            price_str = f"${m.price_prompt:.7f}/in · ${m.price_completion:.7f}/out"
        active = "  <-- attivo" if m.id == state.model.id else ""
        choices.append(f"{m.label} — {m.id} ({price_str}){active}")

    if sys.stdin.isatty():
        current = next((i for i, m in enumerate(MODELS) if m.id == state.model.id), 0)
        picked = questionary.select("Scegli il modello:", choices=choices, default=choices[current]).ask()
        if picked is None or picked not in choices:
            print("Annullato.")
            return
        selected = MODELS[choices.index(picked)]
        json_mode = False
        if selected.json_supported:
            json_mode = bool(
                questionary.confirm(f"Attivare JSON mode per '{selected.label}'?", default=False).ask()
            )
    else:
        # Fallback non interattivo: selezione numerica come il vecchio chat.py
        print()
        for i, choice in enumerate(choices, 1):
            print(f"  [{i}] {choice}")
        raw = input("\nNumero modello (Invio per annullare): ").strip()
        if not raw:
            print("Annullato.")
            return
        try:
            idx = int(raw) - 1
            if not (0 <= idx < len(MODELS)):
                raise ValueError
            selected = MODELS[idx]
        except ValueError:
            print("Scelta non valida.")
            return
        json_mode = False
        if selected.json_supported:
            ans = input(f"Attivare JSON mode per '{selected.label}'? (s/n) ").strip().lower()
            json_mode = ans in {"s", "si", "y", "yes"}

    state.model = selected
    state.json_mode = json_mode
    # Il cambio modello azzera sempre la conversazione
    state.reset_messages()
    suffix = " | JSON mode attivo" if json_mode else ""
    print(f"Modello: {selected.label}{suffix} — conversazione azzerata.")
    if json_mode:
        print(
            "[Avviso] JSON mode attivo: gli strumenti sono disattivati "
            "(incompatibili con response_format json_object).\n"
            "         Per usare gli strumenti disattiva il JSON mode con /model."
        )
    print()


def cmd_save(state: SessionState) -> None:
    """Salva l'intera sessione in saves/<timestamp>_<modello>.txt."""
    saves_dir = state.workdir / "saves"
    saves_dir.mkdir(exist_ok=True)
    model_slug = state.model.id.replace("/", "-").replace(":", "-")
    filepath = saves_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{model_slug}.txt"
    lines = [
        f"# Sessione ernesto — {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"# modello: {state.model.id} · reasoning: {state.reasoning_effort}",
        (
            f"# token: {state.total_prompt_tokens} in / {state.total_completion_tokens} out "
            f"· costo {fmt_cost(state.total_cost)}"
        ),
        "",
    ]
    for msg in state.messages:
        lines.append(f"--- {msg.get('role', '?')} ---")
        lines.append(str(msg.get("content") or ""))
        lines.append("")
    filepath.write_text("\n".join(lines), encoding="utf-8")
    # Il .txt e' per leggere, il .json e' per ricaricare: il testo perde tool_calls e
    # tool_call_id, quindi da solo non basta a riprendere la conversazione con /load.
    jsonpath = filepath.with_suffix(".json")
    jsonpath.write_text(
        json.dumps(session_snapshot(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Salvato: {filepath}")
    print(f"         {jsonpath} (ricaricabile con /load)")


def _saves(state: SessionState) -> list[Path]:
    """Salvataggi ricaricabili, dal piu' recente."""
    saves_dir = state.workdir / "saves"
    if not saves_dir.is_dir():
        return []
    return sorted(saves_dir.glob("*.json"), key=lambda p: p.name, reverse=True)


def _pick_save(saves: list[Path]) -> Path | None:
    """Menu di scelta del salvataggio (questionary se TTY, numerico altrimenti)."""
    choices = [f"{p.name}" for p in saves]
    if sys.stdin.isatty():
        picked = questionary.select("Quale sessione riprendere?", choices=choices).ask()
        return saves[choices.index(picked)] if picked in choices else None
    print()
    for i, choice in enumerate(choices, 1):
        print(f"  [{i}] {choice}")
    raw = input("\nNumero sessione (Invio per annullare): ").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(saves)):
        return None
    return saves[int(raw) - 1]


def cmd_load(state: SessionState, arg: str) -> None:
    """Riprende una sessione salvata: /load [nome file] (senza argomento apre l'elenco)."""
    saves = _saves(state)
    if not saves:
        print("Nessuna sessione salvata in saves/ (usa /save per crearne una).")
        return
    if arg:
        target = next((p for p in saves if arg in p.name), None)
        if target is None:
            print(f"Nessun salvataggio corrisponde a '{arg}'. Usa /load senza argomenti per l'elenco.")
            return
    else:
        target = _pick_save(saves)
        if target is None:
            print("Annullato.")
            return
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Errore nella lettura di {target.name}: {exc}")
        return
    problema = validate_snapshot(data)
    if problema is not None:
        print(f"Salvataggio non valido ({target.name}): {problema}. Conversazione invariata.")
        return

    salvato = data.get("modello")
    if salvato and salvato != state.model.id:
        found = find_model(str(salvato))
        if found is None:
            print(f"[Avviso] la sessione usava '{salvato}', non nel registry: resto su {state.model.label}.")
        else:
            state.model = found
            state.json_mode = bool(data.get("json_mode", False))
            print(f"Modello riportato a {found.label}.")
    # Il system prompt resta quello di oggi: istruzioni e indice delle memorie aggiornati
    ripristinati = [m for m in data["messaggi"] if m.get("role") != "system"]
    state.messages = [{"role": "system", "content": state.system_prompt()}, *ripristinati]
    if state.logger:
        state.logger.log("load", file=target.name, messages=len(ripristinati))
    print(
        f"Ripresa da {target.name}: {len(ripristinati)} messaggi in storia "
        f"(~{fmt_tokens(state.history_token_estimate())} tok stimati)."
    )
    print("I costi cumulativi restano quelli di questa sessione: la spesa precedente e' nel salvataggio.")


def cmd_context(state: SessionState, tools: list[Tool]) -> None:
    """Mostra provenienza e stima token del contesto, strumenti e stato della sessione."""
    print(f"Modello: {state.model.label} ({state.model.id}) · reasoning: {state.reasoning_effort}")
    print("System prompt:")
    total = 0
    for label, text in system_prompt_parts(state.context, state.json_mode):
        tokens = estimate_tokens(text)
        total += tokens
        print(f"  · {label}: ~{fmt_tokens(tokens)} tok")
    print(f"  = totale ~{fmt_tokens(total)} tok stimati")
    storia = f"Messaggi in storia: {len(state.messages)} (~{fmt_tokens(state.history_token_estimate())} tok stimati"
    print(f"{storia} · {state.compacted_count} risultati compattati)" if state.compacted_count else f"{storia})")
    print(
        f"Compattazione: soglia ~{fmt_tokens(COMPACT_THRESHOLD_TOKENS)} tok · "
        f"ultimi {COMPACT_KEEP_RECENT} giri integrali · risparmiati ~{fmt_tokens(state.compacted_tokens)} tok"
    )
    native = [t.name for t in tools if not t.name.startswith("mcp__")]
    mcp = [t.name for t in tools if t.name.startswith("mcp__")]
    if state.json_mode:
        print("Strumenti: DISATTIVATI (JSON mode attivo)")
    else:
        print(f"Strumenti nativi ({len(native)}): {', '.join(native)}")
        if mcp:
            print(f"Strumenti MCP ({len(mcp)}): {', '.join(mcp)}")
    print(f"YOLO: {'attivo' if state.yolo else 'no'} · dry-run: {'attivo' if state.dry_run else 'no'}")
    if state.logger:
        print(f"Log: {state.logger.path}")


def cmd_tools(tools: list[Tool]) -> None:
    """Elenca gli strumenti registrati (nativi + MCP) con descrizione breve."""
    print(f"Strumenti registrati ({len(tools)}):")
    for tool in tools:
        print(f"  · {tool.name}: {tool.description}")


def cmd_log(state: SessionState) -> None:
    """Mostra il percorso del file di log e il riepilogo della sessione."""
    if state.logger:
        print(f"Log di sessione: {state.logger.path}")
    else:
        print("Log di sessione non attivo.")
    print(f"Messaggi in storia: {len(state.messages)} · tool call eseguiti: {state.tool_calls_count}")
    if state.compacted_count:
        print(
            f"Compattazioni: {state.compacted_count} risultati riassunti "
            f"(~{fmt_tokens(state.compacted_tokens)} tok) — contenuto integrale nel JSONL"
        )
    print(
        f"Token totali: {state.total_prompt_tokens} in / {state.total_completion_tokens} out "
        f"· costo cumulativo {fmt_cost(state.total_cost)}"
    )


def summary_model_id(workdir: Path) -> str:
    """Modello usato per il riassunto LLM (config.yaml: compact.summary_model)."""
    return str(config_section(workdir, "compact").get("summary_model") or COMPACT_SUMMARY_MODEL)


def make_summarizer(state: SessionState, client: OpenAI) -> Callable[[str, str], str | None]:
    """Chiusura che riassume un risultato strumento con il modello configurato."""
    model_id = summary_model_id(state.workdir)

    def summarize(content: str, name: str) -> str | None:
        return summarize_with_llm(client, model_id, content, name)

    return summarize


def cmd_compact(state: SessionState, arg: str, client: OpenAI) -> None:
    """Compatta i risultati strumento: /compact [llm] [giri da preservare]."""
    parti = arg.split()
    usa_llm = bool(parti) and parti[0].lower() == "llm"
    if usa_llm:
        parti = parti[1:]
    keep = 1  # chi digita /compact vuole risparmiare adesso, non fra tre giri
    if parti:
        if not parti[0].isdigit():
            print(f"Argomento non valido: '{parti[0]}'. Uso: /compact [llm] [giri da preservare]")
            return
        keep = int(parti[0])
    summarizer = None
    if usa_llm:
        model_id = summary_model_id(state.workdir)
        print(f"Riassunto generato da {model_id} (una chiamata per ogni risultato compattato).")
        summarizer = make_summarizer(state, client)
    compacted, saved = compact_tool_results(state.messages, keep_recent=keep, summarizer=summarizer)
    if not compacted:
        print("Niente da compattare.")
        return
    state.compacted_count += compacted
    state.compacted_tokens += saved
    if state.logger:
        state.logger.log("compact", messages=compacted, saved_tokens=saved, manual=True)
    print(
        f"Compattati {compacted} risultati strumento · ~{fmt_tokens(saved)} tok stimati risparmiati "
        f"(storia ora ~{fmt_tokens(state.history_token_estimate())} tok)."
    )


def cmd_yolo(state: SessionState) -> None:
    """Toggle a runtime del bypass delle conferme."""
    state.yolo = not state.yolo
    if state.yolo:
        print("YOLO attivo — conferme disattivate: il modello eseguira' comandi e invii senza chiedere.")
    else:
        print("YOLO disattivato — le azioni pericolose richiederanno conferma.")


def cmd_reasoning(state: SessionState, arg: str) -> None:
    """Mostra o cambia il livello di reasoning inviato via extra_body."""
    if not arg:
        print(f"Reasoning effort: {state.reasoning_effort} (livelli: {', '.join(REASONING_LEVELS)})")
        return
    if arg not in REASONING_LEVELS:
        print(f"Livello non valido: {arg}. Usa: {', '.join(REASONING_LEVELS)}")
        return
    state.reasoning_effort = arg
    print(f"Reasoning effort impostato a: {arg}")


def handle_command(state: SessionState, user_input: str, tools: list[Tool], client: OpenAI) -> bool:
    """Esegue un comando slash. Restituisce True se il comando era riconosciuto."""
    command, _, arg = user_input.partition(" ")
    arg = arg.strip()

    if command == "/context":
        cmd_context(state, tools)
    elif command == "/clear":
        state.reset_messages()
        print("Conversazione azzerata (conteggi cumulativi e log mantenuti).")
    elif command == "/yolo":
        cmd_yolo(state)
    elif command == "/tools":
        cmd_tools(tools)
    elif command == "/log":
        cmd_log(state)
    elif command == "/cost":
        print(
            f"Costo cumulativo: {fmt_cost(state.total_cost)} "
            f"({state.total_prompt_tokens} tok in / {state.total_completion_tokens} tok out)"
        )
    elif command == "/compact":
        # Il client serve solo a /compact llm: e' l'unica ragione per cui questa funzione
        # riceve il client OpenAI.
        cmd_compact(state, arg, client)
    elif command == "/reasoning":
        cmd_reasoning(state, arg)
    elif command == "/save":
        cmd_save(state)
    elif command == "/load":
        cmd_load(state, arg)
    elif command == "/model":
        cmd_model(state)
    else:
        return False
    return True


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------


def _maybe_offer_credentials_template(workdir: Path, ctx: Context) -> None:
    """Se credentials.md manca e la sessione e' interattiva, propone di crearne uno."""
    if ctx.credentials.content is not None or not sys.stdin.isatty():
        return
    try:
        create = questionary.confirm(
            "credentials.md non trovato. Crearne uno di esempio nella cartella di lavoro?",
            default=False,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return
    if create:
        target = workdir / "credentials.md"
        try:
            target.write_text(CREDENTIALS_TEMPLATE, encoding="utf-8")
            print(f"Creato: {target}")
        except OSError as exc:
            print(f"[Avviso] impossibile creare credentials.md: {exc}")


def main(
    workdir: Path | None = typer.Option(None, "--workdir", help="Cartella di lavoro (sandbox dei tool filesystem)."),
    model: str | None = typer.Option(None, "--model", help="ID OpenRouter del modello iniziale."),
    yolo: bool = typer.Option(False, "--yolo", help="Disattiva tutte le conferme di sicurezza (usare con cautela)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simula le azioni (write/edit/send/run) senza eseguirle."),
    reasoning: str = typer.Option("medium", "--reasoning", help="Livello di reasoning: low|medium|high|xhigh."),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Disabilita gli strumenti MCP."),
    prompt: str | None = typer.Option(
        None, "--prompt", help="Esegue un solo turno con questo messaggio e termina (per cron e script)."
    ),
) -> None:
    """ernesto — agente da terminale con strumenti, basato su OpenRouter."""
    _configure_console()
    workdir = (workdir or Path.cwd()).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    # .env come fallback: popola os.environ solo per le chiavi non gia' presenti, quindi
    # quello del progetto vince su quello globale. Senza il secondo, lanciare ernesto su un
    # progetto qualsiasi richiederebbe di copiare le chiavi in ogni cartella.
    load_env_file(workdir / ".env")
    load_env_file(config_dir() / ".env")

    # Stesso timestamp per log e memoria di sessione: si ritrovano a coppie
    session_stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    session_memory = f"{MEMORY_DIR}/memory-{session_stamp}.md"
    ctx = load_context(workdir, session_memory)
    # Con --prompt la sessione non e' presidiata: nessuna domanda interattiva all'avvio,
    # altrimenti un'esecuzione da cron resterebbe appesa su una richiesta che nessuno vede.
    if not prompt:
        _maybe_offer_credentials_template(workdir, ctx)

    env_vars = extract_env_vars(ctx.credentials.content or "")
    check = verify_env_vars(env_vars)
    if check.fatal_missing:
        print(f"Errore: {check.fatal_missing[0]} non trovata tra le variabili d'ambiente.")
        print(
            "Consulta credentials.md (nella cartella di lavoro o in ~/.config/ernesto/) "
            "per le istruzioni su come configurarla."
        )
        raise typer.Exit(1)
    # Avvisi raccolti e stampati dopo il banner (altrimenti il clear li cancellerebbe)
    startup_warnings = [
        f"[Avviso] variabile opzionale {name} mancante: lo strumento corrispondente rispondera' errore."
        for name in check.optional_missing
    ]

    if reasoning not in REASONING_LEVELS:
        print(f"Errore: --reasoning non valido: {reasoning}. Usa: {', '.join(REASONING_LEVELS)}")
        raise typer.Exit(1)

    # Precedenza del modello iniziale: --model, poi model.default in config.yaml, poi il
    # default del registry.
    model_cfg = config_section(workdir, "model")
    initial_model = DEFAULT_MODEL
    configured = model_cfg.get("default")
    if configured:
        found = find_model(str(configured))
        if found is None:
            startup_warnings.append(f"[Avviso] model.default '{configured}' non nel registry: ignorato.")
        else:
            initial_model = found
    if model:
        found = find_model(model)
        if found is None:
            print(f"[Avviso] modello '{model}' non nel registry: uso {initial_model.label}.")
        else:
            initial_model = found
    initial_json_mode = bool(model_cfg.get("json_mode", False)) and initial_model.json_supported

    api_key = os.environ["OPENROUTER_API_KEY"]
    client = OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://mavida.com",
            "X-Title": "Mavida Chat CLI",
        },
    )

    print("Caricamento prezzi...", end="", flush=True)
    load_pricing(api_key)
    print(" ok")

    # Valori delle credenziali presenti: mai stampati ne' loggati in chiaro
    secrets = [os.environ[name] for name in check.present if os.environ.get(name)]
    logger = SessionLogger(workdir, secrets, session_stamp)

    state = SessionState(
        model=initial_model,
        workdir=workdir,
        context=ctx,
        logger=logger,
        yolo=yolo,
        dry_run=dry_run,
        reasoning_effort=reasoning,
        json_mode=initial_json_mode,
    )
    state.reset_messages()

    confirm_fn = make_confirm_fn(state)
    tools = build_native_tools(state, confirm_fn)
    # Riassunto LLM in compattazione: attivo solo se richiesto in config.yaml, e comunque
    # previa conferma esplicita al primo turno.
    llm_summary_enabled = bool(config_section(workdir, "compact").get("llm_summary", False))
    llm_summary_asked = False
    mcp_tools, mcp_warnings = load_mcp_tools(workdir, enabled=not no_mcp)
    tools.extend(mcp_tools)
    startup_warnings.extend(f"[Avviso] {w}" for w in mcp_warnings)
    if state.yolo:
        startup_warnings.append(
            "YOLO attivo — conferme disattivate: il modello eseguira' comandi e invii senza chiedere."
        )
    if state.dry_run:
        startup_warnings.append("DRY-RUN attivo — write/edit/send/run saranno solo simulati.")

    # Modalita' non presidiata: un turno solo, niente banner ne' schermo pulito, cosi'
    # l'output del processo contiene la risposta e nient'altro.
    if prompt:
        for warning in startup_warnings:
            print(warning)
        state.messages.append({"role": "user", "content": prompt})
        logger.log("user", content=prompt)
        try:
            run_turn(state, client, tools)
        except KeyboardInterrupt:
            print("\n[Interrotto] turno annullato dall'utente (Ctrl+C).")
        print(
            f"[{state.total_prompt_tokens} tok in / {state.total_completion_tokens} out "
            f"· {fmt_cost(state.total_cost)} · log {logger.path}]"
        )
        return

    _clear_screen()
    _print_banner(state, logger)
    for warning in startup_warnings:
        print(warning)
    print()

    while True:
        try:
            _prompt_rule()
            user_input = input(prompt_indicator(state)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nArrivederci!")
            break

        if user_input.lower() in {"exit", "quit"}:
            print("Arrivederci!")
            break
        if not user_input:
            continue
        if user_input.startswith("/") and handle_command(state, user_input, tools, client):
            continue

        # Una volta per turno, mai dentro il ciclo di step: l'agente puo' aver scritto una
        # memoria e l'indice nel system prompt va aggiornato, ma cambiare il prompt a ogni
        # step distruggerebbe il prompt caching del provider.
        if state.refresh_system_prompt():
            print("[Memoria] indice delle memorie aggiornato.")

        # Riassunto LLM nella compattazione automatica: si chiede una volta per sessione,
        # perche' comporta una chiamata API per ogni risultato compattato.
        if llm_summary_enabled and state.summarizer is None and not llm_summary_asked:
            llm_summary_asked = True
            modello_riassunto = summary_model_id(workdir)
            if confirm_fn(
                f"Compattare con riassunti generati da {modello_riassunto} (una chiamata per risultato)?",
                preview=None,
                level=LEVEL_WARNING,
            ):
                state.summarizer = make_summarizer(state, client)
                print(f"[Compattazione] i riassunti useranno {modello_riassunto}.")
            else:
                print("[Compattazione] resta il riassunto deterministico (nessuna chiamata extra).")

        state.messages.append({"role": "user", "content": user_input})
        state.logger.log("user", content=user_input)

        print(f"{state.model.label}> ", end="", flush=True)
        try:
            run_turn(state, client, tools)
        except KeyboardInterrupt:
            # Rete di sicurezza: run_turn gestisce gia' Ctrl+C, ma non si sa mai
            print("\n[Interrotto] turno annullato dall'utente (Ctrl+C).")


def run() -> None:
    """Entry point: avvia la CLI con typer (comando singolo)."""
    typer.run(main)
