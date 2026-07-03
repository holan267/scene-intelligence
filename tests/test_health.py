from __future__ import annotations


def test_health_returns_200_envelope(client):
    # AC-1 + AD-13: /api/v1/health trả 200 + envelope báo trạng thái kho
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert "results" in body and "meta" in body
    stores = body["meta"]["stores"]
    assert stores["postgres"] is True
    assert stores["media_storage"] is True
