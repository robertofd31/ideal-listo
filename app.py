import requests
import pandas as pd
import json
import os
from dotenv import load_dotenv
import openai
import base64
import time
from io import BytesIO
from PIL import Image

# Cargar variables de entorno (para la API key de OpenAI)
load_dotenv()

# Configurar la API de OpenAI
api_key = st.secrets["openai"]

# Primero, obtener los datos de la propiedad
url = "https://idealista7.p.rapidapi.com/propertydetails"
querystring = {"propertyId":"107442883","location":"es","language":"es"}
headers = {
    "x-rapidapi-key": st.secrets["rapidapi"],
    "x-rapidapi-host": "idealista7.p.rapidapi.com"
}

response = requests.get(url, headers=headers, params=querystring)
property_data = response.json()

# Extraer información básica (solo para referencia)
surface_area = property_data["moreCharacteristics"]["constructedArea"]
rooms = property_data["moreCharacteristics"]["roomNumber"]
bathrooms = property_data["moreCharacteristics"]["bathNumber"]
year_built = 2008  # Extraído de la descripción

# Extraer URLs de las imágenes por tipo de habitación
images_by_room = {
    "Estancia": [],
    "Baño": [],
    "Pasillo": [],
    "Vistas": [],
    "Cocina": [],  # Añadido aunque no haya imágenes específicas
    "Desconocido": []
}

for img in property_data["multimedia"]["images"]:
    room_type = img["localizedName"]
    if room_type in images_by_room:
        images_by_room[room_type].append(img["url"])
    else:
        images_by_room["Desconocido"].append(img["url"])

# Función para descargar y codificar una imagen en base64
def get_image_base64(image_url):
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            # Redimensionar la imagen para reducir el tamaño
            img = Image.open(BytesIO(response.content))
            img = img.resize((800, 600), Image.LANCZOS)
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=70)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        else:
            print(f"Error al descargar imagen: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        return None

# Función para analizar una imagen con OpenAI
def analyze_image_with_openai(image_base64, room_type, client):
    try:
        prompt = f"""
        Analiza esta imagen de un {room_type} en una propiedad inmobiliaria.

        Determina si necesita reforma basándote únicamente en lo que ves en la imagen.
        Ignora cualquier texto o descripción previa.

        Responde SOLO con un JSON con este formato exacto:
        {{
          "necesita_reforma": "si/no/?",
          "justificación": "breve explicación de por qué necesita o no reforma",
          "elementos_a_reformar": "lista de elementos que necesitan reforma",
          "estimación_coste": "rango aproximado en euros"
        }}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )

        analysis_text = response.choices[0].message.content.strip()

        # Limpiar la respuesta si contiene texto adicional
        if "```json" in analysis_text:
            analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
        elif "```" in analysis_text:
            analysis_text = analysis_text.split("```")[1].strip()

        return json.loads(analysis_text)

    except Exception as e:
        print(f"Error al analizar imagen de {room_type}: {e}")
        # Devolver un análisis por defecto en caso de error
        return {
            "necesita_reforma": "?",
            "justificación": f"No se pudo analizar la imagen: {str(e)}",
            "elementos_a_reformar": "Desconocido",
            "estimación_coste": "Desconocido"
        }

# Función para realizar análisis manual básico
def analisis_manual():
    # Crear un análisis básico basado en la superficie y año
    analisis = {
        "análisis_por_habitación": {
            "estancias": {"necesita_reforma": "?", "justificación": "No se pudo analizar las imágenes."},
            "baños": {"necesita_reforma": "?", "justificación": "No se pudo analizar las imágenes."},
            "cocina": {"necesita_reforma": "?", "justificación": "No se pudo analizar las imágenes."},
            "pasillo": {"necesita_reforma": "?", "justificación": "No se pudo analizar las imágenes."}
        },
        "estimación_costes": {
            "total": f"{int(surface_area * 600)} - {int(surface_area * 800)} €",
            "desglose": {
                "estancias": f"{int(surface_area * 0.5 * 600)} - {int(surface_area * 0.5 * 800)} €",
                "baños": f"{int(surface_area * 0.2 * 800)} - {int(surface_area * 0.2 * 1000)} €",
                "cocina": f"{int(surface_area * 0.2 * 700)} - {int(surface_area * 0.2 * 900)} €",
                "pasillo": f"{int(surface_area * 0.1 * 500)} - {int(surface_area * 0.1 * 700)} €"
            }
        },
        "nivel_confianza": "bajo",
        "comentarios_adicionales": "Este análisis es aproximado ya que no se pudieron analizar las imágenes."
    }
    return analisis

# Intentar analizar las imágenes con la API de OpenAI
try:
    # Configurar el cliente de OpenAI
    client = openai.OpenAI(api_key=key)

    print("Analizando imágenes de la propiedad...")

    # Diccionario para almacenar los resultados por tipo de habitación
    room_analyses = {}

    # Para cada tipo de habitación, analizar una muestra de imágenes
    for room_type, urls in images_by_room.items():
        if not urls:  # Si no hay imágenes para este tipo de habitación
            room_analyses[room_type.lower()] = {
                "necesita_reforma": "?",
                "justificación": f"No hay imágenes disponibles de {room_type}.",
                "elementos_a_reformar": "Desconocido",
                "estimación_coste": "Desconocido"
            }
            continue

        print(f"Analizando {room_type} ({len(urls)} imágenes)...")

        # Tomar solo la primera imagen de cada tipo para reducir costes de API
        sample_url = urls[0]
        image_base64 = get_image_base64(sample_url)

        if image_base64:
            # Analizar la imagen
            analysis = analyze_image_with_openai(image_base64, room_type, client)
            room_analyses[room_type.lower()] = analysis

            # Pequeña pausa para evitar límites de tasa de la API
            time.sleep(2)
        else:
            room_analyses[room_type.lower()] = {
                "necesita_reforma": "?",
                "justificación": f"No se pudo procesar la imagen de {room_type}.",
                "elementos_a_reformar": "Desconocido",
                "estimación_coste": "Desconocido"
            }

    # Si no tenemos análisis para cocina, usar un valor por defecto
    if "cocina" not in room_analyses:
        room_analyses["cocina"] = {
            "necesita_reforma": "?",
            "justificación": "No hay imágenes disponibles de la cocina.",
            "elementos_a_reformar": "Desconocido",
            "estimación_coste": "Desconocido"
        }

    # Crear el análisis completo
    analysis = {
        "análisis_por_habitación": {
            "estancias": {
                "necesita_reforma": room_analyses.get("estancia", {}).get("necesita_reforma", "?"),
                "justificación": room_analyses.get("estancia", {}).get("justificación", "No analizado")
            },
            "baños": {
                "necesita_reforma": room_analyses.get("baño", {}).get("necesita_reforma", "?"),
                "justificación": room_analyses.get("baño", {}).get("justificación", "No analizado")
            },
            "cocina": {
                "necesita_reforma": room_analyses.get("cocina", {}).get("necesita_reforma", "?"),
                "justificación": room_analyses.get("cocina", {}).get("justificación", "No analizado")
            },
            "pasillo": {
                "necesita_reforma": room_analyses.get("pasillo", {}).get("necesita_reforma", "?"),
                "justificación": room_analyses.get("pasillo", {}).get("justificación", "No analizado")
            }
        },
        "estimación_costes": {
            "total": "Pendiente de cálculo",
            "desglose": {
                "estancias": room_analyses.get("estancia", {}).get("estimación_coste", "No disponible"),
                "baños": room_analyses.get("baño", {}).get("estimación_coste", "No disponible"),
                "cocina": room_analyses.get("cocina", {}).get("estimación_coste", "No disponible"),
                "pasillo": room_analyses.get("pasillo", {}).get("estimación_coste", "No disponible")
            }
        },
        "elementos_a_reformar": {
            "estancias": room_analyses.get("estancia", {}).get("elementos_a_reformar", "No especificado"),
            "baños": room_analyses.get("baño", {}).get("elementos_a_reformar", "No especificado"),
            "cocina": room_analyses.get("cocina", {}).get("elementos_a_reformar", "No especificado"),
            "pasillo": room_analyses.get("pasillo", {}).get("elementos_a_reformar", "No especificado")
        },
        "nivel_confianza": "medio",
        "comentarios_adicionales": "Este análisis se basa únicamente en el análisis visual de las imágenes disponibles."
    }

    # Calcular una estimación total basada en los análisis individuales
    total_min = 0
    total_max = 0

    for room, cost in analysis["estimación_costes"]["desglose"].items():
        if cost != "No disponible" and cost != "Desconocido":
            try:
                # Intentar extraer valores numéricos del rango
                if "-" in cost:
                    min_val, max_val = cost.split("-")
                    min_val = int(''.join(filter(str.isdigit, min_val)))
                    max_val = int(''.join(filter(str.isdigit, max_val)))
                    total_min += min_val
                    total_max += max_val
            except:
                pass

    # Si no pudimos calcular un total basado en los desgloses, usar una estimación basada en superficie
    if total_min == 0 and total_max == 0:
        total_min = int(surface_area * 600)
        total_max = int(surface_area * 800)

    analysis["estimación_costes"]["total"] = f"{total_min} - {total_max} €"

    # Crear un DataFrame para el análisis por habitación
    rooms_analysis = []
    for room_type, data in analysis["análisis_por_habitación"].items():
        rooms_analysis.append({
            "Habitación": room_type.capitalize(),
            "Necesita reforma": data["necesita_reforma"],
            "Justificación": data["justificación"],
            "Elementos a reformar": analysis["elementos_a_reformar"][room_type]
        })

    df_analysis = pd.DataFrame(rooms_analysis)

    # Crear un DataFrame para la estimación de costes
    costs = []
    costs.append({"Concepto": "Total", "Estimación": analysis["estimación_costes"]["total"]})
    for room_type, cost in analysis["estimación_costes"]["desglose"].items():
        costs.append({
            "Concepto": room_type.capitalize(),
            "Estimación": cost
        })

    df_costs = pd.DataFrame(costs)

    # Mostrar los resultados
    print("\nANÁLISIS DE REFORMA POR HABITACIÓN:")
    print(df_analysis)
    print("\nESTIMACIÓN DE COSTES:")
    print(df_costs)
    print("\nNIVEL DE CONFIANZA:")
    print(analysis["nivel_confianza"])
    print("\nCOMENTARIOS ADICIONALES:")
    print(analysis["comentarios_adicionales"])

    # Guardar los resultados en archivos CSV
    df_analysis.to_csv("analisis_reforma_habitaciones_imagenes.csv", index=False)
    df_costs.to_csv("estimacion_costes_reforma_imagenes.csv", index=False)

    # Guardar el análisis completo en JSON
    with open("analisis_reforma_imagenes.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=4)

    print("\nArchivos creados:")
    print("analisis_reforma_habitaciones_imagenes.csv")
    print("estimacion_costes_reforma_imagenes.csv")
    print("analisis_reforma_imagenes.json")

except Exception as e:
    print(f"Error general: {e}")

    # Usar análisis manual si hay un error general
    analysis = analisis_manual()

    print("\nANÁLISIS BÁSICO (generado manualmente):")
    print(f"No se pudieron analizar las imágenes debido a un error.")
    print(f"Superficie: {surface_area} m², lo que podría suponer un coste de reforma entre 600-800€/m².")
    print(f"Estimación aproximada: {int(surface_area * 700)}€ (±20%)")

    # Guardar el análisis manual
    with open("analisis_reforma_manual.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=4)

    print("\nArchivos creados:")
    print("analisis_reforma_manual.json")

# Created/Modified files during execution:
print("\nProceso completado.")
