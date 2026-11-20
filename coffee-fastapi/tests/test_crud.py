def test_product_crud(client):
    assert len(client.get("/products").json()) == 4

    r = client.post("/products", json={"name": "Kenya AA", "price": 9000, "stock": 10})
    assert r.status_code == 201
    pid = r.json()["data"]["id"]

    r = client.put(f"/products/{pid}", json={"name": "Kenya AA+", "price": 9500, "stock": 5})
    assert r.json()["data"]["price"] == 9500

    assert client.delete(f"/products/{pid}").status_code == 200
    assert client.get(f"/products/{pid}").status_code == 404


def test_product_validation(client):
    r = client.post("/products", json={"name": "A", "price": -1, "stock": 0})
    assert r.status_code == 422


def test_order_flow_and_stock(client):
    r = client.post("/orders", json={"customer_email": "a@test.com",
                                     "items": [{"product_id": 1, "quantity": 3}, {"product_id": 2, "quantity": 1}]})
    assert r.status_code == 201
    assert client.get("/products/1").json()["stock"] == 97

    orders = client.get("/orders/a@test.com").json()["data"]
    assert len(orders) == 2
    order_id = next(o["order_id"] for o in orders if o["product_id"] == 1)

    client.put(f"/orders/{order_id}", json={"quantity": 1})
    assert client.get("/products/1").json()["stock"] == 99

    client.delete("/orders/a@test.com")
    assert client.get("/products/1").json()["stock"] == 100
    assert client.get("/orders/a@test.com").json()["data"] == []


def test_order_out_of_stock_rolls_back(client):
    r = client.post("/orders", json={"customer_email": "a@test.com",
                                     "items": [{"product_id": 1, "quantity": 1}, {"product_id": 2, "quantity": 999}]})
    assert r.status_code == 400
    assert "재고" in r.json()["msg"]
    assert client.get("/products/1").json()["stock"] == 100  # 앞 항목도 롤백
