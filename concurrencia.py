import threading
import time
import random
from collections import deque


class SimulacionConcurrencia:
    def __init__(self):
        self.mutex = threading.Lock()
        self.detener_evento = threading.Event()
        self.hilos = []
        self.eventos = deque(maxlen=200)
        self.estados = {}
        self.datos = {}
        self.activa = False

    # ------------------------------------------------------------------
    # Infraestructura común
    # ------------------------------------------------------------------
    def registrar_evento(self, mensaje):
        """Guarda un evento de forma segura."""
        with self.mutex:
            self.eventos.append({
                "tiempo": round(time.time(), 2),
                "mensaje": mensaje
            })

    def actualizar_estado(self, nombre, estado):
        """Actualiza el estado de un hilo de forma segura."""
        with self.mutex:
            self.estados[nombre] = estado

    def obtener_eventos(self):
        with self.mutex:
            return list(self.eventos)

    def obtener_estados(self):
        with self.mutex:
            return dict(self.estados)

    def iniciar(self, funcion, *args, **kwargs):
        """Inicia una simulación en un hilo independiente."""
        # La comprobación y el cambio de 'activa' son atómicos: dos clics
        # seguidos no pueden lanzar dos simulaciones a la vez.
        with self.mutex:
            if self.activa:
                return False
            self.activa = True
            self.eventos.clear()
            self.estados.clear()
            self.datos.clear()

        self.detener_evento.clear()
        self.hilos = []

        hilo = threading.Thread(
            target=self._ejecutar,
            args=(funcion, args, kwargs),
            daemon=True
        )
        self.hilos.append(hilo)
        hilo.start()
        return True

    def _ejecutar(self, funcion, args, kwargs):
        try:
            funcion(*args, **kwargs)
        except Exception as error:
            self.registrar_evento(f"Error: {error}")
        finally:
            self.activa = False

    def detener(self):
        """Solicita que los hilos terminen."""
        self.detener_evento.set()
        self.registrar_evento("Se solicitó detener la simulación.")

    def esperar(self, tiempo=2):
        """Espera interrumpible; devuelve False si se pidió detener."""
        return not self.detener_evento.wait(tiempo)

    def _adquirir(self, semaforo, paso=0.1):
        """wait() interrumpible: devuelve False si se pidió detener antes de conseguirlo."""
        while not self.detener_evento.is_set():
            if semaforo.acquire(timeout=paso):
                return True
        return False

    # --------------------------------------------------
    # 1. PRODUCTOR - CONSUMIDOR
    # --------------------------------------------------
    def productor_consumidor(self, capacidad=5, velocidad=1.0, total_elementos=20):
        """
        Productor y consumidor con dos semáforos (espacios libres / elementos
        disponibles) y un mutex que protege el buffer.

        Orden clásico de cada hilo:
          productor : producir -> wait(espacios) -> [mutex: insertar] -> signal(elementos)
          consumidor: wait(elementos) -> [mutex: retirar] -> signal(espacios) -> consumir
        """
        capacidad = max(1, int(capacidad))
        total_elementos = max(1, int(total_elementos))
        velocidad = max(0.25, min(float(velocidad), 3.0))

        buffer = deque()
        mutex_buffer = threading.Lock()
        espacios_libres = threading.Semaphore(capacidad)
        elementos_disponibles = threading.Semaphore(0)
        productor_terminado = threading.Event()
        cont = {"producidos": 0, "consumidos": 0}

        with self.mutex:
            self.datos.update({
                "buffer": [],
                "capacidad": capacidad,
                "espacios_libres": capacidad,
                "elementos_disponibles": 0,
                "producidos": 0,
                "consumidos": 0,
                "total_elementos": total_elementos,
                "ultimo_producido": None,
                "ultimo_consumido": None,
                "accion": "Preparando recursos",
                "inicio": time.time(),
                "velocidad": velocidad,
            })

        self.actualizar_estado("Productor", "Preparado")
        self.actualizar_estado("Consumidor", "Preparado")
        self.registrar_evento(
            f"Inicio: capacidad={capacidad}, elementos={total_elementos}, velocidad={velocidad:.2f}x."
        )

        def publicar(accion, **extra):
            """Publica el buffer. SIEMPRE se llama con mutex_buffer tomado, así
            la pantalla y el log nunca muestran una foto vieja del buffer."""
            with self.mutex:
                self.datos["buffer"] = list(buffer)
                self.datos["espacios_libres"] = capacidad - len(buffer)
                self.datos["elementos_disponibles"] = len(buffer)
                self.datos["accion"] = accion
                self.datos.update(extra)

        def cambiar_accion(texto):
            with self.mutex:
                self.datos["accion"] = texto

        def productor():
            try:
                for elemento in range(1, total_elementos + 1):
                    if self.detener_evento.is_set():
                        break

                    # 1) Producir (fuera de la sección crítica y sin ocupar espacio)
                    self.actualizar_estado("Productor", f"Produciendo elemento {elemento}")
                    cambiar_accion(f"El productor fabrica el elemento {elemento}")
                    if not self.esperar(0.75 / velocidad):
                        break

                    # 2) wait(espacios_libres): sólo se muestra "esperando" si de verdad se bloquea
                    if not espacios_libres.acquire(blocking=False):
                        self.actualizar_estado("Productor", "Esperando espacio libre (buffer lleno)")
                        cambiar_accion("Buffer lleno: el productor espera un espacio libre")
                        if not self._adquirir(espacios_libres):
                            break

                    # 3) Sección crítica: insertar
                    self.actualizar_estado("Productor", "Insertando en el buffer (mutex)")
                    with mutex_buffer:
                        buffer.append(elemento)
                        cont["producidos"] += 1
                        publicar(
                            f"Elemento {elemento} agregado al buffer",
                            producidos=cont["producidos"],
                            ultimo_producido=elemento,
                        )
                        self.registrar_evento(
                            f"PRODUCTOR: agregó elemento {elemento}; buffer={list(buffer)}."
                        )

                    # 4) signal(elementos_disponibles)
                    elementos_disponibles.release()
            finally:
                productor_terminado.set()
                self.actualizar_estado("Productor", "Terminado")
                self.registrar_evento("PRODUCTOR: terminó su ejecución.")

        def consumidor():
            try:
                while True:
                    # wait(elementos_disponibles)
                    if not elementos_disponibles.acquire(blocking=False):
                        self.actualizar_estado("Consumidor", "Esperando elemento (buffer vacío)")
                        if not elementos_disponibles.acquire(timeout=0.1):
                            with mutex_buffer:
                                buffer_vacio = not buffer
                            # Al detener, el consumidor termina de retirar lo ya producido.
                            if productor_terminado.is_set() and buffer_vacio:
                                break
                            continue

                    self.actualizar_estado("Consumidor", "Retirando del buffer (mutex)")
                    with mutex_buffer:
                        if not buffer:
                            self.registrar_evento("AVISO: semáforo indicó elemento, pero el buffer estaba vacío.")
                            continue
                        elemento = buffer.popleft()
                        cont["consumidos"] += 1
                        publicar(
                            f"Elemento {elemento} retirado del buffer",
                            consumidos=cont["consumidos"],
                            ultimo_consumido=elemento,
                        )
                        self.registrar_evento(
                            f"CONSUMIDOR: retiró elemento {elemento}; buffer={list(buffer)}."
                        )

                    # signal(espacios_libres) y luego consumir fuera de la sección crítica
                    espacios_libres.release()
                    self.actualizar_estado("Consumidor", f"Consumiendo elemento {elemento}")
                    if not self.detener_evento.is_set():
                        self.esperar(1.15 / velocidad)
            finally:
                self.actualizar_estado("Consumidor", "Terminado")
                self.registrar_evento("CONSUMIDOR: terminó su ejecución.")

        hilo_productor = threading.Thread(
            target=productor, name="Hilo-Productor", daemon=True
        )
        hilo_consumidor = threading.Thread(
            target=consumidor, name="Hilo-Consumidor", daemon=True
        )
        self.hilos.extend([hilo_productor, hilo_consumidor])
        hilo_productor.start()
        hilo_consumidor.start()
        hilo_productor.join()
        hilo_consumidor.join()

        with self.mutex:
            producidos = self.datos.get("producidos", 0)
            consumidos = self.datos.get("consumidos", 0)
            self.datos["accion"] = "Simulación completada" if not self.detener_evento.is_set() else "Simulación detenida"
        self.registrar_evento(
            f"Fin: producidos={producidos}, consumidos={consumidos}."
        )

    # --------------------------------------------------
    # 2. LECTORES - ESCRITORES
    # --------------------------------------------------
    def lectores_escritores(
        self, cantidad_lectores=3, cantidad_escritores=2,
        velocidad=1.0, politica="Preferencia a lectores"
    ):
        """Lectores-escritores con preferencia configurable y ritmo ajustable."""
        cantidad_lectores = max(1, min(10, int(cantidad_lectores)))
        cantidad_escritores = max(1, min(10, int(cantidad_escritores)))
        velocidad = max(0.25, min(3.0, float(velocidad)))
        politicas = {
            "Preferencia a lectores",
            "Preferencia a escritores",
            "Equitativa (bloques por turno)",
        }
        if politica not in politicas:
            politica = "Preferencia a lectores"

        mutex_lectores = threading.Lock()
        recurso = threading.Lock()
        puerta = threading.Semaphore(1)
        lectores_activos = [0]
        escritores_esperando = [0]
        dato_compartido = [0]
        with self.mutex:
            self.datos.update({
                "valor_compartido": 0,
                "lectores_activos": 0,
                "escritor_activo": False,
                "lecturas_realizadas": 0,
                "escrituras_realizadas": 0,
                "lectores_configurados": cantidad_lectores,
                "escritores_configurados": cantidad_escritores,
                "politica": politica,
                "velocidad": velocidad,
            })
        self.registrar_evento(
            f"Lectores-escritores: política={politica}; velocidad={velocidad:.2f}x."
        )

        def entrar_lector():
            if politica == "Preferencia a lectores":
                with mutex_lectores:
                    if lectores_activos[0] == 0:
                        if not self._adquirir(recurso, 0.08):
                            return False
                    lectores_activos[0] += 1
                    with self.mutex:
                        self.datos["lectores_activos"] = lectores_activos[0]
                return True

            if politica == "Preferencia a escritores":
                # Un escritor pendiente cierra temporalmente la entrada a nuevos
                # lectores; los lectores que ya estaban dentro pueden terminar.
                while not self.detener_evento.is_set():
                    with mutex_lectores:
                        if escritores_esperando[0] == 0:
                            if lectores_activos[0] == 0:
                                puede_entrar = recurso.acquire(blocking=False)
                            else:
                                puede_entrar = True
                            if puede_entrar:
                                lectores_activos[0] += 1
                                with self.mutex:
                                    self.datos["lectores_activos"] = lectores_activos[0]
                                return True
                    self.esperar(0.04 / velocidad)
                return False

            # Política equitativa por turnos: cada grupo de lectores entra por
            # la puerta y un escritor que la obtiene impide que lleguen lectores nuevos.
            if not self._adquirir(puerta, 0.08):
                return False
            try:
                with mutex_lectores:
                    if lectores_activos[0] == 0:
                        if not self._adquirir(recurso, 0.08):
                            return False
                    lectores_activos[0] += 1
                    with self.mutex:
                        self.datos["lectores_activos"] = lectores_activos[0]
                return True
            finally:
                puerta.release()

        def salir_lector(nombre):
            with mutex_lectores:
                lectores_activos[0] -= 1
                restantes = lectores_activos[0]
                with self.mutex:
                    self.datos["lectores_activos"] = restantes
                # El estado se actualiza ANTES de soltar el recurso: así nunca se
                # ve a un lector "Leyendo" mientras un escritor ya está escribiendo.
                self.actualizar_estado(nombre, "Esperando siguiente lectura")
                if restantes == 0:
                    recurso.release()

        def lector(numero):
            nombre = f"Lector {numero}"
            for vuelta in range(1, 4):
                if self.detener_evento.is_set():
                    break
                self.actualizar_estado(nombre, "Esperando acceso")
                if not entrar_lector():
                    break
                try:
                    self.actualizar_estado(nombre, "Leyendo")
                    with self.mutex:
                        valor_leido = dato_compartido[0]
                    self.registrar_evento(
                        f"{nombre} empieza lectura {vuelta}; valor={valor_leido}."
                    )
                    if not self.esperar(0.65 / velocidad):
                        break
                    with self.mutex:
                        self.datos["lecturas_realizadas"] += 1
                    self.registrar_evento(f"{nombre} termina lectura {vuelta}.")
                finally:
                    salir_lector(nombre)
                if not self.esperar(0.25 / velocidad):
                    break
            self.actualizar_estado(nombre, "Detenido" if self.detener_evento.is_set() else "Terminado")

        def escritor(numero):
            nombre = f"Escritor {numero}"
            for vuelta in range(1, 3):
                if self.detener_evento.is_set():
                    break
                self.actualizar_estado(nombre, "Esperando acceso exclusivo")
                if politica == "Preferencia a lectores":
                    adquirido = self._adquirir(recurso, 0.08)
                elif politica == "Preferencia a escritores":
                    with mutex_lectores:
                        escritores_esperando[0] += 1
                    adquirido = self._adquirir(recurso, 0.08)
                    with mutex_lectores:
                        escritores_esperando[0] -= 1
                else:
                    adquirido = self._adquirir(puerta, 0.08)
                    if adquirido and not self._adquirir(recurso, 0.08):
                        puerta.release()
                        adquirido = False
                if not adquirido:
                    break
                try:
                    self.actualizar_estado(nombre, "Escribiendo")
                    with self.mutex:
                        self.datos["escritor_activo"] = True
                        dato_compartido[0] += 1
                        nuevo_valor = dato_compartido[0]
                        self.datos["valor_compartido"] = nuevo_valor
                    self.registrar_evento(
                        f"{nombre} empieza escritura {vuelta}; valor actualizado a {nuevo_valor}."
                    )
                    if not self.esperar(0.85 / velocidad):
                        break
                    with self.mutex:
                        self.datos["escrituras_realizadas"] += 1
                    self.registrar_evento(f"{nombre} termina escritura {vuelta}.")
                finally:
                    with self.mutex:
                        self.datos["escritor_activo"] = False
                    # Primero se cambia el estado, después se libera el recurso.
                    self.actualizar_estado(nombre, "Esperando siguiente escritura")
                    recurso.release()
                    if politica == "Equitativa (bloques por turno)":
                        puerta.release()
                if not self.esperar(0.3 / velocidad):
                    break
            self.actualizar_estado(nombre, "Detenido" if self.detener_evento.is_set() else "Terminado")

        hilos = [
            threading.Thread(target=lector, args=(i,), name=f"Lector-{i}", daemon=True)
            for i in range(1, cantidad_lectores + 1)
        ] + [
            threading.Thread(target=escritor, args=(i,), name=f"Escritor-{i}", daemon=True)
            for i in range(1, cantidad_escritores + 1)
        ]
        self.hilos.extend(hilos)
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        with self.mutex:
            self.datos["valor_compartido"] = dato_compartido[0]
            self.datos["lectores_activos"] = 0
            self.datos["escritor_activo"] = False
        self.registrar_evento("Lectores-escritores finalizado.")

    # --------------------------------------------------
    # 3. FILÓSOFOS COMENSALES
    # --------------------------------------------------
    def filosofos_comensales(self, cantidad=5, velocidad=1.0):
        """Cada filósofo completa dos comidas adquiriendo sus dos tenedores.

        Evita el deadlock con un semáforo que deja competir a lo sumo N-1
        filósofos a la vez: siempre queda al menos uno que puede conseguir
        ambos tenedores, así que la espera circular es imposible.
        """
        cantidad = max(2, min(10, int(cantidad)))
        velocidad = max(0.20, min(1.0, float(velocidad)))
        tenedores = [threading.Lock() for _ in range(cantidad)]
        limite = threading.Semaphore(cantidad - 1)
        ocupados = [False] * cantidad
        comidas_objetivo = 2
        with self.mutex:
            self.datos.update({
                "cantidad_filosofos": cantidad,
                "comiendo": 0,
                "pensando": cantidad,
                "tenedores_ocupados": list(ocupados),
                "comidas_completadas": 0,
                "comidas_objetivo": cantidad * comidas_objetivo,
                "limite_concurrente": cantidad - 1,
            })

        def poner_estado(nombre, texto):
            """Cambia el estado y recalcula 'comiendo' / 'pensando' a partir de los estados reales."""
            with self.mutex:
                self.estados[nombre] = texto
                filosofos = [e for n, e in self.estados.items() if n.startswith("Filósofo ")]
                self.datos["comiendo"] = sum(1 for e in filosofos if e == "Comiendo")
                self.datos["pensando"] = sum(1 for e in filosofos if e == "Pensando")

        def marcar_tenedor(indice, ocupado):
            with self.mutex:
                ocupados[indice] = ocupado
                self.datos["tenedores_ocupados"] = list(ocupados)

        def filosofo(i):
            nombre = f"Filósofo {i + 1}"
            izquierda_i = i
            derecha_i = (i + 1) % cantidad
            izquierda = tenedores[izquierda_i]
            derecha = tenedores[derecha_i]
            comidas = 0
            while comidas < comidas_objetivo and not self.detener_evento.is_set():
                poner_estado(nombre, "Pensando")
                self.registrar_evento(f"{nombre} piensa antes de intentar comer ({comidas}/{comidas_objetivo} comidas completadas).")
                if not self.esperar(random.uniform(0.15, 0.3) / velocidad):
                    break
                poner_estado(nombre, "Esperando tenedores")
                if not limite.acquire(timeout=0.12):
                    continue
                tiene_izq = False
                tiene_der = False
                try:
                    tiene_izq = izquierda.acquire(timeout=0.15)
                    if not tiene_izq:
                        continue
                    marcar_tenedor(izquierda_i, True)
                    poner_estado(nombre, f"Tiene tenedor {izquierda_i + 1}; busca el otro")
                    tiene_der = derecha.acquire(timeout=0.15)
                    if not tiene_der:
                        self.registrar_evento(f"{nombre} no consiguió el tenedor {derecha_i + 1}; suelta el {izquierda_i + 1} y reintenta.")
                        continue
                    marcar_tenedor(derecha_i, True)
                    poner_estado(nombre, "Comiendo")
                    self.registrar_evento(f"{nombre} adquiere los tenedores {izquierda_i + 1} y {derecha_i + 1}; empieza a comer.")
                    if not self.esperar(0.8 / velocidad):
                        break
                    comidas += 1
                    with self.mutex:
                        self.datos["comidas_completadas"] = self.datos.get("comidas_completadas", 0) + 1
                    self.registrar_evento(f"{nombre} termina de comer ({comidas}/{comidas_objetivo}) y libera ambos tenedores.")
                finally:
                    if tiene_der:
                        # El estado deja de ser "Comiendo" ANTES de soltar los tenedores.
                        poner_estado(nombre, "Pensando")
                        marcar_tenedor(derecha_i, False)
                        derecha.release()
                    if tiene_izq:
                        marcar_tenedor(izquierda_i, False)
                        izquierda.release()
                    limite.release()
            poner_estado(nombre, "Terminado" if not self.detener_evento.is_set() else "Detenido")

        hilos = [
            threading.Thread(target=filosofo, args=(i,), name=f"Filosofo-{i + 1}", daemon=True)
            for i in range(cantidad)
        ]
        self.hilos.extend(hilos)
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        with self.mutex:
            self.datos["comiendo"] = 0
            self.datos["pensando"] = 0
            self.datos["tenedores_ocupados"] = [False] * cantidad
        self.registrar_evento("Filósofos comensales finalizado; todos los tenedores quedaron libres.")

    # --------------------------------------------------
    # 4. BARBERO DORMILÓN
    # --------------------------------------------------
    def barbero_dormilon(self, cantidad_clientes=8, sillas=3, velocidad=1.0):
        """Barbería clásica.

        El semáforo 'clientes_en_espera' cuenta EXACTAMENTE a los clientes
        sentados en la sala (cada cliente que se sienta hace signal; el barbero
        hace wait antes de cada corte). Si el contador es 0, el barbero duerme.
        """
        cantidad_clientes = max(1, min(20, int(cantidad_clientes)))
        sillas = max(1, min(10, int(sillas)))
        velocidad = max(0.25, min(3.0, float(velocidad)))
        clientes_en_espera = threading.Semaphore(0)
        mutex_sala = threading.Lock()
        cola = deque()
        llegadas_completas = threading.Event()
        estadisticas = {"atendidos": 0, "rechazados": 0, "aceptados": 0}
        with self.mutex:
            self.datos.update({
                "sillas": sillas,
                "clientes_esperando": 0,
                "clientes_atendidos": 0,
                "clientes_rechazados": 0,
                "clientes_aceptados": 0,
                "cliente_en_sillon": None,
                "velocidad": velocidad,
            })

        def publicar_sala():
            with self.mutex:
                self.datos["clientes_esperando"] = len(cola)
                self.datos["clientes_atendidos"] = estadisticas["atendidos"]
                self.datos["clientes_rechazados"] = estadisticas["rechazados"]
                self.datos["clientes_aceptados"] = estadisticas["aceptados"]

        def barbero():
            durmiendo = False
            try:
                while not self.detener_evento.is_set():
                    # wait(clientes_en_espera): si no hay nadie, el barbero se duerme.
                    if not clientes_en_espera.acquire(blocking=False):
                        if not durmiendo:
                            durmiendo = True
                            self.actualizar_estado("Barbero", "Durmiendo: no hay clientes")
                            self.registrar_evento("El barbero se duerme: no hay clientes.")
                        if not clientes_en_espera.acquire(timeout=0.1):
                            if llegadas_completas.is_set():
                                with mutex_sala:
                                    if not cola:
                                        break
                            continue
                    if durmiendo:
                        durmiendo = False
                        self.registrar_evento("Un cliente despierta al barbero.")

                    with mutex_sala:
                        if not cola:           # no debería ocurrir: el semáforo cuenta a la cola
                            continue
                        numero, evento_atendido = cola.popleft()
                        publicar_sala()
                    self.actualizar_estado("Barbero", f"Cortando el cabello al cliente {numero}")
                    self.actualizar_estado(f"Cliente {numero}", "En el sillón")
                    with self.mutex:
                        self.datos["cliente_en_sillon"] = numero
                    self.registrar_evento(f"El barbero llama al cliente {numero}; comienza el corte.")
                    if not self.esperar(1.0 / velocidad):
                        self.actualizar_estado(f"Cliente {numero}", "Cancelado")
                        evento_atendido.set()
                        break
                    estadisticas["atendidos"] += 1
                    self.actualizar_estado(f"Cliente {numero}", "Atendido")
                    with self.mutex:
                        self.datos["cliente_en_sillon"] = None
                    publicar_sala()
                    evento_atendido.set()
                    self.registrar_evento(f"El barbero termina con el cliente {numero}.")
            finally:
                # Si se detuvo la simulación, liberar a los clientes que seguían en la sala.
                with mutex_sala:
                    pendientes = list(cola)
                    cola.clear()
                    publicar_sala()
                for numero, evento_atendido in pendientes:
                    self.actualizar_estado(f"Cliente {numero}", "Cancelado")
                    evento_atendido.set()
                self.actualizar_estado("Barbero", "Terminado")

        def cliente(numero):
            nombre = f"Cliente {numero}"
            self.actualizar_estado(nombre, "Llegando")
            if self.detener_evento.is_set():
                self.actualizar_estado(nombre, "Cancelado")
                return
            evento_atendido = threading.Event()
            with mutex_sala:
                # Las sillas cuentan solo a quienes esperan, no al cliente en corte.
                if len(cola) >= sillas:
                    estadisticas["rechazados"] += 1
                    publicar_sala()
                    self.actualizar_estado(nombre, "Se fue: sala llena")
                    self.registrar_evento(f"{nombre} se retira porque las {sillas} sillas de espera están ocupadas.")
                    return
                cola.append((numero, evento_atendido))
                estadisticas["aceptados"] += 1
                publicar_sala()
                self.actualizar_estado(nombre, "Esperando")
                self.registrar_evento(f"{nombre} ocupa una silla de espera. Personas en cola: {len(cola)}.")
                clientes_en_espera.release()      # signal: un cliente más (despierta al barbero si dormía)
            while not evento_atendido.wait(timeout=0.08):
                if self.detener_evento.is_set():
                    self.actualizar_estado(nombre, "Cancelado")
                    return

        hilo_barbero = threading.Thread(target=barbero, name="Barbero", daemon=True)
        self.hilos.append(hilo_barbero)
        hilo_barbero.start()
        hilos_clientes = []
        for numero in range(1, cantidad_clientes + 1):
            if self.detener_evento.is_set():
                break
            hilo = threading.Thread(target=cliente, args=(numero,), name=f"Cliente-{numero}", daemon=True)
            hilos_clientes.append(hilo)
            self.hilos.append(hilo)
            hilo.start()
            if not self.esperar(0.35 / velocidad):
                break
        for hilo in hilos_clientes:
            hilo.join()
        llegadas_completas.set()
        hilo_barbero.join(timeout=10)
        if hilo_barbero.is_alive():
            self.detener_evento.set()
            hilo_barbero.join(timeout=1)
        self.registrar_evento(
            f"Barbería finalizada: atendidos={estadisticas['atendidos']}, "
            f"rechazados={estadisticas['rechazados']}, aceptados={estadisticas['aceptados']}."
        )

    # --------------------------------------------------
    # 5. PROBLEMA DE LOS FUMADORES (Patil, con "pushers")
    # --------------------------------------------------
    def fumadores(self, rondas=6, velocidad=1.0):
        """Fumadores con la solución clásica de los intermediarios (pushers).

        - El AGENTE sólo pone dos ingredientes (signal a dos semáforos) y NO sabe
          quién va a fumar.
        - Cada PUSHER espera un ingrediente concreto y lleva la cuenta de lo que
          hay en la mesa. Cuando ya hay dos ingredientes, despierta al fumador
          que tiene el tercero.
        - Los FUMADORES nunca compiten por ingredientes sueltos, por eso no hay
          deadlock (el problema original: dos fumadores se quedan cada uno con
          un ingrediente y esperan el que tiene el otro).
        """
        rondas = max(1, min(20, int(rondas)))
        velocidad = max(0.25, min(3.0, float(velocidad)))
        # El fumador i posee el ingrediente i y necesita los otros dos.
        nombres_ingredientes = ["Tabaco", "Papel", "Fósforos"]

        agente_sem = threading.Semaphore(1)                               # mesa libre
        ingrediente = [threading.Semaphore(0) for _ in range(3)]          # lo que pone el agente
        despertar_fumador = [threading.Semaphore(0) for _ in range(3)]    # lo que dispara el pusher
        mutex_mesa = threading.Lock()
        hay_en_mesa = [False] * 3                                         # registro de los pushers
        terminado = threading.Event()

        with self.mutex:
            self.datos.update({
                "rondas_configuradas": rondas,
                "ronda_actual": 0,
                "fumador_actual": None,
                "ingredientes_mesa": [],
                "rondas_completadas": 0,
                "ingredientes_propios": nombres_ingredientes,
                "velocidad": velocidad,
            })
        self.actualizar_estado("Agente", "Preparado")

        def debe_seguir():
            return not terminado.is_set() and not self.detener_evento.is_set()

        def pusher(x):
            nombre = f"Pusher {nombres_ingredientes[x]}"
            otros = [j for j in range(3) if j != x]
            self.actualizar_estado(nombre, "Esperando su ingrediente")
            while debe_seguir():
                if not ingrediente[x].acquire(timeout=0.1):
                    continue
                with mutex_mesa:
                    for a in otros:
                        if hay_en_mesa[a]:
                            # Ya había otro ingrediente: la mesa tiene el par completo.
                            hay_en_mesa[a] = False
                            b = 3 - x - a            # el fumador que posee el tercero
                            with self.mutex:
                                self.datos["fumador_actual"] = b + 1
                            self.actualizar_estado(nombre, f"Par completo: despierta al Fumador {b + 1}")
                            self.registrar_evento(
                                f"{nombre}: ya hay {nombres_ingredientes[a]} y {nombres_ingredientes[x]}; "
                                f"despierta al Fumador {b + 1} (tiene {nombres_ingredientes[b]})."
                            )
                            despertar_fumador[b].release()
                            break
                    else:
                        hay_en_mesa[x] = True
                        self.actualizar_estado(nombre, f"Registró {nombres_ingredientes[x]}; espera el otro")
                        self.registrar_evento(
                            f"{nombre}: registra {nombres_ingredientes[x]} y espera el segundo ingrediente."
                        )
            self.actualizar_estado(nombre, "Terminado")

        def fumador(numero):
            nombre = f"Fumador {numero + 1}"
            propio = nombres_ingredientes[numero]
            recoge = [n for k, n in enumerate(nombres_ingredientes) if k != numero]
            self.actualizar_estado(nombre, f"Esperando; tiene {propio}")
            while debe_seguir():
                if not despertar_fumador[numero].acquire(timeout=0.1):
                    continue
                with self.mutex:
                    self.datos["ingredientes_mesa"] = []         # los recogió: la mesa queda libre
                self.actualizar_estado(nombre, "Preparando cigarrillo")
                self.registrar_evento(
                    f"{nombre} tiene {propio}; recoge {recoge[0]} y {recoge[1]} de la mesa."
                )
                if not self.esperar(0.55 / velocidad):
                    break
                self.actualizar_estado(nombre, "Fumando")
                self.registrar_evento(f"{nombre} está fumando.")
                if not self.esperar(0.9 / velocidad):
                    break
                with self.mutex:
                    self.datos["rondas_completadas"] = self.datos.get("rondas_completadas", 0) + 1
                self.actualizar_estado(nombre, f"Esperando; tiene {propio}")
                agente_sem.release()                              # avisa al agente: mesa libre

        def agente():
            for ronda in range(1, rondas + 1):
                self.actualizar_estado("Agente", "Esperando mesa libre")
                if not self._adquirir(agente_sem):
                    break
                # Elige al azar qué ingrediente NO pone (o sea, qué fumador debería fumar),
                # pero sólo coloca los dos que sí pone: el agente no avisa a nadie.
                falta = random.randrange(3)
                puestos = [x for x in range(3) if x != falta]
                random.shuffle(puestos)
                nombres = [nombres_ingredientes[x] for x in puestos]
                with self.mutex:
                    self.datos["ronda_actual"] = ronda
                    self.datos["fumador_actual"] = None
                    self.datos["ingredientes_mesa"] = nombres[:]
                self.actualizar_estado("Agente", "Colocando ingredientes")
                self.registrar_evento(
                    f"Ronda {ronda}: el agente coloca {nombres[0]} y {nombres[1]} sobre la mesa."
                )
                if not self.esperar(0.3 / velocidad):
                    break
                for x in puestos:
                    ingrediente[x].release()                      # signal(ingrediente)
                self.actualizar_estado("Agente", "Ingredientes en la mesa; espera al fumador")
            else:
                # Tras la última ronda, esperar a que el último fumador termine.
                self.actualizar_estado("Agente", "Esperando al último fumador")
                self._adquirir(agente_sem)
            terminado.set()
            self.actualizar_estado("Agente", "Terminado")

        hilos_pushers = [
            threading.Thread(target=pusher, args=(i,), name=f"Pusher-{i + 1}", daemon=True)
            for i in range(3)
        ]
        hilos_fumadores = [
            threading.Thread(target=fumador, args=(i,), name=f"Fumador-{i + 1}", daemon=True)
            for i in range(3)
        ]
        hilo_agente = threading.Thread(target=agente, name="Agente", daemon=True)
        self.hilos.extend(hilos_pushers + hilos_fumadores + [hilo_agente])
        for hilo in hilos_pushers + hilos_fumadores:
            hilo.start()
        hilo_agente.start()
        hilo_agente.join()
        terminado.set()
        for hilo in hilos_pushers + hilos_fumadores:
            hilo.join(timeout=1)
        for i, propio in enumerate(nombres_ingredientes, start=1):
            self.actualizar_estado(f"Fumador {i}", f"Terminado (tenía {propio})")
        with self.mutex:
            self.datos["ingredientes_mesa"] = []
            completadas = self.datos.get("rondas_completadas", 0)
        self.registrar_evento(
            f"Problema de los fumadores finalizado: {completadas} rondas completadas."
        )
