"""Perfil secundário em inglês (RF-LI-10).

O LinkedIn não traduz o conteúdo nem leva para o perfil em inglês as mudanças
do principal. Traduzir é escrever, então passa pelo motor de IA com
autorização (RF-IA-02): o agente monta o pacote, o usuário cola no motor,
traz a resposta de volta, e cada campo traduzido entra no fluxo de aprovação
campo a campo (RF-LI-13) antes de ser colado no LinkedIn.
"""

from __future__ import annotations

from datetime import datetime

from ..models import PerfilMestre
from .estado import chave_experiencia
from .limites import LIMITES
from .textos import gerar_experiencias, gerar_sobre, gerar_titulos

PREFIXO_CAMPO = "### CAMPO:"

PASSOS_PERFIL_INGLES = [
    "No computador (o app não tem a opção): abra seu perfil > 'Adicionar perfil em outro idioma'.",
    "Escolha Inglês; nome e sobrenome ficam como estão.",
    "Cole o título [EN] aprovado e salve — isso cria o perfil secundário.",
    "Com o perfil em inglês selecionado, edite o Sobre e cada experiência colando os textos [EN] aprovados.",
    "Mudanças futuras no perfil principal precisam ser refeitas à mão no perfil em inglês.",
]


def textos_fonte(perfil: PerfilMestre, foco: str, cargo_alvo: str, opcao_titulo: int = 1) -> dict[str, str]:
    """Textos em português que serão traduzidos, por campo do perfil em inglês."""
    fontes: dict[str, str] = {}
    titulos = gerar_titulos(perfil, foco, cargo_alvo)
    if titulos:
        indice = min(max(opcao_titulo, 1), len(titulos)) - 1
        fontes["en:titulo"] = titulos[indice].texto
    sobre = gerar_sobre(perfil, foco).texto
    if sobre:
        fontes["en:sobre"] = sobre
    for exp in gerar_experiencias(perfil):
        if exp.texto:
            fontes["en:" + chave_experiencia(exp.cargo, exp.empresa)] = exp.texto
    return fontes


def dados_enviados(fontes: dict[str, str]) -> list[str]:
    """Relação exata do que vai no prompt (transparência RF-IA-02)."""
    itens: list[str] = []
    if "en:titulo" in fontes:
        itens.append("título do LinkedIn (cargo-alvo, stack e formação)")
    if "en:sobre" in fontes:
        itens.append("seção Sobre (resumo, stack, projetos, formação e links públicos de GitHub/portfólio)")
    experiencias = sum(1 for c in fontes if c.startswith("en:experiencia:"))
    if experiencias:
        itens.append(f"{experiencias} experiência(s): cargo, empresa e texto do cargo")
    itens.append("NÃO são enviados: e-mail, telefone, endereço e documentos")
    return itens


def montar_prompt(fontes: dict[str, str], motor: str) -> str:
    linhas = [
        "# Tarefa: traduzir o perfil do LinkedIn para inglês",
        "",
        "Regras obrigatórias:",
        "- Traduza fielmente para inglês profissional. NÃO acrescente nem infle fatos, tecnologias, números ou resultados.",
        "- Mantenha como estão os nomes de empresas, instituições, projetos, tecnologias e links.",
        f"- Limites: título até {LIMITES['titulo']} caracteres; Sobre até {LIMITES['sobre']}; "
        f"cada experiência até {LIMITES['experiencia']}.",
        "- Marque com [A CONFIRMAR] qualquer trecho em que a tradução exigiu interpretação.",
        f"- Responda SOMENTE no formato abaixo: repita cada linha '{PREFIXO_CAMPO} <id>' exatamente "
        "como recebida e, na linha seguinte, o texto traduzido.",
        "",
        "## Textos de origem (português)",
        "",
    ]
    for campo, texto in fontes.items():
        linhas += [f"{PREFIXO_CAMPO} {campo}", texto, ""]
    linhas += [
        "---",
        f"(Pacote gerado pelo Agente de Carreira em {datetime.now():%d/%m/%Y %H:%M} "
        f"para o motor {motor}; revisão humana obrigatória antes de qualquer uso.)",
    ]
    return "\n".join(linhas)


def ler_resposta(texto: str) -> dict[str, str]:
    """Extrai os campos traduzidos da resposta do motor (só campos 'en:')."""
    campos: dict[str, str] = {}
    atual: str | None = None
    buffer: list[str] = []

    def fechar() -> None:
        if atual is not None:
            campos[atual] = "\n".join(buffer).strip()

    for linha in texto.splitlines():
        limpa = linha.strip()
        if limpa.startswith(PREFIXO_CAMPO):
            fechar()
            atual = limpa[len(PREFIXO_CAMPO):].strip()
            buffer = []
        elif limpa == "---":
            fechar()
            atual, buffer = None, []
        elif atual is not None:
            buffer.append(linha)
    fechar()
    return {c: t for c, t in campos.items() if c.startswith("en:") and t}
