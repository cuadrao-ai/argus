import pytest
from argus.api.main import app
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "commit", ["a" * 40, "B" * 40, None, "", "abc123", "invalid" * 8, "a" * 40 + "\n"]
)
def test_health_reports_only_full_deployment_commit(monkeypatch, commit):
    if commit is None:
        monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    else:
        monkeypatch.setenv("RENDER_GIT_COMMIT", commit)
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "version": "1.0.0-alpha",
        "git_sha": commit if commit in {"a" * 40, "B" * 40} else None,
    }
