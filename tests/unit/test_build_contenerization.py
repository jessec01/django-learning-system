import subprocess
import unittest


class TestBuildContenerization(unittest.TestCase):
    def test_build_contenirization(self):
        result = subprocess.run(
            ["docker", "build", "-t", "django-learning-system:test", "."],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            0,
            result.returncode,
            msg=f"\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}",
        )

    def test_validationoptimization(self):
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "0",
                "django-learning-system:test",
                "sh",
                "-c",
                "test ! -d /root/.cache/uv",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        msg = f"""Se encontró caché de uv (/root/.cache/uv) 
            dentro de la imagen.\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"""
        self.assertEqual(result.returncode, 0, msg=msg)

    def test_python_stdout_is_unbuffered(self):
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "django-learning-system:test",
                "python",
                "-c",
                "import os; print('LOG_INMEDIATO'); os._exit(1)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn("LOG_INMEDIATO\n", result.stdout, result.stderr)
