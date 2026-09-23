# -*- coding: utf-8 -*-
"""
test_sltp.py — مصفوفة اختبار حي (ديمو) لصيغ وضع SL/TP عبر OpenAPI.

الهدف: اكتشاف أي صيغة يقبلها FP Markets على XAUUSD (كسر TRADING_BAD_STOPS):
  V1   open + absolute sl/tp (double)                     trigger TRADE
  V2   open + absolute sl/tp (double)                     trigger OPPOSITE
  V3   open + absolute sl/tp (double)                     trigger DOUBLE_TRADE
  V4   open + absolute sl/tp (double)                     trigger DOUBLE_OPPOSITE
  V5   open + relativeStopLoss/TP (int, ×PRICE_UNIT)      trigger TRADE
  V6   open + relativeStopLoss/TP (int, ×PRICE_UNIT)      trigger OPPOSITE
  V7   naked open ثم AmendPositionSLTP absolute           trigger TRADE
  V8   naked open ثم AmendPositionSLTP absolute           trigger OPPOSITE
  V9   naked open ثم AmendPositionSLTP absolute           trigger DOUBLE_TRADE
  V10  naked open ثم AmendPositionSLTP absolute           trigger DOUBLE_OPPOSITE

كل صفقة تُفتح بملصق TST-SLTP وتُغلق فوراً بعد استخدامها. لا يلمس
السيجнал/الاستراتيجية إطلاقاً.
"""

import sys

import config
from cbot import CtraderSession, _check_error, _unwrap
from ctrader_open_api.messages import OpenApiMessages_pb2 as ProtoMsgs
from twisted.internet import task, defer

SYMBOL = "XAUUSD"
VOL = 100            # 0.01 lots (lotSize=10000)
SL_DIST = 2.00       # STOP dollars from entry
TP_DIST = 1.40       # TP dollars from entry
LABEL_PREFIX = "TST-SLTP"
PRICE_UNIT = 100     # digits == 2

TRI = {"TRADE": 1, "OPPOSITE": 2, "DOUBLE_TRADE": 3, "DOUBLE_OPPOSITE": 4}


@defer.inlineCallbacks
def _send(req, sess, timeout=25):
    res = yield sess._send(req, timeout)
    defer.returnValue(_unwrap(res))


def _symvalue(sym, n):
    f = sym.DESCRIPTOR.fields_by_name.get(n)
    return getattr(sym, n, None) if f else None


@defer.inlineCallbacks
def _close_test_positions(sess):
    try:
        positions = yield sess.open_positions(sess.account_id, max_age=86400.0)
        for p in list(positions):
            tl = getattr(getattr(p, "tradeData", None), "label", "") or ""
            if tl.startswith(LABEL_PREFIX):
                creq = ProtoMsgs.ProtoOAClosePositionReq()
                creq.ctidTraderAccountId = sess.account_id
                creq.positionId = p.positionId
                creq.volume = p.tradeData.volume
                yield sess._send(creq, 20)
                print("closed test pos", p.positionId, flush=True)
    except Exception as exc:
        print("cleanup err:", repr(exc), flush=True)


@defer.inlineCallbacks
def _open_market(sess, symbol_id):
    req = ProtoMsgs.ProtoOANewOrderReq()
    req.ctidTraderAccountId = sess.account_id
    req.symbolId = symbol_id
    req.tradeSide = 1                        # BUY
    req.orderType = 1                        # MARKET
    req.volume = VOL
    req.label = LABEL_PREFIX
    req.comment = ""
    res = yield sess._send(req, 25)
    defer.returnValue(_unwrap(res))


def _new_with_stops(ask_raw):
    req = ProtoMsgs.ProtoOANewOrderReq()
    req.stopLoss = (ask_raw / PRICE_UNIT) - SL_DIST
    req.takeProfit = (ask_raw / PRICE_UNIT) + TP_DIST
    return req


@defer.inlineCallbacks
def main(reactor):
    token = config.CBOT_ACCESS_TOKEN.strip()
    if not token:
        print("NO_TOKEN: CBOT_ACCESS_TOKEN not set")
        defer.returnValue(2)

    sess = CtraderSession()
    yield sess.connect()
    account = yield sess.authenticate(token)
    print("auth account", account, flush=True)

    symbol_id = yield sess.find_symbol(SYMBOL)
    res = yield _send(ProtoMsgs.ProtoOASymbolByIdReq(
        ctidTraderAccountId=account, symbolId=[symbol_id]), sess, 15)
    sym = next((s for s in res.symbol if s.symbolId == symbol_id), None)
    if sym is None:
        print("symbol not loaded"); defer.returnValue(2)
    b, a, _t = yield sess.get_spot(symbol_id)
    print("sym digits=%s lotSize=%s slDist=%s tpDist=%s distanceSetIn=%s"
          % (_symvalue(sym, "digits"), _symvalue(sym, "lotSize"),
             _symvalue(sym, "slDistance"), _symvalue(sym, "tpDistance"),
             _symvalue(sym, "distanceSetIn")), flush=True)
    print("spot bid=%.2f ask=%.2f" % (b / PRICE_UNIT, a / PRICE_UNIT), flush=True)

    def report(tag, status, extra=""):
        print("%s -> %s %s" % (tag, status, extra), flush=True)

    # ---- V1..V4: open with absolute prices, 4 trigger methods ----
    for trig, method in TRI.items():
        tag = "V%s" % ({"TRADE": 1, "OPPOSITE": 2,
                        "DOUBLE_TRADE": 3, "DOUBLE_OPPOSITE": 4}[trig])
        req = _new_with_stops(a)
        req.ctidTraderAccountId = sess.account_id
        req.symbolId = symbol_id
        req.tradeSide = 1
        req.orderType = 1
        req.volume = VOL
        req.label = LABEL_PREFIX
        req.comment = ""
        req.stopTriggerMethod = method
        try:
            res2 = yield _send(req, sess)
            _check_error(res2, tag)
            report(tag, "ACCEPTED", "(absolute, trigger=%s)" % trig)
        except Exception as exc:
            report(tag, "REJECT", repr(exc))
        yield _close_test_positions(sess)

    # ---- V5..V6: open with relative offsets ----
    for trig in ("TRADE", "OPPOSITE"):
        tag = "V%s" % (5 if trig == "TRADE" else 6)
        req = ProtoMsgs.ProtoOANewOrderReq()
        req.relativeStopLoss = int(SL_DIST * PRICE_UNIT)
        req.relativeTakeProfit = int(TP_DIST * PRICE_UNIT)
        req.ctidTraderAccountId = sess.account_id
        req.symbolId = symbol_id
        req.tradeSide = 1
        req.orderType = 1
        req.volume = VOL
        req.label = LABEL_PREFIX
        req.comment = ""
        req.stopTriggerMethod = TRI[trig]
        try:
            res3 = yield _send(req, sess)
            _check_error(res3, tag)
            report(tag, "ACCEPTED", "(relative, trigger=%s)" % trig)
        except Exception as exc:
            report(tag, "REJECT", repr(exc))
        yield _close_test_positions(sess)

    # ---- naked open then amend matrix ----
    res4 = yield _open_market(sess, symbol_id)
    _check_error(res4, "naked")
    pos_id = None
    entry = None
    positions = yield sess.open_positions(sess.account_id, max_age=86400.0)
    for p in list(positions):
        tl = getattr(getattr(p, "tradeData", None), "label", "") or ""
        if tl.startswith(LABEL_PREFIX):
            pos_id = p.positionId
            entry = getattr(p, "price", None) or (a / PRICE_UNIT)
    print("naked positionId", pos_id, "entry", entry, flush=True)
    if pos_id is None:
        print("cannot resolve naked position; abort"); defer.returnValue(1)

    for trig, method in TRI.items():
        tag = "V%s" % (7 if trig == "TRADE" else
                       8 if trig == "OPPOSITE" else
                       9 if trig == "DOUBLE_TRADE" else 10)
        areq = ProtoMsgs.ProtoOAAmendPositionSLTPReq()
        areq.ctidTraderAccountId = sess.account_id
        areq.positionId = pos_id
        areq.stopLoss = float(entry) - SL_DIST
        areq.takeProfit = float(entry) + TP_DIST
        areq.stopLossTriggerMethod = method
        try:
            res5 = yield _send(areq, sess)
            _check_error(res5, tag)
            report(tag, "ACCEPTED", "(absolute amend, trigger=%s)" % trig)
        except Exception as exc:
            report(tag, "REJECT", repr(exc))

    yield _close_test_positions(sess)
    print("DONE", flush=True)
    defer.returnValue(0)


if __name__ == "__main__":
    sys.exit(task.react(lambda r: main(r)))