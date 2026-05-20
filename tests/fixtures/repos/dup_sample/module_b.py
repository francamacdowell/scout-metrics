"""Module B — contains duplicated block (intentional copy for fixture)."""


def handle_items(items):
    results = []
    for item in items:
        if item is None:
            continue
        value = item * 2
        if value > 100:
            value = 100
        results.append(value)
    return results


def calculate(x):
    return x**2 + 3 * x + 1
