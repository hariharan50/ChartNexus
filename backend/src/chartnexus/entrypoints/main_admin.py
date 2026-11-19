"""``chartnexus-admin`` - manage platform admins from the server.

    chartnexus-admin list
    chartnexus-admin grant  --email someone@example.com
    chartnexus-admin revoke --email someone@example.com
    chartnexus-admin audit

This command is the only way to make or remove an admin. There is no web route
for it on purpose: running it needs a shell on the server, and whoever has one
already controls the platform. See ``contexts/identity/application/admin_roles``
for the rules it enforces (active accounts only, a maximum count, never the
last admin, sign-out on every change).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import socket
import sys
from datetime import UTC, datetime

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.settings import Settings, get_settings
from chartnexus.contexts.identity.application.admin_roles import AdminRoleError, AdminRoles
from chartnexus.infrastructure.persistence.postgresql.repositories.identity.refresh_session_repository import (
    SqlAlchemyRefreshSessionRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.identity.user_repository import (
    SqlAlchemyUserRepository,
)
from chartnexus.infrastructure.security.admin_audit import RedisAdminAuditTrail
from chartnexus.shared_kernel.domain.errors import ValidationError


def _actor() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # no login name in some containers
        user = "unknown"
    return f"cli:{user}@{socket.gethostname()}"


async def _main(settings: Settings, args: argparse.Namespace) -> int:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)
    audit = RedisAdminAuditTrail(container.redis)
    try:
        if args.command == "audit":
            for entry in reversed(await audit.recent(args.limit)):
                print(
                    f"{entry.get('at', '?')}  {entry.get('action', '?'):<14} "
                    f"{entry.get('email', '?'):<40} by {entry.get('actor', '?')}"
                )
            return 0

        async with container.database.session_factory() as session:
            roles = AdminRoles(
                users=SqlAlchemyUserRepository(session),
                sessions=SqlAlchemyRefreshSessionRepository(session),
                audit=audit,
                transaction=session,
                max_admins=settings.auth.admin_max_count,
                now=datetime.now(UTC),
                actor=_actor(),
            )
            if args.command == "list":
                admins = await roles.list_admins()
                print(f"{len(admins)} of {settings.auth.admin_max_count} admin slots used")
                for user in admins:
                    print(
                        f"  {user.email.value:<40} {user.status.value:<10} since {user.updated_at:%Y-%m-%d}"
                    )
                return 0

            change = await (roles.grant if args.command == "grant" else roles.revoke)(args.email)
    except (AdminRoleError, ValidationError) as exc:
        print(f"chartnexus-admin: {exc}", file=sys.stderr)
        return 1
    finally:
        await container.aclose()

    if not change.changed:
        state = "already an admin" if args.command == "grant" else "not an admin"
        print(f"{change.email} is {state}; nothing changed.")
        return 0
    verb = "is now an admin" if args.command == "grant" else "is no longer an admin"
    print(f"{change.email} {verb}. Signed out of {change.sessions_revoked} session(s).")
    if not change.email_verified:
        print("note: this account's email address has never been verified.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chartnexus-admin", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show every admin")
    for name, text in (("grant", "make an account an admin"), ("revoke", "remove admin")):
        command = commands.add_parser(name, help=text)
        command.add_argument("--email", required=True)
    audit = commands.add_parser("audit", help="show recent admin changes")
    audit.add_argument("--limit", type=int, default=50)
    return parser


def run() -> None:
    args = _parser().parse_args()
    sys.exit(asyncio.run(_main(get_settings(), args)))


if __name__ == "__main__":
    run()
