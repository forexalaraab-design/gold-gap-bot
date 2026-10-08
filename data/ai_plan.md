# AI plan  (2026-10-08 00:36 UTC)

1) DIAGNOSIS: The recent performance shows an average win of 1.20 and an average loss of 1.68, resulting in a payoff of 0.715, indicating a negative expectancy. The current blocked hours include 1, 2, 5, 9, and 14, which are contributing to the overall negative net performance.

2) WHAT I CHANGED VS LAST HOUR: I have lowered the profit_target_usd to 4.00 to improve the payoff ratio.

3) RISK: The downside of this change is that it may lead to more frequent take-profits, potentially reducing overall profitability if the market conditions do not support this adjustment.

4) PARAMS:  
PARAMS:  
momentum_min=0.60  
profit_target_usd=4.00  
max_loss_usd=1.60  
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.7
momentum_min=0.6
profit_target_usd=4.5
HOURNET: 0=+4.15/58, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-18.78/59, 13=-22.61/71, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+4.89/22, 23=-6.26/23
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.2 avg_loss=1.68 payoff=0.715 n=25 | payoff 0.71 but avg win 1.20 is far below target 4.50 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 87/100 (ready_for_review)
GRADUATION: 3/7 checks | ready_for_review | live-account switch is MANUAL by design
