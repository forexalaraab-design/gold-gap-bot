# AI daily plan

**Diagnosis of Trading Performance (XAUUSD Demo)**

1. **Losing Hours**: The majority of losses occur between 04:00 and 07:00, indicating a potential unfavorable trading environment during these hours.

2. **Win vs. Loss Shape**: The strategy shows a higher frequency of wins (approximately 60% of trades) but suffers from larger losses compared to wins. The average loss is around -1.25, while the average win is approximately +0.75, leading to a net-negative performance.

3. **Net-Negative Strategy**: The strategy is net-negative due to the disproportionate size of losses compared to wins, indicating poor risk management.

**Recommendations**:
- **Entry Threshold**: Implement a minimum price movement of 0.5% before entering trades to avoid choppy market conditions.
- **Time Filter**: Avoid trading between 04:00 and 07:00 to reduce exposure to losing hours.
- **Stop Loss/Take Profit (SL/TP)**: Set a SL at 1.5 times the average loss (around 1.88) and a TP at 1.5 times the average win (around 1.13) to improve risk-reward ratio.

By adjusting these parameters, the strategy can potentially enhance profitability and reduce risk exposure.
