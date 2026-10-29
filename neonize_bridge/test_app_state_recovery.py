"""One request at a time for a fresh app-state copy (app_state_recovery.py).

Reported: with `regular_low` broken, every chat opened started its own 90 s
wait for the phone, on threads the sends needed too; a message was reported
as not confirmed and went out a moment later."""
import threading

import app_state_recovery as ar


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_a_second_caller_gives_up_while_one_request_runs():
    gate = ar.RecoveryGate(clock=_Clock())
    started, release, results = threading.Event(), threading.Event(), []

    def slow():
        started.set()
        release.wait(5)
        return True

    first = threading.Thread(target=lambda: results.append(gate.run("regular_low", slow)))
    first.start()
    started.wait(5)
    calls = []
    assert gate.run("regular_low", lambda: calls.append(1) or True) is False
    assert calls == []                      # it did not wait, nor ask again
    # another collection is not held back
    assert gate.run("regular_high", lambda: True) is True
    release.set()
    first.join(5)
    assert results == [True]


def test_after_an_unanswered_request_nobody_asks_again_for_a_while():
    clock = _Clock()
    gate = ar.RecoveryGate(clock=clock, cooldown=120)
    calls = []
    assert gate.run("regular_low", lambda: calls.append(1) or False) is False
    clock.now += 60
    assert gate.run("regular_low", lambda: calls.append(2) or True) is False
    clock.now += 61
    assert gate.run("regular_low", lambda: calls.append(3) or True) is True
    assert calls == [1, 3]


def test_a_request_that_raises_counts_as_unanswered():
    clock = _Clock()
    gate = ar.RecoveryGate(clock=clock, cooldown=120)

    def broken():
        raise RuntimeError("socket closed")

    try:
        gate.run("regular_low", broken)
    except RuntimeError:
        pass
    assert gate.run("regular_low", lambda: True) is False


def test_send_seen_runs_on_threads_of_its_own():
    import pathlib
    source = (pathlib.Path(__file__).parent / "server.py").read_text(encoding="utf-8")
    route = source[source.index("    async def send_seen(req):"):
                   source.index("    async def subscribe_presence(req):")]
    assert "run_in_executor(marking, s.read_and_confirm, key, True)" in route
    assert "run_in_executor(marking, s.mark_unread, keys[0])" in route
    assert "in_thread(s.read_and_confirm" not in route
