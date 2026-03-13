"""
logging_setup.py — Centraliserad loggning för pipelinen.

Två loggers:
  - pipeline.debug: DEBUG+ → pipeline_debug_<ts>.log
  - pipeline.summary: INFO+ → pipeline_summary_<ts>.log + console
"""

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(out_base: Path):
    """Skapar två loggfiler och en console-handler.
    
    Loggfiler sparas i:
      - log/         → pipeline_debug_<ts>.log
      - summary/     → pipeline_summary_<ts>.log
    """
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_log   = log_dir / f"pipeline_debug_{ts}.log"
    summary_log = summary_dir / f"pipeline_summary_{ts}.log"

    fmt_detail  = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # ── Debug-logg (DEBUG+) ──
    dbg = logging.getLogger("pipeline.debug")
    dbg.setLevel(logging.DEBUG)
    dbg_handler = logging.FileHandler(debug_log)
    dbg_handler.setLevel(logging.DEBUG)
    dbg_handler.setFormatter(fmt_detail)
    dbg.addHandler(dbg_handler)

    # ── Summary-logg (INFO+) – både fil och console ──
    summary = logging.getLogger("pipeline.summary")
    summary.setLevel(logging.INFO)

    # Fil-handler
    summary_file_handler = logging.FileHandler(summary_log)
    summary_file_handler.setLevel(logging.INFO)
    summary_file_handler.setFormatter(fmt_summary)
    summary.addHandler(summary_file_handler)

    # Console-handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt_summary)
    summary.addHandler(console_handler)
    
    summary.info(f"Pipeline startat")
    summary.info(f"Debug-logg: {debug_log}")
    summary.info(f"Summary-logg: {summary_log}")
