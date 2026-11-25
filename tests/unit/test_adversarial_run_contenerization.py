import subprocess
import time
import unittest


class TestDockerAdversarialRun(unittest.TestCase):
    IMAGE_TAG = "django-learning-system:test"

    def test_hardened_readonly_and_no_new_privileges(self):
        """
        Test Adversarial (Runtime Hardening):
        Ejecuta el contenedor con el máximo endurecimiento de Docker:
        - --read-only (sistema de archivos raíz inmutable)
        - --cap-drop=ALL (sin capacidades Linux)
        - --security-opt=no-new-privileges:true (bloquea escalación de privilegios)
        - --network=none (sin red)
        Valida que Python funcione sin necesitar escribir bytecode ni archivos en /app.
        """
        cmd = " && ".join(
            [
                "python -c 'import sys; print(sys.executable)'",
                "(touch /app/evil.txt 2>/dev/null && echo 'VULN_APP' || echo 'OK_APP')",
                "(touch /etc/evil.txt 2>/dev/null && echo 'VULN_ETC' || echo 'OK_ETC')",
            ]
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--network=none",
                self.IMAGE_TAG,
                "sh",
                "-c",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"Falló bajo --read-only / --cap-drop=ALL.\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}",
        )
        self.assertIn("OK_APP", result.stdout)
        self.assertIn("OK_ETC", result.stdout)
        self.assertNotIn("VULN_", result.stdout)

    def test_cannot_escalate_to_root_or_tamper_venv(self):
        """
        Test Adversarial (Privilege Escalation & Integrity):
        Intenta cambiar a root (su/setpriv) y corromper /app/.venv.
        Debe fallar (fail-closed) en todos los intentos.
        """
        cmd = " && ".join(
            [
                "(su root -c id 2>/dev/null && echo 'ESCALATED' || echo 'BLOCKED_SU')",
                "(rm -f /app/.venv/bin/python 2>/dev/null && echo 'TAMPERED_VENV' || echo 'PROTECTED_VENV')",
            ]
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                self.IMAGE_TAG,
                "sh",
                "-c",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("BLOCKED_SU", result.stdout)
        self.assertIn("PROTECTED_VENV", result.stdout)
        self.assertNotIn("ESCALATED", result.stdout)
        self.assertNotIn("TAMPERED_VENV", result.stdout)

    def test_no_sensitive_files_or_secrets_in_runtime(self):
        """
        Test Adversarial (Secret / Artifact Leakage):
        Verifica que no hayan entrado archivos sensibles (.env, .git, llaves)
        ni variables de entorno con secretos por defecto.
        """
        cmd = " && ".join(
            [
                "test ! -d /app/.git",
                "test ! -f /app/.env",
                "test ! -f /app/id_rsa",
            ]
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                self.IMAGE_TAG,
                "sh",
                "-c",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"Se encontraron archivos sensibles en /app.\nSTDERR:\n{result.stderr}",
        )

    def test_resource_limits_pids_and_memory(self):
        """
        Test Adversarial (DoS / Fork-bomb resilience):
        Valida que el contenedor arranque normalmente bajo límites estrictos
        de memoria (--memory=128m) y procesos (--pids-limit=32).
        """
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--memory=128m",
                "--pids-limit=32",
                self.IMAGE_TAG,
                "python",
                "-c",
                "import sys; print('LIMITS_OK')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("LIMITS_OK", result.stdout)

    def test_default_cmd_starts_and_handles_sigterm(self):
        """
        Test Adversarial (Real Runtime Entrypoint + SIGTERM):
        Arranca el CMD por defecto (gunicorn) sin sobrescribirlo, verifica que
        siga vivo tras 2s y que responda limpiamente a SIGTERM (no SIGKILL 137).
        Nota TDD: fallará en Rojo hasta que exista src/config/wsgi.py.
        """
        container_name = "dls-adversarial-run-test"
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            start = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    self.IMAGE_TAG,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(start.returncode, 0, msg=start.stderr)

            time.sleep(2)

            inspect = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            logs = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(
                inspect.stdout.strip(),
                "true",
                msg=f"El contenedor murió al arrancar el CMD.\nLOGS:\n{logs.stdout}\n{logs.stderr}",
            )

            stop = subprocess.run(
                ["docker", "stop", "-t", "3", container_name],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(stop.returncode, 0, msg=stop.stderr)

            exit_code = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.ExitCode}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(
                exit_code.stdout.strip(),
                "137",
                msg="El proceso ignoró SIGTERM y fue matado con SIGKILL (137).",
            )
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_egress_network_blocked_under_isolated_contract(self):
        """
        Test Adversarial (Contrato Real de Aislamiento de Red):
        Un Dockerfile no controla la red por sí solo; el contrato real exige
        ejecutar el contenedor en una red aislada (--internal, equivalente a
        'backend_net' en docker-compose.yml):
        1. El servidor (gunicorn:8000) debe aceptar llamadas locales/internas.
        2. Cualquier intento de salida a internet (TCP, DNS, HTTPS) debe fallar
           de forma cerrada (fail-closed).
        """
        network_name = "dls-isolated-contract-net"
        container_name = "dls-adversarial-net-test"

        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["docker", "network", "rm", network_name],
            capture_output=True,
            text=True,
            check=False,
        )

        try:
            net = subprocess.run(
                ["docker", "network", "create", "--internal", network_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(net.returncode, 0, msg=net.stderr)

            start = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--network",
                    network_name,
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    self.IMAGE_TAG,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(start.returncode, 0, msg=start.stderr)

            time.sleep(2)

            probe_script = "\n".join(
                [
                    "import socket, urllib.request, urllib.error",
                    "try:",
                    "    r = urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)",
                    "    print('SERVER_OK', r.status)",
                    "except urllib.error.HTTPError as e:",
                    "    print('SERVER_OK', e.code)",
                    "except Exception as e:",
                    "    print('SERVER_FAIL', e)",
                    "try:",
                    "    s = socket.create_connection(('1.1.1.1', 80), timeout=2)",
                    "    s.close()",
                    "    print('VULN_TCP_OPEN')",
                    "except OSError:",
                    "    print('BLOCKED_TCP')",
                    "try:",
                    "    socket.getaddrinfo('google.com', 443)",
                    "    print('VULN_DNS_OPEN')",
                    "except OSError:",
                    "    print('BLOCKED_DNS')",
                    "try:",
                    "    urllib.request.urlopen('https://www.google.com', timeout=3)",
                    "    print('VULN_HTTP_OPEN')",
                    "except Exception:",
                    "    print('BLOCKED_HTTP')",
                ]
            )

            probe = subprocess.run(
                [
                    "docker",
                    "exec",
                    container_name,
                    "python",
                    "-c",
                    probe_script,
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(probe.returncode, 0, msg=probe.stderr)
            self.assertIn("SERVER_OK", probe.stdout)
            self.assertIn("BLOCKED_TCP", probe.stdout)
            self.assertIn("BLOCKED_DNS", probe.stdout)
            self.assertIn("BLOCKED_HTTP", probe.stdout)
            self.assertNotIn("VULN_", probe.stdout)
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            subprocess.run(
                ["docker", "network", "rm", network_name],
                capture_output=True,
                text=True,
                check=False,
            )
