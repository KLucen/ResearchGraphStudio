import argparse
import asyncio
import json
import socket
import sys
from pathlib import Path

import uvicorn

from researchgraph.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--parse-pdf", type=Path)
    parser.add_argument("--check-source", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.parse_pdf or args.check_source:
        if not args.output_dir or args.data_dir or (args.parse_pdf and args.check_source):
            parser.error("File worker requires one operation and --output-dir")
        if args.parse_pdf:
            from researchgraph.ingest import parse_pdf

            parse_pdf(str(args.parse_pdf), str(args.output_dir))
        else:
            from researchgraph.source_files import check_source_file

            check_source_file(args.check_source, args.output_dir)
        return
    if not args.data_dir or args.output_dir:
        parser.error("Engine requires --data-dir")
    # Token is passed on a private pipe, never on the command line or in a URL.
    configuration = json.loads(sys.stdin.readline())
    token = configuration["token"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    def ready() -> None:
        print("RGS_READY " + json.dumps({"port": port, "protocol": 1}), flush=True)

    app = create_app(args.data_dir, token, ready=ready)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))

    async def run() -> None:
        async def watch_parent() -> None:
            # EOF means the desktop host died or closed its pipe. No orphan service.
            await asyncio.to_thread(sys.stdin.read)
            server.should_exit = True

        watcher = asyncio.create_task(watch_parent())
        try:
            await server.serve(sockets=[sock])
        finally:
            watcher.cancel()
            sock.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
