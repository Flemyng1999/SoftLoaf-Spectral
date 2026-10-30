"""Read-only parent liveness; Windows os.kill is not a POSIX signal probe."""
import os
import sys


def process_alive(pid):
    if sys.platform!='win32':
        try:os.kill(pid,0);return True
        except ProcessLookupError:return False
        except PermissionError:return True
    import ctypes as ct
    kernel=ct.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ct.c_uint32,ct.c_int,ct.c_uint32];kernel.OpenProcess.restype=ct.c_void_p
    kernel.GetExitCodeProcess.argtypes=[ct.c_void_p,ct.POINTER(ct.c_uint32)]
    kernel.CloseHandle.argtypes=[ct.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return ct.get_last_error()==5
    try:
        status=ct.c_uint32()
        return bool(kernel.GetExitCodeProcess(handle,ct.byref(status))) and status.value==259
    finally:kernel.CloseHandle(handle)
