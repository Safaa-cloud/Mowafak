import os
import time
import logging
import structlog
from functools import wraps
from typing import Any, Callable
from src.settings import settings

# ==========================================
# 1. PII Redaction Processor (Privacy)
# ==========================================
def pii_redaction_processor(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Scans log events and redacts potential PII keys to comply with 
    Responsible AI standards before data is written to disk.
    """
    sensitive_keys = ["email", "name", "candidate_name", "cv_text", "transcript"]
    for key in sensitive_keys:
        if key in event_dict:
            event_dict[key] = "[REDACTED_PII]"
    return event_dict

# ==========================================
# 2. Configure Structlog
# ==========================================
def configure_observability():
    """Sets up structured logging for the entire Mowafak pipeline."""
    
    # Standard logging for internal libraries
    logging.basicConfig(level=logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            pii_redaction_processor, # Our custom RAI privacy filter
            structlog.dev.ConsoleRenderer() if os.getenv("DEBUG") == "True" else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

log = structlog.get_logger()

# ==========================================
# 3. Performance Tracing Decorator
# ==========================================
def trace_node(node_name: str):
    """
    A decorator to measure the execution time and success rate 
    of LangGraph nodes or AI Agent calls.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            log.info("node_started", node=node_name)
            
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                log.info("node_completed", node=node_name, duration_sec=round(duration, 3))
                return result
            except Exception as e:
                log.error("node_failed", node=node_name, error=str(e))
                raise e
        return wrapper
    return decorator

# Initialize on import
configure_observability()