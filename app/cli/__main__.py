import argparse
import asyncio
import sys

from app.cli.promote_admin_cmd import run_promote_admin_cli


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote_parser = subparsers.add_parser(
        "promote-admin",
        help="Promote a registered user to admin role",
    )
    promote_parser.add_argument("email", help="User email address")

    args = parser.parse_args()
    if args.command == "promote-admin":
        code = asyncio.run(run_promote_admin_cli(args.email))
        sys.exit(code)


if __name__ == "__main__":
    main()
