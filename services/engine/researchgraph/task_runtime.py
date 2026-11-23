"""In-process job control. Durable task and receipt state remain in SQLite."""

import asyncio
from collections.abc import Awaitable, Coroutine
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

WorkerStatus = Literal["idle", "running", "recovering", "stopped", "disabled"]
Lane = Literal["jobs", "diagnostics"]


class ModelWaitCancelled(RuntimeError):
    """The user stopped a local wait. A request already sent may still be billed."""

    def __init__(self) -> None:
        super().__init__("已停止本机等待；已发送的请求仍可能产生费用")


@dataclass(frozen=True)
class ClaimedJob:
    job_id: str
    kind: str
    attempt: int


@dataclass
class _Execution:
    wait: asyncio.Task[Any] | None = None
    cancelled: bool = False

    def cancel(self) -> None:
        if not self.cancelled:
            self.cancelled = True
            if self.wait is not None:
                self.wait.cancel()


_execution: ContextVar[_Execution | None] = ContextVar("job_execution", default=None)


async def wait_for_model[T](operation: Coroutine[Any, Any, T]) -> T:
    """Make only the Provider await cancellable, leaving receipt writes to its caller."""
    execution = _execution.get()
    if execution is None:
        return await operation
    if execution.cancelled:
        operation.close()
        raise ModelWaitCancelled()
    task = asyncio.create_task(operation)
    execution.wait = task
    try:
        return await task
    except asyncio.CancelledError:
        owner = asyncio.current_task()
        if execution.cancelled and owner is not None and not owner.cancelling():
            raise ModelWaitCancelled() from None
        raise
    finally:
        execution.wait = None


class TaskRuntime:
    """Track queue health and forward committed cancellation to the owning loop."""

    def __init__(self, *, enabled: bool) -> None:
        self.loop = asyncio.get_running_loop()
        initial: WorkerStatus = "idle" if enabled else "disabled"
        self.lanes: dict[Lane, tuple[WorkerStatus, str | None]] = {
            "jobs": (initial, None),
            "diagnostics": (initial, None),
        }
        self.executions: dict[tuple[str, int], _Execution] = {}
        self.claiming = 0
        self.paused_until = 0.0

    def paused(self) -> bool:
        return self.loop.time() < self.paused_until

    def pause_for_offline_operation(self) -> bool:
        if self.claiming or self.status()[0] in {"running", "recovering"}:
            return False
        # The native host stops the process immediately. A lease makes a lost
        # reply or interrupted native command recover without manual action.
        self.paused_until = self.loop.time() + 15
        return True

    def set_status(self, lane: Lane, status: WorkerStatus, error: str | None = None) -> None:
        self.lanes[lane] = (status, error)

    def status(self) -> tuple[WorkerStatus, str | None]:
        for priority in ("stopped", "recovering", "running", "idle", "disabled"):
            for state in self.lanes.values():
                if state[0] == priority:
                    return state
        raise AssertionError("worker must have a status")

    async def execute[T](self, job: ClaimedJob, operation: Awaitable[T]) -> T:
        key = (job.job_id, job.attempt)
        execution = _Execution()
        self.executions[key] = execution
        context = _execution.set(execution)
        try:
            return await operation
        finally:
            _execution.reset(context)
            del self.executions[key]

    def cancel(self, job_id: str, attempt: int) -> None:
        def interrupt() -> None:
            execution = self.executions.get((job_id, attempt))
            if execution is not None:
                execution.cancel()

        self.loop.call_soon_threadsafe(interrupt)
