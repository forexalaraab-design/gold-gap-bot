# AI plan  (2026-10-07 23:36 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -18.78 with a win rate of 44.1% for the last hour. The average win is 1.84 and the average loss is 1.33, resulting in a payoff of 1.384.  
2) WHAT YOU CHANGED VS LAST HOUR: I lowered the profit_target_usd to 4.50 to improve the win rate.  
3) RISK: The downside of this change is that it may reduce overall profitability if the win rate does not improve significantly.  
4) PARAMS:  
PARAMS:  
momentum_min=0.60  
profit_target_usd=4.50  
max_loss_usd=1.60  
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.7
momentum_min=0.6
profit_target_usd=5.0
HOURNET: 0=-1.22/50, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-18.78/59, 13=-22.61/71, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+4.89/22, 23=-4.54/21
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=1.84 avg_loss=1.33 payoff=1.384 n=25 | payoff 1.38 > 1.35 -> winners are landing, give room
PROFESSIONALISM: 86/100 (ready_for_review)
GRADUATION: 4/7 checks | ready_for_review | live-account switch is MANUAL by design
