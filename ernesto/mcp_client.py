"""Integrazione opzionale con server MCP (stdio) configurati in mcp.json.

Se la libreria `mcp` non e' installata o un server non parte, il caricamento
produce un avviso non fatale e la sessione continua senza quegli strumenti.
Gli strumenti MCP sono registrati come `mcp__<server>__<tool>`, eseguiti con
timeout di 60s e output troncato a 8000 caratteri.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .config import MCP_TOOL_TIMEOUT, TOOL_OUTPUT_LIMIT, config_dir
from .tools import Tool

_MCP_LIST_TIMEOUT = 30


def find_mcp_config(workdir: Path) -> Path | None:
    """Cerca mcp.json nella workdir poi in ~/.config/ernesto/."""
    for candidate in (workdir / "mcp.json", config_dir() / "mcp.json"):
        if candidate.is_file():
            return candidate
    return None


def _server_params(server_cfg: dict[str, Any]) -> Any:
    """Costruisce gli StdioServerParameters per un server configurato."""
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=server_cfg["command"],
        args=server_cfg.get("args", []),
        env=server_cfg.get("env"),
    )


async def _list_tools(server_cfg: dict[str, Any]) -> list[Any]:
    """Avvia il server in stdio e restituisce la lista dei suoi strumenti."""
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(server_cfg)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return list((await session.list_tools()).tools)


async def _call_tool(server_cfg: dict[str, Any], tool_name: str, arguments: dict[str, Any]) -> str:
    """Esegue una chiamata `tools/call` aprendo una sessione stdio dedicata."""
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_server_params(server_cfg)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)
    parts = [getattr(c, "text", None) or str(c) for c in result.content]
    return "\n".join(parts) or "(nessun output)"


class McpTool(Tool):
    """Proxy verso uno strumento esposto da un server MCP (stdio)."""

    def __init__(
        self,
        server_name: str,
        server_cfg: dict[str, Any],
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> None:
        self.name = f"mcp__{server_name}__{tool_name}"
        self.description = description or f"Strumento MCP {tool_name} (server {server_name})"
        self.parameters = schema or {"type": "object", "properties": {}}
        self._server_cfg = server_cfg
        self._tool_name = tool_name

    def run(self, **kwargs: Any) -> str:
        try:
            result = asyncio.run(
                asyncio.wait_for(
                    _call_tool(self._server_cfg, self._tool_name, kwargs),
                    timeout=MCP_TOOL_TIMEOUT,
                )
            )
        except TimeoutError:
            return f"ERRORE: timeout di {MCP_TOOL_TIMEOUT}s nello strumento MCP {self.name}"
        except Exception as exc:
            return f"ERRORE: strumento MCP {self.name} fallito: {exc}"
        if len(result) > TOOL_OUTPUT_LIMIT:
            result = result[:TOOL_OUTPUT_LIMIT] + f"\n…[output troncato a {TOOL_OUTPUT_LIMIT} caratteri]"
        return result


def load_mcp_tools(workdir: Path, enabled: bool = True) -> tuple[list[Tool], list[str]]:
    """Carica gli strumenti MCP configurati. Restituisce (tool, avvisi): mai fatale."""
    warnings: list[str] = []
    if not enabled:
        return [], warnings
    cfg_path = find_mcp_config(workdir)
    if cfg_path is None:
        return [], warnings
    try:
        import mcp  # noqa: F401
    except ImportError:
        warnings.append(
            "mcp.json trovato ma la libreria 'mcp' non e' installata: "
            "strumenti MCP disabilitati (pip install mcp)."
        )
        return [], warnings
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"mcp.json non leggibile: {exc}")
        return [], warnings
    tools: list[Tool] = []
    for server_name, server_cfg in (config.get("mcpServers") or {}).items():
        try:
            remote_tools = asyncio.run(asyncio.wait_for(_list_tools(server_cfg), timeout=_MCP_LIST_TIMEOUT))
            for remote in remote_tools:
                tools.append(
                    McpTool(
                        server_name,
                        server_cfg,
                        remote.name,
                        getattr(remote, "description", "") or "",
                        getattr(remote, "inputSchema", None) or {},
                    )
                )
        except Exception as exc:
            warnings.append(f"Server MCP '{server_name}' non avviato: {exc}")
    return tools, warnings
