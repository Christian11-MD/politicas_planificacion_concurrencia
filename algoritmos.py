import heapq
from bisect import bisect_left, bisect_right
from collections import deque

# Para que el programa no se congele con quantums diminutos y ráfagas enormes
LIMITE_TROZOS_RR = 2_000_000


# ==========================================
# UTILIDADES
# ==========================================

def _validar(procs, politica, q):
    if not procs:
        raise ValueError("No hay procesos")
    if len({p.nombre for p in procs}) != len(procs):
        raise ValueError("Nombres de proceso repetidos")
    for p in procs:
        if p.rafaga <= 0 or p.llegada < 0:
            raise ValueError(f"Datos inválidos en {p.nombre}")
    if politica not in ("FCFS", "SJF", "SRTF", "PRIORIDAD", "RR"):
        raise ValueError(f"Política desconocida: {politica}")
    if politica == "RR":
        if q is None or q <= 0:
            raise ValueError("Round Robin necesita un quantum mayor que 0")
        if sum(p.rafaga for p in procs) / q > LIMITE_TROZOS_RR:
            raise ValueError("Quantum demasiado pequeño para estas ráfagas: la simulación sería enorme")


def _agregar(segs, ini, fin, nombre):
    """Agrega el tramo [ini, fin) de 'nombre' (None = CPU ociosa). Une tramos seguidos iguales."""
    if fin <= ini:
        return
    if segs and segs[-1][2] == nombre and segs[-1][1] == ini:
        segs[-1] = (segs[-1][0], fin, nombre)
    else:
        segs.append((ini, fin, nombre))


def _clave_fija(p, orden, politica):
    """Criterio de elección de FCFS, SJF y Prioridad (menor clave = va primero)."""
    base = (p.llegada, orden[p.nombre])
    if politica == "FCFS":
        return base
    if politica == "SJF":
        return (p.rafaga,) + base
    return (p.prioridad,) + base            # PRIORIDAD (número bajo = prioridad alta)


# ==========================================
# POLÍTICAS
# Cada una devuelve una lista de tramos (inicio, fin, proceso). El proceso es None
# cuando la CPU está ociosa. Esa lista ES el diagrama de Gantt.
# ==========================================

def planificar(procs, politica, q=None):
    """Simula la política y devuelve la lista de tramos [(inicio, fin, nombre_o_None), ...]."""
    _validar(procs, politica, q)
    if politica == "RR":
        return _rr(procs, q)
    if politica == "SRTF":
        return _srtf(procs)
    return _sin_desalojo(procs, politica)


def _sin_desalojo(procs, politica):
    """FCFS, SJF y Prioridad: el elegido corre hasta terminar."""
    orden = {p.nombre: i for i, p in enumerate(procs)}
    por_nombre = {p.nombre: p for p in procs}
    llegadas = sorted(procs, key=lambda p: (p.llegada, orden[p.nombre]))
    n = len(llegadas)
    listos, segs, t, i = [], [], 0, 0           # listos = montículo (mínimo primero)

    while i < n or listos:
        while i < n and llegadas[i].llegada <= t:
            p = llegadas[i]
            heapq.heappush(listos, (_clave_fija(p, orden, politica), p.nombre))
            i += 1

        if not listos:                          # CPU ociosa hasta la próxima llegada
            sig = llegadas[i].llegada
            _agregar(segs, t, sig, None)
            t = sig
            continue

        _, nombre = heapq.heappop(listos)
        p = por_nombre[nombre]
        _agregar(segs, t, t + p.rafaga, nombre)
        t += p.rafaga
    return segs


def _srtf(procs):
    """SRTF: se reevalúa cuando llega un proceso o cuando el actual termina."""
    orden = {p.nombre: i for i, p in enumerate(procs)}
    por_nombre = {p.nombre: p for p in procs}
    llegadas = sorted(procs, key=lambda p: (p.llegada, orden[p.nombre]))
    n = len(llegadas)
    listos, rem, segs = [], {}, []
    actual, t, i = None, 0, 0

    while i < n or listos or actual is not None:
        while i < n and llegadas[i].llegada <= t:
            p = llegadas[i]
            rem[p.nombre] = p.rafaga
            heapq.heappush(listos, (p.rafaga, p.llegada, orden[p.nombre], p.nombre))
            i += 1

        # ¿Alguien tiene ESTRICTAMENTE menos tiempo restante que el actual? (empate: sigue el actual)
        if actual is not None and listos and listos[0][0] < rem[actual]:
            p = por_nombre[actual]
            heapq.heappush(listos, (rem[actual], p.llegada, orden[actual], actual))
            actual = None

        if actual is None:
            if not listos:                      # CPU ociosa hasta la próxima llegada
                sig = llegadas[i].llegada
                _agregar(segs, t, sig, None)
                t = sig
                continue
            actual = heapq.heappop(listos)[3]

        # Corre hasta terminar o hasta la próxima llegada (lo que pase primero)
        fin = t + rem[actual]
        if i < n and llegadas[i].llegada < fin:
            fin = llegadas[i].llegada
        _agregar(segs, t, fin, actual)
        rem[actual] -= fin - t
        t = fin
        if rem[actual] == 0:
            actual = None
    return segs


def _rr(procs, q):
    """Round Robin. Convención: el proceso que llega entra a la cola ANTES que el expulsado."""
    llegadas = sorted(procs, key=lambda p: p.llegada)     # estable: respeta el orden ingresado
    rem = {p.nombre: p.rafaga for p in procs}
    n = len(llegadas)
    cola, segs, t, i = deque(), [], 0, 0

    while i < n or cola:
        while i < n and llegadas[i].llegada <= t:
            cola.append(llegadas[i].nombre)
            i += 1

        if not cola:                            # CPU ociosa hasta la próxima llegada
            sig = llegadas[i].llegada
            _agregar(segs, t, sig, None)
            t = sig
            continue

        nom = cola.popleft()
        corre = min(q, rem[nom])
        _agregar(segs, t, t + corre, nom)
        t += corre
        rem[nom] -= corre

        while i < n and llegadas[i].llegada <= t:       # primero entran los que llegaron...
            cola.append(llegadas[i].nombre)
            i += 1
        if rem[nom] > 0:                                # ...y después el expulsado
            cola.append(nom)
    return segs


# ==========================================
# COLA DE LISTOS EN UN INSTANTE t
# ==========================================

def preparar_inicios(segmentos):
    """Lista con el inicio de cada tramo (sirve para buscar rápido por tiempo)."""
    return [s[0] for s in segmentos]


def cola_listos(procs, segmentos, politica, t, inicios=None):
    """Cola de listos en el instante t, calculada a partir del Gantt.

    Devuelve (en_cpu, lista) donde lista tiene (nombre, restante, prioridad, llegada)
    ordenada como la política atendería a los procesos (el primero es el siguiente).
    """
    if inicios is None:
        inicios = preparar_inicios(segmentos)

    # Cuánto ejecutó cada proceso antes de t, y cuándo terminó su último tramo
    k = bisect_left(inicios, t)                 # tramos que empiezan antes de t
    hecho, ultimo = {}, {}
    for idx in range(k):
        ini, fin, nom = segmentos[idx]
        if nom is None:
            continue
        corte = min(fin, t)
        hecho[nom] = hecho.get(nom, 0) + (corte - ini)
        ultimo[nom] = corte

    # ¿Quién tiene la CPU justo en t?
    en_cpu = None
    j = bisect_right(inicios, t) - 1
    if j >= 0 and segmentos[j][0] <= t < segmentos[j][1]:
        en_cpu = segmentos[j][2]

    orden = {p.nombre: i for i, p in enumerate(procs)}
    listos = []
    for p in procs:
        if p.llegada > t or p.nombre == en_cpu:
            continue
        resta = p.rafaga - hecho.get(p.nombre, 0)
        if resta <= 0:
            continue
        listos.append((p, resta))

    def clave(par):
        p, resta = par
        base = (p.llegada, orden[p.nombre])
        if politica == "FCFS":
            return base
        if politica == "SJF":
            return (p.rafaga,) + base
        if politica == "PRIORIDAD":
            return (p.prioridad,) + base
        if politica == "SRTF":
            return (resta,) + base
        # RR: orden de entrada a la cola (llegada, o fin de su último turno)
        entrada = ultimo.get(p.nombre, p.llegada)
        return (entrada, 1 if p.nombre in ultimo else 0, orden[p.nombre])

    listos.sort(key=clave)
    return en_cpu, [(p.nombre, resta, p.prioridad, p.llegada) for p, resta in listos]