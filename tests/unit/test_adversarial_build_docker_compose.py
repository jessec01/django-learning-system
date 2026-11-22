import json
import re
import subprocess
import unittest
from pathlib import Path


class TestAdversarialBuildDockerCompose(unittest.TestCase):
    COMPOSE_FILE = Path("docker-compose.yml")
    WEAK_PASSWORDS = {
        "1234",
        "123456",
        "admin",
        "password",
        "password_seguro",
        "postgres",
        "root",
        "secret",
    }
    SENSITIVE_KEYS = (
        "PASSWORD",
        "SECRET",
        "TOKEN",
        "API_KEY",
        "PRIVATE_KEY",
    )

    def _load_compose_config(self) -> dict:
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"docker compose config falló.\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}",
        )
        return json.loads(result.stdout)

    def test_compose_has_web_and_db_services(self):
        """
        Premisa (Arquitectura mínima):
        El compose debe ser válido y definir al menos los servicios 'web' y 'db'.
        """
        config = self._load_compose_config()
        services = config.get("services", {})
        self.assertIn("web", services, "Falta el servicio 'web' en docker-compose.yml.")
        self.assertIn("db", services, "Falta el servicio 'db' en docker-compose.yml.")

    def test_no_hardcoded_or_weak_db_credentials(self):
        """
        Premisa Adversarial (Robo de Credenciales):
        Un atacante que lea docker-compose.yml (o el repo) no debe encontrar
        contraseñas ni secretos en texto plano. Deben inyectarse vía env_file,
        secrets o interpolación obligatoria (${VAR:?error}).
        """
        raw_text = self.COMPOSE_FILE.read_text(encoding="utf-8")
        for line_no, line in enumerate(raw_text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for key in self.SENSITIVE_KEYS:
                if key in stripped.upper() and (":" in stripped or "=" in stripped):
                    has_interpolation = bool(re.search(r"\$\{[A-Z0-9_]+", stripped))
                    self.assertTrue(
                        has_interpolation,
                        msg=(
                            f"Posible secreto hardcodeado en línea {line_no}: '{stripped}'. "
                            "Usa env_file, Docker secrets o ${VAR:?msg}."
                        ),
                    )

        config = self._load_compose_config()
        services = config.get("services", {})
        self.assertIn(
            "db", services, "Falta el servicio 'db' para validar credenciales."
        )

        db_env = services["db"].get("environment", {})
        for env_name, env_val in db_env.items():
            if any(k in env_name.upper() for k in self.SENSITIVE_KEYS):
                val_str = str(env_val or "").strip().lower()
                self.assertNotIn(
                    val_str,
                    self.WEAK_PASSWORDS,
                    msg=f"Contraseña débil detectada en '{env_name}'.",
                )

    def test_network_isolation_no_internet_egress_and_db_not_exposed(self):
        """
        Premisa Adversarial (Movimiento Lateral y Salida a Internet):
        1. 'db' nunca debe exponer puertos al host (ej. 5432:5432).
        2. Debe existir al menos una red marcada como 'internal: true' para
           bloquear el tráfico saliente a internet desde la capa privada/DB.
        """
        config = self._load_compose_config()
        services = config.get("services", {})
        networks = config.get("networks", {})

        self.assertIn("db", services, "Falta el servicio 'db'.")
        db_ports = services["db"].get("ports", [])
        self.assertEqual(
            len(db_ports),
            0,
            msg=f"VULNERABILIDAD: 'db' expone puertos al host: {db_ports}",
        )

        internal_nets = {
            name
            for name, net_cfg in networks.items()
            if net_cfg.get("internal") is True
        }
        self.assertTrue(
            len(internal_nets) > 0,
            msg="No hay ninguna red con 'internal: true' para aislar la salida a internet.",
        )

        db_nets = set(services["db"].get("networks", {}).keys())
        self.assertTrue(
            db_nets and db_nets.issubset(internal_nets),
            msg=f"'db' solo debe conectarse a redes internal ({internal_nets}). Actual: {db_nets}",
        )

        self.assertIn("web", services, "Falta el servicio 'web'.")
        web_nets = set(services["web"].get("networks", {}).keys())
        self.assertTrue(
            web_nets and web_nets.issubset(internal_nets),
            msg=(
                f"HUECO DE RED: 'web' tiene acceso a redes no-internal con salida a internet. "
                f"Redes de 'web': {web_nets} | Redes internal: {internal_nets}"
            ),
        )

    def test_least_privilege_and_no_docker_socket_escape(self):
        """
        Premisa Adversarial (Escalación de Privilegios y Escape de Contenedor):
        1. Ningún servicio debe montar /var/run/docker.sock.
        2. 'web' debe correr con read_only, cap_drop: [ALL] y no-new-privileges:true.
        """
        config = self._load_compose_config()
        services = config.get("services", {})
        self.assertIn("web", services, "Falta el servicio 'web'.")

        for svc_name, svc_cfg in services.items():
            for vol in svc_cfg.get("volumes", []):
                source = vol.get("source", "") if isinstance(vol, dict) else str(vol)
                self.assertNotIn(
                    "docker.sock",
                    source,
                    msg=f"CRÍTICO: '{svc_name}' monta docker.sock (permite escape a root del host).",
                )

        web = services["web"]
        self.assertTrue(
            web.get("read_only") is True,
            msg="'web' debe tener 'read_only: true'.",
        )
        cap_drop = [c.upper() for c in web.get("cap_drop", [])]
        self.assertIn(
            "ALL",
            cap_drop,
            msg="'web' debe incluir 'cap_drop: [ALL]'.",
        )
        sec_opt = web.get("security_opt", [])
        self.assertIn(
            "no-new-privileges:true",
            sec_opt,
            msg="'web' debe incluir 'security_opt: [no-new-privileges:true]'.",
        )

    def test_optimization_healthcheck_depends_on_and_pinned_images(self):
        """
        Premisa Adversarial (Ralentización, Race Conditions y Deriva):
        1. 'db' debe definir un healthcheck real.
        2. 'web' debe esperar con 'depends_on: {db: {condition: service_healthy}}'.
        3. Ningún servicio externo debe usar el tag ':latest' sin fijar versión.
        """
        config = self._load_compose_config()
        services = config.get("services", {})
        self.assertIn("web", services, "Falta el servicio 'web'.")
        self.assertIn("db", services, "Falta el servicio 'db'.")

        self.assertIn(
            "healthcheck",
            services["db"],
            msg="'db' debe tener 'healthcheck' para evitar que 'web' falle al arrancar.",
        )

        depends_on = services["web"].get("depends_on", {})
        db_dep = depends_on.get("db", {})
        condition = db_dep.get("condition") if isinstance(db_dep, dict) else None
        self.assertEqual(
            condition,
            "service_healthy",
            msg="'web' debe usar depends_on -> db -> condition: service_healthy.",
        )

        for svc_name, svc_cfg in services.items():
            image = svc_cfg.get("image", "")
            if image:
                self.assertFalse(
                    image.endswith(":latest") or ":" not in image,
                    msg=f"'{svc_name}' usa tag inestable '{image}'. Fija una versión específica.",
                )

    def test_resource_limits_prevent_dos_and_slowdown(self):
        """
        Premisa Adversarial (DoS / Agotamiento de Recursos):
        Todo servicio debe limitar memoria (mem_limit o deploy.resources.limits.memory)
        y procesos (pids_limit) para no ralentizar o tumbar el host.
        """
        config = self._load_compose_config()
        services = config.get("services", {})
        self.assertGreaterEqual(len(services), 2, "Se esperan al menos 'web' y 'db'.")

        for svc_name, svc_cfg in services.items():
            deploy_limits = (
                svc_cfg.get("deploy", {}).get("resources", {}).get("limits", {})
            )
            has_memory = bool(svc_cfg.get("mem_limit") or deploy_limits.get("memory"))
            self.assertTrue(
                has_memory,
                msg=f"'{svc_name}' no tiene límite de memoria (mem_limit o deploy.resources.limits.memory).",
            )
            has_pids = bool(svc_cfg.get("pids_limit") or deploy_limits.get("pids"))
            self.assertTrue(
                has_pids,
                msg=f"'{svc_name}' no tiene límite de procesos (pids_limit).",
            )
