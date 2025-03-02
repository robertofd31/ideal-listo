import streamlit as st
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

# Configuración de la página
st.set_page_config(
    page_title="Análisis de Inmuebles",
    page_icon="🏠",
    layout="wide"
)

# Título de la aplicación
st.title("Analizador de Inmuebles")
st.markdown("Introduce el enlace o ID de un inmueble para analizar sus fotos y obtener un informe de reforma")

# Cargar variables de entorno (para la API key de OpenAI)
load_dotenv()

# Función para extraer el ID de la propiedad de una URL
def extract_property_id(url):
    if not url:
        return None

    # Si es solo un número, asumimos que es el ID directamente
    if url.isdigit():
        return url

    # Intentar extraer el ID de una URL de idealista
    import re
    match = re.search(r'/inmueble/(\d+)/', url)
    if match:
        return match.group(1)

    return None

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
            st.error(f"Error al descargar imagen: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error procesando imagen: {e}")
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
        st.warning(f"Error al analizar imagen de {room_type}: {e}")
        # Devolver un análisis por defecto en caso de error
        return {
            "necesita_reforma": "?",
            "justificación": f"No se pudo analizar la imagen: {str(e)}",
            "elementos_a_reformar": "Desconocido",
            "estimación_coste": "Desconocido"
        }

# Función para realizar análisis manual básico
def analisis_manual(surface_area):
    # Crear un análisis básico basado en la superficie
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

# Interfaz de usuario
api_key = st.sidebar.text_input("OpenAI API Key", type="password")
rapidapi_key = st.sidebar.text_input("RapidAPI Key", type="password", value="aa2dd641d5msh2565cfba16fdf3cp172729jsn62ebc6b556b5")

# Entrada para la URL o ID del inmueble
property_url = st.text_input("Introduce la URL o ID del inmueble de Idealista:", placeholder="https://www.idealista.com/inmueble/107442883/ o simplemente 107442883")

# Botón para iniciar el análisis
if st.button("Analizar inmueble"):
    if not property_url:
        st.error("Por favor, introduce una URL o ID de inmueble válido.")
    elif not api_key:
        st.error("Por favor, introduce tu API Key de OpenAI.")
    else:
        # Extraer el ID de la propiedad
        property_id = extract_property_id(property_url)

        if not property_id:
            st.error("No se pudo extraer el ID del inmueble. Asegúrate de que la URL es correcta.")
        else:
            # Mostrar un mensaje de carga
            with st.spinner(f"Obteniendo datos del inmueble {property_id}..."):
                # Configurar la solicitud a la API de Idealista
                url = "https://idealista7.p.rapidapi.com/propertydetails"
                querystring = {"propertyId": property_id, "location":"es", "language":"es"}
                headers = {
                    "x-rapidapi-key": rapidapi_key,
                    "x-rapidapi-host": "idealista7.p.rapidapi.com"
                }

                try:
                    response = requests.get(url, headers=headers, params=querystring)
                    if response.status_code != 200:
                        st.error(f"Error al obtener datos del inmueble: {response.status_code}")
                        st.json(response.text)
                    else:
                        property_data = response.json()

                        # Extraer información básica
                        try:
                            surface_area = property_data["moreCharacteristics"]["constructedArea"]
                            rooms = property_data["moreCharacteristics"]["roomNumber"]
                            bathrooms = property_data["moreCharacteristics"]["bathNumber"]
                            price = property_data["price"]
                            address = property_data["address"]
                            description = property_data["description"]
                        except KeyError as e:
                            st.warning(f"No se pudo extraer algún dato básico: {e}")
                            surface_area = 0
                            rooms = 0
                            bathrooms = 0
                            price = "No disponible"
                            address = "No disponible"
                            description = "No disponible"

                        # Mostrar información básica del inmueble
                        st.header("Información del inmueble")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Superficie", f"{surface_area} m²")
                        with col2:
                            st.metric("Habitaciones", rooms)
                        with col3:
                            st.metric("Baños", bathrooms)

                        st.subheader("Dirección")
                        st.write(address)

                        st.subheader("Descripción")
                        st.write(description)

                        # Extraer URLs de las imágenes por tipo de habitación
                        images_by_room = {
                            "Estancia": [],
                            "Baño": [],
                            "Pasillo": [],
                            "Vistas": [],
                            "Cocina": [],
                            "Desconocido": []
                        }

                        try:
                            for img in property_data["multimedia"]["images"]:
                                room_type = img["localizedName"]
                                if room_type in images_by_room:
                                    images_by_room[room_type].append(img["url"])
                                else:
                                    images_by_room["Desconocido"].append(img["url"])
                        except KeyError:
                            st.warning("No se pudieron extraer las imágenes del inmueble.")

                        # Mostrar las imágenes por tipo de habitación
                        st.header("Imágenes del inmueble")

                        # Crear pestañas para cada tipo de habitación
                        tabs = st.tabs(list(images_by_room.keys()))

                        for i, (room_type, urls) in enumerate(images_by_room.items()):
                            with tabs[i]:
                                if not urls:
                                    st.write(f"No hay imágenes disponibles de {room_type}")
                                else:
                                    # Mostrar las imágenes en una cuadrícula
                                    cols = st.columns(min(3, len(urls)))
                                    for j, url in enumerate(urls):
                                        with cols[j % 3]:
                                            st.image(url, caption=f"{room_type} {j+1}", use_column_width=True)

                        # Analizar las imágenes con OpenAI
                        st.header("Análisis de reforma")

                        with st.spinner("Analizando imágenes con IA..."):
                            try:
                                # Configurar el cliente de OpenAI
                                client = openai.OpenAI(api_key=api_key)

                                # Diccionario para almacenar los resultados por tipo de habitación
                                room_analyses = {}

                                # Para cada tipo de habitación, analizar una muestra de imágenes
                                progress_bar = st.progress(0)
                                total_rooms = len([room for room, urls in images_by_room.items() if urls])
                                current_room = 0

                                for room_type, urls in images_by_room.items():
                                    if not urls:  # Si no hay imágenes para este tipo de habitación
                                        room_analyses[room_type.lower()] = {
                                            "necesita_reforma": "?",
                                            "justificación": f"No hay imágenes disponibles de {room_type}.",
                                            "elementos_a_reformar": "Desconocido",
                                            "estimación_coste": "Desconocido"
                                        }
                                        continue

                                    st.text(f"Analizando {room_type} ({len(urls)} imágenes)...")

                                    # Tomar solo la primera imagen de cada tipo para reducir costes de API
                                    sample_url = urls[0]
                                    image_base64 = get_image_base64(sample_url)

                                    if image_base64:
                                        # Analizar la imagen
                                        analysis = analyze_image_with_openai(image_base64, room_type, client)
                                        room_analyses[room_type.lower()] = analysis

                                        # Pequeña pausa para evitar límites de tasa de la API
                                        time.sleep(1)
                                    else:
                                        room_analyses[room_type.lower()] = {
                                            "necesita_reforma": "?",
                                            "justificación": f"No se pudo procesar la imagen de {room_type}.",
                                            "elementos_a_reformar": "Desconocido",
                                            "estimación_coste": "Desconocido"
                                        }

                                    current_room += 1
                                    progress_bar.progress(current_room / total_rooms)

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

                                # Mostrar el análisis por habitación
                                st.subheader("Análisis por habitación")

                                # Crear pestañas para cada tipo de habitación
                                room_tabs = st.tabs(["Estancias", "Baños", "Cocina", "Pasillo"])

                                with room_tabs[0]:
                                    st.write("**Necesita reforma:** " + analysis["análisis_por_habitación"]["estancias"]["necesita_reforma"])
                                    st.write("**Justificación:** " + analysis["análisis_por_habitación"]["estancias"]["justificación"])
                                    st.write("**Elementos a reformar:** " + analysis["elementos_a_reformar"]["estancias"])
                                    st.write("**Estimación de coste:** " + analysis["estimación_costes"]["desglose"]["estancias"])

                                with room_tabs[1]:
                                    st.write("**Necesita reforma:** " + analysis["análisis_por_habitación"]["baños"]["necesita_reforma"])
                                    st.write("**Justificación:** " + analysis["análisis_por_habitación"]["baños"]["justificación"])
                                    st.write("**Elementos a reformar:** " + analysis["elementos_a_reformar"]["baños"])
                                    st.write("**Estimación de coste:** " + analysis["estimación_costes"]["desglose"]["baños"])

                                with room_tabs[2]:
                                    st.write("**Necesita reforma:** " + analysis["análisis_por_habitación"]["cocina"]["necesita_reforma"])
                                    st.write("**Justificación:** " + analysis["análisis_por_habitación"]["cocina"]["justificación"])
                                    st.write("**Elementos a reformar:** " + analysis["elementos_a_reformar"]["cocina"])
                                    st.write("**Estimación de coste:** " + analysis["estimación_costes"]["desglose"]["cocina"])

                                with room_tabs[3]:
                                    st.write("**Necesita reforma:** " + analysis["análisis_por_habitación"]["pasillo"]["necesita_reforma"])
                                    st.write("**Justificación:** " + analysis["análisis_por_habitación"]["pasillo"]["justificación"])
                                    st.write("**Elementos a reformar:** " + analysis["elementos_a_reformar"]["pasillo"])
                                    st.write("**Estimación de coste:** " + analysis["estimación_costes"]["desglose"]["pasillo"])

                                # Mostrar la estimación total
                                st.subheader("Estimación total de costes")
                                st.metric("Coste estimado de reforma", analysis["estimación_costes"]["total"])

                                # Nivel de confianza y comentarios adicionales
                                st.subheader("Información adicional")
                                st.write("**Nivel de confianza:** " + analysis["nivel_confianza"])
                                st.write("**Comentarios adicionales:** " + analysis["comentarios_adicionales"])

                                # Opción para descargar el análisis como JSON
                                st.download_button(
                                    label="Descargar análisis como JSON",
                                    data=json.dumps(analysis, ensure_ascii=False, indent=4),
                                    file_name=f"analisis_inmueble_{property_id}.json",
                                    mime="application/json"
                                )

                            except Exception as e:
                                st.error(f"Error al analizar las imágenes: {e}")

                                # Usar análisis manual si hay un error general
                                analysis = analisis_manual(surface_area)

                                st.warning("No se pudieron analizar las imágenes. Se ha generado un análisis básico basado en la superficie.")
                                st.write(f"Superficie: {surface_area} m², lo que podría suponer un coste de reforma entre 600-800€/m².")
                                st.write(f"Estimación aproximada: {int(surface_area * 700)}€ (±20%)")

                except Exception as e:
                    st.error(f"Error al procesar el inmueble: {e}")

# Información adicional en el sidebar
st.sidebar.header("Acerca de")
st.sidebar.info("""
Esta aplicación analiza imágenes de inmuebles para estimar costes de reforma.
Utiliza la API de Idealista para obtener los datos del inmueble y OpenAI para analizar las imágenes.
""")

# Pie de página
st.markdown("---")
st.markdown("Desarrollado con ❤️ usando Streamlit")
