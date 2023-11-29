from collections import defaultdict

import redis

from enum import Enum
import threading
from typing import NamedTuple, Sequence, Mapping, Protocol
from typing import Optional

Timestamp = int
Seconds = int


class WindowRange(NamedTuple):
    current_bucket: Timestamp
    first_bucket: Timestamp
    lifetime: Seconds


class Window(Enum):
    """ Available window types
    """
    SECOND = 'second'
    MINUTE = 'minute'
    HOUR = 'hour'
    DAY = 'day'
    MONTH = 'month'
    YEAR = 'year'


class RateLimiter:
    WINDOW_BUCKETS_LIMITS = {
        Window.SECOND: 60,
        Window.MINUTE: 60,
        Window.HOUR: 60,
        Window.DAY: 24,
        Window.MONTH: 30,
        Window.YEAR: 12,
    }
    __slots__ = (
        'id_or_name',
        'endpoint_name_filter',
        'app_name_filter',
        'user_filter',
        'limit',
        'window',
        'window_buckets',
    )

    def __init__(
        self,
        *,
        id_or_name: str,
        endpoint_name_filter: Optional[str],
        app_name_filter: Optional[str],
        user_filter: bool,
        limit: int,
        window: str,
        window_buckets: int,
    ) -> None:
        self.id_or_name = id_or_name
        self.endpoint_name_filter = endpoint_name_filter
        self.app_name_filter = app_name_filter
        self.user_filter = user_filter
        self.limit = limit
        self.window = Window(window)  # rate = `limit` per `window`
        if self.window is Window.SECOND:
            # we don't need several expiration buckets for a second
            window_buckets = 1
        self.window_buckets = window_buckets
        if window_buckets > self.WINDOW_BUCKETS_LIMITS[self.window]:
            raise ValueError(
                f'Unsupported buckets number {window_buckets} for window type {self.window}'
            )

    def __repr__(self) -> str:
        return (
            f'RateLimiter({self.id_or_name}, {self.endpoint_name_filter}, '
            f'{self.app_name_filter}, '
            f'{self.user_filter}, '
            f'{self.limit}, '
            f'{self.window.value})'
        )


class Request(NamedTuple):
    app_id: str
    """ Application ID of the client making a request.
    """
    user_id: str
    """ ID of a client making a request.
    """
    endpoint: str
    """ An identifier of the endpoint being rate-limited. It could be either a route name or route path, there's no
    big difference as long as it provides a unique name among a collection of all endpoints being rate-limited.
    """


class IState(Protocol):
    """ Generic global shared state interface for rate limiter data.
    """
    def hit_and_collect_counters(
        self,
        domain_key: str,
        window_range: WindowRange
    ) -> Mapping[str, int]:
        """ Increments the current window's current bucket and returns all existing buckets of the
        rate limiter registered under ``domain_key``
        """
        ...

    def expire_buckets(self, domain_key: str, buckets: Sequence[str]) -> None:
        """ Expire buckets that are out of range of the current window.
        """
        ...


class RedisState(IState):
    """ State implementation for Redis backing store.
    """
    __slots__ = ['redis_pool']

    def __init__(self) -> None:
        self.redis_pool = redis.Redis(connection_pool=redis.ConnectionPool())

    def hit_and_collect_counters(
        self,
        domain_key: str,
        window_range: WindowRange
    ) -> Mapping[str, int]:
        with self.redis_pool.pipeline(transaction=True) as pipe:
            pipe.hincrby(domain_key, str(window_range.current_bucket), 1)
            pipe.expire(domain_key, window_range.lifetime)
            pipe.hgetall(domain_key)
            *__, counters = pipe.execute()
            return counters  # type: ignore

    def expire_buckets(self, domain_key: str, buckets: Sequence[str]) -> None:
        if buckets:
            self.redis_pool.hdel(domain_key, *buckets)


class ProcessState(IState):
    """ State implementation for process' in-memory store.
    """
    __slots__ = ['state', 'lock']

    def __init__(self):
        self.state: dict[str, dict[str, int]] = {}
        self.lock = threading.Lock()

    def hit_and_collect_counters(
        self,
        domain_key: str,
        window_range: WindowRange
    ) -> Mapping[str, int]:
        with self.lock:
            domain_buckets = self.state.setdefault(domain_key, defaultdict(int))
            domain_buckets[str(window_range.current_bucket)] += 1
            return domain_buckets

    def expire_buckets(self, domain_key: str, buckets: Sequence[str]) -> None:
        domain_buckets = self.state.get(domain_key)
        if not domain_buckets:
            return

        with self.lock:
            for x in buckets:
                try:
                    self.state[domain_key].pop(x)
                except KeyError:
                    pass
