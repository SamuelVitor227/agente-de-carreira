"""Limites do LinkedIn conferidos na especificação (fontes de set–nov/2026).

São configuração, não código (RNF-14): se o LinkedIn mudar um limite, basta
atualizar aqui.
"""

LIMITES = {
    "titulo": 220,                 # RF-LI-02
    "titulo_trecho_visivel": 60,   # termos principais nos primeiros 60 caracteres
    "sobre": 2600,                 # RF-LI-03
    "sobre_abertura": 300,         # proposta de valor antes do "ver mais"
    "experiencia": 2000,           # RF-LI-04, por cargo
    "competencias": 100,           # RF-LI-05 (vinculadas a experiências não contam)
    "open_to_work_cargos": 5,      # RF-LI-06
    "url_personalizada_min": 3,    # RF-LI-07
    "url_personalizada_max": 100,
    "url_trocas_por_semestre": 5,
    "nota_convite": 300,           # RF-LI-11
    "alertas": 20,                 # RF-LI-09
}
