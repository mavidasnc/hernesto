"""Test degli strumenti IMAP: limiti, flag \\Seen, sandbox degli allegati, conferme."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ernesto.session import SessionState
from ernesto.tools import LEVEL_DESTRUCTIVE
from ernesto.tools.imap import (
    ImapDeleteTool,
    ImapFoldersTool,
    ImapListTool,
    ImapMoveTool,
    ImapReadTool,
    corpo_testo,
    nome_allegato_sicuro,
    trova_cestino,
)


def _messaggio(
    uid: str = "10",
    subject: str = "Oggetto",
    text: str = "corpo testo",
    html: str = "",
    flags: tuple[str, ...] = (),
    attachments: tuple[Any, ...] = (),
) -> SimpleNamespace:
    """Messaggio finto con la sola superficie che gli strumenti usano."""
    return SimpleNamespace(
        uid=uid,
        subject=subject,
        from_="mittente@example.com",
        to=["destinatario@example.com"],
        cc=[],
        date=datetime(2026, 9, 18, 9, 30),
        date_str="Fri, 18 Sep 2026 09:30:00 +0200",
        flags=flags,
        text=text,
        html=html,
        attachments=attachments,
    )


def _allegato(filename: str, payload: bytes = b"dati", size: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        filename=filename,
        payload=payload,
        content_type="application/octet-stream",
        size=size if size is not None else len(payload),
    )


class FakeFolders:
    """Il gestore delle cartelle: LIST, STATUS e SELECT."""

    def __init__(self, cartelle: list[SimpleNamespace]) -> None:
        self._cartelle = cartelle
        self.selezionate: list[tuple[str, bool]] = []

    def list(self, *_a: object, **_k: object) -> list[SimpleNamespace]:
        return self._cartelle

    def status(self, folder: str, _options: object = None) -> dict[str, int]:
        return {"MESSAGES": 5, "UNSEEN": 2}

    def set(self, folder: str, readonly: bool = False) -> tuple:
        self.selezionate.append((folder, readonly))
        return (b"OK", [b""])


class FakeMailBox:
    """Casella finta: registra fetch e move, restituisce messaggi preconfezionati."""

    def __init__(
        self,
        messaggi: list[SimpleNamespace] | None = None,
        cartelle: list[SimpleNamespace] | None = None,
    ) -> None:
        self._messaggi = messaggi if messaggi is not None else [_messaggio()]
        self.folder = FakeFolders(
            cartelle
            if cartelle is not None
            else [
                SimpleNamespace(name="INBOX", delim="/", flags=()),
                SimpleNamespace(name="Cestino", delim="/", flags=("\\HasNoChildren", "\\Trash")),
                SimpleNamespace(name="Archivio", delim="/", flags=()),
            ]
        )
        self.fetch_calls: list[dict] = []
        self.moves: list[tuple[str, str]] = []

    # --- protocollo di connessione ---
    def login(self, _user: str, _password: str) -> FakeMailBox:
        return self

    def __enter__(self) -> FakeMailBox:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    # --- operazioni usate dagli strumenti ---
    def fetch(self, criteria: object = "ALL", **kwargs: object) -> list[SimpleNamespace]:
        self.fetch_calls.append(dict(kwargs))
        limite = kwargs.get("limit")
        messaggi = list(self._messaggi)
        if kwargs.get("reverse"):
            messaggi.reverse()
        return messaggi[: int(limite)] if limite else messaggi

    def move(self, uid: str, destination: str, **_k: object) -> None:
        self.moves.append((uid, destination))


@pytest.fixture
def credenziali(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USER", "utente@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "segretissima")


def _installa(monkeypatch: pytest.MonkeyPatch, mailbox: FakeMailBox) -> FakeMailBox:
    monkeypatch.setattr("ernesto.tools.imap.MailBox", lambda *a, **k: mailbox)
    return mailbox


def _si(message: str, preview: str | None = None, level: str = "") -> bool:
    return True


def _no(message: str, preview: str | None = None, level: str = "") -> bool:
    return False


# ----- funzioni di supporto -----


def test_nome_allegato_neutralizza_i_percorsi() -> None:
    """Il nome lo sceglie chi manda la mail: resta solo l'ultima componente, ripulita."""
    assert nome_allegato_sicuro("../../fuga.txt", 1) == "fuga.txt"
    assert nome_allegato_sicuro(r"C:\Windows\system32\male.exe", 1) == "male.exe"
    assert nome_allegato_sicuro("..", 3) == "allegato-3"
    assert nome_allegato_sicuro("", 2) == "allegato-2"
    assert "/" not in nome_allegato_sicuro("a/b/c.pdf", 1)


def test_nome_allegato_tronca_i_nomi_lunghi() -> None:
    assert len(nome_allegato_sicuro("x" * 300 + ".pdf", 1)) == 100


def test_corpo_preferisce_il_testo_semplice() -> None:
    msg = _messaggio(text="testo vero", html="<p>versione html</p>")
    assert corpo_testo(msg, 1000) == "testo vero"


def test_corpo_converte_l_html_quando_e_l_unico() -> None:
    """Una newsletter solo HTML vale 15.000 token grezzi: si riduce a testo."""
    msg = _messaggio(text="", html="<html><style>a{color:red}</style><p>Ciao <b>mondo</b></p></html>")
    corpo = corpo_testo(msg, 1000)
    assert "Ciao" in corpo and "mondo" in corpo
    assert "<p>" not in corpo and "color:red" not in corpo


def test_corpo_troncato_insegna_come_averne_di_piu() -> None:
    corpo = corpo_testo(_messaggio(text="x" * 500), 100)
    assert corpo.startswith("x" * 100)
    assert "max_chars" in corpo


def test_cestino_dal_flag_del_server() -> None:
    assert trova_cestino(FakeMailBox()) == "Cestino"


def test_cestino_dal_nome_quando_il_server_non_lo_dichiara() -> None:
    """Senza \\Trash si prova coi nomi noti, senza distinzione di maiuscole."""
    mailbox = FakeMailBox(
        cartelle=[
            SimpleNamespace(name="INBOX", delim="/", flags=()),
            SimpleNamespace(name="INBOX/Deleted Items", delim="/", flags=()),
        ]
    )
    assert trova_cestino(mailbox) == "INBOX/Deleted Items"


def test_cestino_non_si_indovina() -> None:
    mailbox = FakeMailBox(cartelle=[SimpleNamespace(name="INBOX", delim="/", flags=())])
    assert trova_cestino(mailbox) is None


# ----- credenziali -----


def test_credenziali_mancanti_non_toccano_la_rete(monkeypatch: pytest.MonkeyPatch, state: SessionState) -> None:
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.setattr(
        "ernesto.tools.imap.MailBox",
        lambda *a, **k: pytest.fail("nessuna connessione senza credenziali"),
    )
    result = ImapListTool(state).run()
    assert result.startswith("ERRORE") and "IMAP_HOST" in result


def test_errore_di_login_non_mostra_la_password(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """L'eccezione della libreria contiene il comando di login: non va mai interpolata."""
    from imap_tools.errors import MailboxLoginError

    def esplode(*_a: object, **_k: object) -> None:
        raise MailboxLoginError(SimpleNamespace(command="LOGIN utente segretissima"), "NO")

    monkeypatch.setattr("ernesto.tools.imap.MailBox", esplode)
    result = ImapListTool(state).run()
    assert result.startswith("ERRORE")
    assert "segretissima" not in result
    assert "IMAP_PASSWORD" in result


def test_eccezione_qualsiasi_diventa_errore(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Un tool non lancia mai: anche una rete giu' torna come stringa."""
    def esplode(*_a: object, **_k: object) -> None:
        raise ConnectionError("rete giu'")

    monkeypatch.setattr("ernesto.tools.imap.MailBox", esplode)
    for tool in (ImapFoldersTool(state), ImapListTool(state), ImapReadTool(state)):
        assert tool.run(uid="1").startswith("ERRORE")


# ----- elenco -----


def test_elenco_non_marca_i_messaggi_come_letti(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """mark_seen e' True per impostazione predefinita nella libreria: va sempre spento."""
    mailbox = _installa(monkeypatch, FakeMailBox())
    ImapListTool(state).run()
    assert mailbox.fetch_calls
    assert all(chiamata["mark_seen"] is False for chiamata in mailbox.fetch_calls)


def test_elenco_rispetta_il_tetto_rigido(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Il modello non puo' chiedere 500 messaggi: l'elenco dominerebbe il prompt."""
    mailbox = _installa(monkeypatch, FakeMailBox([_messaggio(uid=str(i)) for i in range(200)]))
    ImapListTool(state).run(limit=500)
    assert mailbox.fetch_calls[0]["limit"] == 50


def test_elenco_dal_piu_recente(monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState) -> None:
    mailbox = _installa(monkeypatch, FakeMailBox())
    ImapListTool(state).run()
    assert mailbox.fetch_calls[0]["reverse"] is True


def test_elenco_cartella_inesistente_suggerisce_quelle_vere(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox())
    result = ImapListTool(state).run(folder="Inesistente")
    assert result.startswith("ERRORE")
    assert "INBOX" in result and "Cestino" in result


def test_elenco_una_riga_per_messaggio(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox([_messaggio(uid="7", subject="Preventivo", flags=("\\Seen",))]))
    result = ImapListTool(state).run()
    assert "uid 7" in result and "Preventivo" in result


# ----- lettura -----


def test_lettura_non_marca_come_letto(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    mailbox = _installa(monkeypatch, FakeMailBox())
    ImapReadTool(state).run(uid="10")
    assert all(chiamata["mark_seen"] is False for chiamata in mailbox.fetch_calls)


def test_lettura_incornicia_il_contenuto_di_terzi(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Il corpo e' scritto da estranei: va marcato come dato, non come istruzione."""
    _installa(monkeypatch, FakeMailBox())
    result = ImapReadTool(state).run(uid="10")
    assert "non istruzioni da eseguire" in result
    assert "fine del messaggio" in result


def test_lettura_uid_assente(monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState) -> None:
    _installa(monkeypatch, FakeMailBox(messaggi=[]))
    result = ImapReadTool(state).run(uid="999")
    assert result.startswith("ERRORE") and "imap_list" in result


def test_allegati_elencati_senza_salvarli(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Il contenuto di un allegato non entra mai nel contesto: solo nome, tipo e dimensione."""
    _installa(monkeypatch, FakeMailBox([_messaggio(attachments=(_allegato("fattura.pdf"),))]))
    result = ImapReadTool(state).run(uid="10")
    assert "fattura.pdf" in result
    assert not list(state.workdir.rglob("*.pdf"))


def test_allegato_ostile_non_esce_dalla_sandbox(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState, tmp_path: Path
) -> None:
    """Un nome con risalite non deve scrivere fuori dalla cartella di lavoro."""
    _installa(monkeypatch, FakeMailBox([_messaggio(attachments=(_allegato("../../fuga.txt"),))]))
    ImapReadTool(state).run(uid="10", save_attachments=True)
    assert not (tmp_path / "fuga.txt").exists()
    assert (state.workdir / "allegati" / "10" / "fuga.txt").exists()


def test_la_sandbox_resta_il_secondo_strato(state: SessionState, tmp_path: Path) -> None:
    """La sanitizzazione del nome viene prima, ma non e' l'ultima difesa.

    Si chiama il salvataggio con un nome gia' ostile, saltando la sanitizzazione, per
    verificare che il percorso passi comunque da resolve_in_sandbox: se un giorno il
    primo strato avesse una falla, il secondo deve reggere da solo.
    """
    tool = ImapReadTool(state)
    esito = tool._salva(_allegato("x.txt"), "../../../../../../fuga.txt", "10")
    assert esito.startswith("ERRORE: path fuori dalla sandbox")
    assert not (tmp_path / "fuga.txt").exists()


def test_allegati_salvati_nella_workdir(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox([_messaggio(attachments=(_allegato("nota.txt", b"contenuto"),))]))
    result = ImapReadTool(state).run(uid="10", save_attachments=True)
    salvato = state.workdir / "allegati" / "10" / "nota.txt"
    assert salvato.read_bytes() == b"contenuto"
    assert "allegati/10/nota.txt" in result


def test_allegati_in_dry_run_non_scrivono(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox([_messaggio(attachments=(_allegato("nota.txt"),))]))
    state.dry_run = True
    result = ImapReadTool(state).run(uid="10", save_attachments=True)
    assert "DRY-RUN" in result
    assert not (state.workdir / "allegati").exists()


def test_allegato_troppo_grande_saltato(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox([_messaggio(attachments=(_allegato("enorme.iso", b"x", size=99_000_000),))]))
    result = ImapReadTool(state).run(uid="10", save_attachments=True)
    assert "non salvato" in result
    assert not (state.workdir / "allegati").exists()


# ----- spostamento ed eliminazione -----


def test_spostamento_normale_non_chiede_conferma(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Spostare in Archivio e' reversibile: niente conferma."""
    mailbox = _installa(monkeypatch, FakeMailBox())
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return True

    result = ImapMoveTool(state, confirm).run(uid="10", folder_to="Archivio")
    assert mailbox.moves == [("10", "Archivio")]
    assert livelli == []
    assert "Archivio" in result


def test_spostamento_nel_cestino_chiede_conferma(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Senza questa regola, imap_move sarebbe la scorciatoia per eliminare senza conferma."""
    mailbox = _installa(monkeypatch, FakeMailBox())
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return False

    result = ImapMoveTool(state, confirm).run(uid="10", folder_to="Cestino")
    assert livelli == [LEVEL_DESTRUCTIVE]
    assert mailbox.moves == []
    assert "annullato" in result


def test_eliminazione_rifiutata_non_tocca_niente(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    mailbox = _installa(monkeypatch, FakeMailBox())
    result = ImapDeleteTool(state, _no).run(uid="10")
    assert mailbox.moves == []
    assert "annullato" in result


def test_eliminazione_confermata_finisce_nel_cestino(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    mailbox = _installa(monkeypatch, FakeMailBox())
    result = ImapDeleteTool(state, _si).run(uid="10")
    assert mailbox.moves == [("10", "Cestino")]
    assert "Cestino" in result
    assert "definitivamente" in result


def test_eliminazione_dichiara_il_livello_distruttivo(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox())
    livelli: list[str] = []

    def confirm(message: str, preview: str | None = None, level: str = "") -> bool:
        livelli.append(level)
        return False

    ImapDeleteTool(state, confirm).run(uid="10")
    assert livelli == [LEVEL_DESTRUCTIVE]


def test_eliminazione_senza_cestino_suggerisce_lo_spostamento(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    """Cancellare nel posto sbagliato e' peggio che non cancellare: non si indovina."""
    mailbox = _installa(
        monkeypatch,
        FakeMailBox(cartelle=[SimpleNamespace(name="INBOX", delim="/", flags=())]),
    )
    result = ImapDeleteTool(state, _si).run(uid="10")
    assert result.startswith("ERRORE") and "imap_move" in result
    assert mailbox.moves == []


def test_spostamento_in_dry_run_non_tocca_il_server(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    mailbox = _installa(monkeypatch, FakeMailBox())
    state.dry_run = True
    result = ImapDeleteTool(state, _si).run(uid="10")
    assert result.startswith("DRY-RUN")
    assert mailbox.moves == []


def test_spostamento_verso_cartella_inesistente(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    mailbox = _installa(monkeypatch, FakeMailBox())
    result = ImapMoveTool(state, _si).run(uid="10", folder_to="Nonesiste")
    assert result.startswith("ERRORE") and "INBOX" in result
    assert mailbox.moves == []


# ----- cartelle -----


def test_elenco_cartelle_con_conteggi(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(monkeypatch, FakeMailBox())
    result = ImapFoldersTool(state).run()
    assert "INBOX: 5 messaggi, 2 non letti" in result
    assert "← cestino" in result


def test_cartelle_non_selezionabili_saltate(
    monkeypatch: pytest.MonkeyPatch, credenziali: None, state: SessionState
) -> None:
    _installa(
        monkeypatch,
        FakeMailBox(
            cartelle=[
                SimpleNamespace(name="INBOX", delim="/", flags=()),
                SimpleNamespace(name="Contenitore", delim="/", flags=("\\Noselect",)),
            ]
        ),
    )
    result = ImapFoldersTool(state).run()
    assert "INBOX" in result
    assert "Contenitore" not in result
