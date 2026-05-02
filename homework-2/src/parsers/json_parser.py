import json
from collections.abc import Iterable
from typing import Any

from src.parsers.base import ParserError


class JsonTicketParser:
    def parse(self, content: bytes) -> Iterable[dict[str, Any]]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParserError(f"Invalid JSON: {exc}") from exc

        if isinstance(data, dict) and "tickets" in data:
            data = data["tickets"]

        if not isinstance(data, list):
            raise ParserError(
                "JSON root must be an array, or an object with a `tickets` array"
            )

        result: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ParserError(
                    f"Each ticket must be a JSON object, got {type(item).__name__}"
                )
            result.append(item)
        return result
