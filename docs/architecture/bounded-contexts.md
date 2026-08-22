# Bounded contexts

Each package under `backend/src/marketcompass/contexts/` owns one area of the
domain and may not import another. This is enforced, not merely encouraged.

## The layers inside a context

```
contexts/<name>/
  domain/        entities, value objects, errors. No framework, no driver.
  application/   ports (Protocols) and use cases. Depends only on domain.
  api/           FastAPI router, request/response schemas, per-request wiring.
```

Adapters that satisfy a context's ports live in `infrastructure/`, never in the
context itself. Infrastructure may import a context's ports — that is the
direction dependency inversion requires. It may not import `bootstrap/` or
`entrypoints/`.

## Implemented contexts

| Context | Owns |
| --- | --- |
| `identity` | users, credentials, sessions, Google sign-in |
| `tenancy` | tenants/organizations and membership |
| `entitlements` | plan-based feature gating |
| `billing` | subscriptions and billing |
| `preferences` | per-user workspace and display preferences |
| `instrument_catalog` | instruments/symbols reference data |
| `broker_connections` | a tenant's broker API credentials and OAuth token lifecycle |
| `ai_settings` | a user's own LLM provider, API key (encrypted at rest), and model |
| `market_ingestion` | snapshot capture and archival for the market feed |
| `market_data` | canonical quotes, option chains, expiries, and data provenance |
| `options_analytics` | OI, PCR, max-pain, gamma, vega, smart-OI analytics |
| `futures_analytics` | futures heatmap, intraday, and market-movers analytics |
| `signals` | Nifty analysis / guidance (calibrated multi-horizon ensemble) |
| `outcomes` | signal outcome tracking and grading |
| `content_intelligence` | market content/news intelligence |
| `copilot` | the AI Console analyst agent (Hella) |
| `stryx` | the aggressive trade-caller agent (STRYX) |
| `realtime_delivery` | realtime/websocket delivery |
| `audit` | audit trail of sensitive actions |

The set of contexts is enforced by the `independence` contract in
`backend/pyproject.toml` and by `tests/architecture/`. Keep all three (this table,
the contract, the tests) in step when adding or removing a context.

## Contexts must not import each other

Two integration seams exist. Use one of them rather than reaching across.

**1. A port, satisfied by an infrastructure adapter.**

`market_data` needs a broker token, which `broker_connections` owns. It does not
import it. It declares a `MarketDataProvider` port, and
`infrastructure/brokers/provider_resolver.py` reads the broker repository and
builds the right provider. Neither context knows the other exists.

The AI agents work the same way. `copilot` (Hella) and `stryx` each need live
market data they do not own and an LLM key they do not own. Their per-request
wiring imports only a sanctioned bridge in infrastructure —
`agent/langgraph/build.py` and `build_stryx.py` — which reads the
`market_data`/`options_analytics` services and loads the caller's key from
`ai_settings` (via `agent/langgraph/user_llm.py`, decrypting with the
per-purpose cipher), then returns an `AgentPort`. Those bridge edges are the two
`ignore_imports` entries on the independence contract. LLM keys are per-user:
with none saved, the agent's `available` is false and the tab is offline.

**2. Domain events**, once the message bus is in use.

### Shared HTTP plumbing

`get_session`, `SessionUnitOfWork`, `Principal` and `CurrentPrincipal` live in
`infrastructure/transport/http/dependencies.py`.

They were originally in `contexts/identity/api/dependencies.py`, which meant
every other context's router had to import from `identity` just to authenticate
a request — breaking the boundary through framework wiring alone. Authenticating
an HTTP request is transport's job; `identity` owns only the rules behind the
token.

**If a new context's router needs something shared, put it there.**

## Verifying

```bash
cd backend
uv run lint-imports          # import-linter contracts in pyproject.toml
uv run pytest tests/architecture
```

**Run both.** On 2026-08-01 `lint-imports` reported *"Contracts: 3 kept, 0
broken"* while `tests/architecture/test_context_boundaries.py` correctly found
four cross-context imports. The AST-based tests in `tests/architecture/` are the
stricter check and are authoritative.

What the tests enforce:

| Test | Rule |
| --- | --- |
| `test_domain_purity` | domain imports no framework, driver, or vendor SDK |
| `test_context_boundaries` | no context imports another context |
| `test_vendor_imports` | a vendor SDK is importable only from its own adapter directory |
| `test_entrypoint_boundaries` | infrastructure imports neither entrypoints nor the container |

## Adding a context

1. Create `domain/`, `application/`, `api/` with `__init__.py` in each.
2. Add the module to the `independence` contract in `backend/pyproject.toml`.
3. Declare ports in `application/ports.py` as `Protocol` classes; implement them
   under `infrastructure/`.
4. Register the router in `bootstrap/route_registry.py`.
5. Run the two commands above before committing.
