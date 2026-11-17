# Agente de Carreira

Agente de IA para gestão de carreira: otimização de currículo, perfil no LinkedIn, busca de vagas e acompanhamento de candidaturas.

## O que o agente faz

- Mantém um **perfil-mestre único** e otimiza o currículo: versão-base melhorada a partir das vagas-alvo e versão sob medida por vaga, sem inventar nada.
- Prepara as alterações padrão do **LinkedIn** (título, Sobre, competências, Open to Work, alertas), em modo copiloto por padrão.
- Cadastra e sincroniza o currículo em **outras plataformas** (Gupy primeiro).
- **Busca vagas** por alertas de e-mail e páginas de carreira, deduplica, pontua e entrega um resumo diário até as 8h.
- Monta o **kit de candidatura**, preenche o formulário e para antes do envio; acompanha o funil até a proposta.

## Regras centrais

| Regra | Descrição |
|-------|-----------|
| RN-01 | Nada sai sem aprovação explícita |
| RN-02 | Nada é inventado no CV ou no perfil |
| RN-04 | Sem bots no LinkedIn: copiloto por padrão; modo assistido só por opção do usuário |
| RN-14 / RF-IA-02 | Claude Pro e Gemini Pro só com aviso do motor, da tarefa e dos dados enviados, e autorização a cada uso |
| RN-07 | Estágio só com matrícula ativa (Lei 11.788/2008, art. 3º, I) |

## Fases

1. **MVP** — M1 (perfil e currículo), M2 (LinkedIn em copiloto), M4 (resumo diário), M8 (aprovações e uso de IA). Portão: CA-01 a CA-10.
2. **Candidatura** — M3 (Gupy + 2 plataformas P2), M5 (candidatura assistida), M6 (funil). Portão: CA-11 e CA-12.
3. **Aprendizado** — status lido dos e-mails, painel, relatório semanal, pesos por feedback, desempenho por variante de CV.

## Status da implementação

| Requisito | Descrição | Status |
|-----------|-----------|--------|
| RF-PM-01 | Perfil-mestre estruturado (contato, objetivo, resumo, experiências, formação, certificações, projetos, competências, idiomas, links) | ✅ Implementado |
| RF-PM-02 | Importar CV de PDF/DOCX, exportação do LinkedIn (ZIP) e texto livre, com confirmação de tudo o que foi extraído | ✅ Implementado |
| RF-PM-03 | Experiência com cargo, empresa, vínculo, período, local, modelo de trabalho, responsabilidades, conquistas e tecnologias | ✅ Implementado |
| RF-PM-04 | Banco de conquistas reutilizáveis (verbo de ação, resultado com número, tecnologias, competências, evidência) | ✅ Implementado |
| RF-PM-05 | Experiências fora de TI e projetos acadêmicos com competências transferíveis | ✅ Implementado |
| RF-PM-06 | Versionamento do perfil-mestre com histórico de mudanças e restauração | ✅ Implementado |
| RF-PM-07 | Validação de completude e consistência (datas sobrepostas, lacunas, campos por plataforma, duplicatas) | ✅ Implementado |
| RF-CV-01 | Conjunto de vagas-alvo por foco (padrão 30) com extração de termos mais frequentes (motor local) | ✅ Implementado |
| RF-CV-02 | Relatório de lacunas em três grupos (já no CV / tem mas não aparece / não tem) | ✅ Implementado |
| RF-CV-03 | Reescrita de resumo, experiências e projetos em modo copiloto, com autorização de uso de IA (RF-IA-02) | ✅ Implementado |
| RF-CV-04 | Reordenação de seções e itens pelo peso no nível-alvo (formação/projetos/certificações antes de fora da área) | ✅ Implementado |
| RF-CV-05 | Nota de compatibilidade ATS (estrutura, títulos padrão, termos cobertos, legibilidade) com histórico do que mudou | ✅ Implementado |
| RF-CV-06 | Sugestões reais para fechar lacunas (curso/certificação/projeto), priorizando catálogos que você já tem (DIO) | ✅ Implementado |
| RF-CV-07 | Variantes por foco (backend .NET, cloud AWS, mobile, dados, suporte) e idioma (pt/en), derivadas da versão-base | ✅ Implementado |
| RF-CV-08 | Exportação PDF e DOCX compatível com ATS (uma coluna, sem tabelas/imagens, fonte padrão, formato único de data, tamanho-alvo) | ✅ Implementado |
| RF-CV-09 | Revisão da versão-base (mensal ou quando as vagas mudarem) com antes × depois | ✅ Implementado |
| RF-CV-10 | Desempenho por variante (candidaturas × retornos) com recomendação por foco | ✅ Implementado |
| RF-CV-11 | Versão sob medida por vaga, só com itens do perfil-mestre | ✅ Implementado |
| RF-CV-12 | Antes × depois e cobertura da vaga (atendidos / incluídos / sem lastro) | ✅ Implementado |
| RF-CV-13 | Marcador [A CONFIRMAR] com bloqueio de exportação até a confirmação | ✅ Implementado |
| RF-CV-14 | Cópia da versão de CV enviada guardada junto da candidatura | ✅ Implementado |
| RF-LI-01 | Auditoria do perfil contra o checklist do Anexo A, pendências por impacto | ✅ Implementado |
| RF-LI-02 | 3 opções de título (≤220 caracteres, essencial nos primeiros 60) | ✅ Implementado |
| RF-LI-03 | Seção Sobre (≤2.600 caracteres, proposta de valor nos ~300 primeiros) | ✅ Implementado |
| RF-LI-04 | Textos de experiência (≤2.000/cargo), mesmos cargos e datas do CV | ✅ Implementado |
| RF-LI-05 | Competências priorizadas pelas vagas-alvo, com vínculos (limite 100) | ✅ Implementado |
| RF-LI-06 | Pacote do Open to Work (≤5 cargos, locais, visibilidade) | ✅ Implementado |
| RF-LI-07 | Ajustes de perfil: localização, URL personalizada validada, contato, Em destaque, certificações, idiomas | ✅ Implementado |
| RF-LI-08 | Rodada de edições com desligar/religar o compartilhamento de atualizações | ✅ Implementado |
| RF-LI-09 | Até 20 alertas de vagas diários por e-mail, espelhando as buscas | ✅ Implementado |

## Como usar

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev        # instala as dependências
uv run pytest        # roda os testes
uv run agente --help # mostra os comandos
```

Comandos principais:

```bash
uv run agente perfil criar            # cria o perfil-mestre
uv run agente perfil mostrar          # exibe o perfil completo
uv run agente importar meu-cv.pdf     # importa CV (PDF/DOCX/ZIP do LinkedIn/TXT) com confirmação
uv run agente rascunhos               # lista itens importados pendentes de confirmação
uv run agente experiencia adicionar   # registra experiência (aceita fora de TI e projetos acadêmicos)
uv run agente conquista adicionar     # adiciona conquista ao banco de conquistas
uv run agente perfil validar          # checa completude e consistência (RF-PM-07)
uv run agente perfil versoes          # histórico de versões; restaure com 'perfil restaurar N'
uv run agente vaga adicionar          # salva vaga-alvo (descrição por arquivo ou colada)
uv run agente cv termos --foco X      # termos mais frequentes do conjunto de vagas
uv run agente cv lacunas              # relatório de lacunas em 3 grupos
uv run agente cv reescrever           # gera prompt de reescrita p/ Claude/Gemini (com autorização)
uv run agente cv ordenar --nivel estagio   # ordem de seções pelo peso no nível-alvo
uv run agente cv nota                 # nota ATS 0-100 com o que mudou desde a última revisão
uv run agente cv fechar-lacunas       # curso/certificação/projeto para cada lacuna sem lastro
uv run agente cv variante --foco backend-dotnet --idioma pt   # variante derivada da versão-base
uv run agente cv exportar --foco backend-dotnet --formato ambos  # PDF+DOCX compatíveis com ATS
uv run agente cv sob-medida --vaga 1 --exportar  # CV sob medida com cobertura da vaga
uv run agente cv revisar                 # revisão mensal da versão-base (antes × depois)
uv run agente cv desempenho              # candidaturas × retornos por variante
uv run agente confirmar                  # confirma frases [A CONFIRMAR] e libera exportação
uv run agente candidatura registrar --vaga 1 --foco backend-dotnet  # guarda o CV enviado
uv run agente li auditar                 # auditoria do LinkedIn (checklist Anexo A)
uv run agente li titulo / sobre / experiencias / competencias       # textos do LinkedIn
uv run agente li open-to-work / ajustes / alertas / rodada          # pacotes e passo a passo
```

Os dados ficam em `data/perfil-mestre.json` (fora do git), configurável pela variável `AGENTE_CARREIRA_DATA`.

## Documentação

- [Especificação de Requisitos](<docs/Agente de Carreira — Especificação de Requisitos.pdf>) — documento completo *Agente de Carreira — Especificação de Requisitos* (versão de 16/11/2026), a fonte da verdade do projeto.

## Decisões em aberto

Nível-alvo depois de 2026/2; faixa salarial; presencial fora de BH ou mudança de cidade; visibilidade do Open to Work; modo assistido no LinkedIn; construção (A: dentro do Claude, ou B: código próprio em Python ou .NET); motor padrão por tarefa; canal de notificação; plataformas P2 da fase 2.
