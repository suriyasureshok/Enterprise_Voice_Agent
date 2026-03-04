"""Structured logger wrapper using loguru."""

from configs.logging_config import get_logger

log = get_logger(__name__)

__all__ = ["log"]
