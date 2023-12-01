import threading
from collections import defaultdict
from typing import Mapping, Sequence

from .definitions import IState, WindowRange


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
                    domain_buckets.pop(x)
                except KeyError:
                    pass
