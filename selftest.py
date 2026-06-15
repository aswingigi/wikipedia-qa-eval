"""No-key live test of the retrieval contract.

Run with `python selftest.py` (needs internet, NOT an API key). Asserts the SHAPE
of the contract — status resolution and trace fields — not article text, so a
Wikipedia edit can't make it flaky.
"""
import sys

import agents.wikipedia as wp
from agents.wikipedia import DEFAULT_MAX_CHARS, search_wikipedia


def _check(name, fn):
    try:
        fn()
    except AssertionError as e:
        print(f"FAIL  {name}: {e}")
        return False
    except Exception as e:
        print(f"ERROR {name}: {type(e).__name__}: {e}")
        return False
    print(f"PASS  {name}")
    return True


def test_ok():
    r = search_wikipedia("Alan Turing")
    assert r.status == "ok", f"status={r.status}"
    assert not r.is_error
    assert len(r.results) >= 1, "expected at least one result"
    for s in r.results:
        assert s.title.strip(), "empty title"
        assert s.url.startswith("https://"), f"bad url: {s.url!r}"
        assert s.extract.strip(), "empty extract"
        assert len(s.extract) <= DEFAULT_MAX_CHARS + 2, f"extract not truncated: {len(s.extract)} chars"


def test_empty():
    r = search_wikipedia("zzqwxlkjqwer nonexistenttopic 9931 blahblah")
    assert r.status == "empty", f"status={r.status}"
    assert not r.is_error
    assert r.results == [], "empty result must carry no snippets"


def test_error():
    # Point retrieval at a non-existent endpoint to force the failure path.
    original = wp.API_URL
    wp.API_URL = "https://en.wikipedia.org/w/this_endpoint_does_not_exist.php"
    try:
        r = search_wikipedia("Alan Turing")
    finally:
        wp.API_URL = original
    assert r.status == "error", f"status={r.status}"
    assert r.is_error
    assert r.error, "error message should be populated"


if __name__ == "__main__":
    outcomes = [
        _check("ok: real query returns shaped snippets", test_ok),
        _check("empty: nonsense query -> empty, not error", test_empty),
        _check("error: failed request -> error, is_error=True", test_error),
    ]
    print(f"\n{sum(outcomes)}/{len(outcomes)} passed")
    sys.exit(0 if all(outcomes) else 1)
