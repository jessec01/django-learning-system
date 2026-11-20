import subprocess
import unittest


class TestDockerAdversarialSecurity(unittest.TestCase):
    IMAGE_TAG = "django-learning-system:test"

    def test_container_runs_as_non_root_and_isolated_network(self):
        """
        Test Adversarial (Blue Team):
        1. Verifica que el UID efectivo dentro del contenedor NO sea 0 (root).
        2. Verifica que el directorio /app sea de solo lectura para el usuario.
        3. Ejecuta todo con --network none para garantizar cero dependencias externas.
        """
        # Comando adversarial: intenta obtener su UID e intenta escribir en /app
        adversarial_cmd = "id -u && touch /app/hacked.txt 2>/dev/null && echo 'VULNERABLE' || echo 'READ_ONLY_OK'"

        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                self.IMAGE_TAG,
                "sh",
                "-c",
                adversarial_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"El contenedor falló al arrancar aislado: {result.stderr}",
        )

        lines = result.stdout.strip().splitlines()
        uid = lines[0].strip()
        write_check = lines[1].strip()

        # 1. Fail-closed: nunca debe ser UID 0
        self.assertNotEqual(
            uid, "0", "CRÍTICO: El contenedor está corriendo como root (UID 0)."
        )

        # 2. Fail-closed: el usuario de la app no debe ser dueño de /app para escribir en él
        self.assertEqual(
            write_check,
            "READ_ONLY_OK",
            "VULNERABILIDAD: El usuario no-root tiene permisos de escritura sobre /app.",
        )
