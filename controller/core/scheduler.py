import asyncio
from typing import Any


class JobScheduler:
    def __init__(self) -> None:
        # agent_id -> asyncio.Queue[dict]
        self._queues: dict[str, asyncio.Queue] = {}
        # job_id -> asyncio.Event
        self._events: dict[str, asyncio.Event] = {}
        # job_id -> result
        self._results: dict[str, Any] = {}

    def register_agent(self, agent_id: str) -> None:
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()

    def unregister_agent(self, agent_id: str) -> None:
        self._queues.pop(agent_id, None)

    async def dispatch(self, agent_id: str, job: dict) -> asyncio.Event:
        event = asyncio.Event()
        self._events[job["job_id"]] = event
        await self._queues[agent_id].put(job)
        return event

    async def poll(self, agent_id: str, timeout: float) -> dict | None:
        queue = self._queues.get(agent_id)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def complete(self, job_id: str, result: Any) -> None:
        self._results[job_id] = result
        if event := self._events.get(job_id):
            event.set()

    async def wait_result(self, job_id: str, timeout: float) -> Any:
        event = self._events.get(job_id)
        if event is None:
            raise KeyError(job_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._results.pop(job_id, None)
        except asyncio.TimeoutError:
            raise
        finally:
            self._events.pop(job_id, None)

    def find_agent_for_model(self, model: str, online_agents: list[str]) -> str | None:
        for agent_id in online_agents:
            if agent_id in self._queues:
                return agent_id
        return None


scheduler = JobScheduler()
