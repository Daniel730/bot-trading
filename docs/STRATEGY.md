# 📊 Estratégia e Alpha: Alpha Arbitrage

A inteligência do Alpha Arbitrage baseia-se na exploração de ineficiências de reversão à média (Mean Reversion) validadas por contexto macroeconómico.

## 1. Fundamentos Quânticos

### Cointegração vs Correlação
O bot não procura ativos que apenas se movam na mesma direção (correlação). Ele procura ativos que mantenham uma **relação de equilíbrio de longo prazo** (cointegração).
- Se dois ativos são cointegrados, qualquer divergência no seu diferencial de preço (spread) tende a ser temporária.
- Utilizamos o **Teste de Engle-Granger** para verificar a cointegração antes de adicionar qualquer par à lista ativa.

### Cálculo do Spread (Kalman)
O spread é calculado como:
`Spread = Preço_A - (Hedge_Ratio * Preço_B + Intercept)`

O Filtro de Kalman ajusta o `Hedge_Ratio` e o `Intercept` a cada novo tick de mercado, permitindo que o bot entenda se o "preço justo" da relação mudou ou se há uma oportunidade de arbitragem.

---

## 2. Filtros Macro e Narrativa

### Beacon Assets (Faróis de Setor)
Para evitar "Value Traps" e contágio de mercado, utilizamos o conceito de **Beacon Assets**. Cada setor tem um líder institucional que serve como barómetro de saúde:
- **Tecnologia**: NVIDIA (NVDA)
- **Finanças**: JP Morgan (JPM)
- **Energia**: Exxon Mobil (XOM)
- **Consumo**: Coca-Cola (KO)

**Lógica de Veto**:
Se o Beacon Asset de um setor cair mais de 3.5% (Sigma-3) ou entrar num regime de "Extreme Volatility", o bot veta automaticamente qualquer entrada em pares desse setor, mesmo que o Z-Score sugira um trade. Isto protege o capital contra correlações espúrias em momentos de pânico.

---

## 3. Seleção de Pares (Setorial)
Rejeitamos abordagens de "Força Bruta" (testar todos contra todos). A nossa seleção foca-se em pares com fundamentação económica real:
- **Líderes vs Alternativos** (ex: AMD/NVDA)
- **Duenopólios** (ex: V/MA, KO/PEP)
- **ETFs vs Componentes** (ex: XLK/AAPL)

Esta restrição garante que a reversão à média seja ancorada em forças macroeconómicas reais, e não apenas em variações estatísticas aleatórias nos dados passados (*Data Mining Bias*).

---

## 4. Otimização Sortino
O bot utiliza o **Rácio de Sortino** para decidir a alocação. Ao contrário do Rácio de Sharpe, o Sortino foca-se apenas no **Desvio Descendente** (Downside Risk).
- Se o trade proposto aumentar o risco de queda do portefólio de forma desproporcional ao lucro esperado, a confiança do sinal é penalizada.
- Isto garante que o bot prefira trades estáveis a trades altamente voláteis, mesmo que o retorno esperado seja maior nestes últimos.
