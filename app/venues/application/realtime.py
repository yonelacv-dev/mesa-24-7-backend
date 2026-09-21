QUEUE_CHANGED = "queue_changed"


def venue_topic(venue_id: int) -> str:
    """Señal sin datos: 'algo cambió en este local'. La escuchan la tablet y los comensales para recargar."""
    return f"venue:{venue_id}"


def host_topic(venue_id: int) -> str:
    """Detalle de lo ocurrido (quién se unió, a quién se llamó...). Solo lo escucha el anfitrión."""
    return f"venue:{venue_id}:host"
