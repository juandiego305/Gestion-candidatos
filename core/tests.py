from io import BytesIO
from PIL import Image
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import Empresa

User = get_user_model()


def create_test_image(color="blue", size=(200, 200)):
    """
    Crea una imagen temporal en memoria para subir como logo.
    """
    file = BytesIO()
    image = Image.new("RGB", size=size, color=color)
    image.save(file, "PNG")
    file.name = "test_logo.png"
    file.seek(0)
    return file


class EmpresaAPITests(APITestCase):
    def setUp(self):
        # Crear usuario de prueba
        self.user = User.objects.create_user(username="usuario1", password="12345678")
        self.client = APIClient()

        # Obtener token JWT
        response = self.client.post(
            "/api/token/",
            {"username": "usuario1", "password": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, "No se generó el token correctamente")

        self.access_token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

    def test_crear_empresa_con_logo(self):
        """
        ✅ Crea una empresa nueva con un logo.
        """
        data = {
            "nombre": "Mi Empresa",
            "nit": "123456789",
            "direccion": "Calle Falsa 123",
            "logo": create_test_image(),
        }
        response = self.client.post("/api/empresas/", data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("logo_url", response.data)
        self.assertTrue(response.data["logo_url"].startswith("http"))

    def test_actualizar_empresa_y_logo(self):
        """
        ✅ Actualiza datos de la empresa y reemplaza el logo.
        """
        empresa = Empresa.objects.create(
            nombre="Empresa X", nit="999", direccion="Dir 1", owner=self.user
        )

        data = {
            "nombre": "Empresa Actualizada",
            "logo": create_test_image(color="red"),
        }
        url = f"/api/empresas/{empresa.id}/"
        response = self.client.patch(url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nombre"], "Empresa Actualizada")
        self.assertIn("logo_url", response.data)

    def test_no_permite_acceso_a_otro_usuario(self):
        """
        🚫 Un usuario no puede ver empresas de otro.
        """
        other_user = User.objects.create_user(username="otro", password="abcd1234")
        Empresa.objects.create(
            nombre="Privada", nit="777", direccion="Calle oculta", owner=other_user
        )

        response = self.client.get("/api/empresas/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_eliminar_empresa_y_logo(self):
        """
        ✅ Elimina empresa y borra logo del storage (simulado).
        """
        empresa = Empresa.objects.create(
            nombre="Para eliminar",
            nit="888",
            direccion="Dirección",
            owner=self.user,
            logo_url="https://dummy.supabase.co/storage/v1/object/public/logos/1/logo.png",
        )

        url = f"/api/empresas/{empresa.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Empresa.objects.filter(id=empresa.id).exists())
