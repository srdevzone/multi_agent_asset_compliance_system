"""Shared helpers for integration tests."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch


@contextmanager
def patch_dependencies(pinecone=None, embeddings=None, s3=None, dynamodb=None, llm=None):
    """Patch dependency providers used by FastAPI route handlers.

    Each argument is optional; when provided, the corresponding private
    dependency factory is patched to return the supplied value.
    """
    patches = []
    if pinecone is not None:
        patches.append(patch("app.dependencies._get_pinecone_index", return_value=pinecone))
    if embeddings is not None:
        patches.append(patch("app.dependencies._get_embeddings_model", return_value=embeddings))
    if s3 is not None:
        patches.append(patch("app.dependencies._get_s3_client", return_value=s3))
    if dynamodb is not None:
        patches.append(patch("app.dependencies._get_dynamodb_client", return_value=dynamodb))
    if llm is not None:
        patches.append(patch("app.dependencies._get_agent_llm", return_value=llm))

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield
