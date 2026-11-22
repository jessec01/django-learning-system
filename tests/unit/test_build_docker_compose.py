import unittest
import subprocess


class TestBuildDockerCompose(unittest.TestCase):
    def test_build_docker_compose(self):

        result = subprocess.run(
            ["docker", "compose", "build"], check=False, capture_output=True, text=True
        )
        msg = f"\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
        self.assertEqual(result.returncode, 0, msg=msg)
