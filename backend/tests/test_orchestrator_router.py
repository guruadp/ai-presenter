"""EPIC 11 router tests — Presenter Control Panel (state sync).

Uses TestClient as a context manager so all requests share the same anyio
event loop, allowing background orchestrator tasks to persist between calls.
The `await asyncio.sleep(0)` in each endpoint yields the loop so the
orchestrator processes commands before the response is returned.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.project import Project, ShowFile
from app.services import orchestrator as orch_svc


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_sessions():
    orch_svc._sessions.clear()
    yield
    orch_svc._sessions.clear()


@pytest.fixture()
def db_session():
    # StaticPool forces all threads to share the same single connection so the
    # in-memory database persists across the TestClient's anyio thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_ready_show_file(db_session):
    """Create a minimal project + ready Show File in the database."""
    project = Project(id="test-proj", name="Test Project", owner="tester")
    sf = ShowFile(
        id="test-sf",
        project_id="test-proj",
        version=1,
        status="ready",
        manifest_path="/tmp/manifest.json",
        bundle_path="/tmp/bundle.zip",
        manifest={
            "schema_version": 1,
            "slides": [
                {
                    "slide_id": "s1",
                    "position": 1,
                    "image_path": "slides/s1.png",
                    "segments": [
                        {
                            "index": 0,
                            "text": "Hello world.",
                            "audio_path": "audio/s1_0.wav",
                            "audio_duration_seconds": 2.0,
                        }
                    ],
                },
                {
                    "slide_id": "s2",
                    "position": 2,
                    "image_path": "slides/s2.png",
                    "segments": [
                        {
                            "index": 0,
                            "text": "Second slide.",
                            "audio_path": "audio/s2_0.wav",
                            "audio_duration_seconds": 2.0,
                        }
                    ],
                },
            ],
        },
        validation_errors=[],
        tts_provider="test",
    )
    project.show_files.append(sf)
    db_session.add(project)
    db_session.commit()
    return sf


# ── S11.3: pre-flight / error paths ──────────────────────────────────────────

def test_create_session_unknown_project(client):
    resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "nope", "show_file_id": "nope"},
    )
    assert resp.status_code == 404


def test_create_session_unknown_show_file(client, db_session):
    project = Project(id="p-no-sf", name="No SF", owner="x")
    db_session.add(project)
    db_session.commit()

    resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "p-no-sf", "show_file_id": "nonexistent-sf"},
    )
    assert resp.status_code == 404


def test_create_session_non_ready_show_file(client, db_session):
    project = Project(id="p-bad", name="Bad SF", owner="x")
    sf = ShowFile(
        id="sf-bad",
        project_id="p-bad",
        version=1,
        status="invalid",
        manifest_path="/tmp/m.json",
        bundle_path="/tmp/b.zip",
        manifest={},
        validation_errors=["missing audio"],
        tts_provider="test",
    )
    project.show_files.append(sf)
    db_session.add(project)
    db_session.commit()

    resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "p-bad", "show_file_id": "sf-bad"},
    )
    assert resp.status_code == 400


def test_get_unknown_session(client):
    resp = client.get("/orchestrator/sessions/no-such-id")
    assert resp.status_code == 404


def test_command_unknown_session(client):
    resp = client.post(
        "/orchestrator/sessions/no-such-id/command",
        json={"type": "start"},
    )
    assert resp.status_code == 404


def test_internal_command_blocked(client, db_session):
    _seed_ready_show_file(db_session)
    resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = resp.json()["session_id"]

    resp = client.post(
        f"/orchestrator/sessions/{session_id}/command",
        json={"type": "qa_budget_expired"},
    )
    assert resp.status_code == 400


def test_unknown_command_type(client, db_session):
    _seed_ready_show_file(db_session)
    resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = resp.json()["session_id"]

    resp = client.post(
        f"/orchestrator/sessions/{session_id}/command",
        json={"type": "totally_made_up"},
    )
    assert resp.status_code == 400


def test_delete_unknown_session(client):
    resp = client.delete("/orchestrator/sessions/ghost")
    assert resp.status_code == 404


# ── S11.1: State sync integration ─────────────────────────────────────────────

def test_create_session_returns_ready_state(client, db_session):
    _seed_ready_show_file(db_session)
    resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["state"] == "READY"


def test_get_session_returns_current_state(client, db_session):
    _seed_ready_show_file(db_session)
    create_resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = create_resp.json()["session_id"]

    get_resp = client.get(f"/orchestrator/sessions/{session_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["session_id"] == session_id
    assert data["state"] == "READY"
    assert data["cursor"]["slide_index"] == 0
    assert data["cursor"]["segment_index"] == 0
    assert data["jump_stack_depth"] == 0


def test_start_command_transitions_to_speaking(client, db_session):
    _seed_ready_show_file(db_session)
    create_resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = create_resp.json()["session_id"]

    cmd_resp = client.post(
        f"/orchestrator/sessions/{session_id}/command",
        json={"type": "start"},
    )
    assert cmd_resp.status_code == 200
    assert cmd_resp.json()["state"] == "SPEAKING"


def test_pause_and_resume_state_cycle(client, db_session):
    _seed_ready_show_file(db_session)
    create_resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = create_resp.json()["session_id"]

    # READY → SPEAKING
    client.post(f"/orchestrator/sessions/{session_id}/command", json={"type": "start"})

    # SPEAKING → PAUSED
    pause_resp = client.post(
        f"/orchestrator/sessions/{session_id}/command", json={"type": "pause"}
    )
    assert pause_resp.json()["state"] == "PAUSED"

    # PAUSED → SPEAKING
    resume_resp = client.post(
        f"/orchestrator/sessions/{session_id}/command", json={"type": "resume"}
    )
    assert resume_resp.json()["state"] == "SPEAKING"


def test_stop_command_and_session_cleanup(client, db_session):
    _seed_ready_show_file(db_session)
    create_resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = create_resp.json()["session_id"]
    client.post(f"/orchestrator/sessions/{session_id}/command", json={"type": "start"})

    # DELETE removes the session
    del_resp = client.delete(f"/orchestrator/sessions/{session_id}")
    assert del_resp.status_code == 200

    # Subsequent GET returns 404
    get_resp = client.get(f"/orchestrator/sessions/{session_id}")
    assert get_resp.status_code == 404


def test_command_response_includes_cursor(client, db_session):
    _seed_ready_show_file(db_session)
    create_resp = client.post(
        "/orchestrator/sessions",
        json={"project_id": "test-proj", "show_file_id": "test-sf"},
    )
    session_id = create_resp.json()["session_id"]

    resp = client.post(
        f"/orchestrator/sessions/{session_id}/command", json={"type": "start"}
    )
    assert "cursor" in resp.json()
    cursor = resp.json()["cursor"]
    assert "slide_index" in cursor
    assert "segment_index" in cursor
    assert "sentence_index" in cursor
