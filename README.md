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

## Documentação

- [Requisitos (índice)](docs/requisitos-agente-de-carreira.pdf) — a fonte da verdade é o documento completo *Agente de Carreira — Especificação de Requisitos* (versão de 16/11/2026).

## Decisões em aberto

Nível-alvo depois de 2026/2; faixa salarial; presencial fora de BH ou mudança de cidade; visibilidade do Open to Work; modo assistido no LinkedIn; construção (A: dentro do Claude, ou B: código próprio em Python ou .NET); motor padrão por tarefa; canal de notificação; plataformas P2 da fase 2.
