"""Local administrative commands. Not reachable over HTTP.

    python -m app.cli create-admin --email you@example.com --name "Your Name"

The one thing this exists for is the bootstrap problem: ``POST /admin/users`` requires
an authenticated ADMIN, so the first ADMIN cannot be created through the API without a
public endpoint that accepts ``role=ADMIN`` — which is exactly the hole that was just
closed. A command needs shell access to the deployment instead of a network request,
which is a meaningfully harder thing to obtain.

``create-admin`` refuses to run once an ADMIN exists. It is a bootstrap, not a general
way to mint administrators; adding the second one is ``POST /admin/users``'s job, where
it is attributable to an authenticated caller.
"""

import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.schemas.auth import AdminUserCreate, PrivilegedRole, UserRole
from app.services.auth_service import auth_service


async def _create_admin(email: str, name: str, password: str) -> int:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN.value)
        )
        count = existing.scalar_one()
        if count:
            print(
                f"Refusing to run: this database already has {count} ADMIN "
                f"account(s).\n"
                "Create further administrators with POST /admin/users, signed in as "
                "one of them, so the action has an authenticated author.",
                file=sys.stderr,
            )
            return 1

        # Validated through the same schema the HTTP endpoint uses, so the password
        # floor and the role vocabulary cannot drift between the two paths.
        try:
            payload = AdminUserCreate(
                name=name,
                email=email,
                password=password,
                role=PrivilegedRole.ADMIN,
            )
        except ValidationError as exc:
            print(f"Invalid input:\n{exc}", file=sys.stderr)
            return 2

        user = await auth_service.create_privileged_user(session, payload)
        print(f"Created ADMIN id={user.id} email={user.email}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser(
        "create-admin",
        help="Create the first ADMIN account. Fails if one already exists.",
    )
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)

    args = parser.parse_args(argv)

    if args.command == "create-admin":
        # Prompted, never a --password flag: a flag lands in shell history, in `ps`
        # output while the process runs, and in CI logs.
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 2
        return asyncio.run(_create_admin(args.email, args.name, password))

    parser.error(f"Unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
