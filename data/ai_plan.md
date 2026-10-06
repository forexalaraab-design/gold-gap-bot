# AI plan  (2026-10-06 08:40 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -3.93 with a win rate of 46.7% and an average win of 1.106 against an average loss of -1.213, resulting in a payoff of 0.912. The current strategy is underperforming, indicating a need for adjustments to improve profitability.

2) WHAT I CHANGED VS LAST HOUR: I lowered the profit_target_usd to 3.80 to attempt to increase trade frequency and improve profitability.

3) RISK: The worst downside of this change is that it may lead to further losses if the average win does not meet the new target, compounding existing issues.

4) PARAMS:
PARAMS:
momentum_min=0.80
profit_target_usd=3.80
max_loss_usd=1.20
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.2
momentum_min=0.8
profit_target_usd=4.0
HOURNET: 0=+7.13/35, 1=-14.56/26, 2=-22.41/25, 3=-8.9/32, 4=+3.11/30, 5=-30.72/26, 6=+4.12/46, 7=-15.71/45, 8=+7.23/38, 9=-50.17/25, 10=+11.83/21, 11=-9.29/19, 12=-22.5/27, 13=-8.33/30, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+5.84/14, 23=-2.09/16
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.22 avg_loss=1.17 payoff=1.049 n=25 | payoff 1.05 inside the healthy band -> hold
PROFESSIONALISM: 32/100 (unsafe)
GRADUATION: 2/7 checks | unsafe | live-account switch is MANUAL by design
