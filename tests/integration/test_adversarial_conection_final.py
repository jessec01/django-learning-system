import json
import os
import socket
import subprocess
import time
import unittest
import urllib.error
from urllib import request


class TestAdversarialConnectionFinal(unittest.TestCase):
    COMPOSE_FILE = "docker-compose.yml"

    @classmethod
    def setUpClass(cls):
        test_env = os.environ.copy()
        test_env.update(
            {
                "POSTGRES_DB": "test_learning_db",
                "POSTGRES_USER": "test_admin",
                "POSTGRES_PASSWORD": "test_ephemeral_password_123",
                "SECRET_KEY": "django-insecure-test-only-key",
                "DEBUG": "False",
                "ALLOWED_HOSTS": "127.0.0.1,localhost",
            }
        )
        cls.test_env = test_env

        subprocess.run(
            ["docker", "compose", "-f", cls.COMPOSE_FILE, "down", "-v"],
            env=test_env,
            capture_output=True,
            text=True,
            check=False,
        )
        up = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                cls.COMPOSE_FILE,
                "up",
                "-d",
                "--build",
                "--wait",
                "--wait-timeout=30",
            ],
            env=test_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if up.returncode != 0:
            logs = subprocess.run(
                ["docker", "compose", "-f", cls.COMPOSE_FILE, "logs"],
                capture_output=True,
                text=True,
                check=False,
            )
            cls.tearDownClass()
            raise RuntimeError(
                f"Falló docker compose up.\nSTDERR:\n{up.stderr}\nLOGS:\n{logs.stdout}{logs.stderr}"
            )
        cls._wait_for_proxy(timeout=20.0, interval=1.0)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            ["docker", "compose", "-f", cls.COMPOSE_FILE, "down", "--timeout=20", "-v"],
            env=getattr(cls, "test_env", None),
            capture_output=True,
            text=True,
            check=False,
        )

    @classmethod
    def _wait_for_proxy(cls, timeout: float = 20.0, interval: float = 1.0):
        deadline = time.monotonic() + timeout
        last_err = None
        while time.monotonic() < deadline:
            try:
                with request.urlopen("http://127.0.0.1:8080/", timeout=2) as resp:
                    if resp.status < 500:
                        return
            except urllib.error.HTTPError as err:
                if err.code < 500:
                    return
                last_err = err
            except Exception as err:
                last_err = err
            time.sleep(interval)
        raise TimeoutError(f"Proxy no respondió a tiempo: {last_err}")

    def _exec_in(self, service: str, cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "compose", "-f", self.COMPOSE_FILE, "exec", "-T", service, *cmd],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_basic_non_root_and_only_proxy_port_exposed(self):
        """
        [Básico]
        1. 'web' y 'proxy' deben correr con UID != 0 (no root).
        2. El puerto 8080 (proxy) debe responder; el 8000 (gunicorn) NO debe
           estar expuesto directamente en localhost.
        """
        for svc in ("web", "proxy"):
            res = self._exec_in(svc, ["id", "-u"])
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertNotEqual(
                res.stdout.strip(),
                "0",
                msg=f"CRÍTICO: '{svc}' está corriendo como root (UID 0).",
            )

        with self.assertRaises(OSError, msg="El puerto 8000 de gunicorn no debe exponerse al host."):
            sock = socket.create_connection(("127.0.0.1", 8000), timeout=2)
            sock.close()

    def test_intermediate_egress_blocked_on_web_and_db(self):
        """
        [Intermedio 1 — Aislamiento de Salida a Internet]
        Verifica en runtime que ni 'web' ni 'db' puedan:
        - Abrir TCP directo a IP pública (1.1.1.1:80)
        - Resolver DNS externo (google.com)
        - Descargar por HTTPS (https://www.google.com)
        """
        probe_py = "\n".join(
            [
                "import socket, urllib.request",
                "try:",
                "    s = socket.create_connection(('1.1.1.1', 80), timeout=2)",
                "    s.close()",
                "    print('VULN_TCP')",
                "except OSError:",
                "    print('BLOCKED_TCP')",
                "try:",
                "    socket.getaddrinfo('google.com', 443)",
                "    print('VULN_DNS')",
                "except OSError:",
                "    print('BLOCKED_DNS')",
                "try:",
                "    urllib.request.urlopen('https://www.google.com', timeout=2)",
                "    print('VULN_HTTP')",
                "except Exception:",
                "    print('BLOCKED_HTTP')",
            ]
        )
        res = self._exec_in("web", ["python", "-c", probe_py])
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("BLOCKED_TCP", res.stdout)
        self.assertIn("BLOCKED_DNS", res.stdout)
        self.assertIn("BLOCKED_HTTP", res.stdout)
        self.assertNotIn("VULN_", res.stdout)

        db_probe = (
            "timeout 2 bash -c 'cat < /dev/null > /dev/tcp/1.1.1.1/80' 2>/dev/null "
            "&& echo 'VULN_DB_EGRESS' || echo 'BLOCKED_DB_EGRESS'"
        )
        db_res = self._exec_in("db", ["sh", "-c", db_probe])
        self.assertEqual(db_res.returncode, 0, msg=db_res.stderr)
        self.assertIn("BLOCKED_DB_EGRESS", db_res.stdout)
        self.assertNotIn("VULN_DB_EGRESS", db_res.stdout)

    def test_intermediate_readonly_rootfs_and_zero_capabilities(self):
        """
        [Intermedio 2 — Inmutabilidad y Capabilities del Kernel]
        Valida en /proc/self/status dentro de 'web' que:
        - CapEff sea 0000000000000000 (0 capabilities efectivas)
        - NoNewPrivs sea 1
        - El sistema de archivos raíz sea solo lectura (/app y /etc bloqueados)
        """
        check_py = "\n".join(
            [
                "from pathlib import Path",
                "status = Path('/proc/self/status').read_text()",
                "for line in status.splitlines():",
                "    if line.startswith(('CapEff:', 'NoNewPrivs:')):",
                "        print(line)",
                "for target in ('/app/pwned.txt', '/etc/pwned.txt'):",
                "    try:",
                "        Path(target).write_text('x')",
                "        print('VULN_WRITE', target)",
                "    except OSError:",
                "        print('BLOCKED_WRITE', target)",
            ]
        )
        res = self._exec_in("web", ["python", "-c", check_py])
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertRegex(res.stdout, r"CapEff:\s+0000000000000000")
        self.assertRegex(res.stdout, r"NoNewPrivs:\s+1")
        self.assertIn("BLOCKED_WRITE /app/pwned.txt", res.stdout)
        self.assertIn("BLOCKED_WRITE /etc/pwned.txt", res.stdout)
        self.assertNotIn("VULN_WRITE", res.stdout)

    def test_intermediate_db_not_exposed_and_cloud_metadata_ssrf_blocked(self):
        """
        [Intermedio 3 — Exposición de DB y SSRF a Metadata Cloud]
        1. El puerto 5432 de Postgres no debe estar abierto en localhost del host.
        2. Desde 'web' no debe poder alcanzarse el endpoint SSRF clásico
           de metadatos cloud (169.254.169.254:80).
        """
        port_check = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{json .NetworkSettings.Ports}}",
                "learning-postgres",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(port_check.returncode, 0, msg=port_check.stderr)
        ports_map = json.loads(port_check.stdout)
        self.assertFalse(
            any(ports_map.values()),
            msg=f"Postgres no debe exponer puertos al host: {ports_map}",
        )

        ssrf_py = "\n".join(
            [
                "import socket",
                "try:",
                "    s = socket.create_connection(('169.254.169.254', 80), timeout=2)",
                "    s.close()",
                "    print('VULN_SSRF_METADATA')",
                "except OSError:",
                "    print('BLOCKED_SSRF_METADATA')",
            ]
        )
        res = self._exec_in("web", ["python", "-c", ssrf_py])
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("BLOCKED_SSRF_METADATA", res.stdout)
        self.assertNotIn("VULN_SSRF_METADATA", res.stdout)

    def test_high_elo_privilege_escalation_and_lateral_pivot_chain(self):
        """
        [Alto Elo — Cadena de Ataque (Kill-Chain): Escalación + Pivoteo + Persistencia]
        Simula un atacante con ejecución de código (RCE) dentro de 'web' intentando:
        1. Escalación de privilegios: os.setuid(0), su/sudo, binarios SUID en PATH.
        2. Escape de contenedor: acceso a /var/run/docker.sock o /dev/mem.
        3. Pivoteo lateral por el proxy: usar a Nginx ('proxy:8080') como
           open-proxy para saltar hacia internet (http://example.com).
        4. Persistencia: escribir en /app/.venv o /etc/cron.d.
        Todo debe fallar de forma cerrada (fail-closed).
        """
        kill_chain_py = "\n".join(
            [
                "import os, urllib.request, urllib.error",
                "from pathlib import Path",
                "",
                "# 1. Escalacion a UID 0",
                "try:",
                "    os.setuid(0)",
                "    print('VULN_SETUID_0')",
                "except PermissionError:",
                "    print('BLOCKED_SETUID_0')",
                "",
                "# 2. Escape via docker.sock o /dev/mem",
                "for dev in ('/var/run/docker.sock', '/dev/mem', '/dev/kmem'):",
                "    if os.path.exists(dev):",
                "        print('VULN_ESCAPE_DEVICE', dev)",
                "    else:",
                "        print('BLOCKED_DEVICE', dev)",
                "",
                "# 3. Pivoteo lateral: usar proxy:8080 como forward proxy hacia afuera",
                "try:",
                "    proxy_handler = urllib.request.ProxyHandler({'http': 'http://proxy:8080'})",
                "    opener = urllib.request.build_opener(proxy_handler)",
                "    resp = opener.open('http://example.com/', timeout=3)",
                "    body = resp.read(200).decode(errors='ignore')",
                "    if 'Example Domain' in body:",
                "        print('VULN_OPEN_PROXY_PIVOT')",
                "    else:",
                "        print('BLOCKED_PROXY_PIVOT_LOCAL_ONLY')",
                "except urllib.error.HTTPError as e:",
                "    print('BLOCKED_PROXY_PIVOT_HTTP', e.code)",
                "except Exception:",
                "    print('BLOCKED_PROXY_PIVOT')",
                "",
                "# 4. Persistencia en .venv o cron",
                "for target in ('/app/.venv/bin/backdoor.py', '/etc/cron.d/backdoor'):",
                "    try:",
                "        Path(target).write_text('evil')",
                "        print('VULN_PERSISTENCE', target)",
                "    except OSError:",
                "        print('BLOCKED_PERSISTENCE', target)",
            ]
        )
        res = self._exec_in("web", ["python", "-c", kill_chain_py])
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("BLOCKED_SETUID_0", res.stdout)
        self.assertIn("BLOCKED_DEVICE /var/run/docker.sock", res.stdout)
        self.assertIn("BLOCKED_PERSISTENCE /app/.venv/bin/backdoor.py", res.stdout)
        self.assertNotIn("VULN_", res.stdout)
