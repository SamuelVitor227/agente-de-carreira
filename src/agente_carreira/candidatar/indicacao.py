"""Pedido de indicação a partir das conexões exportadas do LinkedIn (RF-CA-08).

Lê o Connections.csv da exportação de dados, acha quem trabalha na empresa da
vaga e rascunha a mensagem. O envio é sempre manual (RN-11), e os dados das
conexões não são guardados (RNF-05).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..models import PerfilMestre
from ..radar.texto import slug


@dataclass
class Conexao:
    nome: str
    empresa: str
    cargo: str
    url: str | None = None


def _linhas_csv(texto: str) -> list[dict[str, str]]:
    linhas = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas) if "First Name" in l), None)
    if inicio is None:
        return []
    leitor = csv.DictReader(io.StringIO("\n".join(linhas[inicio:])))
    return [{(k or "").strip(): (v or "").strip() for k, v in linha.items() if isinstance(k, str)} for linha in leitor]


def ler_conexoes(caminho: Path) -> list[Conexao]:
    """Aceita o Connections.csv solto ou o ZIP completo da exportação."""
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as zf:
            nome = next((n for n in zf.namelist() if Path(n).name.lower() == "connections.csv"), None)
            if nome is None:
                return []
            texto = zf.read(nome).decode("utf-8-sig", errors="replace")
    else:
        texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    return [
        Conexao(nome=" ".join(p for p in (l.get("First Name"), l.get("Last Name")) if p),
                empresa=l.get("Company", ""), cargo=l.get("Position", ""), url=l.get("URL") or None)
        for l in _linhas_csv(texto)
        if l.get("First Name")
    ]


def conexoes_na_empresa(conexoes: list[Conexao], empresa: str) -> list[Conexao]:
    alvo = slug(empresa)
    if not alvo:
        return []
    return [c for c in conexoes if c.empresa and (slug(c.empresa) == alvo or alvo in slug(c.empresa) or slug(c.empresa) in alvo)]


def rascunho_indicacao(perfil: PerfilMestre, conexao: Conexao, vaga_titulo: str, empresa: str, link: str | None) -> str:
    primeiro = conexao.nome.split()[0] if conexao.nome else ""
    linhas = [
        f"Olá, {primeiro}! Tudo bem?",
        "",
        f"Vi que você trabalha na {empresa} e estou me candidatando à vaga de {vaga_titulo}"
        + (f" ({link})" if link else "") + ".",
    ]
    if perfil.objetivo:
        linhas.append(f"Busco {perfil.objetivo[0].lower() + perfil.objetivo[1:].rstrip('.')}.")
    linhas += [
        "Se fizer sentido para você, uma indicação ou uma dica sobre o processo ajudaria muito.",
        "Sem problema nenhum se não for possível. Agradeço desde já!",
        perfil.contato.nome.split()[0],
    ]
    return "\n".join(linhas)
