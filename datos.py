import colorsys

# Nombre que se ve en el combo -> nombre interno de la política
ALGORITMOS = {
    "FCFS": "FCFS",
    "SJF": "SJF",
    "SRTF": "SRTF",
    "Round Robin": "RR",
    "Prioridad": "PRIORIDAD",
}

# Máximo de procesos que acepta el programa (importar TXT o generar)
LIMITE_PROCESOS = 20000

# Colores de las filas del Gantt (uno por proceso, se repiten si hay más de 10)
COLORES = ["#c6b219", "#07b7a8", "#b40a73", "#000000", "#b07a8f",
           "#cc0c0c", "#0ec061", "#ff9da7", "#9c755f", "#86bcb6"]



def color_proceso(i):
    """Color del proceso número i. Los primeros usan COLORES; el resto se genera solo."""
    if i < len(COLORES):
        return COLORES[i]
    tono = (i * 0.61803398875) % 1.0          # número áureo: tonos bien repartidos
    r, g, b = colorsys.hsv_to_rgb(tono, 0.55, 0.85)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))



# Cargas de procesos del taller: (nombre, llegada, ejecución, prioridad)
EJEMPLOS = {
    "Ejercicio 1": [("P0", 0, 6, 0), ("P1", 1, 3, 0), ("P2", 3, 2, 0), ("P3", 5, 4, 0)],
    "Ejercicio 2": [("A", 0, 2, 0), ("B", 0, 1, 0), ("C", 0, 8, 0), ("D", 0, 3, 0), ("E", 0, 5, 0)],
    "Ejercicio 3": [("A", 0, 3, 0), ("B", 1, 5, 0), ("C", 3, 2, 0), ("D", 9, 5, 0), ("E", 12, 5, 0)],
    "Ejercicio 5": [("P0", 0, 6, 0), ("P1", 1, 3, 0), ("P2", 3, 2, 0), ("P3", 5, 4, 0)],
    "Ejercicio 6": [("A", 0, 5, 0), ("B", 0, 2, 0), ("C", 0, 6, 0), ("D", 0, 4, 0), ("E", 0, 3, 0)],
    "Ejercicio 7": [("P1", 0, 10, 3), ("P2", 0, 1, 1), ("P3", 0, 2, 3), ("P4", 0, 1, 4), ("P5", 0, 5, 2)],
}