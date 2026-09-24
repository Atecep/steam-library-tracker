from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO

import psutil

from app_paths import DATA_DIR, ensure_data_dir


HOST = "localhost"
FIRST_PORT = 8501
LAST_PORT = 8599

STARTUP_GRACE_SECONDS = 8.0
STARTUP_TIMEOUT_SECONDS = 30.0
RECOVERY_LOCK_TIMEOUT_SECONDS = 5.0
HEALTH_TIMEOUT_SECONDS = 0.75
PARENT_WATCH_INTERVAL_SECONDS = 1.0

WINDOW_TITLE = "Steam Library Tracker"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
WINDOW_MIN_WIDTH = 960
WINDOW_MIN_HEIGHT = 640

BACKEND_MODE_ARG = "--streamlit-backend"
PARENT_PID_ARG = "--parent-pid"
PARENT_CREATE_TIME_ARG = "--parent-create-time"

INSTANCE_STATE_PATH = DATA_DIR / "instance.json"
INSTANCE_LOCK_PATH = DATA_DIR / "instance.lock"


class InstanceLock:
    """Cross-platform operating-system lock held for the app's lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: BinaryIO | None = None
        self._locked = False

    def try_acquire(self) -> bool:
        ensure_data_dir()
        file_obj = open(self.path, "a+b")

        try:
            if os.name == "nt":
                import msvcrt

                file_obj.seek(0, os.SEEK_END)
                if file_obj.tell() == 0:
                    file_obj.write(b"\0")
                    file_obj.flush()

                file_obj.seek(0)
                try:
                    msvcrt.locking(
                        file_obj.fileno(),
                        msvcrt.LK_NBLCK,
                        1,
                    )
                except OSError:
                    file_obj.close()
                    return False
            else:
                import fcntl

                try:
                    fcntl.flock(
                        file_obj.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                except BlockingIOError:
                    file_obj.close()
                    return False
        except Exception:
            file_obj.close()
            raise

        self._file = file_obj
        self._locked = True
        return True

    def release(self) -> None:
        if not self._locked or self._file is None:
            return

        try:
            if os.name == "nt":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(
                    self._file.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )
            else:
                import fcntl

                fcntl.flock(
                    self._file.fileno(),
                    fcntl.LOCK_UN,
                )
        finally:
            self._file.close()
            self._file = None
            self._locked = False


def get_bundle_dir() -> Path:
    """Return the directory containing bundled application resources."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    return Path(__file__).resolve().parent


def app_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def health_url(port: int) -> str:
    return f"{app_url(port)}/_stcore/health"


def server_is_healthy(port: int) -> bool:
    """Return True if Streamlit responds on the recorded port."""
    try:
        with urllib.request.urlopen(
            health_url(port),
            timeout=HEALTH_TIMEOUT_SECONDS,
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


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


def read_state() -> dict | None:
    try:
        state = json.loads(
            INSTANCE_STATE_PATH.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(state, dict):
        return None

    try:
        state["pid"] = int(state["pid"])
        state["port"] = int(state["port"])
        state["create_time"] = float(state["create_time"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (FIRST_PORT <= state["port"] <= LAST_PORT):
        return None

    return state


def write_state(port: int) -> dict:
    """Atomically write identity information for this exact launcher process."""
    ensure_data_dir()

    process = psutil.Process(os.getpid())
    state = {
        "pid": process.pid,
        "create_time": process.create_time(),
        "port": port,
    }

    temporary_path = INSTANCE_STATE_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(INSTANCE_STATE_PATH)

    return state


def matching_process(state: dict | None) -> psutil.Process | None:
    """
    Return the process only if PID and creation time both match.

    Checking creation time prevents a stale PID from accidentally referring
    to an unrelated process after PID reuse.
    """
    if not state:
        return None

    try:
        process = psutil.Process(state["pid"])
        create_time = process.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    if abs(create_time - state["create_time"]) > 0.01:
        return None

    try:
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    return process


def state_belongs_to_current_process() -> bool:
    state = read_state()
    if not state or state["pid"] != os.getpid():
        return False

    try:
        own_create_time = psutil.Process(os.getpid()).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

    return abs(own_create_time - state["create_time"]) <= 0.01


def remove_own_state() -> None:
    """Remove instance.json only when it still describes this process."""
    if not state_belongs_to_current_process():
        return

    try:
        INSTANCE_STATE_PATH.unlink()
    except FileNotFoundError:
        pass


def wait_for_healthy_instance(
    timeout: float,
) -> tuple[dict | None, psutil.Process | None]:
    """Wait for an existing instance to become healthy."""
    deadline = time.monotonic() + timeout
    latest_state = None
    latest_process = None

    while True:
        latest_state = read_state()
        latest_process = matching_process(latest_state)

        if (
            latest_state is not None
            and latest_process is not None
            and server_is_healthy(latest_state["port"])
        ):
            return latest_state, latest_process

        if time.monotonic() >= deadline:
            return latest_state, latest_process

        time.sleep(0.2)


def terminate_hung_instance(process: psutil.Process) -> None:
    """Gracefully terminate a verified hung instance, then force it if needed."""
    try:
        process.terminate()
        process.wait(timeout=3.0)
        return
    except psutil.NoSuchProcess:
        return
    except psutil.TimeoutExpired:
        pass

    try:
        process.kill()
        process.wait(timeout=2.0)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
        pass


def recover_or_exit(lock: InstanceLock) -> bool:
    """
    Handle the case where another process currently owns the OS lock.

    Returns True when an existing healthy desktop instance is already running.
    Returns False when recovery succeeded and this process acquired the lock.
    """
    state, process = wait_for_healthy_instance(
        STARTUP_GRACE_SECONDS
    )

    if (
        state is not None
        and process is not None
        and server_is_healthy(state["port"])
    ):
        # The existing pywebview window belongs to the other launcher process.
        # Do not open a browser as the old launcher did; simply keep one instance.
        return True

    if process is not None:
        terminate_hung_instance(process)

    deadline = time.monotonic() + RECOVERY_LOCK_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if lock.try_acquire():
            stale_state = read_state()
            if matching_process(stale_state) is None:
                try:
                    INSTANCE_STATE_PATH.unlink()
                except FileNotFoundError:
                    pass
            return False

        time.sleep(0.2)

    raise RuntimeError(
        "Steam Library Tracker could not recover the previous instance. "
        "Please wait a few seconds and try again."
    )


def _argument_value(name: str) -> str | None:
    try:
        index = sys.argv.index(name)
        return sys.argv[index + 1]
    except (ValueError, IndexError):
        return None


def _is_backend_mode() -> bool:
    return BACKEND_MODE_ARG in sys.argv


def _monitor_parent(parent_pid: int, parent_create_time: float) -> None:
    """Stop an orphaned Streamlit backend if its desktop launcher disappears."""
    while True:
        try:
            parent = psutil.Process(parent_pid)
            current_create_time = parent.create_time()
            if abs(current_create_time - parent_create_time) > 0.01:
                os._exit(0)
            if parent.status() == psutil.STATUS_ZOMBIE:
                os._exit(0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            os._exit(0)

        time.sleep(PARENT_WATCH_INTERVAL_SECONDS)


def run_streamlit_backend() -> None:
    """Run Streamlit headlessly in the child process used by pywebview."""
    port_value = _argument_value(BACKEND_MODE_ARG)
    parent_pid_value = _argument_value(PARENT_PID_ARG)
    parent_create_time_value = _argument_value(PARENT_CREATE_TIME_ARG)

    if port_value is None:
        raise RuntimeError("Missing Streamlit backend port.")

    port = int(port_value)

    if parent_pid_value is not None and parent_create_time_value is not None:
        parent_watcher = threading.Thread(
            target=_monitor_parent,
            args=(int(parent_pid_value), float(parent_create_time_value)),
            daemon=True,
            name="launcher-parent-watch",
        )
        parent_watcher.start()

    app_path = get_bundle_dir() / "app.py"
    if not app_path.exists():
        raise FileNotFoundError(
            f"Could not find bundled app.py at: {app_path}"
        )

    from streamlit import config as streamlit_config
    from streamlit.web import bootstrap

    flag_options = {
        "global_developmentMode": False,
        "server_address": HOST,
        "server_port": port,
        "server_headless": True,
        "server_fileWatcherType": "none",
        "browser_serverAddress": HOST,
        "browser_serverPort": port,
        "browser_gatherUsageStats": False,
        "client_toolbarMode": "viewer",
        "logger_hideWelcomeMessage": True,
    }

    streamlit_config._main_script_path = str(app_path)
    bootstrap.load_config_options(flag_options)
    bootstrap.run(
        str(app_path),
        False,
        [],
        flag_options,
    )


def build_backend_command(port: int) -> list[str]:
    parent = psutil.Process(os.getpid())
    backend_args = [
        BACKEND_MODE_ARG,
        str(port),
        PARENT_PID_ARG,
        str(parent.pid),
        PARENT_CREATE_TIME_ARG,
        str(parent.create_time()),
    ]

    if getattr(sys, "frozen", False):
        return [sys.executable, *backend_args]

    return [
        sys.executable,
        str(Path(__file__).resolve()),
        *backend_args,
    ]


def start_streamlit_backend(port: int) -> subprocess.Popen:
    """Start the local Streamlit server as a separate child process."""
    return subprocess.Popen(
        build_backend_command(port),
        stdin=subprocess.DEVNULL,
    )


def wait_for_streamlit_backend(
    process: subprocess.Popen,
    port: int,
    timeout: float = STARTUP_TIMEOUT_SECONDS,
) -> None:
    """Wait until Streamlit is ready before showing the desktop window."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                "The local Streamlit server stopped during startup "
                f"(exit code {return_code})."
            )

        if server_is_healthy(port):
            return

        time.sleep(0.15)

    raise RuntimeError(
        "The local Streamlit server did not become ready in time."
    )


def terminate_backend(process: subprocess.Popen | None) -> None:
    """Terminate the Streamlit child process when the desktop window closes."""
    if process is None or process.poll() is not None:
        return

    try:
        process.terminate()
        process.wait(timeout=3.0)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        process.kill()
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


def open_desktop_window(port: int) -> None:
    """Open the local Streamlit UI in a native pywebview desktop window."""
    if sys.platform.startswith("linux"):
        # Keep QtPy deterministic even on systems that also have another Qt binding.
        os.environ.setdefault("QT_API", "pyside6")

    try:
        import webview
    except ImportError as error:
        raise RuntimeError(
            "pywebview is not installed. Install the build dependencies with "
            "'python -m pip install -r requirements-build.txt'."
        ) from error

    # Preserve existing application behaviour inside the embedded browser.
    # Downloads are used by backup/export, while target=_blank links should be
    # handed back to the operating system (browser, Steam protocol handler, etc.).
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False

    webview.create_window(
        WINDOW_TITLE,
        app_url(port),
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
        resizable=True,
        text_select=True,
    )

    if sys.platform.startswith("linux"):
        # Linux release builds install the PySide6/Qt backend explicitly.
        webview.start(gui="qt")
    elif sys.platform == "win32":
        # Streamlit needs a modern engine; Windows 10/11 normally provide WebView2.
        webview.start(gui="edgechromium")
    else:
        webview.start()


def main() -> None:
    ensure_data_dir()

    lock = InstanceLock(INSTANCE_LOCK_PATH)

    if not lock.try_acquire():
        if recover_or_exit(lock):
            return

    app_path = get_bundle_dir() / "app.py"

    if not app_path.exists():
        lock.release()
        raise FileNotFoundError(
            f"Could not find bundled app.py at: {app_path}"
        )

    port = find_free_port()
    write_state(port)
    backend_process: subprocess.Popen | None = None

    try:
        backend_process = start_streamlit_backend(port)
        wait_for_streamlit_backend(backend_process, port)
        open_desktop_window(port)
    finally:
        terminate_backend(backend_process)
        remove_own_state()
        lock.release()


if __name__ == "__main__":
    if _is_backend_mode():
        run_streamlit_backend()
    else:
        main()
