"""Subprocess helper utilities for cross-platform execution.

Provides Windows-specific subprocess kwargs to prevent console window flash
and handle encoding properly.
"""

import subprocess
import sys


def get_subprocess_kwargs(timeout: int = 5) -> dict:
    """Get subprocess.run kwargs with Windows-specific handling.

    Prevents console window flash when Docker commands run by using
    proper Windows subprocess flags.

    Args:
        timeout: Command timeout in seconds (default 5 for quick status checks)

    Returns:
        Dict of kwargs for subprocess.run()
    """
    kwargs = {
        'capture_output': True,
        'text': True,
        'encoding': 'utf-8',
        'errors': 'replace',
        'timeout': timeout,
    }

    if sys.platform == 'win32':
        # Prevent console window flash and improve subprocess handling
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    return kwargs
