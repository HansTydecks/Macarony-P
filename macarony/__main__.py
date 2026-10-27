"""``python -m macarony`` - start the local Macarony web page."""

from __future__ import annotations

import argparse
import threading
import webbrowser

from macarony.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m macarony",
        description="Build fake mixed-language words from real translations.",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to bind (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8000,
                        help="port to listen on (default: %(default)s)")
    parser.add_argument("--offline", action="store_true",
                        help="never call the online translator; use the bundled dictionary")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open a browser window")
    args = parser.parse_args(argv)

    httpd = serve(args.host, args.port, force_offline=args.offline)
    url = f"http://{args.host}:{args.port}/"
    mode = "offline dictionary" if args.offline else "online translator"
    print(f"Macarony is serving {url}  ({mode})")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
