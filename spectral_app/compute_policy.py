"""One retry boundary for GPU device failures; validation errors stay errors."""
from functools import wraps
from .diagnostics import event


class GPUUnavailable(RuntimeError):
    """The backend has disabled itself before requesting a CPU retry."""


def retry_cpu(operation):
    @wraps(operation)
    def run(*args,**kwargs):
        try:return operation(*args,**kwargs)
        except GPUUnavailable:
            event('compute.cpu_retry',backend='cpu',reason='gpu_dispatch_failed')
            return operation(*args,**kwargs)
    return run


def choose_backend(requested,factory,*,strict=False):
    if requested=='cpu':return None
    try:return factory()
    except (OSError,RuntimeError) as error:
        if strict:raise
        event('compute.fallback',requested_backend=requested,backend='cpu',reason='gpu_startup_failed',error=error)
        return None
