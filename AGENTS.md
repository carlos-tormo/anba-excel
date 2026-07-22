# Codex project instructions

These instructions apply to all future Codex work in this repository.

## Default feature-development protocol

When implementing a new feature or changing an existing workflow:

1. Preserve the current layered architecture.
   - Routes parse input, authenticate/authorize, call services, and return `RouteResponse`.
   - Services own workflow orchestration, transaction boundaries, audit metadata, and outbox coordination.
   - Repositories own SQL reads/writes.
   - Domain modules contain pure calculations, validation rules, and formatting only.
   - Integrations perform external side effects only; they must not mutate league state directly.

2. Avoid legacy growth.
   - Do not add new business logic to `app/server.py`.
   - Do not add new workflow methods to `LeagueDB`.
   - Do not add new compatibility wrappers to `Handler` unless they remove more legacy surface than they add.
   - Do not place new major frontend feature sections directly in `web/admin.js` or `web/guest.js`; prefer cohesive domain modules.

3. Keep route handlers thin.
   - New and modified routes should return `RouteResponse`.
   - Route modules must not call `handler.db` directly.
   - Route modules must not call `handler._json`, `handler._bytes_response`, or `handler._redirect` directly.
   - Mutation routes must have explicit route inventory metadata: permission, CSRF requirement, and `mutates_league_state` where applicable.

4. Keep persistence boundaries explicit.
   - SQL belongs in `app/db` repositories or migrations.
   - Services may coordinate transactions but should not define SQL queries.
   - External calls must not occur while a write transaction is open.
   - Outbox events for league mutations should be committed in the same transaction as the mutation.

5. Protect critical mutations.
   - Use command IDs/idempotency keys where repeated submission is possible.
   - Use expected-version/stale-write checks for workflows edited from browser state.
   - Include command observability metadata for critical commands: command ID, validation result, entity versions, and outbox IDs.
   - Preserve before/after audit snapshots for league-state mutations when practical.

6. Keep frontend rendering safe.
   - Use `web/api.js` for API requests, CSRF headers, duplicate submission prevention, and common error handling.
   - Use `web/dom.js` safe DOM helpers for user/admin/imported/AI-generated text.
   - Avoid new `innerHTML`, `insertAdjacentHTML`, inline event handlers, and `javascript:` URLs unless the code uses an explicitly named sanitized escape hatch and tests cover it.

7. Prevent oversized files and hidden coupling.
   - Prefer cohesive feature modules over adding to already-large transitional files.
   - Avoid route functions that coordinate many services directly.
   - Avoid service/repository cycles.
   - Avoid one-method delegation modules unless they remove a larger legacy dependency.

## Required checks before handing off

For feature work, run focused tests relevant to the changed area plus any affected architecture/security tests. When practical, include:

- `tests.test_architecture_boundaries`
- `tests.test_thin_route_boundaries`
- `tests.test_route_authorization_inventory`
- `tests.test_security_headers`
- `tests.test_frontend_safety` for frontend changes
- `tests.test_transaction_boundaries` or workflow-specific tests for critical mutations

Run the full suite when changing shared infrastructure such as routing, application container, database connection/migrations, security headers, observability, or frontend shared helpers.

If a requested change would violate these instructions, call out the tradeoff explicitly and prefer the architecture-aligned implementation unless the user confirms otherwise.
