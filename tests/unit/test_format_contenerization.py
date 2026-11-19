import unittest
import subprocess
import shutil
from pathlib import Path


class TestContenerization(unittest.TestCase):
    def test_open_dockerfile(self):
        self.assertTrue(Path("Dockerfile").is_file(), "el archivo no existe en la raiz")

    def test_is_exist_hadolint(self):
        self.assertTrue(shutil.which("hadolint"), "Hadolint no esta instalado")

    def test_validation_format(self):
        is_empty = Path("Dockerfile").read_text(encoding="utf-8").strip() != ""
        result = subprocess.run(
            ["hadolint", "Dockerfile"], capture_output=True, text=True, check=False
        )
        print(is_empty)
        self.assertEqual(is_empty, True, "El archivo esta vacio")
        self.assertEqual(
            result.returncode,
            0,
            f"El formato del Dockerfile es incorrecto:{result.stdout}",
        )

    def test_validation_format_critical(self):
        dockerfile = Path("Dockerfile")
        data = set()
        with dockerfile.open(mode="r", encoding="utf-8") as archive:
            for line in archive:
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    # ignora lineas vacias o comentada
                    continue
                instruction = clean_line.split()[0].upper()
                data.add(instruction)
        key_dockerfile_from = "FROM"
        key_dockerfile_workdir = "WORKDIR"
        key_dockerfile_copy = "COPY"
        key_dockerfile_run = "RUN"
        key_dockerfile_cmd = "CMD"
        key_dockerfile_user = "USER"
        self.assertIn(key_dockerfile_from, data, "No se encontro el comando FROM")
        self.assertIn(key_dockerfile_workdir, data, "No se encontro el comando WORKDIR")
        self.assertIn(key_dockerfile_run, data, "No se encontro el comando RUN")
        self.assertIn(key_dockerfile_copy, data, "No se encontro el comando COPY")
        self.assertIn(key_dockerfile_cmd, data, "No se encontro el comando CMD")
        self.assertIn(key_dockerfile_user, data, "No se encontro el comando USER")
