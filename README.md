# 🚀 Alpha Arbitrage V2: Institutional-Grade Engine

![Status](https://img.shields.io/badge/Status-Stable-green)
![Version](https://img.shields.io/badge/Sprint-K-blue)
![Architecture](https://img.shields.io/badge/Mode-Adaptive_Intelligence-purple)

**Alpha Arbitrage** é um motor de trading algorítmico de alta fidelidade desenhado para executar estratégias de Arbitragem Estatística com rigor institucional. O sistema agora opera em modo dual: servindo tanto traders institucionais com execução gRPC de baixa latência, quanto investidores de varejo através da nova **Suite de Investimento de Baixo Custo**.

---

## 🏛️ Filosofia: A Arquitetura Centauro

O projeto opera sob a filosofia **Centauro**:
1.  **Humano-no-Loop (Analista Macro)**: Define a narrativa e os faróis (Beacon Assets).
2.  **Robô-no-Loop (Executor Quant)**: Gere a matemática, o risco e a execução milimétrica.

Esta simbiose permite que o bot ignore o ruído do mercado e foque apenas em divergências estatisticamente significativas, validadas por uma tese económica real.

---

## 🧠 Core Tecnológico

### 1. Motor Quantitativo (Kalman Engine)
Utilizamos um **Filtro de Kalman Recursivo** para estimar o *Hedge Ratio* dinâmico entre pares de ativos.
- **Z-Score Dinâmico**: O bot calcula a distância da média em tempo real, ajustando-se à volatilidade.
- **Auto-Convergência**: O filtro adapta-se a mudanças estruturais sem intervenção manual.

### 2. Monitorização Adaptativa (PixelBot Interface)
O novo Dashboard de Inteligência utiliza **SSE (Server-Sent Events)** para telemetria em tempo real:
- **PixelBot**: Um agente visual que reflete o estado emocional do bot (Idle, Analyzing, Executing, Error).
- **Intelligence Hub**: Classificação de regime de mercado (Bull/Bear/Volatile) e confiança da estratégia global.

### 3. Alpha Verification & Shadow Mode
- **Achievable Alpha**: Cada sinal é auditado contra snapshots L2 para garantir que o lucro é executável.
- **Simulação Realista**: O Shadow Mode penaliza o tamanho da ordem com base na profundidade do livro (0.5bps por 10% de profundidade consumida).

---

## 💎 Suite de Investimento (Low-Budget Suite)

Desenvolvida para democratizar o trading quantitativo, esta suite permite operar com capital reduzido:
- **Fractional Engine**: Execução de ordens fracionárias com precisão de 6 casas decimais.
- **DCA Service**: Automação de investimentos recorrentes (Dollar Cost Averaging).
- **Goal-Setting**: Configuração de metas financeiras com ajuste dinâmico de risco.
- **Micro-Optimization**: Manutenção de fricção < 1.5% para investimentos mínimos.

### 4. Gestão Unificada de Orçamento (BudgetService)
O sistema agora rastreia de forma persistente o capital utilizado em cada venue:
- **Isolamento de Risco**: T212 e Web3 operam com limites de capital independentes e persistentes.
- **Continuidade**: O orçamento utilizado é guardado em SQLite, garantindo que o bot respeita os limites mesmo após reinícios.
- **Abstração de Venue**: O motor de arbitragem decide automaticamente onde executar com base no ticker, sem lógica hardcoded.

---

## 🛠️ Stack Técnica

- **Backend**: Python 3.11+ (FastAPI, SQLAlchemy, Pandas, Statsmodels)
- **Frontend**: React + Vite (Vanilla CSS, Framer Motion para animações "Elite")
- **Comunicação**: gRPC (Nanosegundos) & SSE (Dashboard Telemetry)
- **Infraestrutura**: PostgreSQL (Ledger), Redis (Telemetry/Idempotency), Docker.

---

## 🚀 Instalação e Configuração

### 1. Preparação
Clona o repositório e configura o teu ficheiro `.env`:
```bash
cp .env.template .env
```

### 2. Autenticação Trading 212
Para chaves modernas da T212, é necessário utilizar o protocolo **Basic Auth**:
- `T212_API_KEY`: A tua chave de API.
- `T212_API_SECRET`: O segredo da API (obrigatório para chaves com permissões totais).

### 3. Modo de Desenvolvimento (24/7)
Para testar o bot fora do horário de mercado (NYSE/NASDAQ):
- Define `DEV_MODE=true` no `.env`. O bot passará a vigiar pares Crypto (BTC-USD, ETH-USD).

---

## 📊 Comandos Estratégicos

### Investimento / DCA:
- `/invest.set_goal name="Casa" amount=50000 date=2030-01-01`: Define uma meta financeira.
- `/invest.dca amount=100 frequency=weekly strategy=ARBI`: Ativa o investimento recorrente.
- `/invest.why_buy TICKER`: Retorna a tese de investimento gerada pela IA.

### Monitorização / Auditoria:
- `/exposure`: Verifica a exposição por setor.
- `/dev.audit`: Verificação de saúde e padrões do projeto.
- `/macro`: Sumário do regime económico e volatilidade (Entropy L2).

---

## 📂 Estrutura do Projeto
```text
src/
├── agents/             # Swarm de IAs (Bull, Bear, Macro, Portfolio)
├── services/           # Negócio (Brokerage, Risk, DCA, Performance)
├── daemons/            # Workers de fundo (SEC Worker, Audit Worker)
└── monitor.py          # Entrypoint do motor de arbitragem
frontend/               # Dashboard React (Adaptive Intelligence Hub)
```

---

## ⚖️ Disclaimer
Este software é para fins educacionais. Trading envolve risco significativo. O desenvolvedor não se responsabiliza por perdas financeiras.
cacionais e de investigação. Trading envolve risco significativo de perda de capital. O desenvolvedor não se responsabiliza por perdas financeiras.
