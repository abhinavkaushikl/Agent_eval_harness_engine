# expect: abstain:syntax_error -- the developer is mid-edit and the file does not parse; that is unclassifiable, never a guessed label.
def total_price(items: list[dict[str, float]]) -> float:
    subtotal = sum(item["price"] * item["qty"] for item in items
    if subtotal >
