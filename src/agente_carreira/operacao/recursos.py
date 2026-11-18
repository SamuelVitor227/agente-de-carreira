"""Quanto o agente pode usar do computador: tarefas em paralelo dentro do limite de memória escolhido.

Padrão: até 20% da RAM. Cada tarefa paralela reserva uma fatia estimada (MB_POR_TAREFA); o teto de
tarefas simultâneas (MAXIMO) existe por educação com os sites, não por falta de memória.
"""

from __future__ import annotations

import os
import sys

MB_POR_TAREFA = 256      # leitura de página com Python + folga; um navegador invisível usa ~300 MB
MAXIMO = 8               # nunca mais que isso ao mesmo tempo (pausas por site continuam valendo)


def memoria_total_mb() -> int:
    if sys.platform == "win32":
        import ctypes

        class _Estado(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        estado = _Estado()
        estado.dwLength = ctypes.sizeof(_Estado)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return int(estado.ullTotalPhys // 2**20)
        return 4096
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 2**20)
    except (ValueError, OSError, AttributeError):
        return 4096


def trabalhadores(percentual: int = 20, *, total_mb: int | None = None, mb_por_tarefa: int = MB_POR_TAREFA,
                  maximo: int = MAXIMO) -> int:
    """Tarefas simultâneas que cabem em `percentual`% da RAM (mínimo 1, máximo `maximo`)."""
    orcamento = (total_mb if total_mb is not None else memoria_total_mb()) * max(1, min(percentual, 90)) / 100
    return max(1, min(maximo, int(orcamento // mb_por_tarefa)))
