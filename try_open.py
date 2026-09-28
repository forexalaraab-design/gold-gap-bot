import os
import config
from cbot import CtraderSession
from twisted.internet import defer, reactor
from main import resolve_token, _to_int


@defer.inlineCallbacks
def run():
    sess = CtraderSession()
    yield sess.connect()
    acc = yield sess.authenticate(resolve_token())
    print("auth ok account:", acc)
    sid = yield sess.find_symbol(config.SYMBOL)
    info = yield sess.symbol_info(sid)
    print("symbol:", sid, "minVol:", info.get("minVolume"),
          "lotSize:", info.get("lotSize"), "digits:", info.get("digits"))
    bid, ask, ts = yield sess.get_spot(sid)
    mid = (bid + ask) / 2 / config.SPOT_SCALE
    print(f"mid={mid:.2f} (bid={bid/config.SPOT_SCALE:.2f} ask={ask/config.SPOT_SCALE:.2f})")
    vol = int(round(config.LOT * info["lotSize"]))
    try:
        res = yield sess.open_market(sid, "BUY", vol,
                                     sl=_to_int(mid - 5.0),
                                     tp=_to_int(mid + 5.0),
                                     label="TST1", comment="")
        print("OPEN results stops_set=", res.get("stops_set"))
        pos_id = res.get("positionId")
        print("OPEN positionId=", pos_id)
        o = res.get("order")
        print("OPEN order=", (getattr(o, "orderId", None)
                              if o is not None else None))
        p = res.get("position")
        if p is not None:
            print("position SL=", getattr(p, "stopLoss", None),
                  "TP=", getattr(p, "takeProfit", None))
        if pos_id is None and p is not None:
            pos_id = getattr(p, "positionId", None)
        if pos_id:
            try:
                yield sess.set_sltp(pos_id, _to_int(mid - 5.0), _to_int(mid + 5.0))
                print("SETSLTP OK")
            except Exception as e:
                print("SETSLTP FAIL:", repr(e))
            try:
                yield sess.close_position(pos_id)
                print("CLOSE OK")
            except Exception as e:
                print("CLOSE FAIL:", repr(e))
    except Exception as e:
        print("FULL-FAIL:", repr(e))
    sess.stop()
    reactor.stop()


if __name__ == "__main__":
    reactor.callWhenRunning(run)
    reactor.run()
