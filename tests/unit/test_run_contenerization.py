import subprocess
import unittest


class TestRunContenerization(unittest.TestCase):
    def setUp(self):
        self.image = "django-learning-system:test"

    def test_run_contenerization(self):
        result = subprocess.run(
            ["docker", "run", "--rm", self.image, "python", "manage.py", "check"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_run_only_read(self):
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--cap-drop=ALL",
                "--network",
                "none",
                self.image,
                "python",
                "-c",
                "import django; print('RUNTIME_INMUTABLE_OK')",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
