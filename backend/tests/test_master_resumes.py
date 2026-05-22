def test_create_master_resume(client):
    r = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# Resume\n"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "main"
    assert body["content_markdown"].startswith("# Resume")

    listed = client.get("/master-resumes").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]
