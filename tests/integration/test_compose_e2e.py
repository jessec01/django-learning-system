import unittest
import subprocess
import os
import urllib
import time
from urllib import request
class TestComposeE2E(unittest.TestCase):
    COMPOSE_FILE="docker-compose.yml"
    datalogs={}
    @classmethod
    def setUpClass(cls):
        """Levanta la infraestructura limpia y bloquea hasta que esté lista."""
        # 1. Asegurar estado limpio previo (por si una ejecución anterior abortó)
        test_env = os.environ.copy()
        test_env.update({
            "POSTGRES_DB": "test_learning_db",
            "POSTGRES_USER": "test_admin",
            "POSTGRES_PASSWORD": "test_ephemeral_password_123",
            "SECRET_KEY": "django-insecure-test-only-key",
            "DEBUG": "False",
            "ALLOWED_HOSTS": "127.0.0.1,localhost",
        })
        subprocess.run(
            ["docker", "compose", "-f", cls.COMPOSE_FILE, "down", "-v"],
            env=test_env,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["docker", "compose", "-f", cls.COMPOSE_FILE, "up", "-d", "--build"],
            env=test_env,
            check=True,
        )
        try:
            cls._wait_until_system_ready(timeout=30.0,interval=3.0)
           
        except Exception:
            logs=subprocess.run(
                ["docker", "compose", "-f", cls.COMPOSE_FILE, "logs"],
                capture_output=True,
                text=True
            )
            print(f"\n--- DOCKER COMPOSE LOGS ---\n{logs.stdout}\n{logs.stderr}")
            cls.tearDownClass()
            raise
        
        for service in ["db","web","proxy"]:
            res=subprocess.run(["docker", "compose", "-f", cls.COMPOSE_FILE, "logs", "--no-color", service],
            capture_output=True,
            text=True,
            check=True)
            cls.datalogs[service] = {
                "returncode": res.returncode,
                "output": res.stdout + res.stderr,
           }
    @classmethod
    def _wait_until_system_ready(cls, timeout: float = 30.0, interval: float = 2.0):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                with request.urlopen("http://127.0.0.1:8080/", timeout=2) as resp:
                    if resp.status < 500:
                        return
            except urllib.error.HTTPError as err:
                # 400/404 ya demuestra que Nginx y Django respondieron
                if err.code < 500:
                    return
                last_error = err
            except Exception as err:
                last_error = err
            time.sleep(interval)
        raise TimeoutError(f"Sistema no listo tras {timeout}s. Último error: {last_error}")
    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            ["docker", "compose", "-f", cls.COMPOSE_FILE, "down", "--timeout=20", "-v"],
            capture_output=True,
            text=True,
            check=False,
        )
    def test_startup_logs_are_clean_and_healthy(self):
        # 1. Verificar que la extracción de logs de cada servicio devolvió código 0
        for service, data in self.datalogs.items():
            self.assertEqual(0, data["returncode"], f"Fallo al leer logs de {service}")

        # 2. Buscar mensajes esperados de arranque exitoso (OK)
        self.assertIn("database system is ready to accept connections", self.datalogs["db"]["output"])
        self.assertIn("Listening at: http://0.0.0.0:8000", self.datalogs["web"]["output"])

        # 3. Asegurar ausencia de tracebacks o errores críticos
        self.assertNotIn("Traceback (most recent call last)", self.datalogs["web"]["output"])
        self.assertNotIn("FATAL:", self.datalogs["db"]["output"])
    def test_postgres_in_docker(self):
        result = subprocess.run(
            [                "docker", "compose", "-f", self.COMPOSE_FILE,
                "exec", "-T", "web",
                "python", "manage.py", "shell", "-c",
                (
                    "from django.db import connection; "
                    "assert 'postgresql' in connection.settings_dict['ENGINE']; "
                    "c = connection.cursor(); c.execute('SELECT 1'); print(c.fetchone())"
                ),],
            capture_output=True, text=True, check=False,
        )
        if result.returncode!=0:
            ps=subprocess.run(["docker", "compose", "-f", self.COMPOSE_FILE, "ps", "-a"],capture_output=True,text=True,check=True)
            print("\n--- DOCKER COMPOSE PS ---\n",ps.stdout)
            logs = subprocess.run(
                ["docker", "compose", "-f", self.COMPOSE_FILE, "logs", "--tail=30", "web"],
                capture_output=True, text=True, check=False,
            )
            self.fail(f"\nSTDERR:\n{result.stderr}\nPS:\n{ps.stdout}\nWEB LOGS:\n{logs.stdout}{logs.stderr}")
            self.assertIn("(1,)", result.stdout)
    def test_database_is_ready(self):
        result = subprocess.run(
            [
                "docker", "compose", "-f", self.COMPOSE_FILE,
                "exec", "-T", "db", "pg_isready", "-U", "test_admin", "-d", "test_learning_db",
            ],
            capture_output=True,
            text=True,
            check=False,
            )
        self.assertEqual(result.returncode, 0, msg=f"\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
        
       