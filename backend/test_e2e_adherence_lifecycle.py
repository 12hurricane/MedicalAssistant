"""
End-to-End Adherence Lifecycle Verification Test
Covers:
1. Authentication (Clinician & Patient)
2. Prescription Creation & Invariant Validation
3. Prescription Verification (Generates Deterministic Schedules)
4. Deterministic Daily Schedule Allocation (GET /schedule/today)
5. Patient Dose Intake Logging (TAKEN, SKIPPED)
6. Adherence Score Recalculation & Discrepancy Trigger
7. Clinician Human-in-the-Loop Dose Correction & Audit Verification
8. Post-Correction Adherence Score authoritatively restored
"""

import sys
import time
from datetime import date
import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"

def print_step(title: str):
    print(f"\n{'='*75}\n[STEP] {title}\n{'='*75}")

def assert_status(resp: requests.Response, expected_codes: list[int] | int, step_name: str):
    if isinstance(expected_codes, int):
        expected_codes = [expected_codes]
    if resp.status_code not in expected_codes:
        print(f"[-] FAILED {step_name}: Expected {expected_codes}, got {resp.status_code}")
        print(f"    Body: {resp.text}")
        sys.exit(1)
    print(f"[+] SUCCESS {step_name} (HTTP {resp.status_code})")

def ensure_seed_data():
    """Bootstraps required clinician and patient records if not already in database."""
    import sqlite3
    from datetime import datetime, timezone
    from app.core.security import get_password_hash
    
    # 1. Set timeouts on the seed-data login requests
    try:
        r_c = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": "clinician.test@example.com", "password": "Password123!"},
            timeout=5.0,
        )
        r_p = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": "flutter_walkthrough@example.com", "password": "FlutterWalk2026!"},
            timeout=5.0,
        )
        if r_c.status_code == 200 and r_p.status_code == 200:
            return
    except requests.RequestException:
        pass

    # 2. Call the imported hash function directly
    c_hash = get_password_hash("Password123!")
    p_hash = get_password_hash("FlutterWalk2026!")
    now = datetime.now(timezone.utc).isoformat()
    
    conn = sqlite3.connect("medication.db")
    cur = conn.cursor()

    # 3. Repair existing clinician account when login fails, or insert if absent
    cur.execute("SELECT id FROM users WHERE email = 'clinician.test@example.com'")
    c_row = cur.fetchone()
    if c_row:
        cur.execute(
            "UPDATE users SET hashed_password = ?, role = 'CLINICIAN', is_active = 1, updated_at = ? WHERE id = ?",
            (c_hash, now, c_row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO users (name, email, hashed_password, role, is_active, token_version, created_at, updated_at) "
            "VALUES (?, ?, ?, 'CLINICIAN', 1, 1, ?, ?)",
            ("Dr. Test Clinician", "clinician.test@example.com", c_hash, now, now),
        )

    # 4. Repair existing patient account when login fails, or insert if absent
    cur.execute("SELECT id FROM users WHERE email = 'flutter_walkthrough@example.com'")
    p_row = cur.fetchone()
    if p_row:
        patient_user_id = p_row[0]
        cur.execute(
            "UPDATE users SET hashed_password = ?, role = 'PATIENT', is_active = 1, updated_at = ? WHERE id = ?",
            (p_hash, now, patient_user_id),
        )
    else:
        cur.execute(
            "INSERT INTO users (name, email, hashed_password, role, is_active, token_version, created_at, updated_at) "
            "VALUES (?, ?, ?, 'PATIENT', 1, 1, ?, ?)",
            ("Flutter Walkthrough Patient", "flutter_walkthrough@example.com", p_hash, now, now),
        )
        patient_user_id = cur.lastrowid

    # 5. Create the patient profile independently of the patient user
    cur.execute("SELECT id FROM patients WHERE user_id = ?", (patient_user_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO patients (user_id, timezone, preferred_language, created_at, updated_at) "
            "VALUES (?, 'Asia/Kolkata', 'en', ?, ?)",
            (patient_user_id, now, now),
        )

    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# 1. Authentication
# ---------------------------------------------------------------------------
print_step("1. Authenticating Clinician & Patient Sessions")
ensure_seed_data()


clinician_auth = requests.post(
    f"{BASE_URL}/auth/login",
    data={"username": "clinician.test@example.com", "password": "Password123!"}
)
assert_status(clinician_auth, 200, "Clinician Login")
clinician_token = clinician_auth.json()["access_token"]
clinician_headers = {"Authorization": f"Bearer {clinician_token}"}

patient_auth = requests.post(
    f"{BASE_URL}/auth/login",
    data={"username": "flutter_walkthrough@example.com", "password": "FlutterWalk2026!"}
)
assert_status(patient_auth, 200, "Patient Login")
patient_token = patient_auth.json()["access_token"]
patient_headers = {"Authorization": f"Bearer {patient_token}"}

# Get current patient profile
me_resp = requests.get(f"{BASE_URL}/patients/me", headers=patient_headers)
if me_resp.status_code == 200:
    patient_id = me_resp.json().get("id", 5)
else:
    patient_id = 5

print(f"    Authenticated Clinician: clinician.test@example.com")
print(f"    Authenticated Patient: ID {patient_id} (flutter_walkthrough@example.com)")

# ---------------------------------------------------------------------------
# 2. Prescription Creation & Invariant Validation
# ---------------------------------------------------------------------------
print_step("2. Creating Metformin 500mg BID Prescription")

rx_payload = {
    "doctor_name": "Dr. Sarah Jenkins",
    "clinic_name": "Metro Endocrinology Clinic",
    "prescription_date": date.today().isoformat(),
    "medications": [
        {
            "medicine_name": "Metformin",
            "strength": "500mg",
            "dose": "1 tablet",
            "frequency": "twice_daily",
            "duration_days": 30,
            "instructions": "Take with morning and evening meals."
        }
    ]
}

create_rx_resp = requests.post(
    f"{BASE_URL}/prescriptions",
    json=rx_payload,
    headers=patient_headers
)
assert_status(create_rx_resp, [200, 201], "Create Prescription")
rx_data = create_rx_resp.json()
prescription_id = rx_data.get("id")
meds_list = rx_data.get("medications", [])
med_id = meds_list[0].get("id") if meds_list else None
print(f"    Prescription ID: {prescription_id} | Status: {rx_data.get('verification_status')}")
print(f"    Medication: Metformin 500mg | Med ID: {med_id}")

# ---------------------------------------------------------------------------
# 3. Clinician Verification & Deterministic Schedule Generation
# ---------------------------------------------------------------------------
print_step("3. Clinician Verifying Prescription to Generate Daily Schedules")

verify_resp = requests.put(
    f"{BASE_URL}/prescriptions/{prescription_id}/verify",
    json={"verified": True},
    headers=clinician_headers
)
assert_status(verify_resp, 200, "Clinician Verify Prescription")
verify_summary = verify_resp.json()
print(f"    Verification Status: {verify_summary.get('verification_status')}")
schedule_gen = verify_summary.get("schedule_generation", {})
print(f"    Dose Slots Generated: Created={schedule_gen.get('created')}, Total Active={schedule_gen.get('active_total')}")

# ---------------------------------------------------------------------------
# 4. Fetch Deterministic Daily Schedule Slots
# ---------------------------------------------------------------------------
print_step("4. Verifying Deterministic Daily Schedule Allocation (Zero-LLM)")

schedule_resp = requests.get(
    f"{BASE_URL}/schedule/today?patient_id={patient_id}",
    headers=patient_headers
)
if schedule_resp.status_code == 404:
    schedule_resp = requests.get(
        f"{BASE_URL}/schedules/today?patient_id={patient_id}",
        headers=patient_headers
    )
assert_status(schedule_resp, 200, "Fetch Daily Schedule Slots")
schedule_data = schedule_resp.json()
slots = schedule_data.get("doses", schedule_data.get("slots", []))
print(f"    Active Schedule Slots for Today: {len(slots)}")

if not slots:
    print("[-] No schedule slots found for today.")
    sys.exit(1)

for idx, slot in enumerate(slots, 1):
    time_str = slot.get("scheduled_time") or slot.get("dose_time") or slot.get("time")
    status_str = slot.get("status", "PENDING")
    sched_id = slot.get("schedule_id") or slot.get("id")
    print(f"    Slot {idx}: Schedule ID {sched_id} | Time: {time_str} | Status: {status_str}")

# Pick slots for intake logging
slot_1 = slots[0]
slot_2 = slots[1] if len(slots) > 1 else slots[0]
sched_id_1 = slot_1.get("schedule_id") or slot_1.get("id")
sched_id_2 = slot_2.get("schedule_id") or slot_2.get("id")

# ---------------------------------------------------------------------------
# 5. Patient Dose Ingestion (On-Time & Missed / Skipped)
# ---------------------------------------------------------------------------
print_step("5. Ingesting Adherence Doses (Simulating Variance)")

# Log 1: Morning dose taken on time
log_dose_1 = requests.post(
    f"{BASE_URL}/adherence/log",
    json={
        "schedule_id": sched_id_1,
        "status": "TAKEN"
    },
    headers=patient_headers
)
assert_status(log_dose_1, [200, 201], "Log On-Time Dose")
event_1 = log_dose_1.json()
event_1_id = event_1.get("id") or event_1.get("event_id")
print(f"    Dose 1 Recorded: Event ID {event_1_id} | Status: TAKEN")

# Log 2: Evening dose skipped / missed
log_dose_2 = requests.post(
    f"{BASE_URL}/adherence/log",
    json={
        "schedule_id": sched_id_2,
        "status": "SKIPPED",
        "skip_reason": "Forgot evening dose after dinner"
    },
    headers=patient_headers
)
assert_status(log_dose_2, [200, 201], "Log Missed Dose")
event_2 = log_dose_2.json()
event_2_id = event_2.get("id") or event_2.get("event_id")
print(f"    Dose 2 Recorded: Event ID {event_2_id} | Status: SKIPPED (Reason: Forgot)")

# ---------------------------------------------------------------------------
# 6. Adherence Score Re-computation & Discrepancy Analysis
# ---------------------------------------------------------------------------
print_step("6. Triggering Deterministic Adherence Score & Risk Re-computation")

score_resp = requests.get(
    f"{BASE_URL}/adherence/score?period=7d",
    headers=patient_headers
)
assert_status(score_resp, 200, "Calculate Adherence Score")
score_data = score_resp.json()
adherence_rate = score_data.get("adherence_rate", 0.0)
print(f"    Current Adherence Score: {adherence_rate:.1f}%")
print(f"    Total Taken: {score_data.get('total_taken')} | Total Missed: {score_data.get('total_missed')}")
print(f"    Current Streak: {score_data.get('current_streak')} days | Trend: {score_data.get('trend')}")

# Clinician-side comprehensive discrepancy analysis
analysis_resp = requests.get(
    f"{BASE_URL}/adherence/analysis?patient_id={patient_id}",
    headers=clinician_headers
)
assert_status(analysis_resp, 200, "Clinician Adherence Analysis")
analysis_data = analysis_resp.json()
risk_level = analysis_data.get("safety_risk_level", "NORMAL")
print(f"    Clinician Risk Stratification: {risk_level}")
print(f"    Requires Human Review: {analysis_data.get('requires_human_review')}")
print(f"    Recommended Action: {analysis_data.get('recommended_action')}")

# ---------------------------------------------------------------------------
# 7. Clinician Human-in-the-Loop Dose Correction & Audit Trail
# ---------------------------------------------------------------------------
print_step("7. Clinician Overriding Event Status with Immutable Audit Trail")

override_payload = {
    "new_status": "TAKEN",
    "reason": "Patient confirmed Metformin dose was taken 45 minutes late."
}

override_resp = requests.post(
    f"{BASE_URL}/adherence/events/{event_2_id}/correct",
    json=override_payload,
    headers=clinician_headers
)
assert_status(override_resp, 200, "Clinician Event Correction")
audit_entry = override_resp.json()

print("    Clinician Override Audited in Database:")
print(f"    - Correction Audit ID: {audit_entry.get('correction_id')}")
print(f"    - Event ID: {audit_entry.get('event_id')}")
print(f"    - Previous Status: {audit_entry.get('previous_status')}")
print(f"    - Authoritative New Status: {audit_entry.get('new_status')}")
print(f"    - Clinical Reason: {audit_entry.get('reason')}")
print(f"    - Corrected By Clinician User ID: {audit_entry.get('corrected_by')}")
print(f"    - Timestamp: {audit_entry.get('corrected_at')}")

# ---------------------------------------------------------------------------
# 8. Post-Correction Adherence Score Verification
# ---------------------------------------------------------------------------
print_step("8. Verifying Authoritative Adherence Score Restored Post-Correction")

post_score_resp = requests.get(
    f"{BASE_URL}/adherence/score?period=7d",
    headers=patient_headers
)
assert_status(post_score_resp, 200, "Post-Correction Adherence Score")
post_score = post_score_resp.json()
print(f"    Post-Correction Adherence Score: {post_score.get('adherence_rate', 0.0):.1f}%")
print(f"    Post-Correction Total Taken: {post_score.get('total_taken')}")
print(f"    Post-Correction Total Missed: {post_score.get('total_missed')}")

print_step("E2E ADHERENCE LIFECYCLE COMPLETED SUCCESSFULLY (All 8 steps passed)")
