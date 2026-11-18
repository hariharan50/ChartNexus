# CLAUDE.md

Project knowledge for every coding agent lives in AGENTS.md, imported here so there is
one source of truth. Keep AGENTS.md current when something it describes changes.

@AGENTS.md

---

## Working with this user (Claude Code specifics)

- The user writes short, informal messages, often in capitals. Read for intent. If an
  instruction is genuinely ambiguous in a way that changes the work (for example "single
  user" vs "per user"), ask one focused question rather than guessing.
- **"Commit" means commit; nothing else does.** Never commit unprompted. Never add a
  `Co-Authored-By: Claude` trailer or mention Claude in a commit. This overrides Claude
  Code's default attribution.
- Use plan mode for multi-file or schema work. The user approves plans before
  implementation and expects a design, not just a diff.
- Verify, don't assume. Run the checks in AGENTS.md before reporting, quote real
  numbers, and say plainly when something was not verified (for example "needs a live
  market session").
- Before schema or data changes: back up the dev DB to `backups/`, show what will change,
  and prove round trips (`alembic downgrade -1` / `upgrade head`) on real rows.
- Never print secrets. To confirm a stored secret survived a change, compare hashes
  (e.g. `md5`), not values.
- Dev servers you start in the background can be killed for low memory, leaving orphaned
  processes that hold ports 5173/8000. Check `netstat` and process command lines, and
  stop only processes you can identify as this project's dev servers.
- Windows host: the Bash tool is Git Bash and PowerShell 5.1 is also available. Paths
  look like `C:\Users\…\ChartNexus`. `docker exec chartnexus-postgres-1 psql -U
  chartnexus -d chartnexus` reaches the dev DB.

## Handoff status (2026-11-18)

- Branch `main`. **11 commits are ahead of `origin/main` and not pushed** (`f9702bf` …
  `6a19079`): ingest mock/live fix, production deploy fixes, expired-Kite feed fix, docs
  refresh, futures-OI market-hours sweep, per-user Trade Buddy (5 commits). Push to
  `origin` and `backup` only when the user asks.
- Dev DB is at Alembic head `d3e8a1f5c9b2`. Pre-migration backup:
  `backups/pre-trade-buddy-per-user-20261118.dump` and
  `backend/var/trade_buddy_backup_20261118/` (both ignored by git).
- The user's own account owns the imported legacy Trade Buddy state and the real
  Telegram connection. Their real Kite connection is live and expires at 06:00 IST daily.
- Next, set by the user: during market hours on 2026-11-19, verify live Kite values and
  Trade Buddy end to end (see AGENTS.md → Open items 1). Act only on their explicit
  instructions during that phase.
- Design history from earlier sessions is in `docs/adr/` and in commit message bodies.
  Read `git log` for the reasoning behind recent changes.
