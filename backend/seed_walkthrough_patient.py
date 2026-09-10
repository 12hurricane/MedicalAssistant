"""Seeds the patient the Flutter live-backend walkthrough signs in as.

Registers the patient over HTTP so the real auth path runs, then inserts a verified
prescription with three schedules for today. Without this, ``GET /schedule/today``
returns an empty list and there is no dose to log.

    cd backend
    venv/Scripts/python seed_walkthrough_patient.py

Re-runnable: registration tolerates "already registered", and the prescription is
only created if the patient has no schedules yet. To restore pending doses after
``integration_test/patient_slice_live_test.dart`` has consumed them, pass ``--reset``,
which deletes that patient's medication events and nothing else.

This writes to ``medication.db`` on purpose. That file is the manual-verification
database, and it is what uvicorn serves. The pytest suite's guard against touching it
(``backend/conftest.py``) is unaffected: nothing here runs under pytest.
"""

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

BASE = "http://127.0.0.1:8000/api/v1"
DB = "medication.db"

EMAIL = "flutter_walkthrough@example.com"
PASSWORD = "FlutterWalk2026!"
NAME = "Flutter Walkthrough Patient"

# (medicine_name, strength, dose, frequency, instructions, local times, meal relation)
MEDICATIONS = [
    (
        "Metformin",
        "500 mg",
        "1 tablet",
        "twice daily",
        "Swallow whole with water.",
        ["08:00", "13:00"],
        "AFTER_MEAL",
    ),
    (
        "Atorvastatin",
        "20 mg",
        "1 tablet",
        "once daily",
        "Take in the evening.",
        ["20:00"],
        None,
    ),
]


def register():
    """POSTs /auth/register. Returns True if the patient exists afterwards."""
    # No "role" key. The endpoint creates a PATIENT and has no field to say otherwise,
    # so sending one would be silently ignored — which is worse than an error, because
    # the next reader would take it for a payload that still does something.
    payload = json.dumps(
        {"name": NAME, "email": EMAIL, "password": PASSWORD}
    ).encode()
    request = urllib.request.Request(
        f"{BASE}/auth/register",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(f"register -> {response.status}")
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        if exc.code == 400 and "already registered" in body:
            print("register -> 400 already registered (fine)")
            return True
        print(f"register -> {exc.code} {body}", file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print(
            f"Cannot reach {BASE}: {exc.reason}\n"
            "Start the backend first:\n"
            "  venv/Scripts/python -m uvicorn app.main:app --port 8000",
            file=sys.stderr,
        )
        return False


def locate_patient(cursor):
    user = cursor.execute("select id from users where email = ?", (EMAIL,)).fetchone()
    if user is None:
        sys.exit("No user row after registration.")
    patient = cursor.execute(
        "select id, timezone from patients where user_id = ?", (user["id"],)
    ).fetchone()
    if patient is None:
        sys.exit(
            "A user row exists but no patient profile does. That is the registration "
            "atomicity failure covered by test_registration_atomicity.py."
        )
    return user["id"], patient["id"], patient["timezone"]


def reset_events(cursor, patient_id):
    """Clears this patient's dose history so today's doses are pending again."""
    cursor.execute("delete from medication_events where patient_id = ?", (patient_id,))
    print(f"deleted {cursor.rowcount} medication event(s) for patient {patient_id}")


def create_prescription(cursor, patient_id):
    today = date.today()
    stamp = datetime.now().isoformat(sep=" ", timespec="seconds")

    cursor.execute(
        """insert into prescriptions
           (patient_id, doctor_name, clinic_name, prescription_date,
            verification_status, created_at)
           values (?, ?, ?, ?, 'VERIFIED', ?)""",
        (
            patient_id,
            "Dr. Walkthrough",
            "Flutter Verification Clinic",
            today.isoformat(),
            stamp,
        ),
    )
    prescription_id = cursor.lastrowid

    created = []
    for name, strength, dose, frequency, instructions, times, meal in MEDICATIONS:
        cursor.execute(
            """insert into prescribed_medications
               (prescription_id, patient_id, medicine_name, strength, dose,
                frequency, instructions, is_active, created_at)
               values (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                prescription_id,
                patient_id,
                name,
                strength,
                dose,
                frequency,
                instructions,
                stamp,
            ),
        )
        medication_id = cursor.lastrowid

        for hhmm in times:
            cursor.execute(
                """insert into medication_schedules
                   (prescribed_medication_id, patient_id, scheduled_time,
                    relation_to_meal, start_date, status, created_at)
                   values (?, ?, ?, ?, ?, 'ACTIVE', ?)""",
                (
                    medication_id,
                    patient_id,
                    f"{hhmm}:00",
                    meal,
                    # Backdated so the schedule is already active today.
                    (today - timedelta(days=3)).isoformat(),
                    stamp,
                ),
            )
            created.append((cursor.lastrowid, name, hhmm))

    return created


def main():
    reset = "--reset" in sys.argv[1:]

    if not register():
        sys.exit(1)

    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    user_id, patient_id, timezone = locate_patient(cursor)
    print(f"user_id={user_id} patient_id={patient_id} timezone={timezone}")

    if reset:
        reset_events(cursor, patient_id)

    schedules = cursor.execute(
        """select id, scheduled_time, prescribed_medication_id
           from medication_schedules where patient_id = ? order by scheduled_time""",
        (patient_id,),
    ).fetchall()

    if schedules:
        print(f"{len(schedules)} schedule(s) already exist:")
        for row in schedules:
            print(f"   schedule {row['id']} at {row['scheduled_time']}")
    else:
        for schedule_id, name, hhmm in create_prescription(cursor, patient_id):
            print(f"   created schedule {schedule_id}: {name} at {hhmm}")

    connection.commit()

    pending = cursor.execute(
        """select count(*) from medication_schedules s
           where s.patient_id = ?
             and not exists (
               select 1 from medication_events e
               where e.schedule_id = s.id and date(e.scheduled_at) = date('now')
             )""",
        (patient_id,),
    ).fetchone()[0]
    connection.close()

    print(f"\n{pending} of today's dose(s) are unlogged.")
    if pending < 2:
        print("The integration test needs two. Re-run with --reset.")
    print(f"Sign in as: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
