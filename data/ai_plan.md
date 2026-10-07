# AI plan  (2026-10-07 12:51 UTC)

1) DIAGNOSIS: The recent performance shows a win rate of 66.67% with an average win of 3.17 and an average loss of -1.79, resulting in a payoff of 1.77. The last hour's net was -14.63, indicating a need for adjustments to improve profitability. 

2) WHAT I CHANGED VS LAST HOUR: I lowered the momentum_min to 0.60 to increase trade frequency and potential profitability.

3) RISK: The worst downside of this change could be an increase in losing trades due to lower entry thresholds.

4) PARAMS:  
PARAMS:  
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
HOURNET: 0=-1.22/50, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-20.61/56, 13=-18.09/54, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+3.27/18, 23=-4.06/20
BACKTEST_GATE: REJECTED: history too small (3 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.44 avg_loss=1.46 payoff=0.988 n=25 | payoff 0.99 but avg win 1.44 is far below target 6.00 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 95/100 (ready_for_review)
GRADUATION: 5/7 checks | ready_for_review | live-account switch is MANUAL by design
