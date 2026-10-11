def overlap_days(start_a, end_a, start_b, end_b):
    """Count the days two inclusive integer ranges share; 0 when they do not overlap."""
    low = max(start_a, start_b)
    high = min(end_a, end_b)
    return max(0, high - low + 1)
