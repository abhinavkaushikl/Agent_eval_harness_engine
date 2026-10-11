# expect: abstain:no_gradeable_unit -- every function is a stub (docstring, pass, ..., raise NotImplementedError): there is nothing yet to grade.
"""Payment gateway interface, not written yet."""

GATEWAY_URL = "https://payments.example.invalid"


def charge(card_token: str, amount_paise: int) -> str:
    """Charge a card and return the transaction id."""
    raise NotImplementedError


def refund(transaction_id: str) -> None:
    ...


class Ledger:
    def record(self, transaction_id: str) -> None:
        pass
