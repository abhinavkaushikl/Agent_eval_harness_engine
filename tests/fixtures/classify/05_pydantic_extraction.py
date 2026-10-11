# expect: structured_extraction -- free text in, a pydantic model out: field-level scoring against a schema (A5) is what grades this.
from pydantic import BaseModel


class Invoice(BaseModel):
    number: str
    total: float
    currency: str


def parse_invoice(text: str) -> Invoice:
    """Pull the invoice number, total and currency out of an emailed invoice."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    amount, _, currency = fields["total"].partition(" ")
    return Invoice(number=fields["invoice"], total=float(amount), currency=currency or "INR")
