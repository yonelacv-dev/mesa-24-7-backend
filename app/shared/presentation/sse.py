import json
from typing import Any

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # que nginx no acumule el stream
}


def sse_message(event: str, data: Any) -> str:
    """Un mensaje Server-Sent Events. `data` va como una sola línea de JSON."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def sse_heartbeat() -> str:
    """Comentario SSE: mantiene viva la conexión sin disparar ningún evento en el cliente."""
    return ": heartbeat\n\n"
