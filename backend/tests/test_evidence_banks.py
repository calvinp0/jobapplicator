def test_create_evidence_bank(client):
    r = client.post(
        "/evidence-banks",
        json={"name": "default", "content_markdown": "- thing\n"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "default"

    fetched = client.get(f"/evidence-banks/{body['id']}").json()
    assert fetched["content_markdown"].startswith("- thing")
