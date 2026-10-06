# AI plan  (2026-10-06 02:39 UTC)

1) DIAGNOSIS: The average win is $0.85 and the average loss is -$1.289, resulting in a payoff ratio of 0.659, indicating a negative expectancy. Recent performance shows a net loss of -19.41 over 30 trades with a win rate of only 30.0%.

2) WHAT I CHANGED VS LAST HOUR: I increased the profit_target_usd to 4.50 to improve the payoff ratio.

3) RISK: The worst downside of this change is that it may further reduce trade frequency and exacerbate losses if the average win does not reach the new target.

4) PARAMS:
momentum_min=1.20
profit_target_usd=4.50
max_loss_usd=1.20
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.3
momentum_min=1.2
profit_target_usd=4.0
HOURNET: 0=+7.13/35, 1=-14.56/26, 2=-22.41/25, 3=-3.27/23, 4=-0.65/26, 5=-34.79/25, 6=+2.59/32, 7=-12.22/34, 8=+9.23/29, 9=-50.17/25, 10=+11.83/21, 11=-9.29/19, 12=-22.5/27, 13=-8.33/30, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+5.84/14, 23=-2.09/16
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=0.94 avg_loss=1.32 payoff=0.71 n=25 | payoff 0.71 but avg win 0.94 is far below target 4.00 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 13/100 (unsafe)
GRADUATION: 2/7 checks | unsafe | live-account switch is MANUAL by design
