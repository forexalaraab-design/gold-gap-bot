# AI plan  (2026-10-06 21:48 UTC)

1) DIAGNOSIS: The recent performance shows a win rate of 40.7% with an average win of $0.68 and an average loss of -$0.89, resulting in a payoff of 0.77. The current strategy is not profitable, with a negative expectancy of -0.467.

2) WHAT I CHANGED VS LAST HOUR: I increased the profit_target_usd to 2.80 to improve the average win relative to the average loss.

3) RISK: The downside of this change is that it may lead to fewer trades if the market does not reach the higher profit target.

4) PARAMS:
PARAMS:
momentum_min=0.60
profit_target_usd=2.80
max_loss_usd=0.80
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=0.9
momentum_min=0.6
profit_target_usd=2.4
HOURNET: 0=+7.13/35, 1=-14.56/26, 2=-22.41/25, 3=-8.9/32, 4=+3.11/30, 5=-30.72/26, 6=+4.12/46, 7=-15.71/45, 8=+12.39/43, 9=-49.71/26, 10=+16.43/28, 11=-11.83/29, 12=-24.43/40, 13=-18.09/54, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+5.84/14, 23=-2.09/16
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=0.68 avg_loss=0.89 payoff=0.771 n=25 | payoff 0.77 but avg win 0.68 is far below target 2.40 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 15/100 (unsafe)
GRADUATION: 1/7 checks | unsafe | live-account switch is MANUAL by design
