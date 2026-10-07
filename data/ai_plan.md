# AI plan  (2026-10-07 05:50 UTC)

1) DIAGNOSIS: The recent performance shows a net loss of -1.22 USD for hour 0 with a win rate of 56.0%. The average win is 0.91 USD and the average loss is 1.1 USD, resulting in a payoff of 0.832, indicating a negative expectancy.

2) WHAT I CHANGED VS LAST HOUR: I increased the profit_target_usd to 4.00 to improve the average win relative to the average loss.

3) RISK: The worst downside of this change is that it may further reduce trade frequency and exacerbate losses if the market does not support higher profit targets.

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
profit_target_usd=3.5
HOURNET: 0=-1.22/50, 1=-14.56/26, 2=-22.41/25, 3=-4.38/38, 4=+4.14/34, 5=-32.52/27, 6=+4.12/46, 7=-15.71/45, 8=+12.39/43, 9=-49.71/26, 10=+16.43/28, 11=-11.83/29, 12=-24.43/40, 13=-18.09/54, 14=-8.86/38, 15=-19.02/31, 16=-2.36/34, 17=-111.92/34, 18=-88.13/30, 19=-3.65/28, 20=-24.2/23, 22=+3.27/18, 23=-4.06/20
BACKTEST_GATE: REJECTED: history too small (0 trades) - keep live params | cand exp=None baseline exp=None | cand net=None baseline net=None
CRITIC(Pass2): VETO | improvement margin=0.0
STOP_AUTO_TUNE: avg_win=0.91 avg_loss=1.1 payoff=0.832 n=25 | payoff 0.83 but avg win 0.91 is far below target 3.50 -> winners die early; loosen for room, not tighter
PROFESSIONALISM: 26/100 (unsafe)
GRADUATION: 1/7 checks | unsafe | live-account switch is MANUAL by design
