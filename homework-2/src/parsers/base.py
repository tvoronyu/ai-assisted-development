from collections.abc import Iterable
from typing import Any, Protocol


class TicketParser(Protocol):
    def parse(self, content: bytes) -> Iterable[dict[str, Any]]: ...


class ParserError(Exception):
    pass
