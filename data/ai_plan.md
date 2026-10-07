# AI plan  (2026-10-06 23:49 UTC)

1) DIAGNOSIS: The recent performance shows a win rate of 42.5% with a net loss of -24.43 for hour 12 and a negative expectancy overall. The average win is 0.68 and the average loss is -0.86, resulting in a payoff of 0.79, which is below 1.0.

2) WHAT I CHANGED VS LAST HOUR: I increased the profit_target_usd to 3.50 to improve the payoff ratio.

3) RISK: The worst downside of this change is that it may further reduce trade frequency and exacerbate losses if the market conditions do not improve.

4) PARAMS:
momentum_min=0.60
profit_target_usd=3.50
max_loss_usd=0.80
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=0.9
momentum_min=0.6
profit_target_usd=3.0
HOURNET: 0=+7.13/35, 1=-14.56/26, 2=-22.41/25, 3=-8.9/32, 4=+3.11/30, 5=-30.72/26, 6=+4.12/46, 7=-15.71/45, 8=+12.39/43, 9=-49.71/26, 10=+16.43/28, 11=-11.83/29, 12=-24.43/40, 13=-18.09/54, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+3.27/18, 23=-3.32/19
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=0.68 avg_loss=0.86 payoff=0.792 n=25 | payoff 0.79 but avg win 0.68 is far below target 3.00 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 14/100 (unsafe)
GRADUATION: 1/7 checks | unsafe | live-account switch is MANUAL by design
