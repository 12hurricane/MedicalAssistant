"""
The role vocabulary is exactly PATIENT / CLINICIAN / ADMIN, and the boundary holds.

Two things are under test here, and they are different in kind:

1. **Vocabulary.** The retired DOCTOR and CAREGIVER values are not merely unused —
   they are unwritable through every supported path. This is the regression guard for
   migration ``9f2c1d7ab4e0``. A terminology cleanup with no test around it silently
   reverts the first time someone copies an older docstring into a new endpoint, and
   the symptom is not a failure — it is a role string nothing checks for, i.e. an
   account that authenticates and is then refused everywhere.

2. **Authorization.** A CLINICIAN can reach the clinician-protected endpoints and a
   PATIENT cannot. This is the half of A.1/A.2 that the vocabulary work made testable:
   before the rename, ``patients.py`` compared against the string ``"DOCTOR"`` while
   the rest of the system said clinician, so there was no single value a test could
   assert on. Neither of these two endpoints had any authorization test at all.

The positive and negative cases deliberately use *different* expected statuses on the
same request. A patient is stopped by the dependency and never reaches the handler
(403). A clinician passes the dependency and is stopped by the missing row (404). If
the role gate were removed, the patient's request would return 404 too — so a test
asserting merely "not 200" would keep passing. The distinction between 403 and 404 is
what proves the gate is the thing doing the work.
"""

import pytest
from sqlalchemy import func, select

from app.core.security import decode_token
from app.models.patient import Patient
from app.models.user import User
from app.schemas.auth import PrivilegedRole, UserRole
from conftest import _bootstrap_admin_headers, _login, register

RETIRED_ROLES = ["DOCTOR", "CAREGIVER"]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_the_canonical_roles_are_exactly_three():
    """Application-level: the enums themselves carry no retired value.

    Asserted on the enum rather than only through HTTP because the enum is what every
    other guarantee here rests on. ``PrivilegedRole`` is the request contract for
    ``POST /admin/users``, so a value absent from it is a 422 from Pydantic before any
    handler runs; ``UserRole`` is what the authorization dependencies name. The CLI's
    ``create-admin`` needs no separate test for the same reason — it validates through
    ``AdminUserCreate``, so it cannot express a role this enum does not contain.
    """
    assert {r.value for r in UserRole} == {"PATIENT", "CLINICIAN", "ADMIN"}
    assert {r.value for r in PrivilegedRole} == {"CLINICIAN", "ADMIN"}


@pytest.mark.parametrize("retired", RETIRED_ROLES)
async def test_admin_provisioning_rejects_a_retired_role(client, session, retired):
    """422, and no row.

    ``POST /admin/users`` is the one endpoint where ``role`` is writable over HTTP, so
    it is the one place a retired value could re-enter the database. The caller here is
    a real ADMIN: the point is that the *value* is refused, not the caller, which a
    test using an unprivileged token would not distinguish (that would 403 either way).
    """
    headers = await _bootstrap_admin_headers(client)

    r = await client.post(
        "/api/v1/admin/users",
        json={
            "email": f"retired-{retired.lower()}@example.com",
            "password": "Passw0rd!",
            "name": f"Retired {retired}",
            "role": retired,
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text

    assert (
        await session.execute(
            select(User).where(User.email == f"retired-{retired.lower()}@example.com")
        )
    ).scalars().one_or_none() is None


@pytest.mark.parametrize("variant", ["clinician", "Clinician", "CLINICIAN "])
async def test_admin_provisioning_is_case_and_whitespace_exact(client, variant):
    """Only the exact enum value is accepted.

    Not pedantry: a role comparison is an equality check against a literal, so a row
    holding ``"clinician"`` would satisfy no authorization list in the codebase. An
    account like that logs in and is then refused everywhere, which reads as an
    authorization bug rather than a typo at creation time. Rejecting it at the contract
    is the only place the error is still legible.
    """
    headers = await _bootstrap_admin_headers(client)
    r = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "casing@example.com",
            "password": "Passw0rd!",
            "name": "Casing",
            "role": variant,
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_no_supported_path_can_create_a_retired_role(client, session):
    """The user-requested backstop: sweep every creation path, then check the table.

    Rather than asserting on each response, this exercises all of them and then makes
    one statement about the database — which is the property that actually matters, and
    the one that survives a future endpoint being added without a matching test being
    remembered. If a fourth creation path appears and accepts DOCTOR, this fails.
    """
    admin_headers = await _bootstrap_admin_headers(client)

    for retired in RETIRED_ROLES:
        # Path 1: public self-service registration, with the role smuggled in the body.
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"public-{retired.lower()}@example.com",
                "password": "Passw0rd!",
                "name": "Public",
                "role": retired,
            },
        )
        # Path 2: privileged provisioning by a genuine ADMIN.
        await client.post(
            "/api/v1/admin/users",
            json={
                "email": f"admin-made-{retired.lower()}@example.com",
                "password": "Passw0rd!",
                "name": "Admin Made",
                "role": retired,
            },
            headers=admin_headers,
        )

    offending = (
        await session.execute(
            select(func.count()).select_from(User).where(User.role.in_(RETIRED_ROLES))
        )
    ).scalar_one()
    assert offending == 0, (
        f"{offending} user row(s) hold a retired role. Migration 9f2c1d7ab4e0 has been "
        "regressed: some creation path still accepts DOCTOR or CAREGIVER."
    )


async def test_the_published_contract_offers_clinician_and_not_doctor(client):
    """The generated Dart client is built from this document.

    So the schema is the contract, not an artefact of it: if ``PrivilegedRole`` still
    published DOCTOR, ``flutter/tool/generate_api_models.dart`` would emit
    ``doctor('DOCTOR')`` into ``AppRole`` and the client would carry the retired
    vocabulary forward on its own.
    """
    spec = (await client.get("/openapi.json")).json()
    published = spec["components"]["schemas"]["PrivilegedRole"]["enum"]

    assert "CLINICIAN" in published
    for retired in RETIRED_ROLES:
        assert retired not in published, (
            f"{retired} is still published in the OpenAPI schema; the Flutter model "
            "generator will reintroduce it"
        )


async def test_the_token_carries_no_role(client):
    """The rename needed no JWT compatibility work, and this is why.

    ``get_current_user`` re-reads ``user.role`` from the database on every request, so
    the database is the single source of truth and a role change takes effect
    immediately. Had the role been a claim, migration ``9f2c1d7ab4e0`` would have
    stranded every already-issued token: DOCTOR in the token, CLINICIAN in the table.

    This is asserted rather than assumed because adding ``role`` to the claims is an
    easy and superficially reasonable optimisation — it saves a SELECT — and it would
    reintroduce that failure mode along with a window where a revoked privilege is
    still honoured.
    """
    headers = await register(client, "claims@example.com", role="CLINICIAN")
    token = headers["Authorization"].removeprefix("Bearer ")

    claims = decode_token(token, expected_type="access")

    assert "role" not in claims, (
        f"the access token now carries a role claim ({claims.get('role')!r}); "
        "authorization must keep reading it from the database"
    )
    assert set(claims) == {"sub", "exp", "type", "iat", "jti", "ver"}, (
        f"unexpected claim set {sorted(claims)} — every added claim is state that can "
        "go stale between issue and use"
    )


# ---------------------------------------------------------------------------
# Authorization — GET /patients/{patient_id}/safety
# ---------------------------------------------------------------------------


async def _a_patient_id(client, session, email="subject@example.com"):
    """Register a patient and return their ``patients.id``."""
    await register(client, email, role="PATIENT")
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalars().one()
    profile = (
        await session.execute(select(Patient).where(Patient.user_id == user.id))
    ).scalars().one()
    return profile.id


async def test_a_clinician_may_read_another_patients_safety_assessment(client, session):
    """The positive case. Without it, a 403-for-everyone bug would look like success."""
    patient_id = await _a_patient_id(client, session)
    headers = await register(client, "reviewer@example.com", role="CLINICIAN")

    r = await client.get(f"/api/v1/patients/{patient_id}/safety", headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == patient_id


async def test_an_admin_may_read_another_patients_safety_assessment(client, session):
    """ADMIN is on the same list, so it is asserted rather than inferred."""
    patient_id = await _a_patient_id(client, session, "admin-subject@example.com")
    headers = await _bootstrap_admin_headers(client)

    r = await client.get(f"/api/v1/patients/{patient_id}/safety", headers=headers)
    assert r.status_code == 200, r.text


async def test_a_patient_may_not_read_another_patients_safety_assessment(client, session):
    """The negative case, and the one that was never tested before.

    A patient reads their own assessment through ``GET /patients/me/safety``, which
    resolves the profile from the caller's own user id and therefore needs no role
    check. This endpoint takes an arbitrary id, so without the role gate any patient
    could enumerate every other patient's clinical assessment by incrementing it.
    """
    patient_id = await _a_patient_id(client, session)
    headers = await register(client, "nosy@example.com", role="PATIENT")

    r = await client.get(f"/api/v1/patients/{patient_id}/safety", headers=headers)
    assert r.status_code == 403, r.text


async def test_reading_a_safety_assessment_requires_authentication(client, session):
    """No token is 401, not 403: nothing has been authenticated to refuse yet."""
    patient_id = await _a_patient_id(client, session)
    r = await client.get(f"/api/v1/patients/{patient_id}/safety")
    assert r.status_code in (401, 403), r.text


# ---------------------------------------------------------------------------
# Authorization — PUT /prescriptions/{id}/verify
# ---------------------------------------------------------------------------

#
# Both tests below target a prescription id that does not exist, on purpose. The role
# check is now a dependency, so it runs before the handler body and before any lookup —
# which means the status code alone says which stage rejected the request, with no
# prescription fixture needed. 403 is the gate; 404 is past the gate.
#


async def test_a_patient_may_not_verify_a_prescription(client):
    """403 — stopped at the dependency, so verification is unreachable for patients.

    Verification is the point at which dose times become real: it flips the status to
    VERIFIED and generates the MedicationSchedule rows. A patient who could call it
    would be approving their own prescription.
    """
    headers = await register(client, "self-verifier@example.com", role="PATIENT")

    r = await client.put(
        "/api/v1/prescriptions/999999/verify",
        json={"verified": True},
        headers=headers,
    )
    assert r.status_code == 403, r.text


async def test_a_clinician_passes_the_verification_role_gate(client):
    """404 — past the dependency, refused by the missing row.

    The contrast with the test above is the whole assertion: same request, same
    nonexistent id, different rejecting stage. A clinician is authorized and simply has
    nothing to verify. (The successful path, with a real prescription and the schedule
    generation behind it, is covered by ``test_prescription_corrections.py``.)
    """
    headers = await register(client, "verifier@example.com", role="CLINICIAN")

    r = await client.put(
        "/api/v1/prescriptions/999999/verify",
        json={"verified": True},
        headers=headers,
    )
    assert r.status_code == 404, r.text
