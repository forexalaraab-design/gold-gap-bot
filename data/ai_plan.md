# AI plan  (2026-10-08 01:36 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -18.78 with a win rate of 44.1% for hour 12, indicating poor profitability. The average win is 1.24 and the average loss is 1.62, resulting in a payoff of 0.766, which is below the target of 1.0.

2) WHAT I CHANGED VS LAST HOUR: I increased the profit_target_usd from 4.0 to 5.0 to improve the average win relative to the average loss.

3) RISK: The worst downside of this change is that it may further reduce the win rate if the market conditions do not support higher profit targets.

4) PARAMS:  
PARAMS:  
momentum_min=0.6  
profit_target_usd=5.0  
max_loss_usd=1.6  
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.7
momentum_min=0.6
profit_target_usd=4.0
HOURNET: 0=+3.06/61, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-18.78/59, 13=-22.61/71, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+4.89/22, 23=-6.26/23
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.24 avg_loss=1.62 payoff=0.766 n=25 | payoff 0.77 but avg win 1.24 is far below target 4.00 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 87/100 (ready_for_review)
GRADUATION: 3/7 checks | ready_for_review | live-account switch is MANUAL by design
