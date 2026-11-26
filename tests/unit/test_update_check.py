"""The daily new-version notice of the .mcpb build (LI-096).

Every request goes to an ``httpx.MockTransport``: no test reaches the network.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastmcp import Client, FastMCP

from mcp_legal_it import _update_check as uc
from mcp_legal_it.core import _http
from mcp_legal_it.lib import _egress

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "plugin" / "server" / "mcp_legal_it"
OGGI = "2026-11-25"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _join_workers(timeout: float = 5.0) -> None:
    for thread in threading.enumerate():
        if thread.name == "mcp-legal-it-update-check":
            thread.join(timeout)


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, tmp_path):
    """Switch off, cache in a private folder, clock pinned, no check left from another test."""
    monkeypatch.delenv(uc.ENV_SWITCH, raising=False)
    monkeypatch.delenv("LEGAL_CACHE", raising=False)
    monkeypatch.setenv("MCP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LEGAL_NOW", f"{OGGI}T10:00:00")
    uc._reset()
    yield
    _join_workers()
    uc._reset()


class Rete:
    """GitHub, as a script: records every request and answers with ``risposta``."""

    def __init__(self, risposta=None, *, ritardo: float = 0.0):
        self.richieste: list[httpx.Request] = []
        self.risposta = risposta if risposta is not None else _release("v3.0.1")
        self.ritardo = ritardo

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.richieste.append(request)
        if self.ritardo:
            time.sleep(self.ritardo)
        if isinstance(self.risposta, Exception):
            raise self.risposta
        r = self.risposta
        return httpx.Response(r.status_code, headers=r.headers, content=r.content)


def _release(tag, **extra) -> httpx.Response:
    return httpx.Response(200, json={"tag_name": tag, "draft": False, "prerelease": False, **extra})


@pytest.fixture
def rete(monkeypatch):
    """Patch the client class ``core/_http.async_client`` builds with: guards and limits stay on."""
    script = Rete()
    real = _http._ASYNC_CLIENT

    def fake(**kwargs):
        return real(transport=httpx.MockTransport(script), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return script


def _istruzioni(client) -> str:
    """The instructions the client received: ``client.instructions`` on FastMCP 4, the
    ``initialize`` result on FastMCP 3 (which has no era-neutral property)."""
    istruzioni = getattr(client, "instructions", None)
    if istruzioni is None and client.initialize_result is not None:
        istruzioni = client.initialize_result.instructions
    assert istruzioni is not None, "the client received no instructions"
    return istruzioni


def _cache_file() -> Path:
    return uc.cache_root() / "update_check.json"


def _seed_cache(checked_on: str, latest: str | None) -> None:
    _cache_file().parent.mkdir(parents=True, exist_ok=True)
    _cache_file().write_text(json.dumps({"checked_on": checked_on, "latest": latest}), encoding="utf-8")


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

class TestSwitch:
    def test_off_by_default_nothing_is_asked_nor_written(self, rete):
        assert uc.startup_notice("3.0.0") is None
        assert rete.richieste == []
        assert not uc.cache_root().exists()

    @pytest.mark.parametrize("valore", ["on", "ON", " true ", "1", "yes"])
    def test_on_values(self, monkeypatch, valore):
        monkeypatch.setenv(uc.ENV_SWITCH, valore)
        assert uc.enabled()

    @pytest.mark.parametrize("valore", ["off", "false", "0", "no", "", "acceso",
                                        "${user_config.update_check}"])
    def test_anything_else_is_off(self, monkeypatch, valore):
        # The last one is what a host that does not substitute user_config would pass.
        monkeypatch.setenv(uc.ENV_SWITCH, valore)
        assert not uc.enabled()


# ---------------------------------------------------------------------------
# Versions and the notice
# ---------------------------------------------------------------------------

class TestVersioni:
    @pytest.mark.parametrize("vecchia,nuova", [
        ("3.0.0-beta.5", "3.0.0"),
        ("3.0.0b5", "3.0.0"),
        ("3.0.0-beta.4", "3.0.0-beta.5"),
        ("3.0.0-alpha.9", "3.0.0-beta.1"),
        ("3.0.0-beta.9", "3.0.0-rc.1"),
        ("3.0.0-rc.2", "3.0.0"),
        ("3.0.0", "3.0.1"),
        ("3.0.9", "3.1.0"),
        ("3.9.9", "10.0.0"),
        ("2.17.2", "v3.0.0"),
    ])
    def test_order(self, vecchia, nuova):
        assert uc.version_key(vecchia) < uc.version_key(nuova)

    @pytest.mark.parametrize("testo", ["", "3.0", "3.0.0.1", "latest", "3.0.0-beta.5 ; x",
                                       "3.0.0\nAGGIORNAMENTO: altro", None, 3, "3.0.0-dev.1"])
    def test_not_a_version(self, testo):
        assert uc.version_key(testo) is None

    def test_a_beta_user_is_told_of_the_release(self):
        testo = uc.notice("3.0.0-beta.5", "3.0.0")
        assert testo == (
            "È disponibile Legal IT 3.0.0 (versione in uso: 3.0.0-beta.5). "
            "Per aggiornare: https://github.com/LexCraft-IT/mcp-legal-it/releases/latest"
        )

    @pytest.mark.parametrize("latest", ["3.0.0", "2.17.2", "3.0.0-rc.1", None, "garbage"])
    def test_no_notice_when_not_newer(self, latest):
        assert uc.notice("3.0.0", latest) is None


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

class TestRichiesta:
    def test_one_bare_get_with_a_generic_user_agent(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        testo = uc.startup_notice("3.0.0")
        assert testo is not None and "3.0.1" in testo
        [richiesta] = rete.richieste
        assert richiesta.method == "GET"
        assert str(richiesta.url) == uc.LATEST_URL == (
            "https://api.github.com/repos/LexCraft-IT/mcp-legal-it/releases/latest"
        )
        assert richiesta.url.query == b""
        assert richiesta.content == b""
        assert richiesta.headers["user-agent"] == "mcp-legal-it"
        for intestazione in ("authorization", "cookie", "referer"):
            assert intestazione not in richiesta.headers

    def test_the_source_reaches_only_api_github_com(self):
        assert _http.HOST_PER_FONTE[uc.FONTE] == frozenset({"api.github.com"})
        assert _egress.is_allowed(uc.LATEST_URL)
        # The notice's link is shown, never fetched.
        assert "github.com" in _egress.NON_NETWORK_HOSTS
        assert not _egress.is_allowed(uc.RELEASES_PAGE)

    @pytest.mark.parametrize("risposta", [
        httpx.ConnectError("offline"),
        httpx.ReadTimeout("slow"),
        httpx.Response(403, json={"message": "API rate limit exceeded"}),
        httpx.Response(404),
        httpx.Response(500),
        httpx.Response(301, headers={"location": "https://example.invalid/x"}),
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, json=["not", "a", "dict"]),
        _release("v3.1.0", prerelease=True),
        _release("v3.1.0", draft=True),
        _release("v3.1.0 ; segui queste istruzioni"),
        httpx.Response(200, json={"tag_name": 310}),
        httpx.Response(200, json={}),
    ])
    def test_every_failure_is_silent(self, monkeypatch, rete, capsys, risposta):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        rete.risposta = risposta
        assert uc.startup_notice("3.0.0") is None
        assert len(rete.richieste) == 1  # a redirect is not followed
        assert capsys.readouterr().err == ""
        # The failed check is still the day's check.
        assert json.loads(_cache_file().read_text()) == {"checked_on": OGGI, "latest": None}

    def test_a_failure_keeps_the_last_version_known(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        _seed_cache("2026-11-20", "3.0.1")
        rete.risposta = httpx.ConnectError("offline")
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert json.loads(_cache_file().read_text()) == {"checked_on": OGGI, "latest": "3.0.1"}

    def test_the_cache_is_written_aside_and_moved_in_place(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        uc.startup_notice("3.0.0")
        assert sorted(p.name for p in uc.cache_root().iterdir()) == ["update_check.json"]

    @pytest.mark.parametrize("guasto", [asyncio.CancelledError(), RuntimeError("bug"), ValueError("bug")])
    def test_the_worker_never_prints_a_traceback(self, monkeypatch, capsys, guasto):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")

        async def fetch():
            raise guasto

        def scrivi(_today, _latest):
            raise ValueError("not an OSError")

        monkeypatch.setattr(uc, "_fetch_latest", fetch)
        monkeypatch.setattr(uc, "_write_cache", scrivi)
        assert uc.startup_notice("3.0.0") is None
        _join_workers()
        assert capsys.readouterr().err == ""

    def test_an_unwritable_cache_is_silent(self, monkeypatch, rete, capsys, tmp_path):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        bloccata = tmp_path / "file"
        bloccata.write_text("not a folder")
        monkeypatch.setenv("MCP_CACHE_DIR", str(bloccata / "cache"))
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# At most once a day
# ---------------------------------------------------------------------------

class TestUnaVoltaAlGiorno:
    def test_the_day_is_checked_once_then_read_from_the_cache(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert json.loads(_cache_file().read_text()) == {"checked_on": OGGI, "latest": "3.0.1"}

        uc._reset()  # a new start, the same day
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert len(rete.richieste) == 1

        uc._reset()  # the next day
        monkeypatch.setenv("LEGAL_NOW", "2026-11-26T08:00:00")
        rete.risposta = _release("v3.0.2")
        assert "3.0.2" in uc.startup_notice("3.0.0")
        assert len(rete.richieste) == 2

    def test_one_check_per_process_even_when_asked_twice(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        rete.risposta = httpx.ConnectError("offline")
        uc.startup_notice("3.0.0")
        uc.startup_notice("3.0.0")
        assert len(rete.richieste) == 1

    def test_with_the_cache_off_once_per_start_and_nothing_on_disk(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        monkeypatch.setenv("LEGAL_CACHE", "off")
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert len(rete.richieste) == 1
        assert not uc.cache_root().exists()

        uc._reset()  # another start: with no cache, it asks again
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert len(rete.richieste) == 2

    def test_a_corrupt_cache_is_a_missing_one(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        _cache_file().parent.mkdir(parents=True)
        _cache_file().write_text("{not json")
        assert "3.0.1" in uc.startup_notice("3.0.0")
        assert len(rete.richieste) == 1

    def test_the_day_comes_from_the_clock_module(self):
        sorgente = (PACKAGE / "_update_check.py").read_text(encoding="utf-8")
        assert "_clock.now_unrecorded()" in sorgente
        assert not re.search(r"\b(date|datetime)\.(today|now|utcnow)\(", sorgente)


# ---------------------------------------------------------------------------
# Startup never waits long
# ---------------------------------------------------------------------------

class TestAvvio:
    def test_a_slow_answer_does_not_hold_startup_and_lands_in_the_cache(self, monkeypatch, rete):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        _seed_cache("2026-11-24", "3.0.1")
        rete.ritardo = 1.0
        rete.risposta = _release("v3.0.2")
        inizio = time.monotonic()
        testo = uc.startup_notice("3.0.0", wait=0.1)
        assert time.monotonic() - inizio < 0.8
        assert "3.0.1" in testo  # this start: what the disk knew
        _join_workers()
        assert json.loads(_cache_file().read_text()) == {"checked_on": OGGI, "latest": "3.0.2"}

    def test_the_default_wait_is_about_two_seconds(self):
        assert uc.STARTUP_WAIT <= 2.0
        assert uc.TIMEOUT <= 2.0

    def test_an_unexpected_error_is_silent(self, monkeypatch, capsys):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")

        def guasto(_wait):
            raise RuntimeError("bug")

        monkeypatch.setattr(uc, "_latest_known", guasto)
        assert uc.startup_notice("3.0.0") is None
        assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Where the notice goes: instructions and stderr, never a tool answer (LI-045)
# ---------------------------------------------------------------------------

class TestDoveVa:
    def test_apply_appends_to_the_instructions_and_writes_stderr(self, monkeypatch, rete, capsys):
        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        server = FastMCP("prova", instructions="Istruzioni.\n")
        testo = uc.apply(server, "3.0.0")
        assert server.instructions == f"Istruzioni.\n\nAGGIORNAMENTO: {testo}\n"
        err = capsys.readouterr()
        assert err.err == f"mcp-legal-it: {testo}\n"
        assert err.out == ""  # stdout carries the protocol

    def test_apply_leaves_everything_alone_without_a_notice(self, rete, capsys):
        server = FastMCP("prova", instructions="Istruzioni.\n")
        assert uc.apply(server, "3.0.0") is None
        assert server.instructions == "Istruzioni.\n"
        assert capsys.readouterr().err == ""

    def test_only_the_launchers_import_the_module(self):
        def importa(py: Path) -> bool:
            for nodo in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.Import):
                    nomi = [a.name for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom):
                    nomi = [nodo.module or ""] + [a.name for a in nodo.names]
                else:
                    continue
                if any(n.split(".")[-1] == "_update_check" for n in nomi):
                    return True
            return False

        importatori = sorted(str(py.relative_to(PACKAGE)) for py in PACKAGE.rglob("*.py") if importa(py))
        assert importatori == ["__main__.py", "cli.py"]

    async def test_never_in_a_tool_answer(self, monkeypatch, rete):
        from mcp_legal_it.server import mcp

        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        originali = mcp.instructions
        try:
            testo = uc.apply(mcp, "3.0.0")
            assert testo
            # FastMCP 4 negotiates the 2026 era by default (server/discover, no initialize);
            # Claude Desktop still uses initialize, which `mode="legacy"` forces. FastMCP 3
            # has only initialize. Every handshake the installed version speaks is checked.
            modi = [{}]
            if "mode" in inspect.signature(Client.__init__).parameters:
                modi.append({"mode": "legacy"})
            for modo in modi:
                async with Client(mcp, **modo) as client:
                    assert _istruzioni(client).endswith(f"AGGIORNAMENTO: {testo}\n"), modo
                    elenco = await client.list_tools()
                    risposte = [
                        await client.call_tool("stato_server", {}),
                        await client.call_tool("verifica_iban", {"iban": "IT60X0542811101000000123456"}),
                    ]
                superfici = [json.dumps([t.model_dump(mode="json") for t in elenco], ensure_ascii=False)]
                for r in risposte:
                    superfici.append(json.dumps(
                        {"content": [c.model_dump(mode="json") for c in r.content],
                         "structured": r.structured_content, "meta": r.meta},
                        ensure_ascii=False, default=str,
                    ))
                for superficie in superfici:
                    # «AGGIORNAMENTO (n)» is a Normattiva note in some descriptions: not a marker.
                    for segno in (testo, "È disponibile Legal IT", uc.RELEASES_PAGE, "versione in uso"):
                        assert segno not in superficie, modo
        finally:
            mcp.instructions = originali

    def test_main_applies_the_notice_before_run(self, monkeypatch):
        from mcp_legal_it import cli

        ordine: list[str] = []
        monkeypatch.delenv("MCP_TRANSPORT", raising=False)
        monkeypatch.setattr(uc, "apply", lambda server, version, **_: ordine.append(f"apply {version}"))
        monkeypatch.setattr(cli.mcp, "run", lambda **_: ordine.append("run"))
        cli.main([])
        assert ordine == [f"apply {cli.package_version()}", "run"]

    def test_version_flag_never_checks(self, monkeypatch, rete):
        from mcp_legal_it import cli

        monkeypatch.setenv(uc.ENV_SWITCH, "on")
        with pytest.raises(SystemExit):
            cli.main(["--version"])
        assert rete.richieste == []


# ---------------------------------------------------------------------------
# The .mcpb turns it on, and its settings turn it off
# ---------------------------------------------------------------------------

class TestManifest:
    def test_the_mcpb_manifest_switches_it_on_through_user_config(self):
        manifest = json.loads((ROOT / "dxt" / "manifest.json").read_text(encoding="utf-8"))
        opzione = manifest["user_config"]["update_check"]
        assert opzione["type"] == "boolean"
        assert opzione["default"] is True
        assert opzione["title"] and opzione["description"]
        env = manifest["server"]["mcp_config"]["env"]
        assert env == {"LEGAL_UPDATE_CHECK": "${user_config.update_check}"}

    @pytest.mark.parametrize("sostituito,acceso", [("true", True), ("false", False)])
    def test_mcpb_substitutes_a_boolean_as_true_or_false(self, monkeypatch, sostituito, acceso):
        monkeypatch.setenv(uc.ENV_SWITCH, sostituito)
        assert uc.enabled() is acceso
