"""A fake Google API client: handlers keyed 'collection.method', every call recorded."""

from collections.abc import Callable
from typing import Any


class _Request:
    """What `svc.x().y(...)` returns: `.execute()` runs the handler."""

    def __init__(self, fake: 'FakeGoogle', name: str, kwargs: dict) -> None:
        self.fake, self.name, self.kwargs = fake, name, kwargs

    def execute(self) -> Any:
        """Record the call and answer it."""
        self.fake.calls.append((self.name, self.kwargs))
        return self.fake.handlers[self.name](**self.kwargs)


class _Collection:
    """What `svc.x()` returns."""

    def __init__(self, fake: 'FakeGoogle', collection: str) -> None:
        self.fake, self.collection = fake, collection

    def __getattr__(self, method: str) -> Callable[..., object]:
        """A nested collection when handlers exist below it (gmail users().messages()), otherwise a request."""
        if method.startswith('_'):
            raise AttributeError(method)
        name = f'{self.collection}.{method}'
        if any(key.startswith(f'{name}.') for key in self.fake.handlers):
            return lambda **kwargs: _Collection(self.fake, name)
        return lambda **kwargs: _Request(self.fake, name, kwargs)


class FakeGoogle:
    """Stands in for a googleapiclient Resource."""

    def __init__(self, handlers: dict[str, Callable[..., Any]]) -> None:
        self.handlers = handlers
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, collection: str) -> Callable[[], _Collection]:
        """Any collection name, called like svc.events()."""
        if collection.startswith('_'):
            raise AttributeError(collection)
        return lambda: _Collection(self, collection)


def pages(*items: list[dict], key: str = 'items') -> Callable[..., dict]:
    """A list handler that answers one page per call, with a next page token while pages are left."""
    left = list(items)

    def answer(**kwargs: Any) -> dict:
        page = {key: left.pop(0)}
        return page | ({'nextPageToken': f'p{len(left)}'} if left else {})

    return answer
