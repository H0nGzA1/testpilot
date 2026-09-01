# TestPilot Multi-Account / Role Auth — Design Spec v0.1 (Phase 1)

Test cases execute as different users. A case declares a **role**; at run time the role
resolves to a concrete account and the browser agent logs in as it. Enables cross-role
workflow testing (requester creates → approver approves → admin configures).

## Locked decisions
1. **Role indirection** — a case names a role; run resolves role → account (env-swap
   friendly, decouples test logic from concrete credentials).
2. **Project-level for now** — one project has a role list + an account book; no
   Environments layer yet (Phase 2).
3. **A role may have multiple accounts, leased at run time** — N accounts ⇒ up to N
   same-role cases run in parallel; scarcer ⇒ same-role cases serialize (no session
   collision).
4. **Each account carries its login type** — `storage_state` (inject, no login) or
   `password` (robot account, agent prompt-login). Reuses today's mechanism.
5. **Role list is project-defined**; a case with no role falls back to the project
   default account (current behaviour).

## Data model (one migration)
- `Credential += role: str|null` — the role this account plays (null = general/default).
- `TestCase += role: str|null` — the role this case runs as (null = default account).
- `Project += roles: JSON (list[str])` — the project's role vocabulary (dropdown source).

## Resolution — `_resolve_login(session, run, case)`
1. `case.role` empty → project default (active storage_state / latest password — today's logic).
2. `case.role = R` → candidate accounts = project credentials with `role == R`.
   - none → the case fails `error` "no account for role R" (explicit, never a wrong account).
   - lease one free candidate (see concurrency); use its type to log in.

## Concurrency — account leasing (no session collision)
- Per-account lease: Redis `SET tp:lease:{account_id} nx ex=<case_timeout>`; acquired
  before login, released after. N accounts for a role ⇒ N concurrent; scarcer ⇒ callers
  poll-wait for a free one (up to the case timeout, else fail "all accounts for R busy").
- No-Redis fallback: an in-process asyncio guard over a leased-id set.
- ponytail: account-level leasing only; no cross-role global fairness until it's needed.

## API
- `GET/POST/PUT/DELETE /projects/{pid}/credentials` — account book (existing; add `role`;
  secret never returned).
- `GET/PUT /projects/{pid}/roles` — project role list.
- `TestCaseIn/Patch += role`.

## Frontend
- Settings → account book: role column + multiple accounts per role, login-type tag.
- Project settings → role list editor.
- Case drawer: "runs as" role dropdown (from the role list; empty = default).
- Run report / result rows: show the actual account/role each case used.

## Phasing
- **Phase 1 (this)**: role binding + role list + resolution + account leasing + UI +
  result shows account.
- **Phase 2**: Environments (dev/test/prod) → (env, role) → account; one suite across envs.
- **Phase 3**: smarter same-role pool scheduling; account health (auto-refresh expired sessions).
