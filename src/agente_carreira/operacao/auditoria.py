"""Log de auditoria das ações externas (RF-OP-06).

Toda ação que publica, envia, salva ou altera algo fora do agente (RN-01) é
registrada com plataforma, ação, data e hora, antes e depois, a aprovação que
a autorizou e, quando houver, a captura de tela. O arquivo é só de acréscimo
(uma linha JSON por ação): nada é reescrito nem apagado.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from ..storage import diretorio_dados

ARQUIVO = "auditoria.jsonl"
PASTA_CAPTURAS = Path("auditoria") / "capturas"


class AcaoExterna(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    quando: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    plataforma: str
    acao: str
    alvo: str
    antes: str | None = None
    depois: str | None = None
    modo: str = "copiloto"           # copiloto: o usuário aplicou; assistido: o agente preencheu
    aprovado_em: datetime | None = None
    origem_aprovacao: str            # ex.: "log LinkedIn 1a2b3c4d", "fila de aprovações"
    captura: str | None = None
    resultado: str = "aplicado"


def registrar_acao(
    *, plataforma: str, acao: str, alvo: str, origem_aprovacao: str, antes: str | None = None,
    depois: str | None = None, modo: str = "copiloto", aprovado_em: datetime | None = None,
    captura: Path | None = None, resultado: str = "aplicado",
) -> AcaoExterna:
    registro = AcaoExterna(
        plataforma=plataforma, acao=acao, alvo=alvo, antes=antes, depois=depois, modo=modo,
        aprovado_em=aprovado_em, origem_aprovacao=origem_aprovacao, resultado=resultado,
    )
    if captura is not None:
        destino = diretorio_dados() / PASTA_CAPTURAS / f"{registro.id}{captura.suffix.lower()}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(captura, destino)
        registro.captura = str(destino)
    caminho = diretorio_dados() / ARQUIVO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(registro.model_dump_json() + "\n")
    return registro


def listar_acoes(plataforma: str | None = None) -> list[AcaoExterna]:
    caminho = diretorio_dados() / ARQUIVO
    if not caminho.is_file():
        return []
    acoes = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            acao = AcaoExterna.model_validate(json.loads(linha))
            if plataforma is None or acao.plataforma == plataforma:
                acoes.append(acao)
    return acoes
