import ast
import re
from pathlib import Path
from typing import Iterable, Iterator, Optional
import unittest


APP_ROOT = Path(__file__).resolve().parents[1] / "app"

SQL_OUTSIDE_DB_TRANSITIONAL_EXCEPTIONS = {
    "app/observability/audit.py",
    "app/xlsx_import.py",
}

SQL_PATTERNS = (
    re.compile(r"^\s*SELECT\b.+\bFROM\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*INSERT\s+INTO\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*UPDATE\b.+\bSET\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*DELETE\s+FROM\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*CREATE\s+(?:TABLE|INDEX|VIEW|TRIGGER)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*ALTER\s+TABLE\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*DROP\s+(?:TABLE|INDEX|VIEW|TRIGGER)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*PRAGMA\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*WITH\b.+\bSELECT\b", re.IGNORECASE | re.DOTALL),
)


def app_python_files(*parts: str) -> Iterator[Path]:
    root = APP_ROOT.joinpath(*parts)
    yield from sorted(root.rglob("*.py"))


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP_ROOT.parent).with_suffix("").parts)


def parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.Module) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def resolve_imported_modules(path: Path, tree: ast.Module) -> Iterator[str]:
    current_module = module_name(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = current_module.split(".")[:-1]
                base_parts = package_parts[: max(0, len(package_parts) - (node.level - 1))]
                base = ".".join(base_parts)
                yield ".".join(part for part in (base, node.module or "") if part)
            elif node.module:
                yield node.module


def normalized_imports(tree: ast.Module) -> set[str]:
    normalized: set[str] = set()
    for name in imported_modules(tree):
        normalized.add(name)
        if name.split(".", 1)[0] in {
            "auth",
            "db",
            "domain",
            "integrations",
            "observability",
            "routes",
            "services",
        }:
            normalized.add(f"app.{name}")
    return normalized


def all_app_modules() -> dict[str, Path]:
    return {module_name(path): path for path in app_python_files()}


def normalize_app_import(raw_name: str, known_modules: set[str]) -> Optional[str]:
    name = raw_name
    first = name.split(".", 1)[0]
    if first in {
        "auth",
        "db",
        "domain",
        "integrations",
        "observability",
        "routes",
        "services",
    }:
        name = f"app.{name}"
    for candidate in sorted(known_modules, key=len, reverse=True):
        if name == candidate or name.startswith(f"{candidate}."):
            return candidate
    return None


def app_dependency_graph(paths: Iterable[Path]) -> dict[str, set[str]]:
    known_modules = set(all_app_modules())
    selected_modules = {module_name(path) for path in paths}
    graph = {module: set() for module in selected_modules}
    for path in paths:
        source = module_name(path)
        for raw_name in resolve_imported_modules(path, parsed(path)):
            target = normalize_app_import(raw_name, known_modules)
            if target and target in selected_modules and target != source:
                graph[source].add(target)
    return graph


def dependency_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in indexes:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[neighbor])

        if lowlinks[node] == indexes[node]:
            component: list[str] = []
            while True:
                neighbor = stack.pop()
                on_stack.remove(neighbor)
                component.append(neighbor)
                if neighbor == node:
                    break
            if len(component) > 1:
                cycles.append(sorted(component))

    for node in graph:
        if node not in indexes:
            visit(node)
    return sorted(cycles)


def is_docstring_node(node: ast.AST, parent: Optional[ast.AST]) -> bool:
    return (
        isinstance(parent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and bool(getattr(parent, "body", None))
        and parent.body[0] is node
    )


def string_value(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = [
            part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "{}"
            for part in node.values
        ]
        return "".join(parts)
    return None


def sql_like_strings(path: Path) -> list[tuple[int, str]]:
    tree = parsed(path)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if is_docstring_node(node, parents.get(node)):
            continue
        value = string_value(node)
        if value is None:
            continue
        compact = " ".join(value.strip().split())
        if any(pattern.search(compact) for pattern in SQL_PATTERNS):
            hits.append((getattr(node, "lineno", 0), compact[:120]))
    return hits


def call_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def import_violations(paths: Iterable[Path], forbidden_prefixes: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        imports = normalized_imports(parsed(path))
        bad = sorted(
            name
            for name in imports
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
        )
        if bad:
            violations.append(f"{path.relative_to(APP_ROOT.parent)}: {', '.join(bad)}")
    return violations


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_routes_do_not_import_sqlite_or_database_internals(self) -> None:
        violations = import_violations(app_python_files("routes"), ("sqlite3", "app.db"))
        self.assertEqual([], violations)

    def test_routes_do_not_instantiate_repositories_directly(self) -> None:
        violations: list[str] = []
        for path in app_python_files("routes"):
            tree = parsed(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = call_name(node.func)
                if name and name.endswith("Repository"):
                    violations.append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}: {name}")
        self.assertEqual([], violations)

    def test_routes_do_not_access_repository_container_properties_directly(self) -> None:
        violations: list[str] = []
        for path in app_python_files("routes"):
            tree = parsed(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                if node.attr == "repository" or node.attr.endswith("_repository"):
                    violations.append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}: {node.attr}")
        self.assertEqual([], violations)

    def test_domain_has_no_outer_layer_dependencies(self) -> None:
        violations = import_violations(
            app_python_files("domain"),
            ("sqlite3", "app.db", "app.integrations", "app.routes", "app.services"),
        )
        self.assertEqual([], violations)

    def test_repositories_do_not_import_routes(self) -> None:
        violations = import_violations(app_python_files("db", "repositories"), ("app.routes",))
        self.assertEqual([], violations)

    def test_services_do_not_import_http_handler_types(self) -> None:
        violations = import_violations(app_python_files("services"), ("app.server", "http.server"))
        self.assertEqual([], violations)

        handler_references: list[str] = []
        for path in app_python_files("services"):
            for node in ast.walk(parsed(path)):
                if isinstance(node, ast.Name) and node.id in {"Handler", "BaseHTTPRequestHandler"}:
                    handler_references.append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}: {node.id}")
        self.assertEqual([], handler_references)

    def test_integrations_do_not_mutate_league_state(self) -> None:
        violations = import_violations(
            app_python_files("integrations"),
            ("sqlite3", "app.db", "app.routes", "app.services"),
        )
        execute_calls: list[str] = []
        for path in app_python_files("integrations"):
            tree = parsed(path)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"execute", "executemany", "executescript", "commit", "rollback"}
                ):
                    execute_calls.append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}: {node.func.attr}")
        self.assertEqual([], violations)
        self.assertEqual([], execute_calls)

    def test_sql_strings_do_not_appear_outside_database_layer(self) -> None:
        violations: list[str] = []
        for path in app_python_files():
            relative = path.relative_to(APP_ROOT.parent).as_posix()
            if relative.startswith("app/db/") or relative in SQL_OUTSIDE_DB_TRANSITIONAL_EXCEPTIONS:
                continue
            for line, snippet in sql_like_strings(path):
                violations.append(f"{relative}:{line}: {snippet}")
        self.assertEqual([], violations)

    def test_sql_outside_db_exceptions_are_explicit_and_transitional(self) -> None:
        existing = {
            path.relative_to(APP_ROOT.parent).as_posix()
            for path in app_python_files()
            if not path.relative_to(APP_ROOT.parent).as_posix().startswith("app/db/")
            and sql_like_strings(path)
        }
        self.assertEqual(SQL_OUTSIDE_DB_TRANSITIONAL_EXCEPTIONS, existing)

    def test_services_and_repositories_do_not_form_import_cycles(self) -> None:
        paths = [
            *app_python_files("services"),
            *app_python_files("db", "repositories"),
        ]
        graph = app_dependency_graph(paths)
        self.assertEqual([], dependency_cycles(graph))

    def test_services_keep_direct_persistence_dependency_fanout_small(self) -> None:
        service_paths = list(app_python_files("services"))
        repository_paths_iter = list(app_python_files("db", "repositories"))
        graph = app_dependency_graph([*service_paths, *repository_paths_iter])
        service_modules = {module_name(path) for path in service_paths}
        repository_paths = {module_name(path) for path in app_python_files("db", "repositories")}
        violations: list[str] = []
        for service, deps in sorted(graph.items()):
            if service not in service_modules:
                continue
            repository_deps = sorted(dep for dep in deps if dep in repository_paths)
            if len(repository_deps) > 3:
                violations.append(
                    f"{service}: {len(repository_deps)} repositories: {', '.join(repository_deps)}"
                )
        self.assertEqual([], violations)

    def test_route_functions_do_not_coordinate_too_many_application_services(self) -> None:
        violations: list[str] = []
        for path in app_python_files("routes"):
            tree = parsed(path)
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                dependencies = {
                    child.attr
                    for child in ast.walk(node)
                    if isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Attribute)
                    and child.value.attr == "app"
                    and isinstance(child.value.value, ast.Name)
                    and child.value.value.id == "handler"
                }
                if len(dependencies) > 4:
                    violations.append(
                        f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}: "
                        f"{node.name} uses {len(dependencies)} app dependencies: {sorted(dependencies)}"
                    )
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
