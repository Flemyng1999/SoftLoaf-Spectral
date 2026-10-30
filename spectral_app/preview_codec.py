"""Interactive encoding policy; exported images keep their independent readback checks."""
from contextlib import contextmanager
from contextvars import ContextVar
_interactive=ContextVar('interactive_preview',default=False)


def interactive():return _interactive.get()


@contextmanager
def interactive_encoding():
    token=_interactive.set(True)
    try:yield
    finally:_interactive.reset(token)
