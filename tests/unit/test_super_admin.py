import unittest


def register_superadmin(data: dict):
    return False


class TestRegisterSuperAdmin(unittest.TestCase):
    def test_create_superadmin_success(self):
        data: dict = {
            "name": "Gregory",
            "second_name": "Perozo",
            "phone": "04246466445",
            "email": "jegro17@gmail.com",
            "password": "123",
        }
        self.assertTrue(False, register_superadmin(data))


if __name__ == "__main__":
    unittest.main()
