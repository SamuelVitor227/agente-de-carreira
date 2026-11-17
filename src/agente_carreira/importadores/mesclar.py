"""Mescla um resultado de importação confirmado no perfil-mestre.

Regras (RN-02): só entra o que foi extraído e confirmado; campos já
preenchidos no perfil não são sobrescritos; experiências e formações entram
como rascunho até o usuário completá-las com os campos do RF-PM-03.
"""

from __future__ import annotations

from ..models import Certificacao, Idioma, PerfilMestre
from .resultado import ResultadoImportacao


def aplicar_importacao(perfil: PerfilMestre, resultado: ResultadoImportacao) -> list[str]:
    """Aplica o resultado no perfil e devolve a lista de alterações feitas."""
    alteracoes: list[str] = []

    if resultado.email and not perfil.contato.email:
        perfil.contato.email = resultado.email
        alteracoes.append(f"contato.email = {resultado.email}")
    if resultado.telefone and not perfil.contato.telefone:
        perfil.contato.telefone = resultado.telefone
        alteracoes.append(f"contato.telefone = {resultado.telefone}")
    if resultado.github and not perfil.links.github:
        perfil.links.github = resultado.github
        alteracoes.append(f"links.github = {resultado.github}")
    if resultado.linkedin and not perfil.links.linkedin:
        perfil.links.linkedin = resultado.linkedin
        alteracoes.append(f"links.linkedin = {resultado.linkedin}")
    if resultado.resumo and not perfil.resumo:
        perfil.resumo = resultado.resumo
        alteracoes.append("resumo preenchido a partir da importação")

    for link in resultado.outros_links:
        if link not in perfil.links.outros:
            perfil.links.outros.append(link)
            alteracoes.append(f"links.outros += {link}")

    existentes = {c.lower() for c in perfil.competencias_tecnicas}
    for comp in resultado.competencias:
        if comp.lower() not in existentes:
            perfil.competencias_tecnicas.append(comp)
            existentes.add(comp.lower())
            alteracoes.append(f"competências técnicas += {comp}")

    idiomas_existentes = {i.idioma.lower() for i in perfil.idiomas}
    for idi in resultado.idiomas:
        if idi.idioma.lower() not in idiomas_existentes:
            perfil.idiomas.append(Idioma(idioma=idi.idioma, nivel=idi.nivel or "a confirmar"))
            idiomas_existentes.add(idi.idioma.lower())
            alteracoes.append(f"idiomas += {idi.idioma}")

    cert_existentes = {c.nome.lower() for c in perfil.certificacoes}
    for cert in resultado.certificacoes:
        if cert.nome.lower() not in cert_existentes:
            perfil.certificacoes.append(
                Certificacao(nome=cert.nome, emissor=cert.emissor, url_credencial=cert.url)
            )
            cert_existentes.add(cert.nome.lower())
            alteracoes.append(f"certificações += {cert.nome}")

    for exp in resultado.experiencias:
        perfil.rascunhos.experiencias.append(exp)
        alteracoes.append(
            f"rascunho de experiência += {exp.cargo or '?'} em {exp.empresa or '?'}"
        )
    for form in resultado.formacoes:
        perfil.rascunhos.formacoes.append(form)
        alteracoes.append(
            f"rascunho de formação += {form.curso or '?'} em {form.instituicao or '?'}"
        )

    return alteracoes
