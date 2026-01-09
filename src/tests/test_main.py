from fastapi.testclient import TestClient
from unittest.mock import patch
import pytest
from src.api.main import app


@pytest.fixture
def client():
    # Mock the database connection
    with patch("src.api.main.db") as mock_db:
        mock_db.connect.return_value = None
        mock_db.execute_query.return_value = [{"test": 1}]
        yield TestClient(app)


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "service": "Repository Intelligence API",
        "version": "0.1.0",
        "status": "running",
    }


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
