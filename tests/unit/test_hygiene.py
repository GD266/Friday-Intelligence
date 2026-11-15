"""Hygiene tests: ensure no vacuous tests and no debug artifacts in repo."""

import ast
from pathlib import Path

import pytest


class _Visitor(ast.NodeVisitor):
    """AST visitor to check test functions for assertions."""

    def __init__(self, filename: str):
        self.filename = filename
        self.vacuous_asserts = []
        self.empty_tests = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith("test_"):
            self.generic_visit(node)
            return

        # Check for literal assert True/False in function body
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assert):
                if isinstance(stmt.test, ast.Constant) and stmt.test.value in (
                    True,
                    False,
                ):
                    self.vacuous_asserts.append(
                        f"{self.filename}:{stmt.lineno}: assert {stmt.test.value}"
                    )

        # Check if function has ANY statements (not completely empty)
        if len(node.body) == 0:
            self.empty_tests.append(f"{self.filename}:{node.lineno} ({node.name})")

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test_"):
            self.generic_visit(node)
            return

        # Check for literal assert True/False in function body
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assert):
                if isinstance(stmt.test, ast.Constant) and stmt.test.value in (
                    True,
                    False,
                ):
                    self.vacuous_asserts.append(
                        f"{self.filename}:{stmt.lineno}: assert {stmt.test.value}"
                    )

        # Check if function has ANY statements (not completely empty)
        if len(node.body) == 0:
            self.empty_tests.append(f"{self.filename}:{node.lineno} ({node.name})")

        self.generic_visit(node)

    def _has_assertion_patterns(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> bool:
        """Check if function contains assertion-like patterns."""
        for stmt in ast.walk(node):
            # Check for assert statements
            if isinstance(stmt, ast.Assert):
                return True

            # Check for pytest.raises context manager
            if isinstance(stmt, ast.With):
                for item in stmt.items:
                    if (
                        isinstance(item.context_expr, ast.Call)
                        and isinstance(item.context_expr.func, ast.Attribute)
                        and item.context_expr.func.attr == "raises"
                        and isinstance(item.context_expr.func.value, ast.Name)
                        and item.context_expr.func.value.id == "pytest"
                    ):
                        return True

            # Check for function calls that are assertion-like
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                # Check for .assert_called, call_count, synthesize_calls access
                if isinstance(call.func, ast.Attribute):
                    if call.func.attr in (
                        "assert_called",
                        "assert_called_once",
                        "assert_called_with",
                        "assert_awaited",
                        "call_count",
                        "synthesize_calls",
                    ):
                        return True

            # Check for await on future-like objects
            if isinstance(stmt, ast.Await):
                if isinstance(stmt.value, ast.Name) and "fut" in stmt.value.id:
                    return True

        return False


def test_no_vacuous_tests() -> None:
    """Scan all test files for vacuous `assert True/False` or empty tests."""
    test_dir = Path("tests")
    assert test_dir.exists()

    all_vacuous = []
    all_empty = []

    for test_file in test_dir.rglob("test_*.py"):
        # Skip this hygiene test file itself
        if test_file.name == "test_hygiene.py":
            continue

        content = test_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content, filename=str(test_file))
        except SyntaxError:
            continue

        visitor = _Visitor(str(test_file))
        visitor.visit(tree)

        if visitor.vacuous_asserts:
            all_vacuous.extend(visitor.vacuous_asserts)
        if visitor.empty_tests:
            all_empty.extend(visitor.empty_tests)

    if all_vacuous:
        msg = "Vacuous assertions found (assert True/False):\n" + "\n".join(all_vacuous)
        pytest.fail(msg)

    if all_empty:
        msg = "Completely empty test functions found:\n" + "\n".join(all_empty)
        pytest.fail(msg)


def test_no_debug_artifacts_in_repo_root() -> None:
    """Ensure repo root contains no debug/test artifacts."""
    root = Path(".")
    forbidden_patterns = [
        "debug_*.py",
        "test_*.py",
        "*.mp3",
        "*.wav",
        "*_REPORT.md",
        "STEP0_AUDIT.md",
    ]

    found = []
    for pattern in forbidden_patterns:
        matches = list(root.glob(pattern))
        if matches:
            found.extend(str(m) for m in matches)

    if found:
        msg = "Debug/test artifacts found in repo root:\n" + "\n".join(found)
        pytest.fail(msg)
