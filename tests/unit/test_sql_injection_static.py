"""Static grep guard against SQL-injection regressions in the adapter layer.

Implements Task 3.13 (NFR-4, design §13.1, §17 — SQL-injection risk row).

Strategy
--------
Walk every ``.py`` file under ``nautilus/adapters/`` and scan it with a
5-line sliding window for the co-occurrence of an f-string and a DB-call
token (``execute`` / ``executemany`` / ``fetch`` / ``fetchrow`` /
``fetchval``). Additionally flag ``%s``-style formatting (``"..." % (...)``)
adjacent to a DB call. Either pattern is a regression signal: parameterized
queries go through ``$N`` placeholders exclusively (Task 2.8), so an
f-string sitting within five lines of a DB call is a prima-facie risk.

Allowlist
---------
Lines tagged with a trailing ``# noqa: SQLGREP`` comment are excluded from
the scan. This is reserved for rare legitimate adjacency (e.g. a method
definition whose name happens to collide with the DB-call regex, or a
quoted-identifier SQL string that has already been hardened via
``quote_identifier``). Each such tag should carry a brief rationale.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Canonical patterns — pinned verbatim by the task spec (§3.13). Do not edit.
FSTRING = re.compile(r"f['\"][^'\"]*\{[^}]+\}")
DBCALL = re.compile(r"\b(execute|executemany|fetch|fetchrow|fetchval)\s*\(")
# ``%s``-style formatting: either ``"..." % (...)`` or ``"..." % name`` where
# the format string contains an ``%s`` placeholder. The two sub-patterns
# match the two shapes the task spec calls out explicitly.
PERCENT_FORMAT = re.compile(r"['\"][^'\"]*%s[^'\"]*['\"]\s*%\s*[\(\w]")

WINDOW = 5
NOQA_TAG = "# noqa: SQLGREP"

_ADAPTERS_DIR = Path(__file__).resolve().parents[2] / "nautilus" / "adapters"


def _adapter_files() -> list[Path]:
    """Return every ``.py`` file under ``nautilus/adapters/`` (recursive)."""
    return sorted(p for p in _ADAPTERS_DIR.rglob("*.py") if p.is_file())


def _filter_lines(raw: list[str]) -> list[tuple[int, str]]:
    """Drop allowlisted lines; return ``(1-indexed-line-no, text)`` tuples.

    Filtering removes the line entirely from the scan so a ``# noqa: SQLGREP``
    tag on a method definition (e.g. ``async def execute(...)``) doesn't
    merely shift the window — it takes that line out of consideration.
    """
    kept: list[tuple[int, str]] = []
    for idx, line in enumerate(raw, start=1):
        if NOQA_TAG in line.rstrip():
            continue
        kept.append((idx, line))
    return kept


def _scan_file(path: Path) -> list[str]:
    """Return a list of violation messages for ``path`` (empty == clean)."""
    raw = path.read_text(encoding="utf-8").splitlines()
    filtered = _filter_lines(raw)
    violations: list[str] = []
    for i in range(len(filtered)):
        window = filtered[i : i + WINDOW]
        if len(window) < 2:
            # Need at least two lines to co-occur; single trailing line is safe.
            continue
        window_text = "\n".join(text for _lineno, text in window)
        start_lineno = window[0][0]
        if FSTRING.search(window_text) and DBCALL.search(window_text):
            violations.append(
                f"{path}:{start_lineno}: f-string within {WINDOW} lines of a "
                f"DB call (execute/fetch/...). Use $N placeholders or tag "
                f"the false-positive line with '{NOQA_TAG}'."
            )
        if PERCENT_FORMAT.search(window_text) and DBCALL.search(window_text):
            violations.append(
                f"{path}:{start_lineno}: '%s'-style formatting within "
                f"{WINDOW} lines of a DB call. Use $N placeholders."
            )
    return violations


@pytest.mark.unit
def test_no_fstring_or_percent_formatting_near_db_calls() -> None:
    """No adapter file interpolates into a SQL string near a DB call.

    Done-when (Task 3.13): 0 matches across ``nautilus/adapters/*.py``
    (after excluding lines tagged ``# noqa: SQLGREP``).
    """
    assert _ADAPTERS_DIR.is_dir(), f"adapter source tree not found at {_ADAPTERS_DIR}"
    files = _adapter_files()
    assert files, f"no .py files found under {_ADAPTERS_DIR}"

    all_violations: list[str] = []
    for path in files:
        all_violations.extend(_scan_file(path))

    assert not all_violations, "SQL-injection static grep guard failed:\n" + "\n".join(
        all_violations
    )


@pytest.mark.unit
def test_patterns_are_canonical() -> None:
    """Pin the canonical regex patterns to catch accidental edits.

    The task spec (§3.13) requires the two patterns to be copied verbatim
    into the test file. This test asserts both patterns' ``.pattern``
    attributes match the pinned strings so a stealthy edit (e.g. weakening
    the DB-call set) fails loudly in CI.
    """
    assert FSTRING.pattern == r"f['\"][^'\"]*\{[^}]+\}"
    assert DBCALL.pattern == r"\b(execute|executemany|fetch|fetchrow|fetchval)\s*\("
