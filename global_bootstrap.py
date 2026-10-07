from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

from database import (
    get_app_state,
    import_global_metadata,
    set_app_state,
)


GLOBAL_BOOTSTRAP_VERSION = 1
GLOBAL_BOOTSTRAP_STATE_KEY = (
    f"global_metadata_bootstrap_v{GLOBAL_BOOTSTRAP_VERSION}"
)
GLOBAL_BOOTSTRAP_LAST_ATTEMPT_KEY = (
    f"{GLOBAL_BOOTSTRAP_STATE_KEY}_last_attempt"
)
GLOBAL_BOOTSTRAP_RETRY_HOURS = 6

GLOBAL_RELEASE_BASE_URL = (
    "https://github.com/Atecep/steam-library-tracker/"
    "releases/download/global-db"
)

GLOBAL_DB_ZST_NAME = "global_metadata.db.zst"
GLOBAL_DB_ZST_SHA256_NAME = "global_metadata.db.zst.sha256"

GLOBAL_DB_ZST_URL = (
    f"{GLOBAL_RELEASE_BASE_URL}/{GLOBAL_DB_ZST_NAME}"
)
GLOBAL_DB_ZST_SHA256_URL = (
    f"{GLOBAL_RELEASE_BASE_URL}/{GLOBAL_DB_ZST_SHA256_NAME}"
)


def _now():
    return datetime.now()


def _now_iso():
    return _now().isoformat(
        timespec="seconds"
    )


def global_bootstrap_completed():
    return (
        get_app_state(
            GLOBAL_BOOTSTRAP_STATE_KEY
        )
        == "completed"
    )


def should_attempt_global_bootstrap():
    if global_bootstrap_completed():
        return False

    last_attempt = get_app_state(
        GLOBAL_BOOTSTRAP_LAST_ATTEMPT_KEY
    )

    if not last_attempt:
        return True

    try:
        last_attempt_time = datetime.fromisoformat(
            last_attempt
        )
    except ValueError:
        return True

    retry_after = (
        last_attempt_time
        + timedelta(
            hours=GLOBAL_BOOTSTRAP_RETRY_HOURS
        )
    )

    return _now() >= retry_after


def _download(url, destination):
    destination = Path(destination)

    request = Request(
        url,
        headers={
            "User-Agent": "SteamLibraryTracker/global-metadata-bootstrap",
            "Accept": "application/octet-stream",
        },
    )

    with urlopen(
        request,
        timeout=120,
    ) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(
                response,
                output,
                length=1024 * 1024,
            )


def _read_expected_sha256(checksum_path):
    checksum_text = Path(
        checksum_path
    ).read_text(
        encoding="utf-8"
    ).strip()

    if not checksum_text:
        raise RuntimeError(
            "The global metadata checksum is empty."
        )

    expected = checksum_text.split()[0].strip()

    if (
        len(expected) != 64
        or any(
            character not in "0123456789abcdefABCDEF"
            for character in expected
        )
    ):
        raise RuntimeError(
            "The global metadata checksum is invalid."
        )

    return expected.lower()


def _sha256(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def _verify_download(compressed_path, checksum_path):
    expected = _read_expected_sha256(
        checksum_path
    )
    actual = _sha256(
        compressed_path
    )

    if actual != expected:
        raise RuntimeError(
            "Global metadata checksum verification failed."
        )


def _decompress_zstandard(source_path, destination_path):
    try:
        import zstandard as zstd
    except ImportError as error:
        raise RuntimeError(
            "The zstandard package is required for "
            "the global metadata bootstrap."
        ) from error

    decompressor = zstd.ZstdDecompressor()

    with Path(source_path).open("rb") as source:
        with Path(destination_path).open("wb") as destination:
            decompressor.copy_stream(
                source,
                destination,
            )


def bootstrap_global_metadata(library_records):
    """Run the one-time global metadata bootstrap.

    Failure is non-fatal. The existing local Steam and HLTB workers remain
    the fallback, and another bootstrap attempt is allowed after the cooldown.
    """

    if global_bootstrap_completed():
        return {
            "attempted": False,
            "completed": True,
            "steam_imported": 0,
            "hltb_imported": 0,
            "error": None,
        }

    if not should_attempt_global_bootstrap():
        return {
            "attempted": False,
            "completed": False,
            "steam_imported": 0,
            "hltb_imported": 0,
            "error": None,
        }

    set_app_state(
        GLOBAL_BOOTSTRAP_LAST_ATTEMPT_KEY,
        _now_iso(),
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="slt-global-metadata-"
        ) as temp_dir:
            temp_dir = Path(temp_dir)

            compressed_path = (
                temp_dir
                / GLOBAL_DB_ZST_NAME
            )
            checksum_path = (
                temp_dir
                / GLOBAL_DB_ZST_SHA256_NAME
            )
            database_path = (
                temp_dir
                / "global_metadata.db"
            )

            _download(
                GLOBAL_DB_ZST_URL,
                compressed_path,
            )
            _download(
                GLOBAL_DB_ZST_SHA256_URL,
                checksum_path,
            )

            _verify_download(
                compressed_path,
                checksum_path,
            )

            _decompress_zstandard(
                compressed_path,
                database_path,
            )

            imported = import_global_metadata(
                database_path,
                library_records,
            )

        set_app_state(
            GLOBAL_BOOTSTRAP_STATE_KEY,
            "completed",
        )

        return {
            "attempted": True,
            "completed": True,
            "steam_imported": int(
                imported.get(
                    "steam_imported",
                    0,
                )
            ),
            "hltb_imported": int(
                imported.get(
                    "hltb_imported",
                    0,
                )
            ),
            "error": None,
        }

    except Exception as error:
        print(
            "[global-bootstrap] "
            f"Bootstrap failed: {error}"
        )

        return {
            "attempted": True,
            "completed": False,
            "steam_imported": 0,
            "hltb_imported": 0,
            "error": str(error),
        }
