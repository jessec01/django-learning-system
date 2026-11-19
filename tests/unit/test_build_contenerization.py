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
