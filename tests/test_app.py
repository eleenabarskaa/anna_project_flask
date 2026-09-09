import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app("testing")
    with app.test_client() as c:
        yield c


# --- страницы ------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/?variant=queue",
        "/?variant=command",
        "/prospects",
        "/prospects?q=brunner",
        "/triggers",
        "/triggers?category=M%26A+%2F+Liquidity",
        "/triggers?event=t3",
        "/sources",
        "/healthz",
    ],
)
def test_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


def test_unknown_document_404(client):
    assert client.get("/prospects/nope").status_code == 404


def test_brief_list_shows_documents(client):
    body = client.get("/prospects").get_data(as_text=True)
    assert "Elisabeth Brunner" in body
    assert "Vaduz Chemicals Holding" in body


def test_search_filters(client):
    body = client.get("/prospects?q=ferretti").get_data(as_text=True)
    assert "Lorenzo Ferretti" in body
    assert "Elisabeth Brunner" not in body


# --- действия ------------------------------------------------------------

def test_watch_toggle_roundtrip(client):
    before = client.get("/api/v1/prospects/queue").get_json()["items"][0]["watched"]
    after = client.post("/api/v1/prospects/p1/watch").get_json()["watched"]
    assert after is not before


def test_task_toggle(client):
    first = client.get("/api/v1/desk/tasks").get_json()["items"][0]
    toggled = client.post(f"/api/v1/desk/tasks/{first['id']}/toggle").get_json()
    assert toggled["done"] is not first["done"]


def test_category_toggle(client):
    resp = client.post("/api/v1/sources/categories/PE Exit/toggle", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False


# --- API -----------------------------------------------------------------

def test_api_health(client):
    assert client.get("/api/v1/health").get_json()["status"] == "ok"


def test_api_triggers_pagination(client):
    data = client.get("/api/v1/triggers?per_page=3").get_json()
    assert len(data["items"]) == 3
    assert data["meta"]["pages"] >= 3
    assert data["items"][0]["heat"] in {"amber", "blue", "green"}


def test_api_trigger_category_filter(client):
    data = client.get("/api/v1/triggers?category=Succession").get_json()
    assert {i["type"] for i in data["items"]} == {"Succession"}


def test_api_trigger_detail_and_404(client):
    assert client.get("/api/v1/triggers/t1").get_json()["company"] == "Helvetia Precision AG"
    assert client.get("/api/v1/triggers/zzz").status_code == 404


def test_api_queue_sorted_by_fit(client):
    items = client.get("/api/v1/prospects/queue").get_json()["items"]
    fits = [i["fit"] for i in items]
    assert fits == sorted(fits, reverse=True)


def test_api_overview_shape(client):
    data = client.get("/api/v1/desk/overview").get_json()
    for key in ("kpis", "latest_triggers", "watchlist", "tasks", "queue", "composition"):
        assert key in data and data[key]


def test_api_sources_and_logs(client):
    assert len(client.get("/api/v1/sources").get_json()["items"]) == 8
    assert client.get("/api/v1/sources/logs").get_json()["items"]


def test_api_404_is_json(client):
    resp = client.get("/api/v1/prospects/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"
