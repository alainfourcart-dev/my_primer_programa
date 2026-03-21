from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta
import os
import sqlite3

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

    dias_semana = ["Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]

    horas_manana = generar_horas ("10:00", "14:00", 40)
    horas_tarde = generar_horas ("16:30", "21:00", 40, primera_diferente=True)

    for dia in dias_semana:
        if dia == "Sábado":
            todas = horas_manana
        else:
            todas = horas_manana + horas_tarde
        libres = []

        for hora in todas:
            clave = f"{dia}|{hora}"
            if clave not in citas_ocupadas:
                libres.append(hora)
        disponibilidad[dia] = libres

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
                respuesta = f"{nombre}, hemos recibido tu solicitud para {dia} a las {hora}. Te confirmaremos por teléfono."
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

@app.route("/admin")
def admin():
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("SELECT dia, hora, nombre, telefono, estado FROM citas ORDER BY dia, hora")
    citas = cursor.fetchall()

    conexion.close()

    return render_template("admin.html", citas=citas)

@app.route("/confirmar/<dia>/<hora>")
def confirmar(dia, hora):
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("UPDATE citas SET estado='confirmada' WHERE dia=? AND hora=?", (dia, hora))

    conexion.commit()
    conexion.close()

    return redirect("/admin")

@app.route("/cancelar/<dia>/<hora>")
def cancelar(dia, hora):
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("DELETE FROM citas WHERE dia=? AND hora=?", (dia, hora))

    conexion.commit()
    conexion.close()

    return redirect("/admin")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)