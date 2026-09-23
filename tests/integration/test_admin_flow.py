"""
Integration tests for the admin management endpoints.

Tests:
  GET  /api/v1/admin/assets/{asset_id}/stats
  DELETE /api/v1/admin/assets/{asset_id}

All external service calls (Pinecone, DynamoDB) are mocked.
No real AWS or Pinecone calls are made.
"""

from unittest.mock import MagicMock

import pytest

from tests.integration.helpers import patch_dependencies


@pytest.mark.asyncio
async def test_get_asset_stats_returns_correct_structure(
    async_client, auth_headers, mock_pinecone_index, mock_dynamodb_table
):
    """GET /admin/assets/{asset_id}/stats should return counts from Pinecone and DynamoDB."""
    # Pinecone has 42 vectors in the asset namespace
    ns_mock = MagicMock()
    ns_mock.vector_count = 42
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(
        namespaces={"asset_abc-123": ns_mock}
    )

    with patch_dependencies(pinecone=mock_pinecone_index, dynamodb=mock_dynamodb_table):
        response = await async_client.get(
            "/api/v1/admin/assets/abc-123/stats",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "abc-123"
    assert body["pinecone_namespace"] == "asset_abc-123"
    assert body["pinecone_vector_count"] == 42
    assert "total_audit_runs" in body
    assert "audit_run_status_counts" in body


@pytest.mark.asyncio
async def test_get_asset_stats_empty_namespace(
    async_client, auth_headers, mock_pinecone_index, mock_dynamodb_table
):
    """GET /admin/assets/{asset_id}/stats with no vectors should return zero count."""
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(namespaces={})

    with patch_dependencies(pinecone=mock_pinecone_index, dynamodb=mock_dynamodb_table):
        response = await async_client.get(
            "/api/v1/admin/assets/no-data/stats",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["pinecone_vector_count"] == 0
    assert body["total_audit_runs"] == 0


@pytest.mark.asyncio
async def test_delete_asset_returns_erasure_confirmation(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_dynamodb_table
):
    """DELETE /admin/assets/{asset_id} should delete Pinecone vectors and DynamoDB records."""
    # Pinecone: simulate 10 vectors in namespace, 0 after deletion
    before_stats = MagicMock()
    before_ns = MagicMock()
    before_ns.vector_count = 10
    before_stats.namespaces = {"asset_del-asset": before_ns}

    after_stats = MagicMock()
    after_stats.namespaces = {}

    mock_pinecone_index.describe_index_stats.side_effect = [before_stats, after_stats]
    mock_pinecone_index.delete = MagicMock()

    with patch_dependencies(
        pinecone=mock_pinecone_index, dynamodb=mock_dynamodb_table, s3=s3_bucket
    ):
        response = await async_client.delete(
            "/api/v1/admin/assets/del-asset",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "del-asset"
    assert body["pinecone_vectors_deleted"] == 10
    assert "message" in body
    assert "ERASED" in body["message"] or "deleted" in body["message"]


@pytest.mark.asyncio
async def test_delete_asset_empty_namespace(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_dynamodb_table
):
    """DELETE /admin/assets/{asset_id} on asset with no vectors should return 0 deleted."""
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(namespaces={})

    with patch_dependencies(
        pinecone=mock_pinecone_index, dynamodb=mock_dynamodb_table, s3=s3_bucket
    ):
        response = await async_client.delete(
            "/api/v1/admin/assets/ghost-asset",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["pinecone_vectors_deleted"] == 0


@pytest.mark.asyncio
async def test_admin_endpoints_require_api_key(async_client, mock_pinecone_index):
    """Admin endpoints should return 401 without X-API-Key."""
    with patch_dependencies(pinecone=mock_pinecone_index):
        stats_response = await async_client.get("/api/v1/admin/assets/abc/stats")
        delete_response = await async_client.delete("/api/v1/admin/assets/abc")

    assert stats_response.status_code == 401
    assert delete_response.status_code == 401
