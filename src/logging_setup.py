"""
logging_setup.py — Centraliserad loggning för pipelinen.

Två loggers:
  - pipeline.debug: DEBUG+ → debug_<ts>.log
  - pipeline.summary: INFO+ → summary_<ts>.log + console
"""

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(out_base: Path, step_num: int = None, step_name: str = None):
    """Skapar två loggfiler och en console-handler.
    
    Loggfiler sparas i:
      - log/         → debug_stegN_namn_<ts>.log
      - summary/     → summary_stegN_namn_<ts>.log
    
    Args:
        out_base: Basutmatningskatalog
        step_num: Steg-nummer (om None, är det en master-logg)
        step_name: Steg-namn för loggfil-suffix
    """
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Skapa loggfilnamn med eventuell steg-referens
    if step_num is not None and step_name:
        step_suffix = f"steg_{step_num}_{step_name}_{ts}"
    else:
        step_suffix = f"ts"
    
    debug_log   = log_dir / f"debug_{step_suffix}.log"
    summary_log = summary_dir / f"summary_{step_suffix}.log"

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
    
    summary.info("Pipeline startat")
    summary.info(f"Debug-logg: {debug_log}")
    summary.info(f"Summary-logg: {summary_log}")


def log_step_header(logger, step_num: int, step_name: str, source: str = None, output: str = None):
    """Log a standardized step header with separator lines.
    
    Args:
        logger: Logger instance (pipeline.summary)
        step_num: Step number (1-9)
        step_name: Step description
        source: Source directory path (optional)
        output: Output directory path (optional)
    """
    logger.info("══════════════════════════════════════════════════════════")
    logger.info(f"Steg {step_num}: {step_name}")
    if source:
        logger.info(f"Källmapp : {source}")
    if output:
        logger.info(f"Utmapp   : {output}")
    logger.info("══════════════════════════════════════════════════════════")
