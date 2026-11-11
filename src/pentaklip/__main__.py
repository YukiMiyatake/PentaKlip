"""CLI entry: `python -m pentaklip` or `pentaklip`."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="pentaklip", description="PentaKlip server / tools")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="API bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="API bind port (default: 8787)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development)",
    )
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "pentaklip.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
