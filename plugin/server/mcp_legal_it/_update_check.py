"""The daily new-version notice of the .mcpb build (LI-096).

Who installs the `.mcpb` by hand has no update channel: the plugin updates
itself, PyPI and Docker users have their own tools, the `.mcpb` is a file that
stays as it was downloaded. For that build, and only when it asks for it, the
server checks at most once a day which stable release GitHub calls the latest, and when
the running version is older it says so in two places:

* the server instructions, which a client reads once, at ``initialize``;
* one line on stderr, the startup log.

Never in a tool answer (LI-045): this module is imported only by the launchers
(``cli.py``, ``__main__.py``), so no tool can reach it, and
``tests/unit/test_update_check.py`` checks both facts. It lives next to them, not
in ``lib/``, which holds what the tools use.

**Off unless switched on.** ``LEGAL_UPDATE_CHECK=on`` (also ``1``, ``true``,
``yes``) switches it on; anything else, unset included, leaves it off. The
`.mcpb` manifest (``dxt/manifest.json``) sets it from a ``user_config`` boolean,
true by default, so a Claude Desktop user switches it off in the extension
settings; MCPB substitutes a boolean as the string ``"true"``/``"false"``.

**What leaves the machine.** One ``GET`` to ``LATEST_URL`` with a generic
User-Agent (``mcp-legal-it``): no version, no identifier, nothing about the user
or their queries. GitHub sees the request itself, with the IP address it comes
from. The request goes through ``core/_http.async_client``, so the host guard
(source ``github_releases`` → ``api.github.com`` only, no redirects) applies as
to every other source.

**At most once a day.** The day of the last check and its result live in
``${MCP_CACHE_DIR:-~/.cache/mcp-legal-it}/update_check.json``. A check that fails
still counts as the day's check, and keeps the last version it knew. With
``LEGAL_CACHE=off`` nothing is read or written and the check runs at most once
per start. The day comes from ``_clock`` (``now_unrecorded``: when the process
looked outward, not an answer anchored to today).

**Startup never waits on the network for long.** When the day's check is still
to do, it runs on a daemon thread and startup waits for it at most
``STARTUP_WAIT`` seconds (2). A check that answers in time is in this start's
instructions; one that does not keeps running while this start uses the last
result on disk, and writes the cache for the next start if the process is still
alive when it ends (otherwise the next start asks again). A network failure, a
timeout, a rate limit, a redirect, a bad payload or an unwritable cache are all
silent: no notice, no error, no traceback.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading

from mcp_legal_it.core._http import async_client
from mcp_legal_it.lib import _clock
from mcp_legal_it.lib._cache import cache_enabled, cache_root

#: The switch. Off unless set to one of ``ON_VALUES``.
ENV_SWITCH = "LEGAL_UPDATE_CHECK"
ON_VALUES = frozenset({"on", "1", "true", "yes"})

#: The source name in ``core/_http.HOST_PER_FONTE``.
FONTE = "github_releases"
#: GitHub's latest stable release: drafts and prereleases are never "latest".
LATEST_URL = "https://api.github.com/repos/LexCraft-IT/mcp-legal-it/releases/latest"
#: The page the notice links to.
RELEASES_PAGE = "https://github.com/LexCraft-IT/mcp-legal-it/releases/latest"
#: Generic on purpose: it names the program, not its version, the user or the machine.
USER_AGENT = "mcp-legal-it"
#: Seconds allowed to each phase of the request (connect, read, ...).
TIMEOUT = 2.0
#: Seconds startup waits for a check still to do; past them it goes on without it.
STARTUP_WAIT = 2.0

_CACHE_FILE = "update_check.json"

# A release tag: 3.0.1, v3.0.1, 3.0.0-beta.5, 3.0.0b5, 3.0.0-rc.1. Strict, so the
# text that reaches the instructions is a version and nothing else.
_VERSION = re.compile(
    r"^v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:-?(alpha|a|beta|b|rc)\.?(\d{1,4})?)?$",
    re.IGNORECASE,
)
_PHASES = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2}
_RELEASE = 3  # a release sorts after every prerelease of the same version

# One check per process: the first call does it, later calls reuse its result.
_lock = threading.Lock()
_state: dict = {}


def enabled() -> bool:
    """True when ``LEGAL_UPDATE_CHECK`` switches the check on."""
    return os.environ.get(ENV_SWITCH, "").strip().lower() in ON_VALUES


def version_key(text: object) -> tuple[int, int, int, int, int] | None:
    """A sortable key for a release version, or None for anything that is not one."""
    if not isinstance(text, str):
        return None
    match = _VERSION.match(text.strip())
    if match is None:
        return None
    major, minor, patch = (int(g) for g in match.group(1, 2, 3))
    if match.group(4) is None:
        return (major, minor, patch, _RELEASE, 0)
    return (major, minor, patch, _PHASES[match.group(4).lower()], int(match.group(5) or 0))


def notice(current: str, latest: str | None) -> str | None:
    """The notice text when ``latest`` is newer than ``current``, else None."""
    current_key, latest_key = version_key(current), version_key(latest)
    if current_key is None or latest_key is None or latest_key <= current_key:
        return None
    return (
        f"È disponibile Legal IT {latest} (versione in uso: {current}). "
        f"Per aggiornare: {RELEASES_PAGE}"
    )


def startup_notice(current: str, *, wait: float = STARTUP_WAIT) -> str | None:
    """The notice for this start, or None. Never raises; waits at most ``wait`` seconds."""
    try:
        if not enabled():
            return None
        return notice(current, _latest_known(wait))
    except Exception:  # noqa: BLE001 - a notice is never worth a failed start
        return None


def apply(server, current: str, *, wait: float = STARTUP_WAIT) -> str | None:
    """Add the notice, if any, to ``server``'s instructions and write it on stderr.

    Called by the launchers right before ``run``: the instructions are what a
    client reads at ``initialize``, stderr is the startup log (stdout carries the
    protocol). Returns the notice, or None.
    """
    text = startup_notice(current, wait=wait)
    if text is None:
        return None
    base = (server.instructions or "").rstrip("\n")
    server.instructions = f"{base}\n\nAGGIORNAMENTO: {text}\n"
    print(f"mcp-legal-it: {text}", file=sys.stderr, flush=True)
    return text


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def _latest_known(wait: float) -> str | None:
    """The latest stable version known to this start: the cache, or the day's check."""
    with _lock:
        if "latest" in _state:
            return _state["latest"]
        if _state.get("started"):
            return _state.get("previous")
        cached = _read_cache()
        today = _clock.now_unrecorded().date().isoformat()
        previous = _valid(cached.get("latest")) if cached else None
        if cached and cached.get("checked_on") == today:
            _state["latest"] = previous
            return previous
        _state["started"] = True
        _state["previous"] = previous
    worker = threading.Thread(
        target=_refresh, args=(today, previous), name="mcp-legal-it-update-check", daemon=True
    )
    worker.start()
    worker.join(wait)
    with _lock:
        return _state.get("latest", previous)


def _refresh(today: str, previous: str | None) -> None:
    """The day's check: ask GitHub, keep the answer (or the last one known), store it.

    It runs on its own thread, where an escaped exception would print a traceback:
    everything is caught, cancellation included.
    """
    latest = previous
    try:
        fetched = asyncio.run(_fetch_latest())
        if fetched is not None:
            latest = fetched
    except BaseException:  # noqa: BLE001 - offline, timeout, refused host, cancelled: silent
        pass
    with _lock:
        _state["latest"] = latest
    try:
        _write_cache(today, latest)
    except Exception:  # noqa: BLE001 - _write_cache already swallows OSError; nothing else may print
        pass


async def _fetch_latest() -> str | None:
    """The tag of the latest stable release, without the ``v``; None for any other answer."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    async with async_client(FONTE, timeout=TIMEOUT, headers=headers) as client:
        response = await client.get(LATEST_URL)
    if response.status_code != 200:
        return None
    data = response.json()
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    return _valid(data.get("tag_name"))


def _valid(tag: object) -> str | None:
    """``tag`` as a version (no leading ``v``) when it is one, else None."""
    if version_key(tag) is None:
        return None
    text = str(tag).strip()
    return text[1:] if text[:1] in ("v", "V") else text


# ---------------------------------------------------------------------------
# The cache file
# ---------------------------------------------------------------------------

def _read_cache() -> dict | None:
    if not cache_enabled():
        return None
    try:
        data = json.loads((cache_root() / _CACHE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_cache(today: str, latest: str | None) -> None:
    """Best-effort and silent: an unwritable cache only means asking again next start."""
    if not cache_enabled():
        return
    path = cache_root() / _CACHE_FILE
    # Written aside and moved in place, as the other caches do: a reader in another
    # process never sees half a file.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"checked_on": today, "latest": latest}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _reset() -> None:
    """Forget this process's check (tests only)."""
    with _lock:
        _state.clear()
