from django.test import TestCase
from django.contrib.auth import get_user_model
from core.serializers import EmpresaSerializer

User = get_user_model()

class EmpresaSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="12345678"
        )

    def test_serializer_empresa_valido(self):
        data = {
            "nombre": "Empresa Test",
            "nit": "987654321",
            "direccion": "Carrera 10 # 20-30",
        }

        serializer = EmpresaSerializer(data=data, context={"request": None})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_serializer_empresa_sin_nombre_invalido(self):
        data = {
            "nombre": "",
            "nit": "987654321",
            "direccion": "Carrera 10 # 20-30",
        }

        serializer = EmpresaSerializer(data=data, context={"request": None})
        self.assertFalse(serializer.is_valid())
        self.assertIn("nombre", serializer.errors)