"""Process-lifecycle helpers shared across NAVERA nodes.

Currently exposes :func:`die_with_parent`, which ties a node's lifetime to its
launcher so a killed supervisor (``ros2 launch`` or the systemd service unit)
never leaves orphaned nodes reparented to init (PID 1). This lives in a shared
package so the guarantee is defined once instead of copy-pasted into every
node's ``main()``.
"""
import ctypes
import os
import signal
import sys

# From <linux/prctl.h>. prctl(PR_SET_PDEATHSIG, sig) asks the kernel to deliver
# `sig` to the calling thread when its parent *thread* terminates.
PR_SET_PDEATHSIG = 1


def die_with_parent(sig: int = signal.SIGTERM) -> bool:
    """Request that this process receive ``sig`` when its parent dies.

    On Linux this arms ``prctl(PR_SET_PDEATHSIG, sig)`` so that if the parent
    (e.g. the ``ros2 launch`` process or the systemd unit) is killed, the kernel
    delivers ``sig`` to us instead of silently reparenting us to init. Our nodes
    handle SIGTERM cleanly, so the default gives an orderly shutdown.

    Because ``PR_SET_PDEATHSIG`` fires only on a *future* parent death, there is
    an inherent race: if the parent already exited before this call, no signal
    is ever sent. We close that window by checking ``getppid()`` afterwards — a
    value of 1 means we were already reparented to init, so we raise ``sig`` on
    ourselves immediately.

    Args:
        sig: Signal to request on parent death. Defaults to ``SIGTERM``.

    Returns:
        ``True`` if the death signal was armed, ``False`` on a non-Linux
        platform or if the ``prctl`` call failed. A ``False`` return is
        non-fatal: the caller keeps running, just without the guarantee.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if libc.prctl(PR_SET_PDEATHSIG, ctypes.c_ulong(sig), 0, 0, 0) != 0:
            return False
    except (OSError, AttributeError):
        return False

    # Cover the race: parent may have died between fork/exec and this call.
    if os.getppid() == 1:
        os.kill(os.getpid(), sig)
    return True
