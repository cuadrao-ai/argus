from __future__ import annotations

import os
import sys
from typing import Any

from loguru import logger


def configure_logging(sink: Any = sys.stderr) -> None:
    logger.remove()
    logger.add(sink, diagnose=False, backtrace=False)


def exception_origin(exc: BaseException) -> str:
    # Deepest argus frame, so a local rejection points at the raising line
    # rather than at the generic call site that caught it.
    traceback = exc.__traceback__
    origin = ""
    while traceback is not None:
        frame = traceback.tb_frame
        filename = frame.f_code.co_filename
        if f"{os.sep}argus{os.sep}" in filename:
            origin = f"{os.path.basename(filename)}:{traceback.tb_lineno}"
        traceback = traceback.tb_next
    return origin
