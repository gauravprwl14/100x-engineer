# Covers AC-2: deleting a tag is restricted to the album owner.
def test_non_owner_cannot_delete_a_tag(client, other_member):
    response = client.delete("/api/v1/tags/1", as_user=other_member)
    assert response.status_code == 403
