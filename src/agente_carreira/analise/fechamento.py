"""Sugestões para fechar lacunas de verdade (RF-CV-06).

Para cada termo sem lastro no perfil, sugere curso, certificação ou projeto
de portfólio — nunca inventar no CV (RN-02) —, priorizando catálogos que o
usuário já tem (DIO primeiro). O mapa é configuração e cresce com o uso.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .lacunas import ItemLacuna

CATALOGOS_DO_USUARIO = ["DIO"]  # ordem de prioridade


class Sugestao(BaseModel):
    termo: str
    tipo: Literal["curso", "certificacao", "projeto"]
    descricao: str
    catalogo: str | None = None


# Sugestões específicas por termo (chave em minúsculas).
SUGESTOES_POR_TERMO: dict[str, list[Sugestao]] = {
    "aws": [
        Sugestao(termo="AWS", tipo="curso", descricao="Formação AWS Cloud (trilha gratuita da DIO)", catalogo="DIO"),
        Sugestao(termo="AWS", tipo="certificacao", descricao="AWS Certified Cloud Practitioner (fundacional)"),
        Sugestao(termo="AWS", tipo="projeto", descricao="Publicar uma API do portfólio na AWS (EC2/Lambda + RDS) e documentar no README"),
    ],
    "azure": [
        Sugestao(termo="Azure", tipo="curso", descricao="Bootcamps Microsoft Azure da DIO", catalogo="DIO"),
        Sugestao(termo="Azure", tipo="certificacao", descricao="Microsoft AZ-900 (Azure Fundamentals)"),
    ],
    "docker": [
        Sugestao(termo="Docker", tipo="curso", descricao="Curso de Docker da DIO", catalogo="DIO"),
        Sugestao(termo="Docker", tipo="projeto", descricao="Containerizar um projeto existente do GitHub com Dockerfile e docker-compose"),
    ],
    "kubernetes": [
        Sugestao(termo="Kubernetes", tipo="curso", descricao="Trilha de Kubernetes da DIO", catalogo="DIO"),
        Sugestao(termo="Kubernetes", tipo="projeto", descricao="Orquestrar os containers de um projeto próprio com manifests básicos"),
    ],
    "sql": [
        Sugestao(termo="SQL", tipo="curso", descricao="Trilha de banco de dados/SQL da DIO", catalogo="DIO"),
        Sugestao(termo="SQL", tipo="projeto", descricao="Modelar e consultar um banco relacional em um projeto do portfólio"),
    ],
    "sql server": [
        Sugestao(termo="SQL Server", tipo="curso", descricao="Cursos de SQL Server/T-SQL da DIO", catalogo="DIO"),
        Sugestao(termo="SQL Server", tipo="projeto", descricao="Usar SQL Server (LocalDB/Express) como banco de um projeto .NET do portfólio"),
    ],
    "c#": [
        Sugestao(termo="C#", tipo="curso", descricao="Formação C# Developer da DIO", catalogo="DIO"),
        Sugestao(termo="C#", tipo="projeto", descricao="API REST em C#/.NET no GitHub com testes e README"),
    ],
    ".net": [
        Sugestao(termo=".NET", tipo="curso", descricao="Formação .NET Developer da DIO", catalogo="DIO"),
        Sugestao(termo=".NET", tipo="projeto", descricao="API ASP.NET Core com Entity Framework publicada no GitHub"),
    ],
    "python": [
        Sugestao(termo="Python", tipo="curso", descricao="Formação Python Developer da DIO", catalogo="DIO"),
        Sugestao(termo="Python", tipo="projeto", descricao="Automação ou API em Python no portfólio"),
    ],
    "react": [
        Sugestao(termo="React", tipo="curso", descricao="Formação React Developer da DIO", catalogo="DIO"),
    ],
    "react native": [
        Sugestao(termo="React Native", tipo="curso", descricao="Trilha de React Native da DIO", catalogo="DIO"),
        Sugestao(termo="React Native", tipo="projeto", descricao="App simples em React Native publicado no GitHub com capturas de tela"),
    ],
    "git": [
        Sugestao(termo="Git", tipo="curso", descricao="Curso de Git/GitHub da DIO", catalogo="DIO"),
        Sugestao(termo="Git", tipo="projeto", descricao="Manter o portfólio no GitHub com commits frequentes e branches"),
    ],
    "scrum": [
        Sugestao(termo="Scrum", tipo="curso", descricao="Cursos de metodologias ágeis da DIO", catalogo="DIO"),
        Sugestao(termo="Scrum", tipo="certificacao", descricao="Scrum Foundation (SFC) ou PSM I como meta"),
    ],
    "inglês": [
        Sugestao(termo="Inglês", tipo="curso", descricao="Curso regular de inglês + prática técnica (documentação, vídeos); registrar o nível real no CV"),
    ],
}


def _prioridade_catalogo(sugestao: Sugestao) -> int:
    if sugestao.catalogo in CATALOGOS_DO_USUARIO:
        return CATALOGOS_DO_USUARIO.index(sugestao.catalogo)
    return len(CATALOGOS_DO_USUARIO)


def sugerir_fechamento(lacunas_sem_lastro: list[ItemLacuna]) -> list[Sugestao]:
    """Sugestões para cada termo do grupo 'você não tem', na ordem de peso nas vagas."""
    sugestoes: list[Sugestao] = []
    for item in lacunas_sem_lastro:
        especificas = SUGESTOES_POR_TERMO.get(item.termo.lower())
        if especificas:
            sugestoes.extend(sorted(especificas, key=_prioridade_catalogo))
        else:
            catalogos = " ou ".join(CATALOGOS_DO_USUARIO)
            sugestoes.append(Sugestao(
                termo=item.termo, tipo="projeto",
                descricao=f"Aplicar {item.termo} em um projeto de portfólio no GitHub (com README contando o que foi feito)",
            ))
            sugestoes.append(Sugestao(
                termo=item.termo, tipo="curso",
                descricao=f"Procurar curso de {item.termo} nos catálogos que você já tem ({catalogos})",
                catalogo=CATALOGOS_DO_USUARIO[0],
            ))
    return sugestoes
