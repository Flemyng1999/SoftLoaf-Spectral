"""Cross-process lock for retained stages and atomic workspace publication."""
import errno
import os
import sys
import time


def acquire_file_lock(stream):
    fd=stream if isinstance(stream,int) else stream.fileno()
    if sys.platform!='win32':
        import fcntl
        fcntl.flock(fd,fcntl.LOCK_EX);return
    import msvcrt
    if os.fstat(fd).st_size==0:os.write(fd,b'\0')
    deadline=time.monotonic()+300
    while True:
        try:os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_NBLCK,1);return
        except OSError as error:
            if error.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK) or time.monotonic()>deadline:raise
            time.sleep(.05)


def release_file_lock(stream):
    fd=stream if isinstance(stream,int) else stream.fileno()
    if sys.platform!='win32':
        import fcntl
        fcntl.flock(fd,fcntl.LOCK_UN);return
    import msvcrt
    os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
