"""Module A — contains duplicated block."""


def process_items(items):
    results = []
    for item in items:
        if item is None:
            continue
        value = item * 2
        if value > 100:
            value = 100
        results.append(value)
    return results


def transform(x):
    return x**2 + 3 * x + 1
