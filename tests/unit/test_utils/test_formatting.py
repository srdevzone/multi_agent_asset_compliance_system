"""Tests for retrieval prompt formatting."""

from app.utils.formatting import format_chunks_for_prompt


def test_formats_flat_chunk_with_parent_context():
    rendered = format_chunks_for_prompt(
        [
            {
                "filename": "manual.pdf",
                "page": 2,
                "doc_type": "user_manual",
                "text": "Child clause",
                "parent_text": "Full parent section",
            }
        ]
    )

    assert "[manual.pdf | page 2 | user_manual]" in rendered
    assert "Child clause" in rendered
    assert "[Parent Context]\nFull parent section" in rendered


def test_formats_pinecone_result_metadata():
    rendered = format_chunks_for_prompt(
        [{"metadata": {"filename": "spec.pdf", "text": "Requirement"}}]
    )

    assert "spec.pdf" in rendered
    assert "Requirement" in rendered


def test_empty_chunks_have_explicit_message():
    assert format_chunks_for_prompt([]) == "No documents retrieved."
