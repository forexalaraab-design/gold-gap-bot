# AI plan  (2026-10-07 11:50 UTC)

1) DIAGNOSIS: The average win is $1.12, while the average loss is -$1.53, resulting in a payoff ratio of 0.73, indicating a negative expectancy. Recent trades show a net loss of -$3.43 over 30 trades with a win rate of 53.3%.

2) WHAT I CHANGED VS LAST HOUR: I increased the profit_target_usd to 6.00 to improve the payoff ratio.

3) RISK: The worst downside of this change is that it may further reduce trade frequency and exacerbate losses if the win rate does not improve.

4) PARAMS:
momentum_min=0.60
profit_target_usd=6.00
max_loss_usd=1.50
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.6
momentum_min=0.6
profit_target_usd=6.0
HOURNET: 0=-1.22/50, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-24.43/40, 13=-18.09/54, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+3.27/18, 23=-4.06/20
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=0.9 avg_loss=1.42 payoff=0.634 n=25 | payoff 0.63 but avg win 0.90 is far below target 6.00 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 37/100 (unsafe)
GRADUATION: 2/7 checks | unsafe | live-account switch is MANUAL by design
