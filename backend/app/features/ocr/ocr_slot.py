"""The ONE OCR slot: at most one heavy OCR engine run (PaddleOCR / PP-Structure) at a time.

asyncio.wait_for(asyncio.to_thread(...)) only stops WAITING when its timeout fires - the thread
keeps running. A plain lock released at that moment would let the next job start a second engine
run on the same model. So the slot is released by a done-callback of the thread's own future:
only when the thread has really finished, whatever happened to the caller (timeout, cancel).

Accepted limit: a thread that hangs forever keeps the slot until the app restarts."""

import asyncio
import weakref
from collections.abc import Callable
from typing import Any

from loguru import logger

# One lock per running event loop (a Lock binds to the loop it first waits on; TestClient and
# tests create a new loop each time). Production has a single loop, so a single process-wide slot.
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _slot() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if loop not in _locks:
        _locks[loop] = asyncio.Lock()
    return _locks[loop]


async def run_in_ocr_slot(fn: Callable[..., Any], *args: Any, timeout: float) -> Any:
    """Runs fn(*args) in a thread once the slot is free. `timeout` covers the run only (it starts
    after the slot is taken). On timeout/cancel the caller stops waiting, the slot stays held."""
    lock = _slot()
    await lock.acquire()  # cancelled while waiting -> never acquired, nothing to give back
    try:
        future = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    except BaseException:
        lock.release()
        raise

    def _finished(done: "asyncio.Future[Any]") -> None:
        if not done.cancelled():
            done.exception()  # mark retrieved: no "exception never retrieved" warning
        lock.release()

    future.add_done_callback(_finished)
    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout)
    except TimeoutError:
        logger.error("OCR thread still running after timeout; slot stays held until it ends")
        raise
