from flask import Flask, render_template, request, redirect, session
from collections import defaultdict
from datetime import datetime, timedelta, date
from twilio.rest import Client
from openai import OpenAI 
import os
import sqlite3
ADMIN_PASSWORD = "1234"
SECRET_KEY = "mi_clave_secreta_123"

extras_activadas = False

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cierres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            motivo TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS liberaciones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloqueos_especiales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extras_dias(
            fecha TEXT PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT NOT NULL,
            dias_semana TEXT NOT NULL,
            hora TEXT NOT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE clientes_fijos ADD COLUMN dia_semana TEXT")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE clientes_fijos ADD COLUMN hora TEXT")
    except:
        pass

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

def obtener_dias_extras():
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()
    cursor.execute("SELECT fecha FROM extras_dias")
    datos = cursor.fetchall()
    conexion.close()
    return [fila[0] for fila in datos]

def fecha_esta_cerrada(fecha_str):
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT 1
        FROM cierres
        WHERE ? BETWEEN fecha_inicio AND fecha_fin
        LIMIT 1
    """, (fecha_str,))

    resultado = cursor.fetchone()
    conexion.close()

    return resultado is not None

def hora_liberada(fecha_str, hora):
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT 1
        FROM liberaciones
        WHERE fecha = ? AND hora = ?
        LIMIT 1
    """, (fecha_str, hora))

    resultado = cursor.fetchone()
    conexion.close()

    return resultado is not None

def hora_bloqueada_especial(fecha_str, hora):
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT 1
        FROM bloqueos_especiales
        WHERE fecha = ? AND hora = ?
        LIMIT 1
    """, (fecha_str, hora))

    resultado = cursor.fetchone()
    conexion.close()

    return resultado is not None

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

def esta_cerrado (dia, cierres):
    for inicio, fin in cierres:
        if inicio <= dia <= fin:
            return True
        return False

def obtener_cierres():
    conn = sqlite3.connect("citas.db")
    c = conn.cursor()
    c.execute("SELECT id, fecha_inicio, fecha_fin, motivo FROM cierres")
    datos = c.fetchall()
    conn.close()
    return datos

def obtener_liberaciones():
    conn = sqlite3.connect("citas.db")
    c = conn.cursor()
    c.execute("SELECT id, fecha, hora FROM liberaciones")
    datos = c.fetchall()
    conn.close()
    return datos

def obtener_bloqueos_especiales():
    conn = sqlite3.connect("citas.db")
    c = conn.cursor()
    c.execute("SELECT id, fecha, hora FROM bloqueos_especiales")
    datos = c.fetchall()
    conn.close()
    return datos

def obtener_clientes_fijos():
    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, telefono, dias_semana, hora FROM clientes_fijos")
    datos = cursor.fetchall()
    conexion.close()
    return datos

def obtener_disponibilidad():
    global extras_activadas

    inicializar_db()

    citas_ocupadas = cargar_citas()
    disponibilidad = {}

    conn = sqlite3.connect("citas.db")
    c = conn.cursor()

    c.execute("SELECT fecha_inicio, fecha_fin FROM cierres")
    cierres = c.fetchall()

    c.execute("SELECT fecha, hora FROM bloqueos_especiales")
    bloqueos = c.fetchall()

    c.execute("SELECT fecha, hora FROM liberaciones")
    liberadas = c.fetchall()

    conn.close()

    horas_manana = generar_horas ("10:00", "14:00", 40)
    horas_tarde = generar_horas ("16:30", "21:00", 40, primera_diferente=True)
    horas_extra = ["09:30", "16:00", "21:00"]

    hoy = date.today()
    dias_extras = obtener_dias_extras()

    for i in range (30):
        fecha = hoy + timedelta(days=i)
        fecha_str = fecha.strftime("%Y-%m-%d")
        nombre_dia = DIAS_ES[fecha.weekday()]

        if esta_cerrado(fecha_str, cierres):
            continue

        if nombre_dia not in ["Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]:
            continue

        if nombre_dia == "Sábado":
            todas = horas_manana.copy()
        else:
            todas = horas_manana + horas_tarde
        if fecha_str in dias_extras:
            todas += horas_extra

        bloqueadas = BLOQUEOS_FIJOS.get(nombre_dia, [])
        bloqueadas = [
            hora for hora in bloqueadas 
            if not hora_liberada(fecha_str, hora)
        ]
        libres = []
        etiqueta = f"{nombre_dia} {fecha.strftime('%d/%m')}"

        for hora in todas:
            clave = f"{fecha_str}|{hora}"

            bloqueado_db = (fecha_str, hora) in bloqueos
            liberado_db = (fecha_str,hora) in liberadas
            if (
                (clave not in citas_ocupadas and hora not in bloqueadas and not bloqueado_db)
                or liberado_db
            ):
                es_extra = hora in horas_extra
                libres.append({
                    "hora": hora,
                    "extra": es_extra
                })

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

    cursor.execute("""
        SELECT dia, hora, nombre, telefono, estado
        FROM citas
        ORDER BY dia, hora
    """)
    citas = cursor.fetchall()
    citas = sorted(citas, key=lambda x: (x[0], [1]))

    pendientes = [c for c in citas if c[4] == "pendiente"]
    confirmadas = [c for c in citas if c[4] == "confirmada"]

    def agrupar_por_dia(lista_citas):
        dias = defaultdict(list)

        for cita in lista_citas:
            dia_str, hora, nombre, telefono, estado = cita

            fecha_obj = datetime.strptime(dia_str, "%Y-%m-%d")
            nombres_dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            hoy = date.today()
            mañana = hoy + timedelta(days=1)

            if fecha_obj.date() == hoy:
                dia_bonito = "Hoy"
            elif fecha_obj.date() == mañana:
                dia_bonito = "Mañana"
            else:
                dia_bonito = f"{nombres_dias[fecha_obj.weekday()]} {fecha_obj.strftime('%d/%m')}"

            dias[dia_bonito].append({
                "dia": dia_str,
                "hora": hora,
                "nombre": nombre,
                "telefono": telefono,
                "estado": estado
            })
        return dict(dias)

    pendientes_agrupadas = agrupar_por_dia(pendientes)
    confirmadas_agrupadas = agrupar_por_dia(confirmadas)
    cierres = obtener_cierres()
    liberaciones = obtener_liberaciones()
    bloqueos = obtener_bloqueos_especiales()
    clientes_fijos = obtener_clientes_fijos()

    return render_template(
        "admin.html",
        pendientes_agrupadas=pendientes_agrupadas,
        confirmadas_agrupadas=confirmadas_agrupadas,
        cierres=cierres,
        liberaciones=liberaciones,
        bloqueos=bloqueos,
        extras_activadas=extras_activadas,
        clientes_fijos=clientes_fijos
    )

@app.route("/admin/anadir_cita", methods=["POST"])
def admin_anadir_cita():
    if not session.get("admin"):
        return redirect("/login")

    nombre = request.form["nombre"]
    telefono = request.form["telefono"]
    fecha = request.form["fecha"]
    hora = request.form["hora"]

    conn = sqlite3.connect("citas.db")
    c = conn.cursor()

    c.execute("""
        INSERT INTO citas (dia, hora, nombre, telefono, estado)
        VALUES (?, ?, ?, ?, 'confirmada')
    """, (fecha, hora, nombre, telefono))

    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/admin/anadir_cliente_fijo", methods=["POST"])
def anadir_cliente_fijo():
    if not session.get("admin"):
        return redirect("/login")

    nombre = request.form["nombre"]
    telefono = request.form["telefono"]
    dias_semana = request.form["dia_semana"]
    hora = request.form["hora"]

    if not dias_semana:
        return "Error: debes seleccionar un día"

    conexion = sqlite3.connect("citas.db", timeout=10)
    cursor = conexion.cursor()
    cursor.execute("""
        INSERT INTO clientes_fijos (nombre, telefono, dias_semana, hora)
        VALUES (?, ?, ?, ?)
    """, (nombre, telefono, dias_semana, hora))
    conexion.commit()
    conexion.close()

    return redirect("/admin")

@app.route("/admin/eliminar_cliente_fijo/<int:id>")
def eliminar_cliente_fijo(id):
    if not session.get("admin"):
        return redirect("/login")

    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM clientes_fijos WHERE id = ?", (id,))
    conexion.commit()
    conexion.close()

    return redirect("/admin")

@app.route("/admin/cierre", methods=["POST"])
def admin_cierre():
    if not session.get("admin"):
        return redirect ("/login")

    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    motivo = request.form.get("motivo", "")

    if fecha_inicio and fecha_fin:
        conexion = sqlite3.connect("citas.db")
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO cierres (fecha_inicio, fecha_fin, motivo)
            VALUES (?, ?, ?)
        """, (fecha_inicio, fecha_fin, motivo))
        conexion.commit()
        conexion.close()
    return redirect("/admin")

@app.route("/admin/eliminar_liberacion/<int:id>")
def eliminar_liberacion(id):
    if not session.get("admin"):
        return redirect("/login")
    
    conn = sqlite3.connect("citas.db")
    c = conn.cursor()
    c.execute("DELETE FROM liberaciones WHERE id =?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/admin/eliminar_cierre/<int:id>")
def eliminar_cierre(id):
    if not session.get("admin"):
        return redirect("/login")
    
    conn = sqlite3.connect("citas.db")
    c = conn.cursor()
    c.execute("DELETE FROM cierres WHERE id =?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/admin/extra_dia", methods=["POST"])
def activar_extra_dia():
    if not session.get("admin"):
        return redirect("/login")
    
    fecha = request.form["fecha"]

    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO extras_dias (fecha) VALUES (?)",
        (fecha,)
    )
    conexion.commit()
    conexion.close()

    return redirect("/admin")

@app.route("/admin/quitar_extra_dia", methods=["POST"])
def quitar_extra_dia():
    if not session.get("admin"):
        return redirect("/login")
    
    fecha = request.form["fecha"]

    conexion = sqlite3.connect("citas.db")
    cursor = conexion.cursor()
    cursor.execute(
        "DELETE FROM extras_dias WHERE fecha = ?",
        (fecha,)
    )
    conexion.commit()
    conexion.close()

    return redirect("/admin")

@app.route("/admin/eliminar_bloqueo/<int:id>")
def eliminar_bloqueo(id):
    if not session.get("admin"):
        return redirect("/login")
    
    conn = sqlite3.connect("citas.db")
    c = conn.cursor()
    c.execute("DELETE FROM bloqueos_especiales WHERE id =?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/admin/liberar", methods=["POST"])
def admin_liberar():
    if not session.get("admin"):
        return redirect ("/login")

    fecha = request.form.get("fecha")
    hora = request.form.get("hora")

    if fecha and hora:
        conexion = sqlite3.connect("citas.db")
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO liberaciones (fecha, hora)
            VALUES (?, ?)
        """, (fecha, hora))
        conexion.commit()
        conexion.close()
    return redirect("/admin")

@app.route("/admin/bloquear", methods=["POST"])
def admin_bloquear():
    if not session.get("admin"):
        return redirect ("/login")

    fecha = request.form.get("fecha")
    hora = request.form.get("hora")

    if fecha and hora:
        conexion = sqlite3.connect("citas.db")
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO bloqueos_especiales (fecha, hora)
            VALUES (?, ?)
        """, (fecha, hora))
        conexion.commit()
        conexion.close()
    return redirect("/admin")

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
    try:
        print("=== WEBHOOK WHATSAPP LLAMADO ===")
        print("Form completo:", dict(request.form))

        mensaje = request.form.get("Body", "").strip()
        telefono = request.form.get("From", "").strip()

        print("Mensaje recibido:", mensaje)
        print("Telefono recibido:", telefono)

        if not mensaje or not telefono:
            print("Faltan datos")
            return "OK", 200
    
        try:
            texto_respuesta = respuesta_ia_whatsapp(mensaje)
        except Exception as e:
            print("Error IA:", e)
            texto_respuesta = "Ahora mismo no puedo responder, pero puedes reservar aquí: https://my-primer-programa.onrender.com"

        print("Respuesta IA:", texto_respuesta)

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        respuesta = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=telefono,
            body=texto_respuesta
        )

        print("SID Twilio:", respuesta.sid)

        return "OK", 200

    except Exception as e:
        print("Error webhook WhatsApp:", e)
        return "OK", 200
    
conexion = sqlite3.connect("citas.db")
cursor = conexion.cursor()

conexion = sqlite3.connect("citas.db")
cursor = conexion.cursor()

cursor.execute("""
INSERT INTO bloqueos_especiales (fecha, hora)
VALUES (?, ?)
""", ("2026-04-07", "17:00"))

conexion.commit()
conexion.close()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)