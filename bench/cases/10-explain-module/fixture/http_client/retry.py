import random
import time
from dataclasses import dataclass, field

MAX_ATTEMPTS = 4
BASE_DELAY_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 8.0
MAX_RETRY_AFTER_SECONDS = 30.0
RETRYABLE_STATUS = {429, 502, 503, 504}
IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE"}


@dataclass
class Response:
    status: int
    headers: dict = field(default_factory=dict)


def _may_retry(method: str, headers: dict) -> bool:
    return method in IDEMPOTENT_METHODS or "Idempotency-Key" in headers


def _backoff(attempt: int) -> float:
    ceiling = min(BASE_DELAY_SECONDS * 2 ** (attempt - 1), MAX_BACKOFF_SECONDS)
    return random.uniform(0, ceiling)


def _retry_after(response: Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None or not value.isdigit():
        return None
    return min(float(value), MAX_RETRY_AFTER_SECONDS)


def send_with_retry(send, method: str, url: str, headers: dict | None = None,
                    sleep=time.sleep) -> Response:
    headers = headers or {}
    retryable = _may_retry(method, headers)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        last_attempt = attempt == MAX_ATTEMPTS or not retryable
        try:
            response = send(method, url, headers)
        except (ConnectionError, TimeoutError):
            if last_attempt:
                raise
            sleep(_backoff(attempt))
            continue
        if response.status not in RETRYABLE_STATUS or last_attempt:
            return response
        delay = _retry_after(response)
        sleep(delay if delay is not None else _backoff(attempt))
    raise AssertionError("unreachable")
