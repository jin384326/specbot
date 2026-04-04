from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.clause_browser.services import LLMActionCancelledError, LLMActionQueueFullError


class SharedTaskLimiter:
    def __init__(self, max_concurrent_tasks: int, max_queued_tasks: int) -> None:
        self._max_concurrent_tasks = max(1, int(max_concurrent_tasks))
        self._max_queued_tasks = max(0, int(max_queued_tasks))
        self._lock = asyncio.Lock()
        self._active_tasks = 0
        self._accepted_tasks = 0
        self._queue: asyncio.Queue[_QueuedTask] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._workers = [asyncio.create_task(self._worker_loop()) for _ in range(self._max_concurrent_tasks)]

    async def shutdown(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        self._started = False

    async def run_async(self, fn, *args, should_cancel=None, on_status_change=None, **kwargs):
        await self.start()
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        queued_position = 0
        job = _QueuedTask(
            fn=fn,
            args=args,
            kwargs=kwargs,
            future=future,
            should_cancel=should_cancel,
            on_status_change=on_status_change,
        )
        async with self._lock:
            if self._accepted_tasks >= self._max_concurrent_tasks + self._max_queued_tasks:
                raise LLMActionQueueFullError(
                    "The shared query/translation queue is full. Wait for current tasks to finish and try again."
                )
            queued_position = max(0, self._accepted_tasks - self._active_tasks)
            self._accepted_tasks += 1
            self._queue.put_nowait(job)
        if on_status_change is not None:
            on_status_change(
                {
                    "state": "queued",
                    "queued_position": queued_position + 1,
                    "active_tasks": self._active_tasks,
                    "accepted_tasks": self._accepted_tasks,
                }
            )

        while True:
            if should_cancel and should_cancel():
                job.cancelled = True
                if not future.done():
                    future.set_exception(LLMActionCancelledError("Task cancelled by client."))
                raise LLMActionCancelledError("Task cancelled by client.")
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=0.2)
            except asyncio.TimeoutError:
                continue

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            async with self._lock:
                self._active_tasks += 1
                active_tasks = self._active_tasks
                accepted_tasks = self._accepted_tasks
            try:
                if job.on_status_change is not None:
                    job.on_status_change(
                        {
                            "state": "started",
                            "active_tasks": active_tasks,
                            "accepted_tasks": accepted_tasks,
                        }
                    )
                if job.cancelled or job.future.done() or (job.should_cancel and job.should_cancel()):
                    if not job.future.done():
                        job.future.set_exception(LLMActionCancelledError("Task cancelled by client."))
                    continue
                result = await asyncio.to_thread(job.fn, *job.args, **job.kwargs)
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                async with self._lock:
                    self._active_tasks = max(0, self._active_tasks - 1)
                    self._accepted_tasks = max(0, self._accepted_tasks - 1)
                self._queue.task_done()


@dataclass
class _QueuedTask:
    fn: Any
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: asyncio.Future
    should_cancel: Any = None
    on_status_change: Any = None
    cancelled: bool = field(default=False)
