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
| RF-LI-10 | Perfil secundário em inglês: pacote de tradução com autorização de IA e aprovação campo a campo | ✅ Implementado |
| RF-LI-11 | Rascunhos de pedido de recomendação e de nota de convite (≤300 caracteres), envio manual | ✅ Implementado |
| RF-LI-12 | Pauta e rascunhos de publicações a partir dos projetos do perfil e dos repositórios públicos do GitHub; publicação manual e só após aprovação | ✅ Implementado |
| RF-LI-13 | Antes × depois com contagem de caracteres e aprovação campo a campo | ✅ Implementado |
| RF-LI-14 | Log de cada alteração (data, campo, valor anterior e novo) com reversão | ✅ Implementado |
| RF-LI-15 | Reauditoria a cada 30 dias ou quando o perfil-mestre mudar, com divergências LinkedIn × CV | ✅ Implementado |
| RF-IA-01 | Motor por tipo de tarefa: Claude Pro, Gemini Pro ou local (padrão: perguntar a cada uso) | ✅ Implementado |
| RF-IA-02 | Aviso do motor, da tarefa e dos dados antes de cada uso, com aprovar, trocar de motor ou negar | ✅ Implementado |
| RF-IA-03 | Sem autorização nada é gerado; o pedido fica pendente na fila para autorizar ou descartar depois | ✅ Implementado |
| RF-IA-04 | Filtro automático que remove e-mail, telefone, CPF, RG, CEP e endereço de todo prompt | ✅ Implementado |
| RF-IA-05 | Registro de cada uso: data, motor, tarefa, dados enviados, removidos, autorização e resultado | ✅ Implementado |
| RF-IA-06 | Cada texto gerado identifica quem o escreveu: Claude Pro, Gemini Pro, motor local ou você | ✅ Implementado |
| RF-IA-07 | Recusa por limite de uso: avisa e oferece o outro motor ou o local, com nova autorização | ✅ Implementado |
| RF-IA-08 | Autorização em lote (ex.: toda a rodada de hoje): desligada por padrão, com prazo de até 24 h e revogável | ✅ Implementado |
| RF-VG-01 | Buscas salvas: cargos e sinônimos, nível, modelo, localidades, contrato, salário mínimo, idioma, empresas-alvo e bloqueadas | ✅ Implementado |
| RF-VG-02 | Coleta só de fontes permitidas: alertas por e-mail (.eml ou IMAP somente leitura), páginas de carreira e links seus | ✅ Implementado |
| RF-VG-03 | Rodada sob demanda e agendada (padrão 7h, Agendador do Windows ou cron) | ✅ Implementado |
| RF-VG-04 | Extração de título, empresa, local, modelo, contrato, nível, salário, datas, link, fonte, descrição e requisitos | ✅ Implementado |
| RF-VG-05 | Deduplicação entre fontes (link, empresa + cargo + local, similaridade), mantendo todas as fontes | ✅ Implementado |
| RF-VG-06 | Aderência 0–100 no motor local (TF-IDF + cobertura de requisitos) com justificativa | ✅ Implementado |
| RF-VG-07 | Filtros eliminatórios: experiência, idioma, região, encerrada, empresa bloqueada, nível, modelo, contrato, salário | ✅ Implementado |
| RF-VG-08 | Indícios de golpe: taxa, Pix/dados bancários, renda fácil, contato só por app, salário irreal, empresa sem identificação | ✅ Implementado |
| RF-VG-09 | Resumo diário por aderência, com link, motivo e ação sugerida (candidatar, salvar, descartar) | ✅ Implementado |
| RF-VG-10 | Alerta imediato de vagas acima do limiar (padrão 80) | ✅ Implementado |
| RF-VG-11 | Aprendizado com feedback (interessa ou não, e o motivo): ajusta pesos e sugere filtros | ✅ Implementado |
| RF-VG-12 | Vagas expiradas (prazo, idade, anúncio encerrado, link fora do ar) saem do resumo | ✅ Implementado |
| RF-VG-13 | Regras de estágio (RN-07): sem matrícula ativa, estágio sai do resumo; jornada acima de 6h/30h sinalizada | ✅ Implementado |
| RF-PL-01 | Catálogo de plataformas (Anexo B): URL, foco, prioridade, modo, campos, limites, formatos, revisão dos termos | ✅ Implementado |
| RF-PL-02 | Pacote de cadastro por plataforma, cada campo mapeado do perfil-mestre e ajustado ao limite | ✅ Implementado |
| RF-PL-03 | Cadastro guiado no modo da plataforma (copiloto ou assistido com Playwright), pausando para conta, login, 2FA, CAPTCHA e termos | ✅ Implementado |
| RF-PL-04 | Revisão campo a campo do que a plataforma preencheu a partir do CV | ✅ Implementado |
| RF-PL-05 | Gupy: Experiência e Habilidades ordenadas pelas vagas-alvo e campo "Apresente-se" | ✅ Implementado |
| RF-PL-06 | Variante de CV adequada ao foco da plataforma | ✅ Implementado |
| RF-PL-07 | Conferência do que ficou gravado e percentual de completude | ✅ Implementado |
| RF-PL-08 | Propagação: plataformas desatualizadas pelo perfil-mestre ganham tarefa de atualização | ✅ Implementado |
| RF-PL-09 | Status por plataforma (não iniciado, em andamento, completo, desatualizado) e última revisão | ✅ Implementado |
| RF-PL-10 | Aviso antes de etapas pagas; nada é contratado | ✅ Implementado |
| RF-PL-11 | Testes técnicos são do usuário; o agente prepara material de estudo | ✅ Implementado |
| RF-CA-01 | Kit de candidatura por vaga: CV sob medida, mensagem curta e respostas de triagem | ✅ Implementado |
| RF-CA-02 | Respostas-padrão (Anexo C) aprovadas e reutilizadas; sem resposta aprovada, a pergunta fica para você (RN-09) | ✅ Implementado |
| RF-CA-03 | Preenchimento no modo da plataforma (copiloto ou assistido com Playwright), parando na tela de revisão; o envio é seu | ✅ Implementado |
| RF-CA-04 | Sem candidatura repetida; mesma empresa e cargo em menos de 90 dias pede confirmação | ✅ Implementado |
| RF-CA-05 | Limite diário de candidaturas e aderência mínima configuráveis; vaga suspeita de golpe não recebe dados | ✅ Implementado |
| RF-CA-06 | Registro de cada envio: CV e kit guardados, descrição da vaga preservada, auditoria e captura | ✅ Implementado |
| RF-CA-07 | Perguntas eliminatórias primeiro, com alerta quando a resposta verdadeira pode eliminar | ✅ Implementado |
| RF-CA-08 | Indicação: conexões na empresa (exportação do LinkedIn) e rascunho de pedido, envio manual | ✅ Implementado |
| RF-AC-01 | Funil por etapas (encontrada → aplicada → em análise → testes e entrevistas → proposta → contratado/saída), só para frente | ✅ Implementado |
| RF-AC-02 | Retornos por e-mail atualizam o funil; e-mail ambíguo pede confirmação; o texto é só dado (RNF-04) | ✅ Implementado |
| RF-AC-03 | Lembretes de follow-up e de etapas agendadas, com rascunho de follow-up e agenda .ics | ✅ Implementado |
| RF-AC-04 | Preparação para entrevista: empresa, requisitos × evidências, perguntas prováveis e para fazer | ✅ Implementado |
| RF-AC-05 | Contatos de recrutadores com dados mínimos e exclusão em um passo (RNF-05) | ✅ Implementado |
| RF-AC-06 | Motivo de saída obrigatório em reprovação e desistência | ✅ Implementado |
| RF-RL-01 | Painel com vagas, candidaturas, taxa de retorno, entrevistas e propostas por fonte, foco e variante de CV | ✅ Implementado |
| RF-RL-02 | Relatório semanal: o que funcionou, competências mais pedidas que faltam e próximas ações (agendável) | ✅ Implementado |
| RF-RL-03 | Exportação em CSV (abre no Excel) dos dados e do log de ações | ✅ Implementado |
| RF-OP-01 | Preferências num só lugar: buscas, limites diários, limiares, horários, notificações, modo por plataforma e motor por tarefa | ✅ Implementado |
| RF-OP-02 | Modo global "somente sugestão": nenhuma plataforma é tocada | ✅ Implementado |
| RF-OP-03 | Pausar, retomar e cancelar tarefas; retomar a partir do último passo confirmado | ✅ Implementado |
| RF-OP-04 | Notificações por e-mail ou push (resumo diário, vaga acima do limiar, pedido de aprovação, falha de adaptador) | ✅ Implementado |
| RF-OP-05 | Fila única de aprovações (usos de IA, publicações, alterações do LinkedIn) com aprovar, editar ou rejeitar | ✅ Implementado |
| RF-OP-06 | Log de auditoria das ações externas: plataforma, ação, data e hora, antes e depois, aprovação e captura | ✅ Implementado |
| RF-OP-07 | Saúde dos adaptadores: parar e avisar ao detectar erro ou mudança de layout | ✅ Implementado |

## Portões de aceitação

Todos os requisitos da especificação estão implementados (M1 a M8). `agente aceite` confere os critérios da seção 14 sobre os seus dados reais: o MVP (CA-01 a CA-10) e a fase 2 (CA-11 e CA-12; `--fase 1|2` mostra só um). Ele separa o que já está comprovado, o que depende de uso (vagas coletadas, cinco dias úteis de resumo antes das 8h) e o que pede conferência manual: enviar o PDF à Gupy (CA-03) e ver o agente parar na tela de revisão num formulário real (CA-11, cuja parte automática roda num formulário de teste no Chromium). O CA-12 confere dez vagas de teste com taxa ou Pix e exige 100% de sinalização e bloqueio.

## Como usar

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev        # instala as dependências
uv run pytest        # roda os testes
uv run agente --help # mostra os comandos
```

### App na Área de Trabalho

Para quem não é de TI, o jeito de usar é o app. `uv run agente atalho` cria o atalho **Agente de Carreira** na Área de Trabalho (Windows), e dois cliques abrem a janela, sem nenhum terminal.

- **Início:** mostra o próximo passo sugerido, os números do dia (vagas boas, candidaturas, lembretes, aprovações) e, no primeiro uso, um passo a passo: trazer o currículo, conectar o LinkedIn, dizer que vagas procura e fazer a primeira busca.
- **Vagas** e **Minhas candidaturas:** listas clicáveis, com botões como "Quero me candidatar", "Não tenho interesse" e "O que aconteceu?" (com a data da entrevista ou o motivo da saída).
- **Meu perfil e currículo**, **LinkedIn**, **Aprovações** (aprovar, editar ou recusar com um clique), **Relatórios** e **Configurações** (buscas, agendamentos, avisos por e-mail).

As ações rodam dentro da janela, e cada pergunta do agente aparece como botões de Sim/Não, de opção ou um campo para digitar. Nada é enviado nem publicado sem o seu sim. A janela também abre com `uv run agente app`.

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
uv run agente li conectar export.zip     # traz o LinkedIn pela exportação oficial: perfil + estado atual
uv run agente li automatico [ligar --aceito-o-risco|entrar|testar|desligar]   # automação opcional no LinkedIn
uv run agente li sincronizar export.zip  # estado real do LinkedIn pela exportação oficial
uv run agente li propor                  # antes × depois e aprovação campo a campo
uv run agente li log / aplicado ID / reverter ID   # log de alterações com reversão
uv run agente li reauditar               # reauditoria (30 dias ou perfil mudou) e divergências LinkedIn × CV
uv run agente li ingles preparar / registrar resposta.md --motor claude   # perfil em inglês
uv run agente li recomendacao / convite  # rascunhos de mensagens, envio manual
uv run agente li pauta                   # pauta de posts com seus repositórios públicos do GitHub
uv run agente li post rascunho N --ia / editar / aprovar / publicado   # posts só com aprovação
uv run agente ia motores / motor TAREFA MOTOR   # motor de cada tarefa (claude, gemini, local, perguntar)
uv run agente ia fila / autorizar ID / descartar ID   # pedidos de IA negados, pendentes de decisão
uv run agente ia log                     # registro de cada uso de IA
uv run agente ia recusado ID            # o motor recusou por limite: refazer no outro ou seguir local
uv run agente ia lote / lote criar --tarefa X / lote revogar ID   # autorização em lote (RF-IA-08)
uv run agente app / atalho              # app de janela e atalho na Área de Trabalho
uv run agente aceite [--fase 1|2]        # portões: CA-01 a CA-10 (MVP) e CA-11, CA-12 (fase 2)
uv run agente plataformas / ver ID / pacote ID       # catálogo, campos e pacote de cadastro
uv run agente plataformas cadastrar ID   # cadastro guiado (copiloto ou assistido), pausa e retoma
uv run agente plataformas conferir ID [--antes-de-salvar]   # confere o gravado e mede a completude
uv run agente plataformas propagar       # plataformas desatualizadas ganham tarefa de atualização
uv run agente plataformas estudo ID      # material de estudo para testes técnicos
uv run agente respostas / respostas definir CHAVE "texto"   # respostas-padrão de triagem (Anexo C)
uv run agente candidatar ID_DA_VAGA --perguntas perguntas.txt   # kit, preenchimento e registro do envio
uv run agente indicacao ID_DA_VAGA --conexoes Connections.csv  # quem você conhece na empresa
uv run agente funil / funil mover ID ETAPA [--quando "AAAA-MM-DD HH:MM"]   # funil de candidaturas
uv run agente funil enviada ID           # registra um envio feito por fora do 'candidatar'
uv run agente funil lembretes / feito ID / followup ID / agenda   # follow-ups, etapas e .ics
uv run agente funil emails / confirmar   # retornos por e-mail (.eml em data/caixa-retornos ou IMAP)
uv run agente funil preparar ID          # material de preparação para a entrevista
uv run agente contatos / contatos adicionar --nome X / interacao ID "resumo" / excluir ID
uv run agente painel [--dias 30] [--html]   # painel por fonte, foco e variante; data/painel.html a cada rodada
uv run agente relatorio semanal [--notificar]   # o que funcionou, lacunas e próximas ações
uv run agente relatorio agendar          # relatório todo domingo às 20h no Agendador do Windows
uv run agente exportar                   # CSVs em data/exportacoes/AAAA-MM-DD (vagas, funil, log, IA, contatos)
uv run agente busca criar --nome backend --foco backend-dotnet   # busca salva com cargos e sinônimos
uv run agente busca empresa "Empresa X" --pagina https://empresax.gupy.io/   # empresa-alvo
uv run agente vagas rodada               # coleta, triagem, aderência e resumo do dia
uv run agente vagas link URL [--descricao vaga.txt]   # vaga a partir de um link seu
uv run agente vagas resumo [--ia]        # resumo do dia; --ia prepara a justificativa escrita
uv run agente vagas ver ID / feedback ID --interessa|--nao-interessa --motivo X / salvar ID / descartar ID
uv run agente vagas agendar --hora 07:00 # rodada diária no Agendador do Windows
uv run agente config                     # todas as preferências; altere com 'config definir CAMINHO VALOR'
uv run agente config sugestao --ligar    # modo somente sugestão: nenhuma plataforma é tocada
uv run agente fila / fila revisar        # fila única de aprovações (aprovar, editar, rejeitar)
uv run agente tarefas / pausar|retomar|cancelar ID   # tarefas, inclusive a rodada diária
uv run agente auditoria / auditoria ver ID           # ações externas com antes, depois e aprovação
uv run agente saude / saude reativar NOME            # adaptadores parados por erro ou layout novo
uv run agente notificacoes teste         # testa o canal de notificação
```

### LinkedIn

Por padrão, o agente não entra na sua conta. Os dados do perfil vêm da exportação oficial: no LinkedIn, Eu → Configurações e privacidade → Privacidade de dados → Obter uma cópia dos seus dados. Com o ZIP, rode `agente li conectar ARQUIVO.zip`, ou use o botão "Conectar LinkedIn (ZIP)…" do app. As vagas chegam pelos alertas de e-mail do LinkedIn, e as mudanças no perfil você aprova e cola (copiloto).

**Automação (opcional, RN-04).** Os termos do LinkedIn proíbem automação, então ela fica desligada até você ligar aceitando o risco: `agente li automatico ligar --aceito-o-risco`, ou o botão "Ligar automação…" na tela LinkedIn do app. Com ela ligada:

- Você entra uma vez na conta pelo navegador do agente (`agente li automatico entrar`). Login, 2FA e CAPTCHA são seus.
- Cada rodada de vagas também pesquisa no LinkedIn pelas suas buscas salvas. Por padrão são 4 páginas por rodada e no máximo 12 vagas abertas, com pausas aleatórias de 4 a 11 segundos. Limites e seletores ficam em `linkedin_automatico` na configuração.
- Em `agente candidatar`, o agente abre a Candidatura Simplificada e preenche cada etapa com o seu perfil e as respostas aprovadas. Ele anexa o currículo, avança e **para antes de "Enviar candidatura"**: o envio é sempre seu. Pergunta sem resposta aprovada fica para você.
- Se o LinkedIn pedir login ou verificação, o agente para e avisa. Se a página estiver diferente do esperado, ele para e marca o adaptador em `agente saude`.

`agente li automatico testar` faz uma busca de teste sem salvar nada, e `agente li automatico desligar` volta ao modo padrão.

### De onde vêm as vagas

- **Alertas por e-mail.** Pelo Outlook na web, no navegador do agente: `agente email entrar` (o login é seu), `agente email ligar`, `agente email testar`. A pesquisa do Outlook alcança Prioritário e Outros. O agente só lê, e os alertas não lidos continuam não lidos. Se preferir, a leitura também funciona por IMAP com senha de app (Gmail, Hotmail, Yahoo). Remetentes reconhecidos: LinkedIn, Indeed, Gupy, Vagas.com, ProgramaThor, GeekHunter e Glassdoor.
- **Portal da Gupy (direto no site).** Ligado por padrão: cada rodada pesquisa no portal.gupy.io com termos gerais de TI e o primeiro cargo de cada busca, revezando por dia. Usa um navegador invisível, sem a sua conta, e respeita o robots.txt. Teste com `agente vagas gupy "estágio ti"`.
- **LinkedIn (automação opcional)**, veja acima.
- **Glassdoor:** só pelos alertas de e-mail. O site bloqueia robôs (verificação "Humans only"), e o agente não contorna verificações.
- **Termos.** Além dos cargos de cada área, todas as buscas aceitam termos gerais de TI em início de carreira: estágio TI, trainee, desenvolvedor, programador, analista de TI, suporte etc. Variações como jr/júnior, estagiário/estágio e intern são unificadas.

### Andamento e desempenho

- **Andamento:** toda busca (inclusive a das 7h) grava a etapa atual. No app, uma faixa no topo de todas as telas mostra "Busca de vagas rodando: etapa · há N min", e o botão "Ver andamento" mostra o histórico. No terminal: `agente andamento`. Duas buscas nunca rodam ao mesmo tempo.
- **Desempenho:** até 20% da RAM (`desempenho.memoria_max_percentual`) vira tarefas em paralelo: descrições de sites diferentes lidas ao mesmo tempo (com pausa dentro de cada site), robots.txt consultado uma vez por site e o portal da Gupy rodando junto com o Outlook e o LinkedIn.
- **Região:** presencial e híbrido só em Belo Horizonte e nos 34 municípios da região metropolitana ("BH e região", "Grande BH" e "RMBH" também valem); remoto vale de qualquer lugar. Vaga sem modelo informado conta como presencial, e vaga presencial sem local fica de fora (dá para conferir em "Todas").
- `agente vagas reavaliar [--ler-descricoes N]` dá nota de novo às vagas guardadas com o perfil atual, por exemplo depois de mudar a formação.

### Currículo

O PDF sai de um modelo HTML/CSS impresso pelo Chromium: nome em destaque, contato numa linha, competências agrupadas (Linguagens, Back-end, Front-end e mobile, Dados, Ferramentas, Métodos), datas à direita e 1 página para estágio e júnior, com a fonte reduzida aos poucos se precisar. Continua legível por ATS: uma coluna, texto real, títulos padrão, sem tabelas nem imagens. O Word segue o mesmo visual. Para estágio, trainee e júnior, a ordem é Resumo → Formação → Competências → Projetos → Experiências → Certificações → Idiomas.

### Quero me candidatar

No app, "Quero me candidatar" (e "Candidatar às melhores") abre a vaga no site, no navegador do agente, com o currículo sob medida pronto. No LinkedIn, com a automação ligada, a Candidatura Simplificada é preenchida. Na Gupy e nos outros sites, o agente preenche os dados básicos e anexa o currículo em cada formulário. Você confere e clica em Enviar. Ao fechar o navegador, o app pergunta se você enviou e registra no funil (`agente candidatar ID --direto`).

### Gupy com preenchimento automático

`agente plataformas abrir gupy`, ou o botão "Abrir a Gupy" em Meu perfil, abre a Gupy no navegador do agente. Em qualquer formulário, o agente preenche nome, e-mail, telefone, cidade, estado, país e links. Ele só preenche campos vazios: nunca apaga o que você escreveu, nunca preenche CPF nem senha e nunca clica em salvar ou enviar.

### Candidatar às melhores

No app, Vagas → "Candidatar às melhores" prepara de uma vez até 5 candidaturas: as vagas recomendadas de maior nota, sem indício de golpe e dentro do limite do dia. Em cada uma, o agente monta o kit, preenche no site (Gupy, LinkedIn com automação ligada etc.) e para na revisão. Você confere e clica em Enviar.

### E-mail

No app, "Receber vagas do seu e-mail" (Início ou Configurações) pede o provedor (Gmail, Outlook/Hotmail ou Yahoo), o endereço e uma **senha de app**. É a mesma conta que você vê no Outlook. O agente lê direto do servidor, só para ler, e pode usar o mesmo e-mail para mandar os avisos. As credenciais vão para as variáveis de ambiente do seu usuário do Windows (RNF-01), nunca para `data/` nem para o git. O "novo Outlook" do Windows não permite automação, por isso a leitura é direta pela conta.

### Modo assistido (Playwright)

Plataformas no modo assistido (como a Gupy) abrem um navegador visível com perfil próprio em `data/navegador`. Você faz login, 2FA e CAPTCHA; o agente confere se os campos esperados estão na página, preenche com intervalo entre as ações e limite por sessão, tira uma captura para a auditoria e **para antes de salvar** — quem clica é você. Se a página não tiver os campos esperados, ele não preenche nada e volta para o copiloto. Depois de `uv sync`, instale o navegador uma vez: `uv run playwright install chromium`.

### Candidatura

`agente candidatar` confere antes de tudo se a vaga já foi aplicada, se é a mesma empresa e cargo de uma candidatura recente, o limite do dia, a aderência mínima, sinais de golpe e a matrícula para estágio. Depois monta o kit: CV sob medida, mensagem curta só com fatos do perfil e as respostas de triagem (do banco aprovado ou do perfil; o que não tiver resposta fica para você). As eliminatórias aparecem primeiro. Você aprova ou edita o kit, o agente preenche no modo da plataforma e para na revisão. Quando você confirma que enviou, a candidatura vai para "aplicada", entra na auditoria e ganha um lembrete de follow-up (`limites.followup_dias`, padrão 7). No arquivo de perguntas vai uma por linha; comece com `*` as eliminatórias.

### Notificações

O canal padrão é o e-mail (`agente config definir notificacao.canal email|push|arquivo` e `notificacao.email_para`). As credenciais ficam só em variáveis de ambiente: `AGENTE_SMTP_HOST`, `AGENTE_SMTP_PORTA` (587), `AGENTE_SMTP_USUARIO` e `AGENTE_SMTP_SENHA` para e-mail, ou `AGENTE_NTFY_TOPICO` para push pelo [ntfy](https://ntfy.sh). Toda notificação também fica em `data/notificacoes/`; sem canal configurado, ela só fica lá.

### Alertas de vagas por e-mail

A rodada lê os alertas de duas formas:

- **Arquivos .eml** salvos em `data/caixa-alertas/` (arrastar o e-mail do cliente de e-mail para a pasta). Depois de lidos, vão para `processados/`.
- **IMAP, somente leitura**, numa pasta só de alertas (padrão `Vagas`), sem marcar nada como lido. As credenciais ficam só em variáveis de ambiente, nunca no projeto: `AGENTE_IMAP_HOST`, `AGENTE_IMAP_USUARIO`, `AGENTE_IMAP_SENHA` (use uma senha de app) e, opcionalmente, `AGENTE_IMAP_PASTA`.

Vagas do LinkedIn, Indeed e afins entram só pelos alertas, porque os termos dessas plataformas proíbem leitura automatizada; para a descrição completa, cole o texto com `agente vagas link URL --descricao arquivo.txt`. Páginas de outros sites só são abertas se o robots.txt permitir.

A pauta lê seus repositórios pelo [GitHub CLI](https://cli.github.com) (`gh auth login`), somente leitura; repositórios privados e forks ficam de fora.

Os dados ficam em `data/perfil-mestre.json` (fora do git), configurável pela variável `AGENTE_CARREIRA_DATA`.

## Documentação

- [Especificação de Requisitos](<docs/Agente de Carreira — Especificação de Requisitos.pdf>) — documento completo *Agente de Carreira — Especificação de Requisitos* (versão de 16/11/2026), a fonte da verdade do projeto.

## Decisões em aberto

Já decidido: construção B, em código próprio em Python. Motor por tarefa, canal de notificação e modo por plataforma ficam na configuração (`agente config`) e mudam sem mexer no código.

Modo assistido no LinkedIn: disponível como automação opcional, desligada por padrão e ligada só com o aceite do risco.

Ainda são suas: nível-alvo depois de 2026/2; faixa salarial (`agente respostas definir pretensao_estagio ...`); presencial fora de BH ou mudança de cidade; visibilidade do Open to Work; plataformas P2 da fase 2.
