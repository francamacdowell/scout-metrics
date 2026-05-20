"""Module with intentionally higher complexity for metric testing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Node:
    value: int
    left: Node | None = None
    right: Node | None = None


class BST:
    """Binary Search Tree implementation."""

    def __init__(self) -> None:
        self.root: Node | None = None

    def insert(self, value: int) -> None:
        if self.root is None:
            self.root = Node(value)
        else:
            self._insert(self.root, value)

    def _insert(self, node: Node, value: int) -> None:
        if value < node.value:
            if node.left is None:
                node.left = Node(value)
            else:
                self._insert(node.left, value)
        elif value > node.value:
            if node.right is None:
                node.right = Node(value)
            else:
                self._insert(node.right, value)

    def search(self, value: int) -> bool:
        return self._search(self.root, value)

    def _search(self, node: Node | None, value: int) -> bool:
        if node is None:
            return False
        if value == node.value:
            return True
        if value < node.value:
            return self._search(node.left, value)
        return self._search(node.right, value)

    def inorder(self) -> list[int]:
        result: list[int] = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node: Node | None, result: list[int]) -> None:
        if node is None:
            return
        self._inorder(node.left, result)
        result.append(node.value)
        self._inorder(node.right, result)


def classify_number(n: int) -> str:
    """Classify a number with multiple branches."""
    if n < 0:
        category = "negative"
    elif n == 0:
        category = "zero"
    elif n < 10:
        category = "small"
    elif n < 100:
        category = "medium"
    elif n < 1000:
        category = "large"
    else:
        category = "huge"

    if n % 2 == 0:  # noqa: SIM108
        parity = "even"
    else:
        parity = "odd"

    if n != 0 and n % 3 == 0:  # noqa: SIM108
        divisible = " (div by 3)"
    else:
        divisible = ""

    return f"{category} {parity}{divisible}"
