from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

class AuthTests(TestCase):
    def test_creacion_usuario(self):
        user = User.objects.create_user(
            username="usuario@test.com",
            email="usuario@test.com",
            password="12345678"
        )

        self.assertEqual(user.username, "usuario@test.com")
        self.assertTrue(user.check_password("12345678"))

    def test_password_incorrecto(self):
        user = User.objects.create_user(
            username="usuario@test.com",
            password="12345678"
        )

        self.assertFalse(user.check_password("mala-clave"))