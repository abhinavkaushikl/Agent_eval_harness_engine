"""Temperature helpers. No tests here — the pet should write and run them himself."""


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (f - 32.0) * 5.0 / 9.0


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value into the inclusive range [low, high]."""
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(high, value))


def is_freezing(celsius: float) -> bool:
    """True when the temperature is at or below water's freezing point."""
    return celsius <= 0.0
