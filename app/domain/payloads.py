def build_payload_confirmacion(
    to_e164_digits: str,
    invitado_text: str,
    organizador: str,
    referencia_entrada: str,
    fecha_hora_str: str,
    image_url: str,
    template_name: str = "confirmacion_registro",
    template_language: str = "es_CL",
) -> dict:
    lugar = "La Faustina Eventos | Edison 424, Paso del Rey"
    fiesta_text = f"la fiesta de {organizador}"

    return {
        "messaging_product": "whatsapp",
        "to": f"+{to_e164_digits}",
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_language},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {"link": image_url},
                        }
                    ],
                },
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": invitado_text},
                        {"type": "text", "text": fiesta_text},
                        {"type": "text", "text": referencia_entrada},
                        {"type": "text", "text": fecha_hora_str},
                        {"type": "text", "text": lugar},
                    ],
                },
            ],
        },
    }
