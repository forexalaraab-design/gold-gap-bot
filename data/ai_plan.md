# AI plan  (2026-10-06 10:41 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -1.56 with a win rate of 50%. The average win is 1.4 and the average loss is 1.09, resulting in a payoff of 1.29, indicating a healthy ratio.

2) WHAT I CHANGED VS LAST HOUR: I lowered the momentum_min to 0.60 to increase trade frequency.

3) RISK: The worst downside of this change is potentially increasing low-quality trades, which could worsen the existing net loss.

4) PARAMS:  
PARAMS:  
momentum_min=0.60  
profit_target_usd=3.80  
max_loss_usd=1.20  
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.2
momentum_min=0.7
profit_target_usd=3.8
HOURNET: 0=+7.13/35, 1=-14.56/26, 2=-22.41/25, 3=-8.9/32, 4=+3.11/30, 5=-30.72/26, 6=+4.12/46, 7=-15.71/45, 8=+12.39/43, 9=-49.71/26, 10=+15.8/25, 11=-9.29/19, 12=-22.5/27, 13=-8.33/30, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+5.84/14, 23=-2.09/16
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.4 avg_loss=1.09 payoff=1.291 n=25 | payoff 1.29 inside the healthy band -> hold
PROFESSIONALISM: 91/100 (ready_for_review)
GRADUATION: 5/7 checks | ready_for_review | live-account switch is MANUAL by design
