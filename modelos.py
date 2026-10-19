from dataclasses import dataclass


@dataclass
class Proc:
    nombre: str
    llegada: int
    rafaga: int
    prioridad: int = 0