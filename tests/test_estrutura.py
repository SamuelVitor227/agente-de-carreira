"""Estrutura do código: toda importação relativa resolve, inclusive as feitas dentro de funções.

As telas do app e os comandos importam muita coisa só na hora de usar (dentro da função). Um erro nessas
importações só aparece quando a tela abre; este teste pega antes, sem abrir janela nenhuma.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import agente_carreira

PACOTE = Path(agente_carreira.__file__).parent


def _importacoes_relativas():
    for arquivo in sorted(PACOTE.rglob("*.py")):
        partes = arquivo.relative_to(PACOTE.parent).with_suffix("").parts
        pacote = ".".join(partes[:-1]) if arquivo.name != "__init__.py" else ".".join(partes[:-1])
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.ImportFrom) and no.level:
                yield arquivo, no, importlib.util.resolve_name("." * no.level + (no.module or ""), pacote)


def test_toda_importacao_relativa_resolve():
    problemas = []
    for arquivo, no, alvo in _importacoes_relativas():
        try:
            modulo = importlib.import_module(alvo)
        except ImportError as erro:
            problemas.append(f"{arquivo.name}:{no.lineno}: {alvo} ({erro})")
            continue
        for nome in no.names:
            if nome.name == "*" or hasattr(modulo, nome.name):
                continue
            try:
                importlib.import_module(f"{alvo}.{nome.name}")
            except ImportError:
                problemas.append(f"{arquivo.name}:{no.lineno}: {alvo} não tem {nome.name}")
    assert not problemas, "\n".join(problemas)


def test_cada_tela_do_menu_tem_o_seu_metodo():
    from agente_carreira.app.janela import MENU, App

    for chave, _nome in MENU:
        assert callable(getattr(App, f"_pagina_{chave}", None)), chave
