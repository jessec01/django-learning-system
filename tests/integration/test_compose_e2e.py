import unittest
import subprocess
import os
class TestComposeE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass
    def test_postgres_in_docker(self):
        result=subprocess.run(["docker","compose","config"],
        capture_output=True,
        text=True,
        check=True)
        self.assertIn("learning-postgres",result.stdout)
    def test_database_is_ready(self):
        test_env = os.environ.copy()
        test_env.update({
            "POSTGRES_DB": "test_learning_db",
            "POSTGRES_USER": "test_admin",
            "POSTGRES_PASSWORD": "test_ephemeral_password_123",
            "SECRET_KEY": "django-insecure-test-only-key",
            "DEBUG": "False",
            "ALLOWED_HOSTS": "127.0.0.1,localhost",
        })
        try:
            result = subprocess.run(
            ["docker","compose","up","-d","--build",
            "--wait","--wait-timeout=10"],env=test_env,
            capture_output=True,
            text=True,  
            check=False
            )
            diagnotics=subprocess.run(["docker","compose","logs","--tail=10"],capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, f"Docker compose failed: {result.stderr}\n{diagnotics.stdout}")
        finally:
            subprocess.run(
            ["docker","compose","down",
            "--timeout=20","-v"],
            capture_output=True,
            text=True,
            check=False
            )
            
       