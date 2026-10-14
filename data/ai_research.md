# AI research log (append-only)
- [2026-10-06 01:59] baseline: signalled=0/507 -> no edge extractable yet (OOS search parked until >=40)
- [2026-10-07 15:47] real_state: last50 win%38.0 avgW0.80 avgL1.38 payoff0.58 net-27.50 -> winners dying early; need samples+room (autonomous)
- [2026-10-07 15:49] cycle: handing control to self-tuning (samples+room)
- [2026-10-07 16:43] state: collecting real signal samples at mom=1.1 with enforced stop 1.35; OOS search activates at >=40 signalled trades
- [2026-10-08 18:04] user: disabled AI self-tuning (AI_ON=0, AI_APPLY_ON=0); running without the brain
- [2026-10-08 18:08] manual: momentum_min set to 1.0 (AI disabled)
- [2026-10-08 18:21] manual: removed session blocks; mom=0.8, max_loss=1.5 for stronger entries & more trades (AI off)
