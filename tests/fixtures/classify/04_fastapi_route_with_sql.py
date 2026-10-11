# expect: api_endpoint, sql_generation -- a FastAPI route that runs a SELECT: both at once, as planner fixture 18; its pydantic return is the response schema, not an extraction.
import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class Order(BaseModel):
    id: int
    status: str


@router.get("/orders/{order_id}")
def read_order(order_id: int) -> Order:
    conn = sqlite3.connect("shop.db")
    row = conn.execute("select id, status from orders where id = ?", (order_id,)).fetchone()
    return Order(id=row[0], status=row[1])
