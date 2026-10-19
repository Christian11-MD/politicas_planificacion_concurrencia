def calcular_metricas(procs, segmentos):
    primero, ultimo = {}, {}
    ocupado = 0
    cambios = 0
    previo = None

    for ini, fin, nom in segmentos:
        if nom is None:
            continue
        ocupado += fin - ini
        if nom not in primero:
            primero[nom] = ini
        ultimo[nom] = fin
        if previo is not None and previo != nom:
            cambios += 1                       # la CPU pasó a otro proceso
        previo = nom

    filas = []
    for p in procs:
        tf = ultimo[p.nombre]
        tr = tf - p.llegada
        tes = tr - p.rafaga
        tresp = primero[p.nombre] - p.llegada
        filas.append((p.nombre, p.llegada, p.rafaga, tf, tr, tes, tresp))

    n = len(filas)
    prom_es = sum(f[5] for f in filas) / n
    prom_r = sum(f[4] for f in filas) / n
    prom_resp = sum(f[6] for f in filas) / n
    var_es = sum((f[5] - prom_es) ** 2 for f in filas) / n      # varianza poblacional
    tiempo_total = max(f[3] for f in filas)

    globales = {
        "n": n,
        "prom_es": prom_es,
        "prom_r": prom_r,
        "prom_resp": prom_resp,
        "max_es": max(f[5] for f in filas),
        "var_es": var_es,
        "desv_es": var_es ** 0.5,
        "tiempo_total": tiempo_total,
        "ocupado": ocupado,
        "uso_cpu": ocupado / tiempo_total * 100,           # % del tiempo (desde t = 0) que la CPU trabajó
        "rendimiento": n / tiempo_total,                   # procesos terminados por unidad de tiempo
        "cambios": cambios,
    }
    return filas, globales