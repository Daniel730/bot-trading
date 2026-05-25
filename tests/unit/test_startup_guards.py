import ast
from pathlib import Path


def test_startup_guards_construct_monitor_through_isolated_factory():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    violations = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_Call(self, node):
            if getattr(node.func, "id", None) == "ArbitrageMonitor":
                current = self.stack[-1] if self.stack else None
                if current != "_make_startup_monitor":
                    violations.append(node.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)

    assert violations == []
