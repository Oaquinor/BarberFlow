"""Static guard against adding private API routes without authentication."""

import ast
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1] / "app" / "api" / "v1"
AUTH_GUARDS = {
    "_get_current_user",
    "get_current_user",
    "get_current_active_user",
    "get_current_owner",
    "get_current_barber",
    "CurrentUser",
    "OptionalUser",
}
PUBLIC_OR_CAPABILITY_ROUTES = (
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
    "/auth/password-reset/",
    "/saas/register",
    "/saas/registration-status",
    "/support/contact",
    "/public/",
)


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            continue
        if value.func.id != "APIRouter":
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        prefix = next((
            keyword.value.value
            for keyword in value.keywords
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant)
        ), "")
        for target in targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _is_public_or_capability_route(path: str) -> bool:
    return any(path == route or path.startswith(route) for route in PUBLIC_OR_CAPABILITY_ROUTES)


def test_private_api_routes_declare_an_authentication_guard():
    unguarded = []
    for file in API_ROOT.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        prefixes = _router_prefixes(tree)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_decorators = [
                decorator
                for decorator in node.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id in prefixes
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
            ]
            for decorator in route_decorators:
                route = next((
                    argument.value
                    for argument in decorator.args
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                ), "")
                path = prefixes[decorator.func.value.id] + route
                if _is_public_or_capability_route(path):
                    continue
                names = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
                if not names.intersection(AUTH_GUARDS):
                    unguarded.append(f"{file.relative_to(API_ROOT)}:{node.lineno} {path}")

    assert not unguarded, "Private API routes without an authentication guard:\n" + "\n".join(unguarded)
