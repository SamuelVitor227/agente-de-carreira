"""Aderência da vaga ao perfil, de 0 a 100, com justificativa (RF-VG-06), e aprendizado (RF-VG-11).

Motor local, sem IA externa. A nota junta três partes:

- cobertura das tecnologias pedidas (obrigatórias pesam o dobro das desejáveis). Com pouca evidência ela
  fica perto do meio: uma vaga que só cita "SQL" não vira 100% compatível por isso;
- similaridade TF-IDF entre o texto da vaga e o perfil-mestre;
- encaixe do cargo e do nível com as suas buscas (estágio/júnior em desenvolvimento, por exemplo).

Depois entram o ajuste aprendido com o seu feedback e um desconto para anúncio em inglês quando o seu
inglês é básico. Sem a descrição, a nota é estimada só pelo título: aparece como "≈ 50", tem teto e
não dispara alerta nem "candidatar".
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from ..analise.lacunas import gerar_relatorio
from ..analise.termos import TermoFrequente
from ..models import PerfilMestre
from .modelos import Aderencia, ConfigVagas, VagaEncontrada
from .tecnologias import TECNOLOGIAS_VAGAS
from .texto import norm, slug, tokens

# Similaridade TF-IDF considerada "muito parecida". Calibrada com vagas reais: um anúncio longo raramente
# passa de 0,12 contra o perfil, mesmo quando combina muito.
SIMILARIDADE_REFERENCIA = 0.12
NOTA_MAXIMA_ESTIMADA = 65       # só o título não basta para alerta nem para "candidatar"
EVIDENCIA_MINIMA = 2.0          # peso "imaginário" de tecnologias neutras: pouca evidência fica perto de 50%
COBERTURA_NEUTRA = 0.5          # anúncio sem nenhuma tecnologia reconhecida: não ajuda nem atrapalha
PENALIDADE_INGLES = 0.10        # anúncio em inglês e inglês básico no perfil
PALAVRAS_NIVEL = {"estagio": "estagio", "trainee": "trainee", "junior": "junior", "pleno": "pleno", "senior": "senior"}
AJUSTE_MAXIMO = 0.15
PASSO_FEEDBACK = 0.2

MOTIVOS_FEEDBACK = {
    "area": "área ou tecnologias",
    "requisitos": "requisitos fora do meu perfil",
    "nivel": "nível",
    "modelo": "modelo de trabalho",
    "local": "local",
    "salario": "salário",
    "empresa": "empresa",
    "outro": "outro",
}


_PADROES_TECNOLOGIA = [(tec, re.compile(rf"(?<![\w#+.]){re.escape(tec)}(?![\w#])", re.IGNORECASE))
                       for tec in TECNOLOGIAS_VAGAS]


def tecnologias_em(texto: str) -> list[str]:
    return [tec for tec, padrao in _PADROES_TECNOLOGIA if padrao.search(texto or "")]


def encaixe_cargo(vaga: VagaEncontrada, config: ConfigVagas) -> float:
    """0 a 1: o título e o nível do anúncio batem com os cargos e níveis das suas buscas?

    Título: todas as palavras de um cargo da busca aparecem no título ("estágio ti" em "Estagiário em TI"
    vale 1; um cargo de uma palavra só, como "cloud", vale 0,6). Só parte das palavras vale a metade da
    fração ("analista de ti" em "Analista Financeiro": 0,25). Nível: 1 se é um dos que você procura, 0,5 se o
    anúncio não diz.
    """
    buscas = [b for b in config.buscas if b.nome == vaga.busca] or config.buscas
    if not buscas:
        return 0.5
    do_titulo = set(tokens(vaga.titulo))
    melhor = 0.0
    for busca in buscas:
        for cargo in busca.cargos_efetivos():
            exigidos = set(tokens(cargo))
            if exigidos:
                fracao = len(exigidos & do_titulo) / len(exigidos)
                valor = (1.0 if len(exigidos) >= 2 else 0.6) if fracao == 1 else 0.5 * fracao
                melhor = max(melhor, valor)
    alvo = {n for b in buscas for n in b.niveis}
    nivel = vaga.nivel or next((PALAVRAS_NIVEL[t] for t in do_titulo if t in PALAVRAS_NIVEL), None)
    nivel_ok = 0.5 if nivel is None else 1.0 if nivel in alvo else 0.0
    return round(0.6 * melhor + 0.4 * nivel_ok, 3)


def documento_perfil(perfil: PerfilMestre) -> str:
    partes = [perfil.objetivo or "", perfil.resumo or ""]
    partes += perfil.competencias_tecnicas + perfil.competencias_comportamentais
    for exp in perfil.experiencias:
        partes += [exp.cargo, *exp.responsabilidades, *exp.tecnologias, *exp.competencias_transferiveis]
    for proj in perfil.projetos:
        partes += [proj.nome, proj.descricao or "", *proj.tecnologias]
    for conq in perfil.banco_conquistas:
        partes += [conq.descricao, conq.resultado or "", *conq.tecnologias]
    for form in perfil.formacao:
        partes.append(form.curso)
    for cert in perfil.certificacoes:
        partes.append(cert.nome)
    return "\n".join(p for p in partes if p)


def documento_vaga(vaga: VagaEncontrada) -> str:
    return "\n".join([vaga.titulo, vaga.titulo, *vaga.requisitos_obrigatorios, vaga.descricao])


class IndiceTFIDF:
    def __init__(self, documentos: list[str]) -> None:
        self.total = len(documentos)
        self.df: Counter[str] = Counter()
        for doc in documentos:
            self.df.update(set(tokens(doc)))

    def vetor(self, texto: str) -> dict[str, float]:
        contagem = Counter(tokens(texto))
        if not contagem:
            return {}
        total = sum(contagem.values())
        vetor = {
            termo: (n / total) * (math.log((1 + self.total) / (1 + self.df.get(termo, 0))) + 1)
            for termo, n in contagem.items()
        }
        norma = math.sqrt(sum(v * v for v in vetor.values()))
        return {t: v / norma for t, v in vetor.items()}

    @staticmethod
    def cosseno(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(t, 0.0) for t, v in a.items())


def chaves_preferencia(vaga: VagaEncontrada) -> list[str]:
    chaves = [f"tec:{norm(t)}" for t in tecnologias_em(f"{vaga.titulo}\n{vaga.descricao}")]
    if vaga.nivel:
        chaves.append(f"nivel:{vaga.nivel}")
    if vaga.modelo:
        chaves.append(f"modelo:{vaga.modelo}")
    if vaga.empresa and slug(vaga.empresa):
        chaves.append(f"empresa:{slug(vaga.empresa)}")
    return chaves


def ajuste_preferencias(preferencias: dict[str, float], chaves: list[str]) -> float:
    soma = sum(preferencias.get(c, 0.0) for c in chaves)
    return max(-AJUSTE_MAXIMO, min(AJUSTE_MAXIMO, 0.05 * soma))


def calcular_aderencia(
    perfil: PerfilMestre, vaga: VagaEncontrada, indice: IndiceTFIDF, config: ConfigVagas,
    vetor_perfil: dict[str, float] | None = None,
) -> Aderencia:
    texto = f"{vaga.titulo}\n{vaga.descricao}"
    tecs = tecnologias_em(texto)
    obrigatorias = set(tecnologias_em("\n".join(vaga.requisitos_obrigatorios)))
    desejaveis = set(tecnologias_em("\n".join(vaga.requisitos_desejaveis))) - obrigatorias
    tem_secoes = bool(vaga.requisitos_obrigatorios or vaga.requisitos_desejaveis)
    peso = {t: (2.0 if t in obrigatorias else 1.0 if t in desejaveis else 1.5 if tem_secoes else 1.0) for t in tecs}

    relatorio = gerar_relatorio(perfil, [
        TermoFrequente(termo=t, vagas_em_que_aparece=1, total_de_vagas=1, e_tecnologia=True) for t in tecs
    ])
    no_cv = [i.termo for i in relatorio.ja_no_cv]
    escondidos = [i.termo for i in relatorio.tem_mas_nao_aparece]
    lacunas = [i.termo for i in relatorio.nao_tem]
    atendidos = no_cv + escondidos

    # Pouca evidência puxa a cobertura para o meio: 1 tecnologia de 1 reconhecida não é "100% compatível".
    total = sum(peso.values())
    cobertura = (sum(peso[t] for t in atendidos) + 0.5 * EVIDENCIA_MINIMA) / (total + EVIDENCIA_MINIMA) if tecs else None
    vetor_perfil = vetor_perfil if vetor_perfil is not None else indice.vetor(documento_perfil(perfil))
    similaridade = indice.cosseno(vetor_perfil, indice.vetor(documento_vaga(vaga)))
    sim_normalizada = min(1.0, similaridade / SIMILARIDADE_REFERENCIA)
    encaixe = encaixe_cargo(vaga, config)
    partes_nota = [(config.peso_cobertura, COBERTURA_NEUTRA if cobertura is None else cobertura),
                   (config.peso_similaridade, sim_normalizada), (config.peso_cargo, encaixe)]
    soma_pesos = sum(p for p, _ in partes_nota) or 1.0
    base = sum(p * v for p, v in partes_nota) / soma_pesos
    ingles = _desconto_ingles(perfil, vaga)
    ajuste = ajuste_preferencias(config.preferencias, chaves_preferencia(vaga))
    nota = round(100 * max(0.0, min(1.0, base + ajuste - ingles)))
    estimada = not vaga.descricao
    if estimada:
        nota = min(nota, NOTA_MAXIMA_ESTIMADA)

    partes: list[str] = []
    if tecs:
        detalhe = f" ({', '.join(atendidos)})" if atendidos else ""
        partes.append(f"atende {len(atendidos)} de {len(tecs)} tecnologias pedidas{detalhe}")
        if lacunas:
            obrig_faltando = [t for t in lacunas if t in obrigatorias]
            partes.append("faltam: " + ", ".join(lacunas) + (f" (obrigatórias: {', '.join(obrig_faltando)})" if obrig_faltando else ""))
        if escondidos:
            partes.append("você tem mas não aparece no CV: " + ", ".join(escondidos))
    else:
        partes.append("sem tecnologias reconhecidas no anúncio")
    partes.append(f"similaridade com o perfil {similaridade:.2f}")
    partes.append("cargo e nível " + ("combinam com as suas buscas" if encaixe >= 0.8 else
                                      "combinam em parte com as suas buscas" if encaixe >= 0.5 else
                                      "pouco parecidos com as suas buscas"))
    if ingles:
        partes.append(f"anúncio em inglês e o seu inglês está como básico ({-ingles * 100:.0f} pontos)")
    if ajuste:
        partes.append(f"ajuste pelo seu feedback {ajuste * 100:+.0f} pontos")
    if estimada:
        partes.append(f"descrição não coletada: nota estimada só pelo título (no máximo {NOTA_MAXIMA_ESTIMADA}) — "
                      "a próxima busca tenta ler a descrição")
    justificativa = "; ".join(partes)

    return Aderencia(
        nota=nota, atendidos=atendidos, lacunas=lacunas, faltam_no_cv=escondidos,
        similaridade=round(similaridade, 3), cobertura=None if cobertura is None else round(cobertura, 3),
        ajuste_feedback=round(ajuste, 3), justificativa=justificativa[:1].upper() + justificativa[1:],
        encaixe_cargo=encaixe, estimada=estimada,
    )


def _desconto_ingles(perfil: PerfilMestre, vaga: VagaEncontrada) -> float:
    """Anúncio todo em inglês costuma pedir inglês para trabalhar; com inglês básico, a nota desce um pouco."""
    from .filtros import nivel_no_perfil

    if vaga.idioma != "en" or "ingles" in vaga.idiomas_exigidos:  # exigência explícita já é tratada no filtro
        return 0.0
    return PENALIDADE_INGLES if nivel_no_perfil(perfil, "ingles") < 2 else 0.0


# ---------------------------------------------------------------- RF-VG-11

class SugestaoFiltro(BaseModel):
    tipo: Literal["bloquear_empresa", "remover_nivel", "remover_modelo", "remover_localidade", "salario_minimo"]
    valor: str
    descricao: str


def aplicar_feedback(config: ConfigVagas, vaga: VagaEncontrada, interessa: bool, motivo: str | None) -> list[SugestaoFiltro]:
    """Ajusta os pesos aprendidos e devolve sugestões de filtro para o usuário confirmar."""
    chaves = chaves_preferencia(vaga)
    if interessa:
        alvo, passo = chaves, PASSO_FEEDBACK
    else:
        prefixos = {
            "area": ("tec:",), "requisitos": ("tec:",), "nivel": ("nivel:",), "modelo": ("modelo:",),
            "local": ("modelo:",), "empresa": ("empresa:",),
        }.get(motivo or "outro")
        alvo = [c for c in chaves if prefixos is None or c.startswith(prefixos)]
        passo = -PASSO_FEEDBACK if prefixos else -PASSO_FEEDBACK / 2
    for chave in alvo:
        config.preferencias[chave] = round(max(-1.0, min(1.0, config.preferencias.get(chave, 0.0) + passo)), 3)

    if interessa:
        return []
    sugestoes: list[SugestaoFiltro] = []
    if motivo == "empresa" and vaga.empresa:
        sugestoes.append(SugestaoFiltro(tipo="bloquear_empresa", valor=vaga.empresa,
                                        descricao=f"bloquear a empresa {vaga.empresa} em todas as buscas"))
    if motivo == "nivel" and vaga.nivel:
        sugestoes.append(SugestaoFiltro(tipo="remover_nivel", valor=vaga.nivel,
                                        descricao=f"tirar o nível {vaga.nivel} das buscas"))
    if motivo == "modelo" and vaga.modelo:
        sugestoes.append(SugestaoFiltro(tipo="remover_modelo", valor=vaga.modelo,
                                        descricao=f"tirar o modelo {vaga.modelo} das buscas"))
    if motivo == "local" and vaga.local and vaga.modelo != "remoto":
        cidade = vaga.local.split(",")[0].strip()
        sugestoes.append(SugestaoFiltro(tipo="remover_localidade", valor=cidade,
                                        descricao=f"tirar {cidade} das localidades aceitas"))
    if motivo == "salario" and vaga.salario_max:
        minimo = math.ceil((vaga.salario_max + 1) / 100) * 100
        sugestoes.append(SugestaoFiltro(tipo="salario_minimo", valor=str(minimo),
                                        descricao=f"definir salário mínimo de R$ {minimo:,}".replace(",", ".")))
    return sugestoes


def aplicar_sugestao(config: ConfigVagas, sugestao: SugestaoFiltro) -> None:
    for busca in config.buscas:
        if sugestao.tipo == "bloquear_empresa" and sugestao.valor not in busca.empresas_bloqueadas:
            busca.empresas_bloqueadas.append(sugestao.valor)
        elif sugestao.tipo == "remover_nivel" and sugestao.valor in busca.niveis:
            busca.niveis.remove(sugestao.valor)
        elif sugestao.tipo == "remover_modelo" and sugestao.valor in busca.modelos:
            busca.modelos.remove(sugestao.valor)
        elif sugestao.tipo == "remover_localidade":
            busca.localidades = [l for l in busca.localidades if slug(l) != slug(sugestao.valor)]
        elif sugestao.tipo == "salario_minimo":
            busca.salario_minimo = float(sugestao.valor)
