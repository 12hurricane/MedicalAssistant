import asyncio
import httpx
from datetime import datetime
import json

BASE_URL = "http://localhost:8000/api/v1"
EMAIL = "flutter_walkthrough@example.com"
PASSWORD = "FlutterWalk2026!"

async def main():
    async with httpx.AsyncClient(timeout=600.0) as client:
        # 1. Login
        resp = await client.post(f"{BASE_URL}/auth/login", data={"username": EMAIL, "password": PASSWORD})
        assert resp.status_code == 200, resp.text
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        print("1. Logged in")

        # 2. Fetch today's schedule
        resp = await client.get(f"{BASE_URL}/schedule/today", headers=headers)
        assert resp.status_code == 200, resp.text
        schedule = resp.json()
        print(f"Schedule: {json.dumps(schedule, indent=2)}")
        # If schedule is dict with date keys, flatten it
        events = []
        if isinstance(schedule, dict):
            for v in schedule.values():
                if isinstance(v, list):
                    events.extend(v)
                else:
                    events.append(v)
        else:
            events = schedule

        if len(events) >= 3:
            # log first as TAKEN
            ev = events[0]
            resp = await client.post(f"{BASE_URL}/schedule/events", json={
                "schedule_id": ev["schedule_id"],
                "status": "TAKEN",
                "scheduled_at": ev["scheduled_time"],
                "logged_at": datetime.utcnow().isoformat() + "Z"
            }, headers=headers)
            print(f"3a. Logged TAKEN: {resp.status_code}")
            
            # log second as SKIPPED
            ev = schedule[1]
            resp = await client.post(f"{BASE_URL}/schedule/events", json={
                "schedule_id": ev["schedule_id"],
                "status": "SKIPPED",
                "scheduled_at": ev["scheduled_time"],
                "logged_at": datetime.utcnow().isoformat() + "Z",
                "skip_reason_code": "SIDE_EFFECTS",
                "skip_reason": "I felt a bit nauseous after taking it yesterday."
            }, headers=headers)
            print(f"3b. Logged SKIPPED: {resp.status_code}")

            # log third as MISSED
            ev = schedule[2]
            resp = await client.post(f"{BASE_URL}/schedule/events", json={
                "schedule_id": ev["schedule_id"],
                "status": "MISSED",
                "scheduled_at": ev["scheduled_time"],
                "logged_at": datetime.utcnow().isoformat() + "Z"
            }, headers=headers)
            print(f"3c. Logged MISSED: {resp.status_code}")

        # 4. Refetch schedule to confirm updates
        resp = await client.get(f"{BASE_URL}/schedule/today", headers=headers)
        print(f"4. Refetched schedule: {[e.get('status') for e in resp.json()]}")

        # 5. Fetch Adherence Score
        resp = await client.get(f"{BASE_URL}/adherence/score?period=7d", headers=headers)
        print(f"5. Adherence Score: {json.dumps(resp.json(), indent=2)}")

        # 6. Fetch Analysis
        print("6. Requesting analysis... (this hits the live LLM)")
        resp = await client.get(f"{BASE_URL}/adherence/analysis?period=7d", headers=headers)
        print(f"   Analysis status: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(resp.text)

if __name__ == "__main__":
    asyncio.run(main())
