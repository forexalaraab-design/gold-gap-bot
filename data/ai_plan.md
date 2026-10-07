# AI plan  (2026-10-07 14:51 UTC)

1) DIAGNOSIS: The recent performance shows a win rate of 43.3% with an average win of $2.08 and an average loss of -$1.39, resulting in a payoff of 1.50. The last hour's net was -22.61 with a win rate of 39.4%.

2) WHAT I CHANGED VS LAST HOUR: I lowered the momentum_min to 0.60 and adjusted max_loss_usd to 1.65 to improve trade frequency and manage risk better.

3) RISK: The worst downside of this change could be an increase in losing trades due to the lower entry threshold.

4) PARAMS:
PARAMS:
momentum_min=0.60
profit_target_usd=6.00
max_loss_usd=1.65
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.6
momentum_min=0.6
profit_target_usd=6.0
HOURNET: 0=-1.22/50, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=-2.01/51, 7=-14.63/60, 8=+11.9/51, 9=-49.71/26, 10=+16.72/38, 11=-11.85/33, 12=-18.78/59, 13=-22.61/71, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+3.27/18, 23=-4.06/20
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=2.12 avg_loss=1.4 payoff=1.517 n=25 | payoff 1.52 > 1.35 -> winners are landing, give room
PROFESSIONALISM: 80/100 (ready_for_review)
GRADUATION: 5/7 checks | ready_for_review | live-account switch is MANUAL by design
