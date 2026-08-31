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
    print("symbol:", sid, "minVol:", info.get("minVolume"), "lotSize:", info.get("lotSize"))
    bid, ask, ts = yield sess.get_spot(sid)
    mid = (bid + ask) / 2 / config.SPOT_SCALE
    print(f"mid={mid:.2f} (bid={bid/config.SPOT_SCALE:.2f} ask={ask/config.SPOT_SCALE:.2f})")
    vol = int(round(config.LOT * info["lotSize"]))
    try:
        res = yield sess.open_market(sid, "BUY", vol,
                                     sl=_to_int(mid - 5.0),
                                     tp=_to_int(mid + 5.0),
                                     label="TST1", comment="")
        print("OPEN OK orderId=", res.order.orderId,
              "positionId=", res.position.positionId if res.position else None)
        if res.position:
            try:
                yield sess.set_sltp(res.position.positionId, _to_int(mid - 5.0), _to_int(mid + 5.0))
                print("SETSLTP OK")
            except Exception as e:
                print("SETSLTP FAIL:", repr(e))
            yield sess.close_position(res.position.positionId)
            print("CLOSE OK")
    except Exception as e:
        print("FULL-FAIL:", repr(e))
    sess.stop()
    reactor.stop()


if __name__ == "__main__":
    reactor.callWhenRunning(run)
    reactor.run()
