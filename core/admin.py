from django.contrib import admin
from .models import Empresa

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("id","nombre","nit","owner","created_at")
    search_fields = ("nombre","nit")
