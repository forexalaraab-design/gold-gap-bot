# AI plan  (2026-10-06 01:30 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -365.91 with an average win of 1.56 and an average loss of -3.56, resulting in a payoff ratio of 0.438. The win rate is 55.4%, indicating a need for adjustments to improve profitability. 

2) WHAT I CHANGED VS LAST HOUR: I have increased the profit_target_usd to 3.60 and reduced max_loss_usd to 1.20 to improve the payoff ratio.

3) RISK: The worst downside of this change is that it may lead to fewer trades being executed if the profit target is set too high relative to market conditions.

4) PARAMS:
momentum_min=1.20
profit_target_usd=3.60
max_loss_usd=1.20
blocked_hours=1,2,5,9,14,15

## APPLIED (auto-applied next cycle, hard-bounded)
PARAMS:
blocked_hours=[2, 5, 9, 14]
max_loss_usd=1.2
momentum_min=1.2
profit_target_usd=1.6
HOURNET: 0=+7.13/35, 1=-14.56/26, 2=-22.41/25, 3=-3.27/23, 4=-0.65/26, 5=-34.79/25, 6=+2.59/32, 7=-12.22/34, 8=+9.23/29, 9=-50.17/25, 10=+11.83/21, 11=-9.29/19, 12=-22.5/27, 13=-8.33/30, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+5.84/14, 23=-2.09/16
BACKTEST_GATE: REJECTED: no real signal data (0/507 trades carry catch_up, need 40) - refusing unvalidated change; truth: net=-365.91 payoff=0.438 over 507 trades | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
PROFESSIONALISM: 13/100 (unsafe)
GRADUATION: 2/7 checks | unsafe | live-account switch is MANUAL by design
