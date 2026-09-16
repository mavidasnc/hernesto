"""Interfaccia a riga di comando di ernesto: avvio (typer), REPL e comandi slash."""

from __future__ import annotations

import contextlib
import os
import sys
from datetime import datetime
from pathlib import Path

import questionary
import typer
from openai import OpenAI

from . import __version__
from .agent import run_turn
from .config import OPENROUTER_BASE, load_env_file
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
    estimate_tokens,
    fmt_cost,
    fmt_tokens,
    prompt_indicator,
)
from .tools import ConfirmFn, Tool, build_native_tools

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
    "/context · /clear · /model · /tools · /reasoning [livello] · /yolo · "
    "/log · /cost · /save · exit/quit · Ctrl+C"
)


def _configure_console() -> None:
    """Evita crash su console Windows non-UTF8 con i caratteri ✓/✗/·."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")


def make_confirm_fn(state: SessionState) -> ConfirmFn:
    """Callback di conferma: questionary se TTY; se stdin non e' un TTY, default False."""

    def confirm(message: str, preview: str | None = None) -> bool:
        if state.yolo:
            return True
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
    print(f"Modello: {selected.label}{suffix} — conversazione azzerata.\n")


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
    print(f"Salvato: {filepath}")


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
    print(f"Messaggi in storia: {len(state.messages)} (~{fmt_tokens(state.history_token_estimate())} tok stimati)")
    native = [t.name for t in tools if not t.name.startswith("mcp__")]
    mcp = [t.name for t in tools if t.name.startswith("mcp__")]
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
    print(
        f"Token totali: {state.total_prompt_tokens} in / {state.total_completion_tokens} out "
        f"· costo cumulativo {fmt_cost(state.total_cost)}"
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


def handle_command(state: SessionState, user_input: str, tools: list[Tool]) -> bool:
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
    elif command == "/reasoning":
        cmd_reasoning(state, arg)
    elif command == "/save":
        cmd_save(state)
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
) -> None:
    """ernesto — agente da terminale con strumenti, basato su OpenRouter."""
    _configure_console()
    workdir = (workdir or Path.cwd()).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    # .env come fallback: popola os.environ solo per le chiavi non gia' presenti
    load_env_file(workdir / ".env")

    ctx = load_context(workdir)
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
    for name in check.optional_missing:
        print(f"[Avviso] variabile opzionale {name} mancante: lo strumento corrispondente rispondera' errore.")

    if reasoning not in REASONING_LEVELS:
        print(f"Errore: --reasoning non valido: {reasoning}. Usa: {', '.join(REASONING_LEVELS)}")
        raise typer.Exit(1)

    initial_model = DEFAULT_MODEL
    if model:
        found = find_model(model)
        if found is None:
            print(f"[Avviso] modello '{model}' non nel registry: uso {DEFAULT_MODEL.label}.")
        else:
            initial_model = found

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
    logger = SessionLogger(workdir, secrets)

    state = SessionState(
        model=initial_model,
        workdir=workdir,
        context=ctx,
        logger=logger,
        yolo=yolo,
        dry_run=dry_run,
        reasoning_effort=reasoning,
    )
    state.reset_messages()

    tools = build_native_tools(state, make_confirm_fn(state))
    mcp_tools, mcp_warnings = load_mcp_tools(workdir, enabled=not no_mcp)
    tools.extend(mcp_tools)
    for warning in mcp_warnings:
        print(f"[Avviso] {warning}")

    print(f"\nernesto v{__version__} — modello attivo: {state.model.label}")
    print(summary_line(ctx))
    print(f"Log: {logger.path}")
    if state.yolo:
        print("YOLO attivo — conferme disattivate: il modello eseguira' comandi e invii senza chiedere.")
    if state.dry_run:
        print("DRY-RUN attivo — write/edit/send/run saranno solo simulati.")
    print(f"Comandi: {COMANDI}\n")

    while True:
        try:
            user_input = input(prompt_indicator(state)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nArrivederci!")
            break

        if user_input.lower() in {"exit", "quit"}:
            print("Arrivederci!")
            break
        if not user_input:
            continue
        if user_input.startswith("/") and handle_command(state, user_input, tools):
            continue

        state.messages.append({"role": "user", "content": user_input})
        state.logger.log("user", content=user_input)

        print(f"{state.model.label}> ", end="", flush=True)
        run_turn(state, client, tools)


def run() -> None:
    """Entry point: avvia la CLI con typer (comando singolo)."""
    typer.run(main)
