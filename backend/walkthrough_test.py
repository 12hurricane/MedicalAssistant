"""
Live end-to-end walkthrough against a running server.

Not a pytest module despite the filename — there are no test functions here, so
pytest collects it and finds nothing. It drives the real API over HTTP against
``medication.db``, which is exactly what the suite is forbidden to do.

Prints the analysis response in full. An earlier version printed only
``clinical_brief["insights"]``, a key ``ClinicalBrief`` has never had, so the one
output the walkthrough exists to show came out as ``{}`` and the run looked like it
had succeeded. The whole body is dumped now: a field that is missing should read as
missing, not as empty.

Usage::

    python walkthrough_test.py [base_url]
    python walkthrough_test.py http://127.0.0.1:8001/api/v1
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1").rstrip("/")
EMAIL = "flutter_walkthrough@example.com"
PASSWORD = "FlutterWalk2026!"


def req(path, method="GET", data=None, token=None, timeout=300):
    """One JSON request. Returns ``(status, body)``; body is ``None`` if not JSON.

    The status is returned rather than swallowed because the fallback checks care
    about the difference between a 200 carrying a deterministic payload and a 5xx —
    a helper that collapsed both to ``None`` could not tell them apart.
    """
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{BASE}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, {"_raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"_raw": raw}


def main():
    print(f"Base URL: {BASE}")
    print("Logging in...")
    data = f"username={EMAIL}&password={PASSWORD}".encode()
    request = urllib.request.Request(f"{BASE}/auth/login", data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            token = json.loads(r.read().decode())["access_token"]
        print("Logged in.")
    except Exception as exc:  # noqa: BLE001 - a live script reports and stops
        print(f"Login failed: {exc}")
        return 1

    print("Fetching today's schedule...")
    status, schedule = req("/schedule/today", token=token)
    if status != 200 or not schedule or "doses" not in schedule:
        print(f"No schedule (HTTP {status}): {schedule}")
        return 1

    doses = schedule["doses"]
    print(f"Found {len(doses)} doses for today.")

    if len(doses) >= 3:
        print("Logging TAKEN...")
        req("/adherence/log", "POST",
            {"schedule_id": doses[0]["schedule_id"], "status": "TAKEN"}, token)
        print("Logging SKIPPED...")
        req("/adherence/log", "POST",
            {"schedule_id": doses[1]["schedule_id"], "status": "SKIPPED",
             "skip_reason": "Too busy today",
             "skip_reason_code": "SCHEDULE_CONFLICT"}, token)
        print("Logging MISSED...")
        req("/adherence/log", "POST",
            {"schedule_id": doses[2]["schedule_id"], "status": "MISSED"}, token)
    else:
        print("Not enough schedule entries to log the three states.")

    print("Re-fetching today's schedule to confirm...")
    _, schedule2 = req("/schedule/today", token=token)
    print("Updated schedule status:")
    for d in schedule2["doses"]:
        print(f" - {d['medicine_name']} ({d['scheduled_local_time']}): {d.get('status')}")

    print("\nRequesting adherence analysis (with 600s client timeout)...")
    started = time.monotonic()
    status, analysis = req("/adherence/analysis?days=7", token=token, timeout=600)
    elapsed = time.monotonic() - started
    print(f"HTTP {status} in {elapsed:.1f}s")

    if analysis is None:
        print("No body returned.")
        return 1

    print("\n--- safety_risk_level / requires_human_review ---")
    print(f"  safety_risk_level     : {analysis.get('safety_risk_level')}")
    print(f"  requires_human_review : {analysis.get('requires_human_review')}")
    print(f"  recommended_action    : {analysis.get('recommended_action')}")
    print(f"  validation_passed     : {analysis.get('validation_passed')}")

    print("\n--- clinical_brief (complete) ---")
    print(json.dumps(analysis.get("clinical_brief"), indent=2))

    print("\n--- full response body ---")
    print(json.dumps(analysis, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
