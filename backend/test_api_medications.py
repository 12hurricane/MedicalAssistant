import pytest
from httpx import AsyncClient

# Expose the conftest fixtures if they aren't automatically found (they usually are)
from conftest import register

@pytest.mark.asyncio
async def test_list_medications(client: AsyncClient, session):
    headers = await register(client, "patient1@example.com", role="PATIENT")
    
    # Needs some initial setup of medications or we can just test if it returns a list
    resp = await client.get("/api/v1/medications", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

@pytest.mark.asyncio
async def test_create_medication_admin(client: AsyncClient):
    headers = await register(client, "admin1@example.com", role="ADMIN")
    
    payload = {
        "brand_name": "TestMeds",
        "generic_name": "GenericTest",
        "standard_strength": "10mg",
        "dosage_form": "Tablet",
        "route_of_administration": "ORAL",
        "controlled_substance_schedule": "None"
    }
    resp = await client.post("/api/v1/medications", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["brand_name"] == "TestMeds"
    
    # Test conflict
    resp2 = await client.post("/api/v1/medications", json=payload, headers=headers)
    assert resp2.status_code == 409

@pytest.mark.asyncio
async def test_create_medication_non_admin(client: AsyncClient):
    headers = await register(client, "patient2@example.com", role="PATIENT")
    
    payload = {
        "brand_name": "TestMeds2",
        "generic_name": "GenericTest2"
    }
    resp = await client.post("/api/v1/medications", json=payload, headers=headers)
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_get_medication(client: AsyncClient):
    headers = await register(client, "admin2@example.com", role="ADMIN")
    
    payload = {
        "brand_name": "GetMed",
        "generic_name": "GetGeneric"
    }
    post_resp = await client.post("/api/v1/medications", json=payload, headers=headers)
    assert post_resp.status_code == 201
    med_id = post_resp.json()["id"]
    
    get_resp = await client.get(f"/api/v1/medications/{med_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["brand_name"] == "GetMed"
    
    bad_resp = await client.get("/api/v1/medications/999999", headers=headers)
    assert bad_resp.status_code == 404

@pytest.mark.asyncio
async def test_update_medication_admin(client: AsyncClient):
    headers = await register(client, "admin3@example.com", role="ADMIN")
    
    payload = {
        "brand_name": "UpdateMed",
        "generic_name": "UpdateGeneric"
    }
    post_resp = await client.post("/api/v1/medications", json=payload, headers=headers)
    med_id = post_resp.json()["id"]
    
    update_payload = {
        "brand_name": "UpdatedMedName"
    }
    put_resp = await client.put(f"/api/v1/medications/{med_id}", json=update_payload, headers=headers)
    assert put_resp.status_code == 200
    assert put_resp.json()["brand_name"] == "UpdatedMedName"
    
    # Conflict test
    payload2 = {
        "brand_name": "AnotherMed",
        "generic_name": "AnotherGeneric"
    }
    await client.post("/api/v1/medications", json=payload2, headers=headers)
    
    put_conflict = await client.put(f"/api/v1/medications/{med_id}", json=payload2, headers=headers)
    assert put_conflict.status_code == 409

@pytest.mark.asyncio
async def test_search_medications(client: AsyncClient):
    headers = await register(client, "admin4@example.com", role="ADMIN")
    
    await client.post("/api/v1/medications", json={"brand_name": "SpecialDrug", "generic_name": "SpecialGeneric"}, headers=headers)
    await client.post("/api/v1/medications", json={"brand_name": "OtherDrug", "generic_name": "OtherGeneric"}, headers=headers)
    
    # Search for Special
    resp = await client.get("/api/v1/medications?search=Special", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(m["brand_name"] == "SpecialDrug" for m in data)
    assert all(m["brand_name"] != "OtherDrug" for m in data)
