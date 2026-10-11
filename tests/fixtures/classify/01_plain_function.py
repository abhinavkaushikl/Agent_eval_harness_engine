# expect: code_generation -- a plain pure function with no route, SQL or schema return: generated code, graded by running it (A1).
"""Text helpers."""

import unicodedata


def slugify(title: str, max_length: int = 60) -> str:
    """Lowercase ASCII slug, words joined by hyphens."""
    normalised = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = "".join(c if c.isalnum() else " " for c in normalised.lower()).split()
    slug = "-".join(words)
    return slug[:max_length].rstrip("-")
