from __future__ import annotations

import logging
from pathlib import Path


def setup_langtars_file_logging() -> Path:
    """Ensure root logger always writes to ~/.langtars/logs/langtars.log."""
    preferred_log_file = Path.home() / ".langtars" / "logs" / "langtars.log"
    fallback_log_file = Path("/tmp/langtars.log")

    log_file = preferred_log_file
    try:
        preferred_log_file.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_file = fallback_log_file
        fallback_log_file.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    known_log_paths = set()
    for p in (preferred_log_file, fallback_log_file, log_file):
        try:
            known_log_paths.add(p.resolve())
        except Exception:
            pass

    has_file_handler = False
    has_stream_handler = False

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if Path(handler.baseFilename).resolve() in known_log_paths:
                    has_file_handler = True
            except Exception:
                pass
        if isinstance(handler, logging.StreamHandler):
            has_stream_handler = True

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    if not has_file_handler:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception:
            if log_file != fallback_log_file:
                file_handler = logging.FileHandler(fallback_log_file, encoding="utf-8")
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                log_file = fallback_log_file

    return log_file
