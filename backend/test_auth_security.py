"""
Exploit-regression and authorization tests for account creation.

Two properties are under test, and they are separate:

1. ``POST /auth/register`` cannot create anything but a PATIENT, no matter what the
   request body says. The field was removed rather than validated, so the test is not
   "a bad role is rejected" — it is "the resulting account is a PATIENT" — which holds
   whether an extra ``role`` key is ignored, stripped, or refused.

2. ``POST /admin/users`` is the only way to create a privileged account, and it
   requires an authenticated ADMIN.

Property 1 without property 2 is not security, it is an inconvenience: if the
privileged endpoint were unguarded, closing the public one would only have moved the
hole. So the escalation attempt is followed all the way through to the admin endpoint
in ``test_a_self_registered_account_cannot_reach_the_admin_endpoint``, which is the
test that actually says the original vulnerability is closed.

These tests do not use ``conftest.register``: that helper now routes privileged roles
through ``POST /admin/users`` on purpose, which is precisely the machinery under
examination here. They post to the endpoints directly.
"""

import pytest
from sqlalchemy import select

from app.models.patient import Patient
from app.models.user import User
from conftest import _bootstrap_admin_headers, _login

PATIENT = {
    "email": "self-signup@example.com",
    "password": "Passw0rd!",
    "name": "Self Signup",
}


async def _register(client, **overrides):
    """POST the public registration endpoint with the given body overrides."""
    return await client.post("/api/v1/auth/register", json={**PATIENT, **overrides})


# ---------------------------------------------------------------------------
# Finding 1 — self-service role escalation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smuggled_role",
    [
        "ADMIN",
        "CLINICIAN",
        "admin",
        "clinician",
        # The retired values. Kept in the parametrize list on purpose: the property under
        # test is "no role in the body has any effect", and a value that is no longer in
        # any enum is exactly the kind of input a validate-and-reject implementation
        # might handle differently from a recognised one.
        "DOCTOR",
        "CAREGIVER",
    ],
)
async def test_public_registration_always_produces_a_patient(
    client, session, smuggled_role
):
    """
    A role in the public request body must not reach the account that gets created.

    Asserted on the persisted row, not on the response body: a response that merely
    *reported* PATIENT while storing ADMIN would be the worse bug of the two, and a
    response-only assertion would pass for it.

    The lowercase variant is here because case-insensitive matching is a classic way
    for a validate-and-reject implementation to be bypassed. Removal is immune to it,
    which is the argument for removal — but the test states the property rather than
    trusting the argument.
    """
    r = await _register(client, role=smuggled_role)
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "PATIENT"

    user = (
        await session.execute(select(User).where(User.email == PATIENT["email"]))
    ).scalars().one()
    assert user.role == "PATIENT", (
        f"a request body carrying role={smuggled_role!r} created a {user.role} account: "
        "anonymous privilege escalation"
    )

    # And it is a real patient, not a role string on an otherwise useless account.
    profile = (
        await session.execute(select(Patient).where(Patient.user_id == user.id))
    ).scalars().one_or_none()
    assert profile is not None


async def test_a_self_registered_account_cannot_reach_the_admin_endpoint(client):
    """
    The end-to-end exploit regression.

    Follows the original attack all the way through: sign up asking for ADMIN, then use
    the token that comes back to try to create a clinician. Both halves have to hold —
    the signup must not grant the role, and the privileged endpoint must not accept the
    caller. Testing only the first half would pass even if ``/admin/users`` were wide
    open.

    The role in the second request is a currently-valid one (CLINICIAN). That matters:
    a retired value would be rejected by request validation with 422 before the
    authorization dependency was ever consulted, so the test would pass without
    exercising the boundary it names.
    """
    r = await _register(client, role="ADMIN")
    assert r.status_code == 201, r.text
    headers = await _login(client, PATIENT["email"], PATIENT["password"])

    r = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "smuggled-clinician@example.com",
            "password": "Passw0rd!",
            "name": "Smuggled Clinician",
            "role": "CLINICIAN",
        },
        headers=headers,
    )
    assert r.status_code == 403, r.text


async def test_registration_schema_does_not_advertise_a_role(client):
    """
    The published contract must not mention ``role`` on ``UserRegister``.

    This is the half of the fix that a behavioural test cannot see. An endpoint that
    accepts-then-ignores ``role`` behaves identically to one that never had the field,
    but its schema tells every client and every code generator that roles are
    assignable at signup — so the next client, or the next refactor, reintroduces the
    hole in good faith. The generated Dart models come from this document.
    """
    spec = (await client.get("/openapi.json")).json()
    register_schema = spec["components"]["schemas"]["UserRegister"]

    assert "role" not in register_schema["properties"], (
        "UserRegister still publishes a role field; the Flutter generator will emit it "
        "and a client will eventually send it"
    )
    # The privileged schema is where the vocabulary belongs, and it must not offer
    # PATIENT: patients register themselves, which is the only path that also creates
    # the profile row.
    assert "role" in spec["components"]["schemas"]["AdminUserCreate"]["properties"]
    assert "PATIENT" not in spec["components"]["schemas"]["PrivilegedRole"]["enum"]


# ---------------------------------------------------------------------------
# POST /admin/users — the authorization boundary
# ---------------------------------------------------------------------------

NEW_CLINICIAN = {
    "email": "new-clinician@example.com",
    "password": "Passw0rd!",
    "name": "New Clinician",
    "role": "CLINICIAN",
}


async def test_admin_users_rejects_anonymous_callers(client):
    """No token at all is a 401, not a 403: nothing has been authenticated yet."""
    r = await client.post("/api/v1/admin/users", json=NEW_CLINICIAN)
    assert r.status_code == 401, r.text


async def test_admin_users_rejects_a_patient(client):
    """An authenticated non-admin is a 403. This is the check the fix depends on."""
    r = await _register(client)
    assert r.status_code == 201, r.text
    headers = await _login(client, PATIENT["email"], PATIENT["password"])

    r = await client.post("/api/v1/admin/users", json=NEW_CLINICIAN, headers=headers)
    assert r.status_code == 403, r.text


async def test_admin_can_create_a_clinician(client, session):
    """The positive case. A closed door that is closed to everyone is just a wall."""
    headers = await _bootstrap_admin_headers(client)

    r = await client.post("/api/v1/admin/users", json=NEW_CLINICIAN, headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "CLINICIAN"

    user = (
        await session.execute(select(User).where(User.email == NEW_CLINICIAN["email"]))
    ).scalars().one()
    assert user.role == "CLINICIAN"
    # No patient profile: CLINICIAN has no profile table, and fabricating one would put
    # clinicians into patient-scoped queries.
    assert (
        await session.execute(select(Patient).where(Patient.user_id == user.id))
    ).scalars().one_or_none() is None

    # The created account works, which is the point of creating it.
    await _login(client, NEW_CLINICIAN["email"], NEW_CLINICIAN["password"])


async def test_admin_cannot_create_a_patient_here(client):
    """
    PATIENT is not merely refused, it is inexpressible: ``AdminUserCreate.role`` is a
    ``PrivilegedRole``, a different enum from ``UserRole``. Self-registration is the
    only path that creates the ``patients`` profile row, so an admin-created "patient"
    would be the orphaned-profile account that ``test_registration_atomicity`` exists
    to prevent.
    """
    headers = await _bootstrap_admin_headers(client)
    r = await client.post(
        "/api/v1/admin/users",
        json={**NEW_CLINICIAN, "email": "not-a-patient@example.com", "role": "PATIENT"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


async def test_admin_can_create_another_admin(client):
    """
    Succession. Once one admin exists the API can mint the next, so the CLI bootstrap
    is needed exactly once per deployment and can stay refuse-if-any-exists.
    """
    headers = await _bootstrap_admin_headers(client)
    r = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "second-admin@example.com",
            "password": "Passw0rd!",
            "name": "Second Admin",
            "role": "ADMIN",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "ADMIN"


# ---------------------------------------------------------------------------
# Finding 2 — password length bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    ["", "a", "1234567"],
    ids=["empty", "one-char", "seven-chars"],
)
async def test_passwords_below_the_floor_are_rejected(client, session, password):
    """Under 8 characters is a 422, and no account is created."""
    r = await _register(client, password=password)
    assert r.status_code == 422, r.text

    assert (
        await session.execute(select(User).where(User.email == PATIENT["email"]))
    ).scalars().one_or_none() is None


async def test_eight_characters_is_accepted_and_can_log_in(client):
    """
    The floor is exactly 8, inclusive.

    Login is exercised too. A validator that accepted a password at registration but
    could not authenticate it — because the two paths disagreed about normalisation or
    truncation — would lock the account on creation, which is worse than rejecting it.
    """
    r = await _register(client, password="12345678")
    assert r.status_code == 201, r.text
    await _login(client, PATIENT["email"], "12345678")


async def test_passwords_above_the_ceiling_are_rejected(client):
    """
    129 characters is a 422.

    The ceiling is a cost bound, not a strength rule: hashing is deliberately slow, and
    this endpoint is anonymous, so an unbounded field is free CPU for whoever posts to
    it. 128 is far above any real password and far below a useful amount of work.
    """
    r = await _register(client, password="x" * 129)
    assert r.status_code == 422, r.text

    r = await _register(client, password="x" * 128)
    assert r.status_code == 201, r.text


async def test_the_password_floor_applies_to_privileged_creation_too(client):
    """
    Both creation paths validate through the same schema, so neither can drift into
    accepting a weaker password than the other. An admin account is the last one that
    should be allowed a 4-character password.
    """
    headers = await _bootstrap_admin_headers(client)
    r = await client.post(
        "/api/v1/admin/users",
        json={**NEW_CLINICIAN, "password": "short"},
        headers=headers,
    )
    assert r.status_code == 422, r.text

async def test_revoked_token_is_rejected(client):
    """
    After /logout-all, existing tokens must be rejected because their token_version
    is older than the one in the database.
    """
    r = await _register(client, password="12345678")
    assert r.status_code == 201, r.text
    
    # Login to get valid token
    headers = await _login(client, PATIENT["email"], "12345678")
    
    # Use token to call a protected endpoint (e.g. /me)
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    
    # Revoke tokens
    r = await client.post("/api/v1/auth/logout-all", headers=headers)
    assert r.status_code == 200, r.text
    
    # The exact same token should now be rejected
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "Token revoked"

async def test_fresh_login_succeeds_after_logout_all(client):
    """
    A revocation mechanism that revokes but cannot reissue correctly locks the user out.
    A fresh login after /logout-all must yield a token carrying the new token_version,
    allowing the user back in.
    """
    r = await _register(client, password="12345678")
    assert r.status_code == 201, r.text
    
    # Login, revoke
    headers = await _login(client, PATIENT["email"], "12345678")
    await client.post("/api/v1/auth/logout-all", headers=headers)
    
    # Fresh login
    new_headers = await _login(client, PATIENT["email"], "12345678")
    
    # Use new token to call protected endpoint
    r = await client.get("/api/v1/auth/me", headers=new_headers)
    assert r.status_code == 200, r.text

from sqlalchemy import select
from app.models.user import User

async def test_deleted_user_token_is_rejected(client, session):
    """
    If a User row is erased (e.g. via the patient data erasure path), their
    formerly valid JWTs must instantly be rejected by auth middleware.
    """
    r = await _register(client, password="12345678")
    assert r.status_code == 201, r.text
    
    headers = await _login(client, PATIENT["email"], "12345678")
    
    # Confirm it works
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    
    # Delete the user manually
    user = (
        await session.execute(select(User).where(User.email == PATIENT["email"]))
    ).scalars().one()
    await session.delete(user)
    await session.commit()
    
    # The token should now be rejected, typically as 401 Unauthorized
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401, r.text
