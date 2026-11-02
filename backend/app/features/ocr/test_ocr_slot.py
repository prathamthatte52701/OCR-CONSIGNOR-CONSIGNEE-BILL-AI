"""OCR slot: plain fake functions, no PaddleOCR."""

import asyncio
import threading
import time

import pytest

from app.features.ocr.ocr_slot import run_in_ocr_slot


async def test_simultaneous_calls_never_overlap() -> None:
    lock, state = threading.Lock(), {"now": 0, "peak": 0}

    def work() -> int:
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return 1

    results = await asyncio.gather(*(run_in_ocr_slot(work, timeout=5) for _ in range(4)))
    assert results == [1, 1, 1, 1] and state["peak"] == 1


async def test_next_call_waits_for_a_thread_that_outlived_its_timeout() -> None:
    release, first_ended, second_started = threading.Event(), threading.Event(), threading.Event()

    def slow() -> None:
        release.wait(5)
        first_ended.set()

    def second() -> str:
        assert first_ended.is_set(), "second run started while the first thread was still running"
        second_started.set()
        return "ok"

    with pytest.raises(TimeoutError):
        await run_in_ocr_slot(slow, timeout=0.1)
    task = asyncio.ensure_future(run_in_ocr_slot(second, timeout=5))
    await asyncio.sleep(0.2)
    assert not second_started.is_set()  # still waiting: the slot is held
    release.set()
    assert await task == "ok"


async def test_exception_in_thread_releases_the_slot() -> None:
    def boom() -> None:
        raise ValueError("engine crashed")

    with pytest.raises(ValueError):
        await run_in_ocr_slot(boom, timeout=5)
    assert await run_in_ocr_slot(lambda: "next", timeout=5) == "next"


async def test_cancelling_a_waiting_task_leaks_nothing() -> None:
    release = threading.Event()
    holder = asyncio.ensure_future(run_in_ocr_slot(lambda: release.wait(5), timeout=10))
    await asyncio.sleep(0.05)
    waiter = asyncio.ensure_future(run_in_ocr_slot(lambda: "never", timeout=10))
    await asyncio.sleep(0.05)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await holder
    assert await run_in_ocr_slot(lambda: "free", timeout=5) == "free"


async def test_cancelling_the_running_caller_keeps_the_slot_until_the_thread_ends() -> None:
    release, ended = threading.Event(), threading.Event()

    def slow() -> None:
        release.wait(5)
        ended.set()

    running = asyncio.ensure_future(run_in_ocr_slot(slow, timeout=10))
    await asyncio.sleep(0.05)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    follow = asyncio.ensure_future(run_in_ocr_slot(lambda: ended.is_set(), timeout=10))
    await asyncio.sleep(0.1)
    assert not follow.done()  # the thread is still running: slot still held
    release.set()
    assert await follow is True  # it only started after the first thread had ended


def _one_run() -> str:
    async def main() -> str:
        return str(await run_in_ocr_slot(lambda: "ok", timeout=5))

    return asyncio.run(main())


def test_works_from_two_separate_event_loops() -> None:
    assert _one_run() == "ok"
    assert _one_run() == "ok"
