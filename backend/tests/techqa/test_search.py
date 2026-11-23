import psycopg
import pytest

from app.techqa.search import Method, search_chunks
from tests.techqa.helpers import CHUNK_SET_ID

pytestmark = pytest.mark.db

OTHER_CHUNK_SET_ID = f"{CHUNK_SET_ID}-other"
METHODS: list[Method] = ["bm25", "fts"]


@pytest.mark.parametrize("method", METHODS)
def test_inflected_query_finds_document(
    imported_conn: psycopg.Connection, method: Method
) -> None:
    hits = search_chunks(
        imported_conn, "restarting", method=method, chunk_set_id=CHUNK_SET_ID
    )
    assert "multiline_title" in {hit.doc_id for hit in hits}
    assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))
    assert all(len(hit.snippet) <= 200 for hit in hits)


@pytest.mark.parametrize("method", METHODS)
def test_scores_descending_and_k_respected(
    imported_conn: psycopg.Connection, method: Method
) -> None:
    hits = search_chunks(
        imported_conn, "restart server", method=method, chunk_set_id=CHUNK_SET_ID, k=3
    )
    assert 0 < len(hits) <= 3
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("method", METHODS)
def test_other_chunk_set_is_not_returned(
    imported_conn: psycopg.Connection, method: Method
) -> None:
    imported_conn.execute(
        "INSERT INTO chunk_sets (id, snapshot_id, variant, config, config_sha256)"
        " SELECT %s, snapshot_id, 'other', '{}', 'x' FROM chunk_sets WHERE id = %s",
        (OTHER_CHUNK_SET_ID, CHUNK_SET_ID),
    )
    imported_conn.execute(
        "INSERT INTO chunks (id, chunk_set_id, snapshot_id, doc_id, ordinal, headings,"
        " start_offset, end_offset, text, text_sha256)"
        " SELECT id || '-other', %s, snapshot_id, doc_id, ordinal, headings,"
        " start_offset, end_offset, text, text_sha256"
        " FROM chunks WHERE chunk_set_id = %s",
        (OTHER_CHUNK_SET_ID, CHUNK_SET_ID),
    )
    main_hits = search_chunks(
        imported_conn, "restart", method=method, chunk_set_id=CHUNK_SET_ID, k=50
    )
    other_hits = search_chunks(
        imported_conn, "restart", method=method, chunk_set_id=OTHER_CHUNK_SET_ID, k=50
    )
    assert main_hits
    assert len(other_hits) == len(main_hits)
    assert not any(hit.chunk_id.endswith("-other") for hit in main_hits)
    assert all(hit.chunk_id.endswith("-other") for hit in other_hits)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize(
    "query",
    [
        '"restart',
        'restart "server',
        "restart & server",
        "restart | server",
        "(restart",
        "restart)",
        "((restart) & (server |",
        "it's a 'quote'",
        "restart:*  !server -",
        "&|()\"'",
    ],
)
def test_special_characters_in_query_do_not_fail(
    imported_conn: psycopg.Connection, method: Method, query: str
) -> None:
    hits = search_chunks(
        imported_conn, query, method=method, chunk_set_id=CHUNK_SET_ID, k=5
    )
    assert len(hits) <= 5
    assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_is_rejected(
    imported_conn: psycopg.Connection, method: Method, k: int
) -> None:
    with pytest.raises(ValueError, match="k"):
        search_chunks(
            imported_conn, "restart", method=method, chunk_set_id=CHUNK_SET_ID, k=k
        )
