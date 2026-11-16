import unittest 
import subprocess
import shutil
from pathlib import Path

class TestContainerization(unittest.TestCase):
    
    def test_open_dockerfile(self):
        self.assertTrue(Path("Dockerfile").is_file(), "el archivo no existe en la raiz")
    def test_is_exist_hadolint(self):
        self.assertTrue(shutil.which("hadolint"),"Hadolint no esta instalado")
    
    def test_validation_format(self):
        is_empty=Path("Dockerfile").read_text(encoding="utf-8").strip() != ""
        result=subprocess.run(["hadolint","Dockerfile"],
        capture_output=True,
        text=True,
        check=False)
        print(is_empty)
        self.assertEqual(is_empty,True,"El archivo esta vacio")
        self.assertEqual(result.returncode,0,"El formato del Dockerfile es incorrecto")
    def test_validation_format_critical(self):
        dockerfile=Path("Dockerfile")
        with dockerfile.open(mode="r",encoding="utf-8") as archive:
            data=None
            for line in archive:
                data=line
            key_dockerfile_from="FROM"
            key_dockerfile_workdir="WORKDIR"
            self.assertIn(data,key_dockerfile_from)
            self.assertIn(data,key_dockerfile_workdir)            