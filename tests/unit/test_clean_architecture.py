import ast
import unittest
from pathlib import Path


class TestCleanArchitecture(unittest.TestCase):
    BACKEND_ROOT = Path("src/backend")

    REQUIRED_STRUCTURE = {
        "domain": ("value_objects", "entities", "errors", "repositories"),
        "application": ("dtos", "interfaces", "use_cases"),
        "infrastructure": ("database", "repositories_impl", "external_services", "server"),
        "presentation": ("middlewares", "controllers", "routes"),
    }

    FRAMEWORK_IMPORTS = {
        "django",
        "rest_framework",
        "psycopg2",
        "argon2",
        "jwt",
        "requests",
        "httpx",
        "celery",
    }

    def _iter_python_files(self, layer: str) -> list[Path]:
        layer_dir = self.BACKEND_ROOT / layer
        if not layer_dir.exists():
            return []
        return sorted(layer_dir.rglob("*.py"))

    def _extract_imports(self, file_path: Path) -> list[tuple[int, str]]:
        tree = ast.parse(
            file_path.read_text(encoding="utf-8"),
            filename=str(file_path),
        )
        imports: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level > 0:
                    # Resuelve imports relativos respecto al paquete del archivo
                    rel_parts = file_path.relative_to(self.BACKEND_ROOT).parts[:-1]
                    up = max(0, len(rel_parts) - (node.level - 1))
                    base = ".".join(("backend", *rel_parts[:up]))
                    full = f"{base}.{module}" if module else base
                    imports.append((node.lineno, full))
                elif module:
                    imports.append((node.lineno, module))
        return imports

    def _assert_forbidden_imports(
        self,
        layer: str,
        forbidden_prefixes: set[str],
        rule_name: str,
    ) -> None:
        violations: list[str] = []
        for py_file in self._iter_python_files(layer):
            for lineno, mod in self._extract_imports(py_file):
                parts = mod.split(".")
                # Normaliza 'src.backend.<capa>' o 'backend.<capa>' o '<capa>'
                candidates = {parts[0]}
                if len(parts) >= 2 and parts[0] == "backend":
                    candidates.add(parts[1])
                if len(parts) >= 3 and parts[0] == "src" and parts[1] == "backend":
                    candidates.add(parts[2])

                for prefix in forbidden_prefixes:
                    if mod == prefix or mod.startswith(f"{prefix}.") or prefix in candidates:
                        violations.append(f"{py_file}:{lineno} -> '{mod}'")
                        break

        self.assertEqual(
            violations,
            [],
            msg=f"Violación de Clean Architecture ({rule_name}):\n" + "\n".join(violations),
        )

    def test_required_clean_layers_exist(self):
        """Deben existir las 4 capas principales en src/backend/."""
        for layer in self.REQUIRED_STRUCTURE:
            self.assertTrue(
                (self.BACKEND_ROOT / layer).is_dir(),
                msg=f"Falta la capa '{layer}' en {self.BACKEND_ROOT}.",
            )

    def test_required_subfolders_per_layer(self):
        """Cada capa debe contener sus subcarpetas obligatorias (como paquete Python)."""
        missing: list[str] = []
        for layer, subfolders in self.REQUIRED_STRUCTURE.items():
            for sub in subfolders:
                sub_dir = self.BACKEND_ROOT / layer / sub
                if not sub_dir.is_dir():
                    missing.append(f"Falta carpeta: {sub_dir}")
                elif not (sub_dir / "__init__.py").is_file():
                    missing.append(f"Falta __init__.py en: {sub_dir}")

        self.assertEqual(
            missing,
            [],
            msg="Estructura Clean Architecture incompleta:\n" + "\n".join(missing),
        )

    def test_domain_is_pure_python_and_isolated(self):
        """
        1. src/backend/domain/: Python puro.
        Cero imports de Django/frameworks y cero imports de application,
        infrastructure o presentation.
        """
        forbidden = self.FRAMEWORK_IMPORTS | {
            "application",
            "infrastructure",
            "presentation",
        }
        self._assert_forbidden_imports(
            layer="domain",
            forbidden_prefixes=forbidden,
            rule_name="domain debe ser Python puro y sin dependencias externas",
        )

    def test_application_has_no_framework_or_outer_layers(self):
        """
        2. src/backend/application/: Orquestación sin HTTP ni ORM.
        Solo puede depender de domain (nunca de Django/DRF, infrastructure ni presentation).
        """
        forbidden = self.FRAMEWORK_IMPORTS | {
            "infrastructure",
            "presentation",
        }
        self._assert_forbidden_imports(
            layer="application",
            forbidden_prefixes=forbidden,
            rule_name="application no puede importar frameworks ni capas externas",
        )

    def test_infrastructure_does_not_depend_on_presentation(self):
        """
        3. src/backend/infrastructure/: ORM, DB y servicios externos.
        Nunca debe importar presentation.
        """
        self._assert_forbidden_imports(
            layer="infrastructure",
            forbidden_prefixes={"presentation"},
            rule_name="infrastructure no puede depender de presentation",
        )

    def test_presentation_does_not_access_orm_or_db_directly(self):
        """
        4. src/backend/presentation/: Adaptadores HTTP / DRF.
        No debe importar modelos ORM ni acceso directo a DB (django.db, psycopg2,
        infrastructure.database, infrastructure.repositories_impl).
        """
        forbidden = {
            "django.db",
            "psycopg2",
            "infrastructure.database",
            "backend.infrastructure.database",
            "infrastructure.repositories_impl",
            "backend.infrastructure.repositories_impl",
        }
        self._assert_forbidden_imports(
            layer="presentation",
            forbidden_prefixes=forbidden,
            rule_name="presentation no puede acceder directo al ORM ni a DB",
        )
