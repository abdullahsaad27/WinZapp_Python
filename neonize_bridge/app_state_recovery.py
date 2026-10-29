"""One request at a time for a fresh copy of an app-state collection.

When a collection's LTHash stops matching, the bridge asks the phone for a
fresh copy and waits up to 90 s for it (an iPhone only answers with WhatsApp
open on the screen). Reported: on one account `regular_low` stayed broken, and
every chat the user opened (send-seen -> markChatAsRead) started its own
request and its own 90 s wait, each on a thread of the executor the sends use
too. A message then waited past the client's 25 s, was reported as not
confirmed, and went out a moment later.

`RecoveryGate` lets one request run per collection: another caller meanwhile
gives up at once instead of waiting, and after a request the phone did not
answer, nobody asks again for COOLDOWN seconds. Giving up only skips the state
notice (the chat's "read" on the phone); the read receipts to the contact are
sent as before. Tested in test_app_state_recovery.py.
"""
import threading
import time

#: seconds after an unanswered request before the phone is asked again
COOLDOWN = 120.0


class RecoveryGate:
    def __init__(self, clock=time.monotonic, cooldown=COOLDOWN):
        self._clock = clock
        self._cooldown = cooldown
        self._guard = threading.Lock()
        self._running = set()
        self._failed_at = {}

    def run(self, name, recover):
        """`recover()` for collection `name` unless one is running or one just
        went unanswered; False without calling it then."""
        with self._guard:
            failed = self._failed_at.get(name)
            if name in self._running or (
                    failed is not None and self._clock() - failed < self._cooldown):
                return False
            self._running.add(name)
        recovered = False
        try:
            recovered = bool(recover())
            return recovered
        finally:
            with self._guard:
                self._running.discard(name)
                if recovered:
                    self._failed_at.pop(name, None)
                else:
                    self._failed_at[name] = self._clock()
