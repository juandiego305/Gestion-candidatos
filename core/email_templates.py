class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


EMAIL_TEMPLATES = {
    "welcome": {
        "subject": "Bienvenido a Talento Hub",
        "html": """
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <img src="{logo_url}" alt="Talento Hub" style="max-height: 52px; width: auto; margin-bottom: 12px;" />
                        <h2 style="color: #007bff;">Bienvenido a Talento Hub</h2>
                    </div>

                    <div style="padding: 20px; background-color: #f9f9f9; border-radius: 5px;">
                        <p>Hola <strong>{user_name}</strong>,</p>

                        <p>Gracias por registrarte en <strong>Talento Hub</strong>. Estamos emocionados de tenerte como parte de nuestra comunidad.</p>

                        <p>Con tu cuenta puedes:</p>
                        <ul style="color: #555;">
                            <li>Explorar oportunidades de empleo</li>
                            <li>Enviar postulaciones a tus empleos favoritos</li>
                            <li>Actualizar tu perfil profesional</li>
                            <li>Estar conectado con empresas lideres</li>
                        </ul>

                        <p style="margin-top: 30px;">
                            <a href="{login_url}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">Inicia sesion aqui</a>
                        </p>
                    </div>

                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; font-size: 12px; color: #999;">
                        <p>Si tienes alguna pregunta, no dudes en contactarnos.</p>
                        <p>Talento Hub</p>
                    </div>
                </div>
            </body>
        </html>
        """,
        "text": "Hola {user_name}, gracias por registrarte en Talento Hub. Inicia sesion en {login_url}",
    },
    "password_reset": {
        "subject": "Restablecer tu contrasena",
        "html": """
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <img src="{logo_url}" alt="Talento Hub" style="max-height: 52px; width: auto; margin-bottom: 12px;" />
                        <h2 style="color: #007bff;">Restablecer contrasena</h2>
                    </div>

                    <p>Hola <strong>{username}</strong>,</p>
                    <p>Recibimos una solicitud para restablecer tu contrasena.</p>

                    <p style="margin: 24px 0; text-align: center;">
                        <a href="{reset_link}" style="display: inline-block; padding: 12px 20px; background-color: #007bff; color: #fff; text-decoration: none; border-radius: 6px;">Restablecer contrasena</a>
                    </p>

                    <p>Si el boton no funciona, copia y pega este enlace en tu navegador:</p>
                    <p><a href="{reset_link}">{reset_link}</a></p>

                    <p>Si tu no solicitaste esto, ignora este correo.</p>

                    <div style="margin-top: 24px; font-size: 12px; color: #888;">
                        <p>Equipo Talento Hub</p>
                    </div>
                </div>
            </body>
        </html>
        """,
        "text": """
Hola {username},

Recibimos una solicitud para restablecer tu contrasena.

Haz clic en el enlace para continuar:
{reset_link}

Si tu no solicitaste esto, simplemente ignora este mensaje.

Saludos,
Equipo Talento Hub
""",
    },
    "account_locked": {
        "subject": "Cuenta bloqueada temporalmente",
        "html": """
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <img src="{logo_url}" alt="Talento Hub" style="max-height: 52px; width: auto; margin-bottom: 12px;" />
                        <h2 style="color: #c0392b;">Cuenta bloqueada temporalmente</h2>
                    </div>

                    <p>Hola,</p>
                    <p>Tu cuenta ha sido bloqueada temporalmente debido a multiples intentos fallidos de acceso.</p>
                    <p>El bloqueo se levantara automaticamente en <strong>{minutes_remaining} minutos</strong>.</p>
                    <p>Si no fuiste tu, por favor escribe a <strong>{support_email}</strong>.</p>

                    <div style="margin-top: 24px; font-size: 12px; color: #888;">
                        <p>Equipo Talento Hub</p>
                    </div>
                </div>
            </body>
        </html>
        """,
        "text": """
Hola,

Tu cuenta ha sido bloqueada temporalmente debido a multiples intentos fallidos de acceso.

El bloqueo se levantara automaticamente en {minutes_remaining} minutos.

Si no fuiste tu, por favor contacta al administrador.

Saludos,
Sistema de Gestion de Candidatos
""",
    },
}


def render_email_template(template_key, context=None):
    template = EMAIL_TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"Template '{template_key}' no existe")

    values = SafeDict(context or {})
    subject = template["subject"].format_map(values)
    text = template.get("text", "").format_map(values)
    html = template.get("html")
    if html:
        html = html.format_map(values)
    return subject, text, html