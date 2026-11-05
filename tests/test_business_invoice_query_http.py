from typing import Annotated

import pytest
from argus.domain.business.invoicing.queries import CustomerQuery, Query
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app = FastAPI()

    @app.get("/customers")
    def customers(query: Annotated[CustomerQuery, Depends()]):
        return query.model_dump(mode="json")

    @app.get("/invoices")
    def invoices(query: Annotated[Query, Depends()]):
        return query.model_dump(mode="json")

    client = TestClient(app)
    yield client
    client.close()


@pytest.mark.parametrize("path", ["/customers", "/invoices"])
@pytest.mark.parametrize("page_size", [25, 50, 100])
def test_explicit_page_size_binds_from_http(client, path, page_size):
    response = client.get(path, params={"page_size": str(page_size)})
    assert response.status_code == 200, response.text
    assert response.json()["page_size"] == page_size


@pytest.mark.parametrize("path", ["/customers", "/invoices"])
def test_omitted_page_size_keeps_default(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["page_size"] == 25


@pytest.mark.parametrize("path", ["/customers", "/invoices"])
@pytest.mark.parametrize(
    "params",
    [
        {"page_size": "13"},
        {"page_size": "0"},
        {"page_size": "25.0"},
        {"page_size": "25.5"},
        {"page_size": "2.5e1"},
        {"page_size": "abc"},
        {"page_size": ""},
        {"page": "0"},
        {"search": "x" * 201},
    ],
)
def test_invalid_query_values_stay_rejected(client, path, params):
    assert client.get(path, params=params).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"currency": "BTC"},
        {"stage": "paid"},
        {"date_from": "not-a-date"},
        {"sort": "customer"},
    ],
)
def test_invoice_specific_validation_stays_rejected(client, params):
    assert client.get("/invoices", params=params).status_code == 422


def test_normal_invoice_list_query_binds(client):
    response = client.get("/invoices?page=1&page_size=25&search=&stage=all&sort=newest")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "page": 1,
        "page_size": 25,
        "search": "",
        "currency": None,
        "stage": "all",
        "date_from": None,
        "date_to": None,
        "sort": "newest",
    }


@pytest.mark.parametrize("path", ["/customers", "/invoices"])
def test_http_schema_keeps_integer_enum_and_default(client, path):
    parameters = client.get("/openapi.json").json()["paths"][path]["get"]["parameters"]
    page_size = next(item for item in parameters if item["name"] == "page_size")
    assert page_size["required"] is False
    assert page_size["schema"]["type"] == "integer"
    assert page_size["schema"]["enum"] == [25, 50, 100]
    assert page_size["schema"]["default"] == 25
