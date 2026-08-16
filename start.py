"""Run the local backend and frontend with one command: python start.py."""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    if not port_is_open(6379):
        print("Memurai is not reachable on 127.0.0.1:6379.", file=sys.stderr)
        print("Start the Memurai Windows service, then retry.", file=sys.stderr)
        return 1

    occupied = [str(port) for port in (8000, 3000) if port_is_open(port)]
    if occupied:
        print(
            f"Port(s) {', '.join(occupied)} already in use. Stop the existing app first.",
            file=sys.stderr,
        )
        return 1

    node = shutil.which("node")
    next_cli = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"
    if not node or not next_cli.exists():
        print("Frontend dependencies are missing. Run: cd frontend; npm.cmd install", file=sys.stderr)
        return 1

    commands = [
        (
            "backend",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--reload",
            ],
            ROOT,
        ),
        ("frontend", [node, str(next_cli), "dev", "-p", "3000"], FRONTEND),
    ]

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        for name, command, cwd in commands:
            processes.append((name, subprocess.Popen(command, cwd=cwd)))

        print("\nApplication started:")
        print("  UI:      http://localhost:3000")
        print("  Backend: http://127.0.0.1:8000/api/health")
        print("  State:   Memurai on 127.0.0.1:6379")
        print("\nPress Ctrl+C to stop both servers.\n")

        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{name} exited with status {code}.", file=sys.stderr)
                    return code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping application...")
        return 0
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for _, process in reversed(processes):
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
