"""Redis-backed async checkpointer for the LangGraph agent graph.

The checkpointer persists graph state between steps, enabling:
- HITL (human-in-the-loop): graph pauses at interrupt(), resumes via thread_id
- Conversation continuity: same thread_id picks up where it left off

Usage in app.py lifespan:
    async with create_checkpointer(settings.redis_url) as checkpointer:
        app.state.checkpointer = checkpointer
        yield

Nodes receive thread_id via config["configurable"]["thread_id"] at invoke time.
"""

from langgraph.checkpoint.redis.aio import AsyncRedisSaver


def create_checkpointer(redis_url: str) -> AsyncRedisSaver:
    """Return an AsyncRedisSaver context manager for the given Redis URL.

    Enter it with ``async with`` in the app lifespan to open the connection;
    exiting closes it. Pass the live instance to ``build_graph(checkpointer=...)``.
    """
    return AsyncRedisSaver.from_conn_string(redis_url)
