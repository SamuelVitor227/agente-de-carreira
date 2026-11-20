"""Gravação segura dos arquivos de dados (data/).

O app roda várias tarefas ao mesmo tempo, cada uma no seu processo, e todas gravam nos mesmos arquivos.
Três garantias:

- gravação atômica: o conteúdo novo vai para um arquivo ao lado e só então troca o antigo. Uma tarefa
  parada no meio nunca deixa um arquivo pela metade;
- trava entre processos enquanto um arquivo é gravado;
- mescla em três vias: quem grava relê o arquivo e mantém o que outra tarefa mudou desde que ele o leu.
  Exemplo: a busca de vagas termina e não desfaz o "Não tenho interesse" clicado no meio dela.

Arquivo danificado (JSON inválido) é trocado pela cópia de segurança mais recente (copias.py), com aviso.
"""

from __future__ import annotations

import json
import os
import sys
import time
import weakref
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal, TypeVar

from pydantic import BaseModel

Preferencia = Literal["meu", "disco"]
M = TypeVar("M", bound=BaseModel)

_AUSENTE: Any = type("_Ausente", (), {"__repr__": lambda self: "<ausente>"})()
ESPERA_TRAVA = 15.0  # segundos esperando outra tarefa terminar de gravar


# ---------------------------------------------------------------- gravação atômica

def gravar_texto(caminho: Path, texto: str, *, tentativas: int = 30) -> Path:
    """Grava o arquivo inteiro de uma vez: ou fica o conteúdo novo, ou o antigo (nunca metade)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(f".{caminho.name}.{os.getpid()}.tmp")
    try:
        with open(temporario, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        for tentativa in range(tentativas):
            try:
                os.replace(temporario, caminho)
                return caminho
            except PermissionError:  # OneDrive ou antivírus lendo o arquivo naquele instante
                if tentativa == tentativas - 1:
                    raise
                time.sleep(0.1)
    finally:
        if temporario.exists():
            temporario.unlink(missing_ok=True)
    return caminho


# ---------------------------------------------------------------- trava entre processos

class TravaArquivo:
    """Trava de arquivo entre processos (msvcrt no Windows, flock nos outros). Some sozinha se o processo morrer."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = Path(caminho)
        self._arquivo = None

    def tentar(self) -> bool:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = open(self.caminho, "a+b")  # noqa: SIM115 - fica aberto enquanto a trava durar
        try:
            if os.name == "nt":
                import msvcrt

                arquivo.seek(0)
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            arquivo.close()
            return False
        self._arquivo = arquivo
        return True

    def soltar(self) -> None:
        if self._arquivo is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._arquivo.seek(0)
                msvcrt.locking(self._arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._arquivo.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._arquivo.close()
            self._arquivo = None


@contextmanager
def travado(caminho: Path, espera: float = ESPERA_TRAVA) -> Iterator[bool]:
    """Espera a vez de gravar `caminho`. Devolve False se a espera acabou (grava assim mesmo: melhor que perder)."""
    from .storage import diretorio_dados

    trava = TravaArquivo(diretorio_dados() / "travas" / f"{Path(caminho).name}.trava")
    limite = time.monotonic() + espera
    obtida = trava.tentar()
    while not obtida and time.monotonic() < limite:
        time.sleep(0.05)
        obtida = trava.tentar()
    try:
        yield obtida
    finally:
        trava.soltar()


# ---------------------------------------------------------------- mescla em três vias

def _lista_com_ids(valor: Any) -> bool:
    if not isinstance(valor, list) or not all(isinstance(x, dict) and "id" in x for x in valor):
        return False
    ids = [x["id"] for x in valor]
    return len(ids) == len(set(map(repr, ids)))


def _lista_simples(valor: Any) -> bool:
    return isinstance(valor, list) and all(x is None or isinstance(x, (str, int, float, bool)) for x in valor)


def mesclar(base: Any, meu: Any, disco: Any, preferir: Preferencia = "meu") -> Any:
    """Junta duas versões de um JSON que partiram da mesma `base`.

    Cada lado fica com o que só ele mudou. Dicionários se juntam chave a chave; listas de itens com "id"
    (vagas, candidaturas, lembretes), item a item; listas de textos, como conjuntos. Quando os dois mudaram
    o mesmo valor, vence `preferir`: "meu" para ações da pessoa, "disco" para tarefas automáticas (a busca
    não desfaz o que a pessoa fez enquanto ela rodava).
    """
    if meu == disco:
        return meu
    if meu == base:
        return disco
    if disco == base:
        return meu
    if isinstance(meu, dict) and isinstance(disco, dict):
        b = base if isinstance(base, dict) else {}
        resultado = {}
        for chave in [*meu, *(k for k in disco if k not in meu)]:
            valor = mesclar(b.get(chave, _AUSENTE), meu.get(chave, _AUSENTE), disco.get(chave, _AUSENTE), preferir)
            if valor is not _AUSENTE:
                resultado[chave] = valor
        return resultado
    if _lista_com_ids(meu) and _lista_com_ids(disco) and (base is _AUSENTE or _lista_com_ids(base)):
        b = {repr(x["id"]): x for x in base} if isinstance(base, list) else {}
        m = {repr(x["id"]): x for x in meu}
        d = {repr(x["id"]): x for x in disco}
        lista = []
        for chave in [*m, *(k for k in d if k not in m)]:
            valor = mesclar(b.get(chave, _AUSENTE), m.get(chave, _AUSENTE), d.get(chave, _AUSENTE), preferir)
            if valor is not _AUSENTE:
                lista.append(valor)
        return lista
    if _lista_simples(meu) and _lista_simples(disco) and (base is _AUSENTE or _lista_simples(base)):
        b = base if isinstance(base, list) else []
        removidos_no_disco = [x for x in b if x not in disco]
        return [x for x in meu if x not in removidos_no_disco] + [x for x in disco if x not in b and x not in meu]
    return meu if preferir == "meu" else disco


# ---------------------------------------------------------------- modelos guardados em JSON

# O que cada objeto tinha quando foi lido (ou gravado) por este processo: a "base" da mescla.
_INSTANTANEOS: dict[int, tuple[weakref.ref, Any]] = {}


def _guardar_instantaneo(obj: BaseModel, dados: Any) -> None:
    chave = id(obj)
    _INSTANTANEOS[chave] = (weakref.ref(obj, lambda _ref, k=chave: _INSTANTANEOS.pop(k, None)), dados)


def _instantaneo(obj: BaseModel) -> Any:
    registro = _INSTANTANEOS.get(id(obj))
    if registro is None or registro[0]() is not obj:
        return None
    return registro[1]


class ArquivoDanificado(ValueError):
    """O arquivo de dados está ilegível e não há cópia de segurança para voltar."""


def _avisar(texto: str) -> None:
    try:
        print(f"Aviso: {texto}", file=sys.stderr)
    except (OSError, ValueError):
        pass


def _recuperar(caminho: Path, modelo: type[M], erro: Exception) -> M:
    """Põe o arquivo danificado de lado e volta para a cópia de segurança mais recente que estiver legível."""
    from .copias import copias_do_arquivo

    reserva = caminho.with_name(f"{caminho.stem}.danificado-{datetime.now():%Y%m%d-%H%M%S}{caminho.suffix}")
    for copia in copias_do_arquivo(caminho.name):
        try:
            texto = copia.read_text(encoding="utf-8")
            obj = modelo.model_validate_json(texto)
        except (OSError, ValueError):
            continue
        os.replace(caminho, reserva)
        gravar_texto(caminho, texto)
        _avisar(f"{caminho.name} estava danificado; voltei para a cópia de segurança de {copia.parent.name}. "
                f"O arquivo danificado ficou em {reserva.name}.")
        return obj
    raise ArquivoDanificado(
        f"O arquivo {caminho} está danificado ({type(erro).__name__}) e não há cópia de segurança legível. "
        "Restaure uma cópia em Configurações > Cópias de segurança, ou apague o arquivo para começar do zero."
    ) from erro


def ler_modelo(caminho: Path, modelo: type[M]) -> M:
    """Lê o arquivo (ou um objeto vazio se ele não existe) e lembra como ele estava, para a mescla ao gravar."""
    caminho = Path(caminho)
    if caminho.is_file():
        try:
            obj = modelo.model_validate_json(caminho.read_text(encoding="utf-8"))
        except ValueError as erro:  # JSON inválido ou fora do formato
            obj = _recuperar(caminho, modelo, erro)
    else:
        obj = modelo()
    _guardar_instantaneo(obj, obj.model_dump(mode="json"))
    return obj


def _modelos_em(tipo: Any) -> list[type[BaseModel]]:
    """Os modelos dentro de uma anotação de tipo (X, X | None...)."""
    import types
    import typing

    if isinstance(tipo, type) and issubclass(tipo, BaseModel):
        return [tipo]
    if typing.get_origin(tipo) in (typing.Union, types.UnionType):
        return [m for arg in typing.get_args(tipo) for m in _modelos_em(arg)]
    return []


def preservar_desconhecidos(final: Any, bruto: Any, tipo: Any) -> Any:
    """Põe de volta em `final` os campos do arquivo que este código não conhece.

    Um processo com uma versão antiga do agente (ex.: o app aberto antes de uma atualização) lê o arquivo com o
    modelo antigo e, ao gravar, apagaria as opções novas. Só campos de modelo voltam: uma chave tirada de propósito de
    um dicionário livre (ex.: uma resposta apagada do banco) continua apagada.
    """
    import typing

    modelos = _modelos_em(tipo)
    if modelos and isinstance(final, dict) and isinstance(bruto, dict):
        campos = modelos[0].model_fields
        for chave, valor in bruto.items():
            if chave not in campos:
                final.setdefault(chave, valor)
            elif chave in final:
                final[chave] = preservar_desconhecidos(final[chave], valor, campos[chave].annotation)
        return final
    origem, argumentos = typing.get_origin(tipo), typing.get_args(tipo)
    if origem is list and argumentos and _lista_com_ids(final) and _lista_com_ids(bruto):
        por_id = {repr(x["id"]): x for x in bruto}
        return [preservar_desconhecidos(x, por_id[repr(x["id"])], argumentos[0]) if repr(x["id"]) in por_id else x
                for x in final]
    if origem is dict and len(argumentos) == 2 and isinstance(final, dict) and isinstance(bruto, dict):
        return {k: preservar_desconhecidos(v, bruto[k], argumentos[1]) if k in bruto else v for k, v in final.items()}
    return final


def gravar_modelo(caminho: Path, obj: BaseModel, *, preferir: Preferencia = "meu", antes_de_trocar=None) -> Path:
    """Grava `obj` mantendo o que outra tarefa gravou desde que este processo leu o arquivo.

    `antes_de_trocar` roda com o arquivo travado, logo antes da troca (ex.: arquivar a versão anterior).
    """
    caminho = Path(caminho)
    meu = obj.model_dump(mode="json")
    base = _instantaneo(obj)
    with travado(caminho):
        final: BaseModel = obj
        bruto = None
        if caminho.is_file():
            try:
                texto_disco = caminho.read_text(encoding="utf-8")
                bruto = json.loads(texto_disco)
            except (OSError, ValueError):
                texto_disco = None  # ilegível: fica a versão deste processo
            if base is not None and texto_disco is not None:
                try:
                    disco = type(obj).model_validate_json(texto_disco).model_dump(mode="json")
                except ValueError:
                    disco = None
                if disco is not None and disco != base:
                    try:
                        final = type(obj).model_validate(mesclar(base, meu, disco, preferir))
                    except ValueError:
                        final = obj
        if antes_de_trocar is not None:
            antes_de_trocar()
        dados = preservar_desconhecidos(final.model_dump(mode="json"), bruto, type(final)) if bruto is not None else None
        gravar_texto(caminho, json.dumps(dados, ensure_ascii=False, indent=2) if dados is not None
                     else final.model_dump_json(indent=2))
    _guardar_instantaneo(obj, meu)
    return caminho


def lembrar(obj: BaseModel) -> None:
    """Marca o estado atual de `obj` como base da próxima mescla (para um pedaço de um arquivo maior)."""
    _guardar_instantaneo(obj, obj.model_dump(mode="json"))


def mesclar_modelo(obj: M, atual: M, preferir: Preferencia = "meu") -> M:
    """Junta `obj` com `atual` (relido do disco), com o que `obj` tinha quando foi lido como base."""
    base = _instantaneo(obj)
    if base is None:
        return obj
    disco = atual.model_dump(mode="json")
    if disco == base:
        return obj
    try:
        return type(obj).model_validate(mesclar(base, obj.model_dump(mode="json"), disco, preferir))
    except ValueError:
        return obj


def gravar_json(caminho: Path, dados: Any) -> Path:
    """Para arquivos pequenos sem modelo (estado do navegador, registros): só a gravação atômica."""
    return gravar_texto(caminho, json.dumps(dados, ensure_ascii=False, indent=1))
