from typing import Mapping, Sequence

import redis

from .definitions import IState, WindowRange


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
