# AI plan  (2026-10-07 09:50 UTC)

1) DIAGNOSIS: The average win is 1.34 and the average loss is 1.69, resulting in a payoff of 0.793, indicating a negative expectancy. Recent trades show a net loss of -1.22 for hour 0 and -14.56 for hour 1, suggesting poor performance during these hours.

2) WHAT I CHANGED VS LAST HOUR: I lowered the max_loss_usd to 1.50 to mitigate downside risk.

3) RISK: The worst downside of this change is that it may lead to more frequent stop-outs, potentially reducing overall trade frequency.

4) PARAMS:
PARAMS:
momentum_min=0.60
profit_target_usd=6.00
max_loss_usd=1.50
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.7
momentum_min=0.6
profit_target_usd=6.0
HOURNET: 0=-1.22/50, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.43/28, 11=-11.83/29, 12=-24.43/40, 13=-18.09/54, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+3.27/18, 23=-4.06/20
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.34 avg_loss=1.69 payoff=0.793 n=25 | payoff 0.79 but avg win 1.34 is far below target 6.00 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 32/100 (unsafe)
GRADUATION: 2/7 checks | unsafe | live-account switch is MANUAL by design
