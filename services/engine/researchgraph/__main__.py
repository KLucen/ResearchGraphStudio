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
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
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
