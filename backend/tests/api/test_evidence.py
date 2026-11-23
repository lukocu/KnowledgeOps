import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.techqa.helpers import CHUNK_SET_ID, REVISION, SNAPSHOT_ID

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _chunk_set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mini-migawka ma rewizję testową, więc zestaw wskazujemy jawnie.
    monkeypatch.setenv("CHUNK_SET_ID", CHUNK_SET_ID)


def _multi_chunk_doc(conn: psycopg.Connection) -> tuple[str, str]:
    row = conn.execute(
        "SELECT doc_id, (array_agg(id ORDER BY ordinal))[2] FROM chunks"
        " WHERE chunk_set_id = %s GROUP BY doc_id HAVING count(*) >= 3"
        " ORDER BY doc_id LIMIT 1",
        (CHUNK_SET_ID,),
    ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1])


def test_corpus(api_client: TestClient) -> None:
    response = api_client.get("/api/corpus")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] == SNAPSHOT_ID
    assert body["revision_short"] == REVISION[:7]
    assert body["chunk_set_id"] == CHUNK_SET_ID
    assert body["document_count"] > 0
    assert body["chunk_count"] > 0


def test_evidence_window(
    api_client: TestClient, imported_conn: psycopg.Connection
) -> None:
    _, chunk_id = _multi_chunk_doc(imported_conn)
    response = api_client.get("/api/evidence", params={"chunk_id": chunk_id})
    assert response.status_code == 200
    body = response.json()
    row = imported_conn.execute(
        "SELECT text FROM chunks WHERE id = %s", (chunk_id,)
    ).fetchone()
    assert row is not None
    highlighted = body["window_text"][body["highlight_start"] : body["highlight_end"]]
    assert highlighted == row[0]
    assert body["chunk_id"] == chunk_id


def test_evidence_unknown_chunk_is_404(api_client: TestClient) -> None:
    response = api_client.get("/api/evidence", params={"chunk_id": "brak/@1"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "params",
    [{"before": 6}, {"after": 6}, {"before": -1}, {"after": -1}],
)
def test_evidence_context_out_of_range_is_422(
    api_client: TestClient, params: dict[str, int]
) -> None:
    response = api_client.get("/api/evidence", params={"chunk_id": "x", **params})
    assert response.status_code == 422


def test_evidence_requires_chunk_id(api_client: TestClient) -> None:
    assert api_client.get("/api/evidence").status_code == 422


def test_document(api_client: TestClient, imported_conn: psycopg.Connection) -> None:
    doc_id, _ = _multi_chunk_doc(imported_conn)
    response = api_client.get(
        "/api/documents", params={"snapshot_id": SNAPSHOT_ID, "doc_id": doc_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == doc_id
    assert body["chunks"]
    first = body["chunks"][0]
    row = imported_conn.execute(
        "SELECT text FROM chunks WHERE id = %s", (first["chunk_id"],)
    ).fetchone()
    assert row is not None
    assert body["text"][first["start_offset"] : first["end_offset"]] == row[0]


def test_document_unknown_is_404(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/documents", params={"snapshot_id": SNAPSHOT_ID, "doc_id": "brak"}
    )
    assert response.status_code == 404
