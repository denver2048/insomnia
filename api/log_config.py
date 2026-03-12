"""
Logging: filter to suppress uvicorn access log for /healthz and /readyz.
"""
import logging


class SkipHealthProbeFilter(logging.Filter):
    """Drop access log records for GET /healthz and GET /readyz."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "healthz" not in msg and "readyz" not in msg


def install_access_log_filter():
    """Add filter to uvicorn.access logger so healthz/readyz are not logged."""
    access_log = logging.getLogger("uvicorn.access")
    access_log.addFilter(SkipHealthProbeFilter())
