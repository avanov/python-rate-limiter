"""
Public API for Rate Limits
--------------------------
"""
import logging
import time
from typing import Sequence

from .definitions import Request
from .definitions import RateLimiter
from .definitions import IState
from .definitions import Timestamp
from .definitions import Window
from .definitions import WindowRange

log = logging.getLogger(__name__)


def is_limit_reached(
    state: IState,
    rate_limits: Sequence[RateLimiter],
    request: Request
) -> bool:
    """ Checks if a given request is made outside existing rate limits.

    :param state: Rate Limiters' global shared state.
    :param rate_limits: sequence of currently active rate limiters.
    :param request: A request description object necessary for rate limiter functionality.
    """
    # Since we are using a generator expression to perform "check & hit",
    # we will return from this function on the first non-passed rate limiter.
    # Therefore, we need to make sure that we hit the smallest rate limit
    # first, to have a deterministic behaviour with multiple rate limits
    # that may / may not register the hit based on the success of the hit
    # of the preceding rate limiter. Hence, this sorting:
    rate_limits = sorted(rate_limits, key=lambda x: x.limit)

    now = time.time()
    # keep it a lazy object here, no lists
    limits_pass = (
        _hit(state, now, rl, request) for rl in rate_limits
        if _match(rl, request)
    )
    return not all(limits_pass)


def _match(rate_limiter: RateLimiter, request: Request) -> bool:
    """ Decides if the current rate limit is applicable to a given request.
    """
    if (
        rate_limiter.endpoint_name_filter
        and rate_limiter.endpoint_name_filter != request.endpoint
    ):
        return False

    if (
        rate_limiter.app_name_filter
        and rate_limiter.app_name_filter != request.app_id
    ):
        return False

    return True


def _hit(state: IState, now: float, rl: RateLimiter, request: Request) -> bool:
    """ Register an endpoint hit and tell if it is beyond allowed limit.

    :return: True if the hit was made within allowed limit, False otherwise.
    """
    try:
        window_range = _get_window_range(now, rl)
        domain_key = _get_counter_domain_key(rl, request)

        # Calculate the hit
        # -----------------
        counters = state.hit_and_collect_counters(domain_key, window_range)

        total_hits = 0
        expired = []
        for bucket, hits in counters.items():
            if Timestamp(bucket) < window_range.first_bucket:
                expired.append(bucket)
            else:
                total_hits += int(hits)

        # Invalidate (if necessary)
        # -------------------------
        state.expire_buckets(domain_key, expired)

        return total_hits <= rl.limit
    except Exception as e:
        log.error(str(e))
    return True


def _get_window_range(now: float, rl: RateLimiter) -> WindowRange:
    # we infer the number of seconds that fit into a single bucket of a provided window size,
    # note that different windows have different number of possible bucket sizes, and that affects
    # the number of seconds we can fit into one bucket
    seconds_per_bucket = _SECONDS_IN_WINDOW_SIZE[rl.window] // rl.window_buckets
    # once we have a number of seconds per bucket per window size, we can infer the current id
    # of the bucket by chunking the entire timeline into buckets
    # (because we know a typical bucket size in terms of seconds)
    current_serial_bucket_pos = int(now // seconds_per_bucket)

    return WindowRange(
        current_bucket=current_serial_bucket_pos * seconds_per_bucket,
        first_bucket=(current_serial_bucket_pos - rl.window_buckets + 1) * seconds_per_bucket,  # noqa
        lifetime=rl.window_buckets * seconds_per_bucket,
    )


def _get_counter_domain_key(rl: RateLimiter, request: Request) -> str:
    """ Counter Domain Key is the key of a hashkey object
    that is used for storing bucket-based counters for a given rate limiter.
    """
    endpoint_name = rl.endpoint_name_filter or _NOT_LIMITED_BY_ENDPOINT_NAME
    app_name = rl.app_name_filter or _NOT_LIMITED_BY_APP_NAME
    if rl.user_filter:
        user_id = request.user_id
    else:
        user_id = _NOT_LIMITED_BY_USER
    # We use {rl.id_or_name} prefix to prevent situations like:
    # 1. a rate limit with 100/hour is created on endpoint A
    # 2. a rate limit with 1000/day is created on endpoint A
    # 3. sum(counters) on the endpoint A is now mixed
    #    with 100/hour and 1000/day metrics.
    # We also don't want to use just {rl.id_or_name}, because modifications
    # made to endpoint name / app name / user_id will be mixed
    # within one hash object, which would provide the same mixed counters
    # issue across multiple subsequent modifications of the settings.
    return f'LIMIT:{rl.id_or_name}:{app_name}:{endpoint_name}:{user_id}'


# A few constants for underlying Redis storage implementation.
# Tilde is used for preventing id_or_name clash with actual endpoint / app id_or_name etc
_NOT_LIMITED_BY_ENDPOINT_NAME = '~anyendpoint'
_NOT_LIMITED_BY_APP_NAME = '~anyapp'
_NOT_LIMITED_BY_USER = '~anyuser'

_SECONDS_IN_WINDOW_SIZE = {
    Window.SECOND: 1,
    Window.MINUTE: 60,
    Window.HOUR: 60 * 60,
    Window.DAY: 60 * 60 * 24,
    Window.MONTH: 60 * 60 * 24 * 30,
    Window.YEAR: 60 * 60 * 24 * 365,
}
