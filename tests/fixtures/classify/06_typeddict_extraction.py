# expect: structured_extraction -- a TypedDict return built from an unstructured string: the TypedDict form of the schema signal.
from typing import TypedDict


class Contact(TypedDict):
    name: str
    email: str | None


def extract_contact(signature_block: str) -> Contact:
    lines = [line.strip() for line in signature_block.strip().splitlines() if line.strip()]
    email = next((line for line in lines if "@" in line), None)
    return {"name": lines[0], "email": email}
