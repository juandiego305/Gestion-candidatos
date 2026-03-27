from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Empresa

User = get_user_model()

class EmpresaModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dueno",
            password="12345678"
        )

    def test_creacion_empresa(self):
        empresa = Empresa.objects.create(
            nombre="Talento Hub",
            nit="900123456",
            direccion="Calle 1",
            owner=self.user
        )

        self.assertEqual(empresa.nombre, "Talento Hub")
        self.assertEqual(empresa.owner, self.user)

    def test_string_representation_empresa(self):
        empresa = Empresa.objects.create(
            nombre="Empresa Demo",
            nit="123",
            direccion="Dir",
            owner=self.user
        )

        self.assertIn("Empresa Demo", str(empresa))