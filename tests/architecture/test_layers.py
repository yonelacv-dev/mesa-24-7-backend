"""Protege el hexágono: cada capa solo puede depender de lo que tiene permitido.

Estructura: app/<módulo>/{domain,application,infrastructure,presentation}, más app/shared.
`app/<módulo>/dependencies.py`, `app/main.py`, `app/config.py` y `app/database.py` son la raíz de
composición y quedan fuera de las reglas como origen.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
LAYERS = ("domain", "application", "infrastructure", "presentation")
ALL_LAYERS = set(LAYERS)

# capa -> qué capas puede importar del mismo módulo / de shared / de otros módulos
ALLOWED = {
    "domain": {"same": {"domain"}, "shared": {"domain"}, "other": set()},
    "application": {
        "same": {"domain", "application"},
        "shared": {"domain", "application"},
        "other": {"domain", "application"},
    },
    "infrastructure": {
        "same": {"domain", "application", "infrastructure"},
        "shared": ALL_LAYERS - {"presentation"},
        "other": {"domain", "application"},
    },
    "presentation": {
        "same": {"domain", "application", "presentation"},
        "shared": {"domain", "application", "presentation"},
        "other": {"domain", "application"},
    },
}

# Contratos de datos de otro módulo que presentation sí puede reutilizar (el anfitrión ve el local dentro de la cola).
SHARED_PRESENTATION_CONTRACTS = {"schemas", "mappers"}

# módulos raíz que solo puede importar la infraestructura
INFRA_ONLY_ROOT = {"app.config", "app.database"}

FORBIDDEN_PACKAGES = {
    "domain": ("fastapi", "starlette", "sqlalchemy", "alembic", "pydantic", "aiomysql"),
    "application": ("fastapi", "starlette", "sqlalchemy", "alembic", "pydantic", "aiomysql"),
    "infrastructure": ("fastapi", "starlette"),
    "presentation": ("sqlalchemy", "alembic", "aiomysql"),
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def source_files():
    for path in sorted(APP.rglob("*.py")):
        parts = path.relative_to(APP).parts
        if len(parts) >= 3 and parts[1] in LAYERS:
            yield path, parts[0], parts[1]


def violations_for(path: Path, module: str, layer: str) -> list[str]:
    rules = ALLOWED[layer]
    found = []
    for target in imported_modules(path):
        parts = target.split(".")
        if parts[0] != "app":
            if target.startswith(FORBIDDEN_PACKAGES[layer]):
                found.append(f"{layer} no debe importar {target}")
            continue
        if target in INFRA_ONLY_ROOT:
            if layer != "infrastructure":
                found.append(f"solo infrastructure puede importar {target}")
            continue
        if len(parts) < 3 or parts[2] not in LAYERS:
            # p. ej. app.<módulo>.dependencies: solo presentation puede usarlo
            if not (layer == "presentation" and parts[-1] == "dependencies"):
                found.append(f"{layer} no debe importar {target}")
            continue
        target_module, target_layer = parts[1], parts[2]
        scope = "same" if target_module == module else "shared" if target_module == "shared" else "other"
        reuses_contract = (
            layer == "presentation"
            and target_layer == "presentation"
            and scope == "other"
            and parts[-1] in SHARED_PRESENTATION_CONTRACTS
        )
        if target_layer not in rules[scope] and not reuses_contract:
            found.append(f"{module}.{layer} no debe importar {target_module}.{target_layer} ({target})")
    return found


@pytest.mark.parametrize(("path", "module", "layer"), list(source_files()), ids=lambda v: getattr(v, "name", v))
def test_imports_respect_hexagonal_layers(path, module, layer):
    violations = violations_for(path, module, layer)
    assert not violations, f"{path.relative_to(APP)}:\n" + "\n".join(violations)


def test_the_rules_actually_detect_violations(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from app.waitlist.infrastructure.repo import X\nimport sqlalchemy\n")
    assert violations_for(bad, "waitlist", "domain")
    assert violations_for(bad, "waitlist", "application")


def test_presentation_cannot_reach_infrastructure_config_or_the_orm(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from app.waitlist.infrastructure.repositories import SQLAlchemyQueueEntryRepository\n"
        "from app.config import Settings\n"
        "from sqlalchemy.ext.asyncio import AsyncSession\n"
    )
    found = violations_for(bad, "waitlist", "presentation")
    assert len(found) == 3


def test_a_module_cannot_use_the_infrastructure_of_another_module(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from app.venues.infrastructure.repository import SQLAlchemyVenueRepository\n")
    assert violations_for(bad, "waitlist", "application")
    assert violations_for(bad, "waitlist", "infrastructure")


def test_presentation_may_reuse_the_schemas_of_another_module_but_not_its_routers(tmp_path):
    ok = tmp_path / "ok.py"
    ok.write_text("from app.venues.presentation.schemas import HostVenueOut\n")
    bad = tmp_path / "bad.py"
    bad.write_text("from app.venues.presentation.host_router import router\n")
    assert violations_for(ok, "waitlist", "presentation") == []
    assert violations_for(bad, "waitlist", "presentation")
