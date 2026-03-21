print("Asistente virtual del negocio")
print("VERSION NUEVA")
print("Escribe tu pregunta. Para salir escribe: salir")

# leer información del negocio
datos = {}

with open("negocio.txt", "r", encoding="utf-8") as archivo:
    for linea in archivo:
        if "=" in linea:
            clave, valor = linea.strip().split("=", 1)
            datos[clave.strip()] = valor.strip()

    print ("\nAsistente:", "Buenos días.")
    print ("Asistente: En primer lugar, gracias por contactar con", datos ["nombre"] + ".")
    print ("Asistente: ¿En qué puedo ayudarle?")

while True:
    pregunta = input("\nCliente: ").lower()

    if pregunta == "salir":
        print("Asistente: Gracias, hasta luego.")
        break

    elif "horario" in pregunta or "hora" in pregunta or "abris" in pregunta or "abres" in pregunta or "abierto" in pregunta or "apertura" in pregunta or "cierre" in pregunta or "cerrais" in pregunta or "cerráis" in pregunta:
        print("Asistente: Nuestro horario es", datos["horario"])

    elif "direccion" in pregunta or "dirección" in pregunta or "donde" in pregunta or "ubicacion" in pregunta or "ubicación" in pregunta or "dónde" in pregunta or "zona" in pregunta:
        print("Asistente: Estamos en", datos["direccion"])

    elif "telefono" in pregunta or "teléfono" in pregunta:
        print("Asistente: Puedes llamarnos al", datos["telefono"])

    elif "nombre" in pregunta or "llama" in pregunta or "restaurante" in pregunta:
        print("Asistente: Está contactando con", datos["nombre"])

    elif "servicio" in pregunta or "servicios" in pregunta:
        print("Asistente: Ofrecemos", datos["servicios"])
        
    elif "whatsapp" in pregunta:
        print("Asistente: Puede escribirnos por whatsapp al", datos["whatsapp"])

    elif "tipo" in pregunta or "qué sois" in pregunta or "que sois" in pregunta:
        print("Asistente: Somos un", datos["tipo"])

    elif "cita" in pregunta or "reserva" in pregunta or "reservar" in pregunta:
        if datos ["reservas"] == "si":
            print("Asistente: Perfecto.")
            print("Asistente: Puedes reservar tu cita directamente aquí:")
            print(datos["link_reserva"])
        else:
            print("Asistente: Lo siento, no trabajamos con reservas.")

    elif ("precio" in pregunta or "cuanto cuesta" in pregunta or "cuánto cuesta" in pregunta or "cuanto es" in pregunta or "cuánto es" in pregunta or "cuanto vale" in pregunta or "cuánto vale" in pregunta or "coste" in pregunta or "vale" in pregunta):
        if "barba" in pregunta and "corte" in pregunta:
            print("Asistente: Corte + barba cuesta", datos["precio_corte_barba"])    
        elif "barba" in pregunta:
            print("Asistente: La barba cuesta", datos["precio_barba"])
        elif "niño" in pregunta or "nino" in pregunta:
            print("Asistente: El corte de niño cuesta", datos["precio_nino"])
        elif "mechas" in pregunta:
            print("Asistente: El servicio de mechas cuesta", datos["precio_mechas"])
        elif "decoloracion" in pregunta or "decoloración" in pregunta or "blanco" in pregunta:
            print("Asistente: La decoloración cuesta", datos["precio_decoloracion"])
        else:
            print("Asistente: El corte de pelo cuesta", datos["precio_corte"])

    elif "corte" in pregunta and "barba" in pregunta:
        print("Asistente: El servicio de corte + barba cuesta", datos["precio_corte_barba"])                   

    elif "pago" in pregunta or "tarjeta" in pregunta or "efectivo" in pregunta:
        print ("Asistente:", datos["pago"])

    else:
        print("Asistente: Lo siento, todavía no entiendo esa pregunta.")