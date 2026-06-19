def test_add_and_list_facts(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()
    resp = client.post(
        f"/kbs/{kb['id']}/facts",
        json={"key": "price", "value": "$99/mo", "source": "pricing.pdf"},
    )
    assert resp.status_code == 201
    fact = resp.json()
    assert fact["key"] == "price"
    assert fact["value"] == "$99/mo"
    assert fact["source"] == "pricing.pdf"

    facts = client.get(f"/kbs/{kb['id']}/facts").json()
    assert len(facts) == 1


def test_fact_bumps_version(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()
    client.post(f"/kbs/{kb['id']}/facts", json={"key": "k", "value": "v"})
    assert client.get(f"/kbs/{kb['id']}").json()["version"] == 2


def test_delete_fact(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()
    fact = client.post(f"/kbs/{kb['id']}/facts", json={"key": "k", "value": "v"}).json()
    assert client.delete(f"/kbs/{kb['id']}/facts/{fact['id']}").status_code == 204
    assert client.get(f"/kbs/{kb['id']}/facts").json() == []


def test_delete_fact_wrong_kb(client):
    kb1 = client.post("/kbs", json={"name": "KB1", "owner": "alice"}).json()
    kb2 = client.post("/kbs", json={"name": "KB2", "owner": "alice"}).json()
    fact = client.post(f"/kbs/{kb1['id']}/facts", json={"key": "k", "value": "v"}).json()
    assert client.delete(f"/kbs/{kb2['id']}/facts/{fact['id']}").status_code == 404


def test_add_and_list_limitations(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()
    resp = client.post(
        f"/kbs/{kb['id']}/limitations",
        json={"description": "Does not support video playback"},
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "Does not support video playback"

    lims = client.get(f"/kbs/{kb['id']}/limitations").json()
    assert len(lims) == 1


def test_limitation_bumps_version(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()
    client.post(f"/kbs/{kb['id']}/limitations", json={"description": "No video"})
    assert client.get(f"/kbs/{kb['id']}").json()["version"] == 2


def test_delete_limitation(client):
    kb = client.post("/kbs", json={"name": "KB", "owner": "alice"}).json()
    lim = client.post(
        f"/kbs/{kb['id']}/limitations", json={"description": "No video"}
    ).json()
    assert client.delete(f"/kbs/{kb['id']}/limitations/{lim['id']}").status_code == 204
    assert client.get(f"/kbs/{kb['id']}/limitations").json() == []
