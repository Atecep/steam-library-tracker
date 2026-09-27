from __future__ import annotations

import ctypes
import errno
import json
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from streamlit import config as streamlit_config
from streamlit.web import bootstrap

from app_paths import DATA_DIR, ensure_data_dir
from version import APP_VERSION


HOST = "localhost"
FIRST_PORT = 8501
LAST_PORT = 8599

INSTANCE_STATE_PATH = DATA_DIR / "instance.json"
INSTANCE_LOCK_PATH = DATA_DIR / "instance.lock"


def get_bundle_dir() -> Path:
    """Return the directory containing bundled application resources."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    return Path(__file__).resolve().parent


def pid_is_running(pid: int) -> bool:
    """Return True if the given process ID currently exists."""
    if pid <= 0:
        return False

    if os.name == "nt":
        # PROCESS_QUERY_LIMITED_INFORMATION
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False

        ctypes.windll.kernel32.CloseHandle(process)
        return True

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        return False

    return True


def find_free_port() -> int:
    """Return the first available local port in the configured range."""
    for port in range(FIRST_PORT, LAST_PORT + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise RuntimeError(
        f"No free port available between {FIRST_PORT} and {LAST_PORT}."
    )


def app_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def health_url(port: int) -> str:
    return f"{app_url(port)}/_stcore/health"


def server_is_healthy(port: int, timeout: float = 0.75) -> bool:
    """Return True if Streamlit is responding on the recorded port."""
    try:
        with urllib.request.urlopen(
            health_url(port),
            timeout=timeout,
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def write_instance_state(pid: int, port: int) -> None:
    """Atomically persist the current instance PID and port."""
    ensure_data_dir()

    temporary_path = INSTANCE_STATE_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "pid": pid,
                "port": port,
                "version": APP_VERSION,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(INSTANCE_STATE_PATH)


def remove_if_owned(path: Path, pid: int) -> None:
    """Remove a state/lock file only when it still belongs to this PID."""
    data = read_json(path)

    if data and data.get("pid") != pid:
        return

    try:
        path.unlink()
    except FileNotFoundError:
        pass


def read_existing_instance() -> tuple[int, int, str | None] | None:
    """Return (pid, port, version) for a valid existing app instance."""
    state = read_json(INSTANCE_STATE_PATH)
    if not state:
        return None

    try:
        pid = int(state["pid"])
        port = int(state["port"])
    except (KeyError, TypeError, ValueError):
        return None

    if not pid_is_running(pid):
        return None

    if not (FIRST_PORT <= port <= LAST_PORT):
        return None

    version = state.get("version")
    if version is not None:
        version = str(version)

    return pid, port, version



def parse_version(version: str | None) -> tuple[int, ...] | None:
    """Parse simple dotted numeric application versions such as 1.3.0."""
    if not version:
        return None

    value = str(version).strip().lstrip("vV")
    parts = value.split(".")

    if not parts or not all(part.isdigit() for part in parts):
        return None

    return tuple(int(part) for part in parts)


def compare_versions(
    current_version: str,
    existing_version: str | None,
) -> int:
    """
    Compare the launcher version with the running instance.

    Returns:
        1  -> current launcher is newer
        0  -> same version
        -1 -> existing instance is newer

    Legacy instance files did not store a version. They are treated as older
    so that the first version-aware launcher can replace them automatically.
    """
    if existing_version == current_version:
        return 0

    current = parse_version(current_version)
    existing = parse_version(existing_version)

    if existing is None:
        return 1

    if current is None:
        # Exact equality was handled above. For an unknown format, prefer the
        # launcher the user explicitly started rather than getting stuck on
        # another build forever.
        return 1

    width = max(len(current), len(existing))
    current += (0,) * (width - len(current))
    existing += (0,) * (width - len(existing))

    if current > existing:
        return 1

    if current < existing:
        return -1

    return 0


def terminate_process(pid: int) -> None:
    """Terminate an older Steam Library Tracker process."""
    if pid <= 0 or pid == os.getpid():
        return

    if os.name == "nt":
        # PROCESS_TERMINATE
        process = ctypes.windll.kernel32.OpenProcess(
            0x0001,
            False,
            pid,
        )
        if not process:
            return

        try:
            ctypes.windll.kernel32.TerminateProcess(
                process,
                0,
            )
        finally:
            ctypes.windll.kernel32.CloseHandle(process)

        return

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def wait_for_process_exit(
    pid: int,
    timeout: float = 5.0,
) -> bool:
    """Wait briefly for a process to terminate."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if not pid_is_running(pid):
            return True

        time.sleep(0.1)

    return not pid_is_running(pid)


def stop_older_instance(pid: int) -> None:
    """Stop an older app version before launching the current version."""
    terminate_process(pid)

    if wait_for_process_exit(pid):
        return

    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return

        if wait_for_process_exit(pid, timeout=2.0):
            return

    raise RuntimeError(
        "An older Steam Library Tracker instance could not be closed. "
        "Close it manually and start the new version again."
    )


def remove_stale_instance_files(pid: int) -> None:
    """Remove old instance files after their owning process has stopped."""
    if pid_is_running(pid):
        return

    remove_if_owned(INSTANCE_STATE_PATH, pid)
    remove_if_owned(INSTANCE_LOCK_PATH, pid)


def should_replace_existing_version(
    existing_version: str | None,
) -> bool:
    """Return True when this launcher should replace the running instance."""
    return compare_versions(APP_VERSION, existing_version) > 0

def reopen_existing_instance(
    wait_seconds: float = 0.0,
) -> bool:
    """
    Reopen a compatible running Steam Library Tracker instance.

    If the running instance is older than this launcher, stop it so the new
    version can start. If the running instance is newer, keep and reopen it.
    """
    deadline = time.monotonic() + wait_seconds

    while True:
        existing = read_existing_instance()

        if existing is not None:
            pid, port, existing_version = existing
            relation = compare_versions(
                APP_VERSION,
                existing_version,
            )

            if relation > 0:
                stop_older_instance(pid)
                remove_stale_instance_files(pid)
                return False

            if server_is_healthy(port):
                webbrowser.open(app_url(port))
                return True

        if time.monotonic() >= deadline:
            return False

        time.sleep(0.15)


def read_lock_state() -> tuple[int, str | None] | None:
    """Return (pid, version) from the launcher lock file."""
    lock = read_json(INSTANCE_LOCK_PATH)
    if not lock:
        return None

    try:
        pid = int(lock["pid"])
    except (KeyError, TypeError, ValueError):
        return None

    version = lock.get("version")
    if version is not None:
        version = str(version)

    return pid, version


def acquire_instance_lock() -> int:
    """
    Atomically acquire the launcher lock.

    A same/newer running version is reopened. An older version is stopped so
    the version the user just launched can take over.
    """
    ensure_data_dir()
    own_pid = os.getpid()

    while True:
        try:
            fd = os.open(
                INSTANCE_LOCK_PATH,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            lock_state = read_lock_state()

            if lock_state is not None:
                lock_pid, lock_version = lock_state

                if pid_is_running(lock_pid):
                    if should_replace_existing_version(
                        lock_version
                    ):
                        stop_older_instance(lock_pid)
                        remove_stale_instance_files(
                            lock_pid
                        )
                        continue

                    if reopen_existing_instance(
                        wait_seconds=5.0
                    ):
                        return 0

                    raise RuntimeError(
                        "Steam Library Tracker is starting, but its local "
                        "server did not become available."
                    )

            # Stale lock left behind after a crash or forced termination.
            try:
                INSTANCE_LOCK_PATH.unlink()
            except FileNotFoundError:
                pass

            continue

        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            json.dump(
                {
                    "pid": own_pid,
                    "version": APP_VERSION,
                },
                lock_file,
            )

        return own_pid


def main() -> None:
    ensure_data_dir()

    # Fast path: an existing healthy instance is already running.
    if reopen_existing_instance():
        return

    own_pid = acquire_instance_lock()
    if own_pid == 0:
        return

    app_path = get_bundle_dir() / "app.py"

    if not app_path.exists():
        remove_if_owned(INSTANCE_LOCK_PATH, own_pid)
        raise FileNotFoundError(
            f"Could not find bundled app.py at: {app_path}"
        )

    port = find_free_port()
    write_instance_state(own_pid, port)

    flag_options = {
        "global_developmentMode": False,
        "server_address": HOST,
        "server_port": port,
        "server_headless": False,
        "server_fileWatcherType": "none",
        "browser_serverAddress": HOST,
        "browser_serverPort": port,
        "browser_gatherUsageStats": False,
        "client_toolbarMode": "viewer",
        "logger_hideWelcomeMessage": True,
    }

    streamlit_config._main_script_path = str(app_path)
    bootstrap.load_config_options(flag_options)

    try:
        bootstrap.run(
            str(app_path),
            False,
            [],
            flag_options,
        )
    finally:
        remove_if_owned(INSTANCE_STATE_PATH, own_pid)
        remove_if_owned(INSTANCE_LOCK_PATH, own_pid)


if __name__ == "__main__":
    main()
