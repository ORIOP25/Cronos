"""Poll cooperative cancellation while a native solver blocks."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Event


def solve_with_cancellation(
    solve: Callable[[], int],
    stop: Callable[[], None],
    should_cancel: Callable[[], bool] | None,
) -> int:
    if should_cancel is None:
        return solve()
    finished = Event()

    def run():
        try:
            return solve()
        finally:
            finished.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(run)
        try:
            while not finished.wait(0.1):
                if should_cancel():
                    # Retry until termination: stopping can race native startup.
                    stop()
        finally:
            while not finished.is_set():
                stop()
                finished.wait(0.1)
        return result.result()
