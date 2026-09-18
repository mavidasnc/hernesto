"""Loop agentico: streaming con tool calls, righe di step e guard rail sui turni."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from openai import APIConnectionError, APIError, APIStatusError

from .config import API_RETRY_WAIT_SECONDS, API_STREAM_RETRIES, COMPACT_THRESHOLD_TOKENS
from .session import compact_tool_results, fmt_duration, fmt_tokens
from .tools import tool_schemas

if TYPE_CHECKING:
    from openai import OpenAI

    from .session import SessionState
    from .tools import Tool


def run_tool_call(tools_by_name: dict[str, Tool], tool_call: dict[str, Any]) -> str:
    """Esegue una tool call senza mai lanciare eccezioni.

    Gli `arguments` JSON malformati producono un risultato "ERRORE: ..." che viene
    rimandato al modello come messaggio tool, senza interrompere il loop.
    """
    function = tool_call.get("function", {})
    name = function.get("name", "")
    raw_args = function.get("arguments") or ""
    try:
        args = json.loads(raw_args) if raw_args.strip() else {}
        if not isinstance(args, dict):
            raise TypeError("gli argomenti devono essere un oggetto JSON")
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERRORE: argomenti JSON non validi: {exc}"
    tool = tools_by_name.get(name)
    if tool is None:
        return f"ERRORE: strumento sconosciuto: {name}"
    try:
        return tool.run(**args)
    except Exception as exc:  # rete di sicurezza: i tool non devono lanciare
        return f"ERRORE: esecuzione di {name} fallita: {exc}"


def _summarize(result: str, limit: int = 60) -> str:
    """Prima riga del risultato, troncata, per la riga di step."""
    first = result.splitlines()[0] if result else ""
    return first if len(first) <= limit else first[:limit] + "…"


def _tools_unsupported_error(exc: APIStatusError) -> bool:
    """True se l'errore API indica che il provider non supporta il tool calling."""
    return "tool" in str(exc).lower()


def _print_content(delta: str, state: list[int]) -> None:
    """Stampa un delta di contenuto ripulendo le righe vuote.

    Due regole, solo a console (il contenuto in storia resta originale):
    - prima del primo carattere visibile spazi e a-capo non si stampano: nei turni
      con tool call il modello emette spesso solo "\\n\\n", che sommato al print()
      delle righe di step produceva due o tre righe vuote tra uno step e l'altro;
    - a risposta iniziata, le righe vuote ripetute collassano a una sola.

    `state` e' una lista [newline di fila stampate, risposta iniziata]: mutabile
    perche' deve sopravvivere tra i delta dello stream.
    """
    out = []
    for ch in delta:
        if not state[1]:
            if ch.isspace():
                continue
            state[1] = 1
        if ch == "\n":
            if state[0] >= 2:
                continue
            state[0] += 1
        else:
            state[0] = 0
        out.append(ch)
    if out:
        print("".join(out), end="", flush=True)


def _consume_stream(stream: Any) -> tuple[str, list[dict[str, Any]], int, int]:
    """Consuma lo stream stampando i delta e accumulando content, tool_calls e usage.

    Le tool calls arrivano a chunk parziali: vengono accumulate per `index`
    (id, function.name, function.arguments concatenati).
    """
    content = ""
    partial: dict[int, dict[str, str]] = {}
    prompt_tokens = 0
    completion_tokens = 0
    print_state = [0, 0]
    for chunk in stream:
        # L'ultimo chunk porta usage quando stream_options include_usage e' True
        if chunk.usage:
            prompt_tokens = chunk.usage.prompt_tokens or 0
            completion_tokens = chunk.usage.completion_tokens or 0
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue
        if delta.content:
            _print_content(delta.content, print_state)
            content += delta.content
        for tc in delta.tool_calls or []:
            slot = partial.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                slot["id"] += tc.id
            if tc.function:
                if tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
    tool_calls = [
        {
            "id": slot["id"] or f"call_{index}",
            "type": "function",
            "function": {"name": slot["name"], "arguments": slot["arguments"]},
        }
        for index, slot in sorted(partial.items())
    ]
    return content, tool_calls, prompt_tokens, completion_tokens


def run_turn(
    state: SessionState,
    client: OpenAI,
    tools: list[Tool],
    compact_confirm: Callable[[int], bool] | None = None,
) -> None:
    """Esegue un turno agentico: chiama il modello e cicla sui tool fino alla risposta finale.

    `compact_confirm` (solo sessioni interattive) riceve la stima dei token in storia
    quando si supera la soglia di compattazione e decide se compattare; viene chiamata
    al massimo una volta per turno. None = compattazione automatica (non presidiato).
    """
    tools_by_name = {t.name: t for t in tools}
    schemas = tool_schemas(tools)
    rewind_index = len(state.messages) - 1  # posizione dell'ultimo user message
    compact_asked = False

    # Il tempo del turno comprende le chiamate al modello, gli strumenti e le attese
    # di conferma: e' il tempo che l'utente aspetta davvero. `perf_counter` e non
    # `monotonic` perche' su Windows quest'ultimo si muove a scatti di ~15 ms, troppo
    # grossolani per i turni brevi. Il `finally` registra anche le uscite anticipate,
    # cosi' il cumulativo di sessione non perde i turni finiti in errore o interrotti.
    inizio = time.perf_counter()
    tempo_registrato = False

    try:
        for step in range(1, state.max_steps + 1):
            # Compattazione prima della chiamata: il risparmio vale gia' sullo step che la
            # innesca. Non cambia la lunghezza della lista, quindi rewind_index resta valido.
            estimate = state.history_token_estimate()
            if estimate > COMPACT_THRESHOLD_TOKENS:
                do_compact = True
                if compact_confirm is not None and not compact_asked:
                    compact_asked = True
                    do_compact = compact_confirm(estimate)
                if do_compact:
                    compacted, saved = compact_tool_results(state.messages, summarizer=state.summarizer)
                    if compacted:
                        state.compacted_count += compacted
                        state.compacted_tokens += saved
                        print(
                            f"\n[Compattazione] {compacted} risultati strumento riassunti "
                            f"· ~{fmt_tokens(saved)} tok in meno"
                        )
                        if state.logger:
                            state.logger.log("compact", messages=compacted, saved_tokens=saved)
            call_kwargs: dict[str, Any] = {
                "model": state.model.id,
                "messages": state.messages,
                "stream": True,
                # include_usage fa si' che l'ultimo chunk contenga i conteggi token
                "stream_options": {"include_usage": True},
                "extra_body": {"reasoning": {"effort": state.reasoning_effort}},
            }
            if state.json_mode:
                call_kwargs["response_format"] = {"type": "json_object"}
            # JSON mode (response_format json_object) e' incompatibile col tool calling:
            # il modello emetterebbe un blob JSON testuale invece di tool calls native.
            if state.tools_enabled and schemas and not state.json_mode:
                call_kwargs["tools"] = schemas

            # Retry sulle cadute di rete: "Network connection lost" puo' arrivare a meta'
            # stream, dove i retry del SDK non arrivano. La chiamata e' idempotente e il
            # contenuto parziale non e' ancora in storia: si ricrea la richiesta identica.
            # Il testo gia' stampato resta su schermo, quindi il nuovo tentativo e'
            # annunciato per non sembrare una ripetizione.
            tentativi = 0
            while True:
                try:
                    stream = client.chat.completions.create(**call_kwargs)
                    content, tool_calls, prompt_tok, completion_tok = _consume_stream(stream)
                    esito = "ok"
                except APIStatusError as exc:
                    if state.tools_enabled and "tools" in call_kwargs and _tools_unsupported_error(exc):
                        # Degradazione: il provider non supporta i tool, riprovo senza (avviso una volta)
                        state.tools_enabled = False
                        print("\n[Avviso] questo provider non supporta strumenti: continuo senza tools.")
                        esito = "senza_tools"
                    else:
                        print(f"\n[Errore API {exc.status_code}] {exc.message}")
                        esito = "fatale"
                except (APIConnectionError, APIError) as exc:
                    tentativi += 1
                    if tentativi <= API_STREAM_RETRIES:
                        attesa = API_RETRY_WAIT_SECONDS * tentativi
                        print(
                            f"\n[Connessione persa] {exc} — "
                            f"riprovo ({tentativi}/{API_STREAM_RETRIES}) tra {attesa:.0f}s…"
                        )
                        time.sleep(attesa)
                        continue
                    print(f"\n[Errore di rete] {exc} — rinuncio dopo {tentativi} tentativi.")
                    esito = "fatale"
                except KeyboardInterrupt:
                    # Ctrl+C durante lo streaming: annulla il turno, torna al prompt
                    print("\n[Interrotto] turno annullato dall'utente (Ctrl+C).")
                    esito = "fatale"
                break

            if esito == "senza_tools":
                continue
            if esito == "fatale":
                del state.messages[rewind_index:]
                return

            state.record_usage(prompt_tok, completion_tok)

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content or None}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            state.messages.append(assistant_msg)
            if state.logger:
                state.logger.log(
                    "assistant",
                    model=state.model.id,
                    content=content,
                    tool_calls=len(tool_calls),
                    usage={"prompt": prompt_tok, "completion": completion_tok},
                )

            if not tool_calls:
                # Risposta finale: token e costo dell'ultima chiamata, poi il tempo del
                # turno intero e quello speso finora nella sessione.
                state.record_time(time.perf_counter() - inizio)
                tempo_registrato = True
                print()
                if prompt_tok or completion_tok:
                    cost = prompt_tok * state.model.price_prompt + completion_tok * state.model.price_completion
                    print(
                        f"[{prompt_tok} tok in / {completion_tok} tok out · ${cost:.6f}"
                        f" · {fmt_duration(state.last_seconds)} · {fmt_duration(state.total_seconds)} tot]"
                    )
                else:
                    print(f"[{fmt_duration(state.last_seconds)} · {fmt_duration(state.total_seconds)} tot]")
                print()
                return

            print()
            for tool_call in tool_calls:
                try:
                    result = run_tool_call(tools_by_name, tool_call)
                except KeyboardInterrupt:
                    # Ctrl+C durante uno strumento (es. run_command): il tool ha gia'
                    # ucciso il processo figlio; qui annullo il turno e torno al prompt
                    print("\n[Interrotto] esecuzione strumento annullata dall'utente (Ctrl+C).")
                    del state.messages[rewind_index:]
                    return
                state.tool_calls_count += 1
                name = tool_call["function"]["name"]
                print(
                    f"  step {step}/{state.max_steps} · +{fmt_tokens(prompt_tok)} in · "
                    f"+{fmt_tokens(completion_tok)} out · {name} → {_summarize(result)}"
                )
                state.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": name,
                        "content": result,
                    }
                )
                if state.logger:
                    state.logger.log("tool", tool_call_id=tool_call["id"], name=name, content=result)

            # Una conferma distruttiva negata senza nessuno al terminale chiude il turno
            # invece di tornare al modello come errore: altrimenti il passo successivo e'
            # il tentativo di ottenere lo stesso risultato per un'altra strada.
            if state.abort_reason:
                print(f"\n[Interrotto] azione distruttiva non autorizzata: {state.abort_reason}\n")
                return

        print(f"\n[Guard rail] raggiunto il limite di {state.max_steps} step: interrompo il loop.\n")
    finally:
        if not tempo_registrato:
            state.record_time(time.perf_counter() - inizio)
