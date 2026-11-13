# tests/unit/testsloaddependencies
from os import name
import unittest
import tomllib


class TestLoadDependencies(unittest.TestCase):
    def test_load_build_system(self):
        with open("./pyproject.toml", "rb") as toml:
            data_tomlib: dict = tomllib.load(toml)
        main_dependencies = "build-system"
        self.assertIn(main_dependencies, data_tomlib)

    def test_load_build_system_backend(self):
        with open("./pyproject.toml", "rb") as toml:
            data_tomlib: dict = tomllib.load(toml)
        require_dependencies = "requires"
        backend_dependencies = "build-backend"
        self.assertIn(require_dependencies, data_tomlib["build-system"])
        self.assertIn(backend_dependencies, data_tomlib["build-system"])

    def test_load_project(self):
        with open("./pyproject.toml", "rb") as toml:
            data_tomlib: dict = tomllib.load(toml)
        project_dependencies = "project"
        self.assertIn(project_dependencies, data_tomlib)

    def test_load_meta_data(self):
        with open("./pyproject.toml", "rb") as toml:
            data_tomlib: dict = tomllib.load(toml)
        name_project = "name"
        version_project = "version"
        dependencies = "dependencies"

        self.assertIn(name_project, data_tomlib["project"])
        self.assertIn(version_project, data_tomlib["project"])
        self.assertIn(dependencies, data_tomlib["project"])
