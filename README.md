# Nautilus

Nautilus is a policy-first data broker: a single `broker.request(...)` call
plans an intent, routes it to the right sources, enforces CLIPS-backed scope
rules, executes adapters concurrently, and emits a signed attestation plus a
complete audit entry per request.

See [`./specs/core-broker/design.md`](./specs/core-broker/design.md) for the
architecture and [`./specs/core-broker/requirements.md`](./specs/core-broker/requirements.md)
for the functional/non-functional requirements this implementation satisfies.

## Install

```bash
uv add nautilus
```

Python 3.12+ is required. PostgreSQL 16+ with the `pgvector` extension is
required only if you register `postgres` or `pgvector` sources.

## Quickstart

The snippet below is runnable verbatim against the repo's two-source test
fixture at [`tests/fixtures/nautilus.yaml`](./tests/fixtures/nautilus.yaml).
Export `TEST_PG_DSN` and `TEST_PGV_DSN` first (the fixture references them
via `${TEST_PG_DSN}` / `${TEST_PGV_DSN}`); any reachable PostgreSQL with
`pgvector` installed works.

```python
from nautilus import Broker

broker = Broker.from_config("tests/fixtures/nautilus.yaml")
try:
    response = broker.request(
        "agent-alpha",
        "Find vulnerabilities for CVE-2026-1234",
        {"clearance": "unclassified", "purpose": "threat-analysis", "session_id": "s1", "embedding": [0.1, 0.2, 0.3]},
    )
    print(response.data)
finally:
    broker.close()
```

`response` is a `BrokerResponse` (see design §4.8): `response.data` is a
`dict[source_id, list[row]]`, `response.sources_queried` lists successful
sources, `response.attestation_token` is the signed JWS, and
`response.request_id` is the UUID4 key that joins the response to the
per-request audit entry in `./audit.jsonl`.

## What you get per request

- **Planned routing** via the Fathom intent router — sources selected by
  intent + data types, never by the caller.
- **Scope enforcement** through a CLIPS rules engine over the
  `(clearance, purpose, source)` triple; denials are recorded, not
  swallowed.
- **Concurrent adapter execution** with per-adapter error isolation so one
  failing source never sinks the response.
- **Signed attestation** (JWS) bound to `request_id`, enabling external
  verification without replaying the query.
- **Complete audit entry** (design §4.9) appended to `./audit.jsonl` for
  every request — success, denial, or error.

## Configuration

A `nautilus.yaml` declares `sources`, `rules`, `analysis`, `audit`, and
`attestation` blocks. The test fixture is the minimal working example;
design §12 documents the full schema.

## Async usage

From inside a running event loop, call `await broker.arequest(...)` —
`broker.request()` deliberately raises `RuntimeError` in that context
(design §8, UQ-4) to prevent nested `asyncio.run` calls.

## Development

```bash
uv sync
uv run pytest -m unit            # fast suite, no containers
uv run pytest -m integration     # full e2e, boots PostgreSQL via testcontainers
uv run ruff check && uv run ruff format --check && uv run pyright
```

## License

See `LICENSE`.
