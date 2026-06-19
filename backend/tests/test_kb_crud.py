def test_create_kb(client):
    resp = client.post("/kbs", json={"name": "Product KB", "owner": "alice"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Product KB"
    assert data["owner"] == "alice"
    assert data["version"] == 1
    assert "id" in data
    assert "content_hash" in data


def test_list_kbs(client):
    client.post("/kbs", json={"name": "KB1", "owner": "alice"})
    client.post("/kbs", json={"name": "KB2", "owner": "bob"})
    resp = client.get("/kbs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_kb(client):
    created = client.post("/kbs", json={"name": "Test KB", "owner": "alice"}).json()
    resp = client.get(f"/kbs/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_kb_not_found(client):
    assert client.get("/kbs/nonexistent").status_code == 404


def test_update_kb_bumps_version(client):
    created = client.post("/kbs", json={"name": "Original", "owner": "alice"}).json()
    resp = client.patch(f"/kbs/{created['id']}", json={"name": "Updated"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "Updated"
    assert updated["version"] == 2
    assert updated["content_hash"] != created["content_hash"]


def test_delete_kb(client):
    created = client.post("/kbs", json={"name": "Delete Me", "owner": "alice"}).json()
    assert client.delete(f"/kbs/{created['id']}").status_code == 204
    assert client.get(f"/kbs/{created['id']}").status_code == 404
