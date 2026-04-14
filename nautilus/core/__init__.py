"""Nautilus core package: shared models, broker facade, and policy router.

Public exports:
- :class:`PolicyEngineError` — raised by :class:`FathomRouter` for engine
  construction or fact-assertion failures (design §3.4 failure modes).
"""

from __future__ import annotations


class PolicyEngineError(Exception):
    """Raised on Fathom engine construction or fact-assertion failure.

    Per design §3.4: engine construction failures surface at broker
    construction time; fact assertion / evaluation failures surface
    per-request with the offending fact payload in the message.
    """


__all__ = ["PolicyEngineError"]
