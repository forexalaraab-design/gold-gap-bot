# AI plan  (2026-10-08 05:37 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -14.56 USD for hour 1 with a win rate of 57.7%. The average win is 1.4 USD and the average loss is 1.25 USD, resulting in a payoff of 1.116.

2) WHAT I CHANGED VS LAST HOUR: I have lowered the max_loss_usd to 1.50 to reduce the risk of larger losses.

3) RISK: The worst downside of this change is that it may lead to more frequent stop-outs without addressing the underlying negative performance.

4) PARAMS:
PARAMS:
momentum_min=0.60
profit_target_usd=4.00
max_loss_usd=1.50
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.6
momentum_min=0.6
profit_target_usd=4.0
HOURNET: 0=+3.06/61, 1=-14.56/26, 2=-22.41/25, 3=-2.77/49, 4=+5.11/40, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-18.78/59, 13=-22.61/71, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+4.89/22, 23=-6.26/23
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.4 avg_loss=1.25 payoff=1.116 n=25 | payoff 1.12 inside the healthy band -> hold
PROFESSIONALISM: 96/100 (ready_for_review)
GRADUATION: 5/7 checks | ready_for_review | live-account switch is MANUAL by design
