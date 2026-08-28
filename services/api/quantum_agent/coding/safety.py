"""Static safety validation for Coding-Agent-generated Python.

The validator runs BEFORE the sandbox.  It enforces an import allowlist and a
call allowlist using ``ast`` so the subprocess never even starts for code that
tries to open a socket, spawn a process, read the host filesystem, or import a
project module.  The sandbox adds runtime defense-in-depth (rlimits, timeout,
restricted env, bounded output); the AST layer is the first gate.

This is intentionally conservative.  The Coding Agent is told the allowlist in
its system prompt so it generates compliant code.  Anything outside the
allowlist is rejected with a structured violation the repair loop can feed
back to the agent.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


class CodeSafetyError(ValueError):
    """The generated program falls outside the safe scientific subset."""


# Modules the Coding Agent may import.  Everything here is standard scientific
# Python.  ``os`` and ``sys`` are deliberately excluded; the agent does not
# need them for a physics calculation, and excluding them removes a large
# filesystem/process attack surface.
_ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "math",
        "cmath",
        "json",
        "re",
        "itertools",
        "collections",
        "typing",
        "functools",
        "statistics",
        "decimal",
        "fractions",
        "numbers",
        "time",
        "random",
        "numpy",
        "scipy",
        "sympy",
        "matplotlib",
        "qutip",
    }
)

# Submodules under an allowed top-level package that are NOT safe.  These reach
# native-library loading (``ctypes``/``cffi``) even though the top-level package
# (``numpy``/``scipy``) is allowlisted, which would let generated code escape the
# process sandbox by calling ``system``/``execve`` from a hostile shared library.
# ``matplotlib.pyplot`` is allowed because the sandbox forces ``MPLBACKEND=Agg``
# (no GUI window) and the Coding Agent needs it to save figures via ``savefig``.
_BLOCKED_SUBMODULES: dict[str, frozenset[str]] = {
    "numpy": frozenset(
        {
            "numpy.ctypeslib",
            "numpy.ctypeslib._ctypeslib",
            "numpy._core._dtype_ctypes",
            "numpy.core._dtype_ctypes",
        }
    ),
    "scipy": frozenset(
        {
            "scipy._lib._ccallback",
        }
    ),
}

# Callable names that are banned everywhere, even if imported.  ``open`` is
# banned because file I/O is not needed for an in-memory scientific
# computation.  ``eval``/``exec``/``compile`` are banned to prevent nested
# code generation.  Dunder attribute access is banned to prevent escaping the
# sandbox via ``__builtins__`` etc.
_BANNED_CALLS: frozenset[str] = frozenset(
    {
        "open",
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "__import__",
    }
)

_MAX_AST_NODES = 4_000
_MAX_CODE_BYTES = 20_000
_MAX_IMPORT_COUNT = 24


@dataclass(frozen=True, slots=True)
class CodeSafetyReport:
    ok: bool
    violations: tuple[str, ...]


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def _is_allowed_import(module_name: str) -> bool:
    root = _module_root(module_name)
    if root not in _ALLOWED_IMPORTS:
        return False
    blocked = _BLOCKED_SUBMODULES.get(root, frozenset())
    if module_name in blocked:
        return False
    return True


def _is_blocked_submodule(module_name: str) -> bool:
    """Return True if ``module_name`` is a blocked submodule under an allowed root.

    Used by ``visit_ImportFrom`` to catch ``from X import Y`` where the composed
    dotted path ``X.Y`` is a blocked submodule (e.g. ``scipy._lib._ccallback``).
    """

    root = _module_root(module_name)
    blocked = _BLOCKED_SUBMODULES.get(root, frozenset())
    return module_name in blocked


class _SafetyVisitor(ast.NodeVisitor):
    """Walks the full program AST and accumulates violations."""

    def __init__(self) -> None:
        self._violations: list[str] = []
        self._node_count = 0
        self._import_count = 0

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(self._violations)

    def _count(self) -> None:
        self._node_count += 1
        if self._node_count > _MAX_AST_NODES:
            self._violations.append(
                f"program exceeds the structural budget ({_MAX_AST_NODES} AST nodes)"
            )

    def _banned_call(self, name: str) -> None:
        if name in _BANNED_CALLS:
            self._violations.append(f"call to banned builtin '{name}'")

    def _banned_attribute(self, name: str) -> None:
        if name.startswith("__") and name.endswith("__"):
            self._violations.append(f"access to dunder attribute '{name}'")

    def visit_Import(self, node: ast.Import) -> None:
        self._count()
        self._import_count += len(node.names)
        if self._import_count > _MAX_IMPORT_COUNT:
            self._violations.append(
                f"program imports more than {_MAX_IMPORT_COUNT} modules"
            )
        for alias in node.names:
            if not _is_allowed_import(alias.name):
                self._violations.append(f"import of non-allowlisted module '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._count()
        module = node.module or ""
        self._import_count += 1
        if self._import_count > _MAX_IMPORT_COUNT:
            self._violations.append(
                f"program imports more than {_MAX_IMPORT_COUNT} modules"
            )
        if not module or not _is_allowed_import(module):
            self._violations.append(f"from-import of non-allowlisted module '{module}'")
        for alias in node.names:
            if alias.name.startswith("__") or alias.name.endswith("__"):
                self._violations.append(f"from-import of forbidden dunder '{alias.name}'")
            # ``from X import Y`` where Y is itself a blocked submodule (e.g.
            # ``from scipy._lib import _ccallback``) must be rejected: the
            # ``module`` check above only inspects ``X``.  Compose the full
            # dotted path and re-check so a blocked deep submodule cannot be
            # pulled in by its leaf name.
            if module and _is_blocked_submodule(f"{module}.{alias.name}"):
                self._violations.append(
                    f"from-import of blocked submodule '{module}.{alias.name}'"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._count()
        func = node.func
        if isinstance(func, ast.Name):
            self._banned_call(func.id)
        elif isinstance(func, ast.Attribute):
            self._banned_attribute(func.attr)
            if func.attr in _BANNED_CALLS:
                self._violations.append(f"call to banned method '{func.attr}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._count()
        self._banned_attribute(node.attr)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self._count()
        if node.id in _BANNED_CALLS:
            self._violations.append(f"reference to banned builtin '{node.id}'")
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        self._count()
        super().generic_visit(node)


def validate_code_safety(code: str) -> CodeSafetyReport:
    """Return a safety report for ``code`` without executing it.

    Never raises for unsafe code; returns ``ok=False`` with structured
    violations so the repair loop can feed them back to the Coding Agent.
    Raises :class:`CodeSafetyError` only for unparseable input, since that
    indicates a Coding Agent contract violation rather than a safety issue.
    """

    if len(code.encode("utf-8")) > _MAX_CODE_BYTES:
        return CodeSafetyReport(
            ok=False,
            violations=(f"program exceeds the {_MAX_CODE_BYTES}-byte size guard",),
        )
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeSafetyError(f"generated code is not valid Python: {exc.msg}") from exc
    visitor = _SafetyVisitor()
    visitor.visit(tree)
    if visitor.violations:
        return CodeSafetyReport(ok=False, violations=visitor.violations)
    return CodeSafetyReport(ok=True, violations=())


__all__ = [
    "CodeSafetyError",
    "CodeSafetyReport",
    "validate_code_safety",
]
