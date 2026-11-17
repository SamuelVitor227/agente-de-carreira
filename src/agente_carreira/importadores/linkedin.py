"""Importação da exportação de dados do LinkedIn (ZIP de CSVs) — RF-PM-02.

O LinkedIn entrega em "Obter uma cópia dos seus dados" um ZIP com arquivos
como Profile.csv, Positions.csv, Education.csv, Skills.csv, Languages.csv e
Certifications.csv. Tudo extraído vira rascunho para confirmação do usuário.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from ..models import ExperienciaRascunho, FormacaoRascunho
from .resultado import CertificacaoRascunho, IdiomaRascunho, ResultadoImportacao


def importar_exportacao_linkedin(caminho: Path) -> ResultadoImportacao:
    resultado = ResultadoImportacao(origem=f"linkedin-export:{caminho.name}")
    with zipfile.ZipFile(caminho) as zf:
        indice = {Path(nome).name.lower(): nome for nome in zf.namelist()}

        def ler(nome_csv: str) -> list[dict[str, str]]:
            real = indice.get(nome_csv.lower())
            if not real:
                return []
            with zf.open(real) as f:
                texto = io.TextIOWrapper(f, encoding="utf-8-sig")
                return [
                    {k.strip(): (v or "").strip() for k, v in linha.items() if k}
                    for linha in csv.DictReader(texto)
                ]

        for perfil in ler("Profile.csv")[:1]:
            nome = " ".join(
                p for p in [perfil.get("First Name"), perfil.get("Last Name")] if p
            )
            resultado.nome = nome or None
            resultado.resumo = perfil.get("Summary") or None

        for email in ler("Email Addresses.csv"):
            if email.get("Email Address"):
                resultado.email = email["Email Address"]
                if email.get("Primary", "").lower() in {"yes", "sim", "true"}:
                    break

        for tel in ler("PhoneNumbers.csv")[:1]:
            resultado.telefone = tel.get("Number") or None

        for pos in ler("Positions.csv"):
            resultado.experiencias.append(
                ExperienciaRascunho(
                    cargo=pos.get("Title") or None,
                    empresa=pos.get("Company Name") or None,
                    periodo_texto=_periodo(pos.get("Started On"), pos.get("Finished On")),
                    local=pos.get("Location") or None,
                    descricao=pos.get("Description") or None,
                    origem="linkedin:Positions.csv",
                )
            )

        for edu in ler("Education.csv"):
            resultado.formacoes.append(
                FormacaoRascunho(
                    curso=edu.get("Degree Name") or None,
                    instituicao=edu.get("School Name") or None,
                    periodo_texto=_periodo(edu.get("Start Date"), edu.get("End Date")),
                    observacoes=edu.get("Notes") or None,
                    origem="linkedin:Education.csv",
                )
            )

        resultado.competencias = [
            s["Name"] for s in ler("Skills.csv") if s.get("Name")
        ]

        resultado.idiomas = [
            IdiomaRascunho(idioma=l["Name"], nivel=l.get("Proficiency") or None)
            for l in ler("Languages.csv")
            if l.get("Name")
        ]

        resultado.certificacoes = [
            CertificacaoRascunho(
                nome=c["Name"],
                emissor=c.get("Authority") or None,
                data_texto=c.get("Started On") or None,
                url=c.get("Url") or None,
            )
            for c in ler("Certifications.csv")
            if c.get("Name")
        ]

    return resultado


def _periodo(inicio: str | None, fim: str | None) -> str | None:
    inicio = (inicio or "").strip()
    fim = (fim or "").strip()
    if not inicio and not fim:
        return None
    return f"{inicio or '?'} – {fim or 'atual'}"
