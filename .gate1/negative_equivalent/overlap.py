def overlap_days(start_a, end_a, start_b, end_b):
    """Count the days two inclusive integer ranges share; 0 when they do not overlap."""
    shared = [day for day in range(start_a, end_a + 1) if start_b <= day <= end_b]
    return len(shared)
