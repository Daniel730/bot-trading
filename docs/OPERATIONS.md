# 🎮 Guia de Operações: Alpha Arbitrage

Este guia explica como interagir com o bot diariamente e como interpretar os seus sinais.

## 1. Comandos Telegram (Controlo Remoto)

O bot responde a comandos no Telegram para fornecer visibilidade instantânea.

| Comando | Descrição | Pro-Tip |
| :--- | :--- | :--- |
| `/status` | Mostra a fase atual do bot (Scanning, Booting, etc). | Útil para verificar se o bot está "preso". |
| `/exposure` | Exibe a percentagem de capital alocado por setor. | Verifica se estás perto do limite de 15%. |
| `/cash` | Balanço total e quanto está investido em SGOV. | Garante que tens liquidez para novas oportunidades. |
| `/macro` | Resumo do regime (BULL/BEAR) dos líderes de setor. | Verifica se o "filtro de pânico" está ativo. |
| `/why TICKER` | Gera a tese de investimento atual para um ativo. | Usa isto antes de aprovar um trade manual. |

## 2. Aprovação de Trades

Se o bot identificar um sinal de alta confiança (>0.5), ele enviará um pedido de aprovação:
- **Botão Approve**: Executa a ordem (ou simula em Shadow Mode).
- **Botão Reject**: Descarta o sinal e loga o motivo.

*Nota: Podes automatizar isto removendo o `request_approval` no monitor.py, mas em modo institucional recomendamos o modelo "Centauro" (aprovação humana).*

## 3. Gestão de Pares

Os pares de ativos são configurados no `src/monitor.py` ou via Base de Dados (`trading_bot.db`).
Para adicionar um novo par:
1.  Verifica se são **cointegrados**.
2.  Associa o par a um **setor** para que o filtro macro funcione.
3.  Reinicia o bot para inicializar o Filtro de Kalman do novo par.

## 5. Configurações de Segurança e Infraestrutura

O bot agora exige a configuração de variáveis de ambiente obrigatórias para garantir a segurança e o roteamento correto.

### Variáveis de Ambiente Obrigatórias

| Variável | Descrição | Importância |
| :--- | :--- | :--- |
| `POSTGRES_PASSWORD` | Senha para a base de dados PostgreSQL. | **Crítica**: O bot não inicia sem esta variável (removido default hardcoded). |
| `DASHBOARD_TOKEN` | Token de autenticação para o Dashboard. | **Crítica**: Exigido mesmo em `DEV_MODE=True`. |
| `REGION` | Região de execução (`US` ou `EU`). | Garante que os endpoints de hedge corretos são utilizados. |

### Verificação de Saúde (Docker)

O Docker Healthcheck agora monitoriza o endpoint `/` do `mcp-server` para garantir que o motor de execução está pronto para receber sinais.

## 6. Troubleshooting nos Logs
