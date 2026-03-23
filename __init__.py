#!/usr/bin/env python3
"""
NotebookLM Tools Package

A collection of tools for generating artifacts from NotebookLM sources.
"""

__version__ = "1.0.0"

from .utils import *
from .client import *
from .task import *
from .cli import *

__all__ = [
    # utils
    "sanitize_filename",
    "log_message",
    "run_command",
    "parse_indices",
    
    # client
    "check_login_status",
    "list_notebooks",
    "list_sources",
    
    # task
    "BaseGenerationTask",
    "submit_generation_tasks",
    "poll_task_statuses",
    
    # cli
    "get_user_choice",
    "get_language_choice",
    "get_instructions",
]