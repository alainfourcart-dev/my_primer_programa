from flask import Flask, render_template, request, redirect, session
from datetime import datetime, timedelta, date
from twilio.rest import Client
from openai import OpenAI 
import os
import sqlite3
ADMIN_PASSWORD = "1234"
SECRET_KEY = "mi_clave_secreta_123"

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI()

BLOQUEOS_FIJOS = {
    "Jueves": ["12:00", "12:40", "13:20", "16:30", "17:00", "17:40", "18:20", "19:00", "19:40", "20:20"],
    "Viernes": ["10:00", "12:00", "12:40", "13:20", "16:30", "17:00", "18:20", "19:00", "19:40"]
}

DIAS_ES = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo"
}

def inicializar_db():
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            dia TEXT NOT NULL, 
            hora TEXT NOT NULL,
            nombre TEXT,
            telefono TEXT,
            estado TEXT DEFAULT 'pendiente'
        )
    """)

    conexion.commit()
    conexion.close()

app = Flask(__name__)
app.secret_key = SECRET_KEY

inicializar_db()

def cargar_datos():
    datos = {}
    with open("negocio.txt", "r", encoding="utf-8") as archivo:
        for linea in archivo:
            if "=" in linea:
                clave, valor = linea.strip().split("=", 1)
                datos[clave.strip()] = valor.strip()
    return datos

def cargar_citas():
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("SELECT dia, hora FROM citas")
    filas = cursor.fetchall()

    conexion.close()

    citas = [f"{dia}|{hora}" for dia, hora in filas]
    return citas

def guardar_cita(fecha, hora, nombre, telefono):
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT COUNT (*) FROM citas WHERE dia=? AND hora=?",
        (fecha, hora)
    )
    existe = cursor.fetchone()[0]

    if existe > 0:
        conexion.close()
        return False

    cursor.execute(
        "INSERT INTO citas (dia, hora, nombre, telefono, estado) VALUES (?, ?, ?, ?, ?)",
        (fecha, hora, nombre, telefono, "pendiente")
    )

    conexion.commit()
    conexion.close()
    return True

def normalizar_telefono_whatsapp(telefono):
    telefono = telefono.strip().replace(" ", "")
    if telefono.startswith("+"):
        return f"whatsapp:{telefono}"
    if telefono.startswith("6") or telefono.startswith("7"):
        return f"whatsapp:+34{telefono}"
    return f"whatsapp:{telefono}"

def enviar_whatsapp(telefono, mensaje):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        destino = normalizar_telefono_whatsapp(telefono)

        print("Enviando a:", destino)
        print("Mensaje:", mensaje)

        respuesta = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=destino,
            body=mensaje
        )

        print("SID mensaje:", respuesta.sid)
        return True
    
    except Exception as e:
        print("Error enviando whatsApp:", e)
        return False

def respuesta_ia_whatsapp(mensaje_usuario):
    prompt_sistema = f"""
Eres el asistente de WhatsApp de Rocha Peluqueros.

Datos del negocio:
- Horario: martes a viernes de 10:00 a 14:00 y de 16:30 a 21:00. Sábado de 10:00 a 14:00.
- Servicios: corte, barba, corte + barba, corte + mechas, corte + color.
- Las citas se solicitan desde un enlace con calendario.
- Si el cliente quiere reservar, indícale este enlace: https://my-primer-programa.onrender.com
- Sé breve, amable y claro.
- Responde en español.
- Si no sabes algo, dilo sin inventar.
"""
    
    respuesta = openai_client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": mensaje_usuario}
        ]
    )

    return respuesta.output_text.strip()

def generar_horas(inicio, fin, intervalo=40, primera_diferente=False):
    horas = []
    actual = datetime.strptime(inicio, "%H:%M")
    final = datetime.strptime(fin, "%H:%M")

    primera = True

    while actual < final:
        horas.append(actual.strftime("%H:%M"))

        if primera and primera_diferente:
            actual += timedelta(minutes=30)
            primera = False
        else:
            actual += timedelta(minutes=intervalo)

    return horas

def obtener_disponibilidad():
    citas_ocupadas = cargar_citas()
    disponibilidad = {}

    horas_manana = generar_horas ("10:00", "14:00", 40)
    horas_tarde = generar_horas ("16:30", "21:00", 40, primera_diferente=True)

    hoy = date.today()

    for i in range (30):
        fecha = hoy + timedelta(days=i)
        nombre_dia = DIAS_ES[fecha.weekday()]

        if nombre_dia not in ["Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]:
            continue

        if nombre_dia == "Sábado":
            todas = horas_manana
        else:
            todas = horas_manana + horas_tarde
        bloqueadas = BLOQUEOS_FIJOS.get(nombre_dia, [])
        libres = []

        fecha_str = fecha.strftime("%Y-%m-%d")
        etiqueta = f"{nombre_dia} {fecha.strftime('%d/%m')}"

        for hora in todas:
            clave = f"{fecha_str}|{hora}"

            if clave not in citas_ocupadas and hora not in bloqueadas:
                libres.append(hora)

        disponibilidad[etiqueta] = {
            "fecha": fecha_str,
            "horas": libres
        }

    return disponibilidad                

def responder(pregunta, datos):
    pregunta = pregunta.lower()

    if "horario" in pregunta or "hora" in pregunta or "abierto" in pregunta:
        return f"Nuestro horario es {datos['horario']}"

    elif "direccion" in pregunta or "dirección" in pregunta or "donde" in pregunta or "dónde" in pregunta:
        return f"Estamos en {datos['direccion']}"

    elif "telefono" in pregunta or "teléfono" in pregunta or "numero" in pregunta or "número" in pregunta:
        return f"Puedes llamarnos al {datos['telefono']}"

    elif "whatsapp" in pregunta:
        return f"Puedes escribirnos por WhatsApp al {datos['whatsapp']}"

    elif "nombre" in pregunta or "llama" in pregunta:
        return f"Estás contactando con {datos['nombre']}"

    elif "tipo" in pregunta or "que sois" in pregunta or "qué sois" in pregunta:
        return f"Somos una {datos['tipo']}"

    elif "servicio" in pregunta or "servicios" in pregunta:
        return f"Ofrecemos {datos['servicios']}"

    elif "corte" in pregunta and "barba" in pregunta:
        return f"El servicio de corte + barba cuesta {datos['precio_corte_barba']}"

    elif (
        "precio" in pregunta
        or "cuanto cuesta" in pregunta
        or "cuánto cuesta" in pregunta
        or "cuanto vale" in pregunta
        or "cuánto vale" in pregunta
        or "vale" in pregunta
    ):
        if "barba" in pregunta:
            return f"La barba cuesta {datos['precio_barba']}"
        elif "niño" in pregunta or "nino" in pregunta:
            return f"El corte de niño cuesta {datos['precio_nino']}"
        elif "mechas" in pregunta:
            return f"El servicio de mechas cuesta {datos['precio_mechas']}"
        elif "decoloracion" in pregunta or "decoloración" in pregunta:
            return f"La decoloración cuesta {datos['precio_decoloracion']}"
        else:
            return f"El corte de pelo cuesta {datos['precio_corte']}"

    elif "pago" in pregunta or "tarjeta" in pregunta or "efectivo" in pregunta:
        return datos["pago"]

    elif "cita" in pregunta or "reservar" in pregunta or "reserva" in pregunta:
        if datos["reservas"] == "si":
            return f"Perfecto 🙌 Puedes reservar tu cita directamente aquí: {datos['link_reserva']}"
        else:
            return "Lo siento, ahora mismo no trabajamos con reservas."

    else:
        return "Lo siento, no he entendido tu mensaje. Puedes preguntarme por horario, dirección, servicios, precios, WhatsApp o reservas."

@app.route("/", methods=["GET", "POST"])
def inicio():
    datos = cargar_datos()
    respuesta = None
    pregunta = ""
    tipo_respuesta = ""

    disponibilidad = obtener_disponibilidad()

    if request.method == "POST":
        if "pregunta" in request.form:
            pregunta = request.form["pregunta"]
            respuesta = responder(pregunta, datos)

        elif "dia" in request.form and "hora" in request.form:
            dia = request.form["dia"]
            hora = request.form["hora"]
            nombre = request.form["nombre"]
            telefono = request.form["telefono"]

            guardada = guardar_cita(dia, hora, nombre, telefono)

            tipo_respuesta = ""

            if guardada:
                fecha_obj = datetime.strptime(dia, "%Y-%m-%d")
                dia_bonito = f"{DIAS_ES[fecha_obj.weekday()]} {fecha_obj.strftime('%d/%m')}"

                respuesta = f"{nombre}, hemos recibido tu solicitud para {dia_bonito} a las {hora}. Te confirmaremos por teléfono."
                tipo_respuesta = "ok"
            else:
                respuesta = f"Lo siento, {nombre}. Esa hora ya no está disponible. Elige otra por favor."
                tipo_respuesta = "error"

            disponibilidad = obtener_disponibilidad()
            pregunta = ""

    bienvenida = [
        f"Buenos días. Gracias por contactar con {datos['nombre']}.",
        "¿En qué puedo ayudarte?"
    ]

    return render_template("index.html", bienvenida=bienvenida, respuesta=respuesta, pregunta=pregunta, disponibilidad=disponibilidad, tipo_respuesta=tipo_respuesta)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        password = request.form["password"]

        if password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        else:
            error = "Contraseña incorrecta"

    return render_template("login.html", error=error)

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")
    
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("SELECT dia, hora, nombre, telefono, estado FROM citas ORDER BY dia, hora")
    citas = cursor.fetchall()

    conexion.close()

    return render_template("admin.html", citas=citas)

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/login")

@app.route("/confirmar/<dia>/<hora>")
def confirmar(dia, hora):
    if not session.get("admin"):
        return redirect("/login")
    
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT nombre, telefono FROM citas WHERE dia=? AND hora=?",
        (dia, hora)
    )
    fila = cursor.fetchone()

    cursor.execute(
        "UPDATE citas SET estado='confirmada' WHERE dia=? AND hora=?",
        (dia, hora)
    )

    conexion.commit()
    conexion.close()

    if fila:
        nombre, telefono = fila
        fecha_obj = datetime.strptime(dia, "%Y-%m-%d")
        dia_bonito = f"{DIAS_ES[fecha_obj.weekday()]} {fecha_obj.strftime('%d/%m')}"
        mensaje = f"Hola {nombre}, tu cita en Rocha Peluqueros ha sido confirmada para {dia_bonito} a las {hora}."
        enviar_whatsapp(telefono, mensaje)

    return redirect("/admin")

@app.route("/cancelar/<dia>/<hora>")
def cancelar(dia, hora):
    if not session.get("admin"):
        return redirect("/login")
    
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT nombre, telefono FROM citas WHERE dia=? AND hora=?",
        (dia, hora)
    )
    fila = cursor.fetchone()

    if fila:
        nombre, telefono = fila
        fecha_obj = datetime.strptime(dia, "%Y-%m-%d")
        dia_bonito = f"{DIAS_ES[fecha_obj.weekday()]} {fecha_obj.strftime('%d/%m')}"
        mensaje = f"Hola {nombre}, tu solicitud de cita en Rocha Peluqueros para {dia_bonito} a las {hora} ha sido cancelada."
        enviar_whatsapp(telefono, mensaje)

    cursor.execute(
        "DELETE FROM citas WHERE dia=? AND hora=?",
        (dia, hora)
    )

    conexion.commit()
    conexion.close()

    return redirect("/admin")

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    mensaje = request.form.get("Body", "").strip()
    telefono = request.form.get("From", "").strip()

    if not mensaje or not telefono:
        return "OK", 200
    
    try:
        texto_respuesta = respuesta_ia_whatsapp(mensaje)

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=telefono,
            body=texto_respuesta
        )

    except Exception as e:
        print("Error webhook WhatsApp:", e)

    return "OK", 200

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)