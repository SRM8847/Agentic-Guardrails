"""
Per-session trifecta signal tracking. A session accumulates signals across
multiple tool calls -- once a flag goes True it stays True for the rest of
the session, since "has this session ever touched sensitive data" doesn't
un-happen partway through.

Design decision: trifecta_state(session_id) reflects signals from calls
that happened BEFORE the one currently being decided, not including it.
The proxy looks up trifecta_state, uses it to decide the current call,
and only afterward calls update() with the current call's own signals.
This avoids a call's decision depending on itself, and matches how the
Rego was written and tested: trifecta_state is an input representing
prior session risk, not something recomputed mid-decision.
"""
import threading

_lock = threading.Lock()
_sessions = {}


def _blank():
    return {"touched_sensitive": False, "ingested_untrusted": False, "external_reach_attempted": False}


def update(session_id, touched_sensitive=False, ingested_untrusted=False, external_reach_attempted=False):
    """Record this call's own signal contributions. Called AFTER the
    decision for this call has already been made, using the prior state --
    intentionally unconditional on whether the call was allowed, denied, or
    required approval, since an attempted action (even a blocked one) is
    still meaningful context for what comes after it in the session."""
    with _lock:
        state = _sessions.setdefault(session_id, _blank())
        state["touched_sensitive"] = state["touched_sensitive"] or touched_sensitive
        state["ingested_untrusted"] = state["ingested_untrusted"] or ingested_untrusted
        state["external_reach_attempted"] = state["external_reach_attempted"] or external_reach_attempted
        return dict(state)


def trifecta_state(session_id):
    with _lock:
        state = _sessions.get(session_id, _blank())
    count = sum(state.values())
    if count == 3:
        return "tripped"
    if count == 2:
        return "partial"
    return "none"


def reset(session_id):
    with _lock:
        _sessions.pop(session_id, None)
