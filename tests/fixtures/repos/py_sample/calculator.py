"""Simple calculator module for fixture testing."""

from __future__ import annotations


class Calculator:
    """A basic calculator with history."""

    def __init__(self) -> None:
        self.history: list[float] = []

    def add(self, a: float, b: float) -> float:
        result = a + b
        self.history.append(result)
        return result

    def subtract(self, a: float, b: float) -> float:
        result = a - b
        self.history.append(result)
        return result

    def multiply(self, a: float, b: float) -> float:
        result = a * b
        self.history.append(result)
        return result

    def divide(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Division by zero")
        result = a / b
        self.history.append(result)
        return result

    def clear_history(self) -> None:
        self.history.clear()


def parse_expression(expr: str) -> tuple[float, str, float]:
    """Parse a simple 'a op b' expression."""
    parts = expr.strip().split()
    if len(parts) != 3:
        raise ValueError(f"Invalid expression: {expr!r}")
    left, op, right = parts
    return float(left), op, float(right)


def evaluate(expr: str) -> float:
    """Evaluate a simple arithmetic expression."""
    calc = Calculator()
    left, op, right = parse_expression(expr)
    if op == "+":
        return calc.add(left, right)
    elif op == "-":
        return calc.subtract(left, right)
    elif op == "*":
        return calc.multiply(left, right)
    elif op == "/":
        return calc.divide(left, right)
    else:
        raise ValueError(f"Unknown operator: {op!r}")
