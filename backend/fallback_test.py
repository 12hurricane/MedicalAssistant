import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL = "flutter_walkthrough@example.com"
PASSWORD = "FlutterWalk2026!"

def main():
    data = f"username={EMAIL}&password={PASSWORD}".encode()
    r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/auth/login", data=data, method="POST"))
    token = json.loads(r.read().decode())["access_token"]
    
    req = urllib.request.Request(f"{BASE}/adherence/analysis?days=7", method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        resp = json.loads(r.read().decode())
        print(f"Status: {r.status}")
        print(f"Risk: {resp.get('safety_risk_level')}")
        print(f"Requires HR: {resp.get('requires_human_review')}")
        print(f"Insights generated: {bool(resp.get('clinical_brief', {}).get('insights'))}")
    except urllib.error.HTTPError as e:
        print(f"Failed with {e.code}")

if __name__ == "__main__":
    main()
