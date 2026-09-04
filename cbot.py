# -*- coding: utf-8 -*-
"""
cbot.py — Simple cTrader API wrapper
Connection, auth, symbols, prices, orders, close with auto-volume recovery.
"""

import random
import string
import time
import config
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages import OpenApiMessages_pb2 as ProtoMsgs
from twisted.internet import reactor, defer
from twisted.internet import task as _task


def _side(v):
    return ProtoMsgs.ProtoOATradeSide.DESCRIPTOR.values_by_name[v].number


def random_label(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _unwrap(msg):
    return Protobuf.extract(msg)


def _check_error(resp, ctx):
    code = getattr(resp, "errorCode", None)
    desc = (getattr(resp, "error_description", "") or
            getattr(resp, "message", "") or "")
    if code is None or code == 0 or str(code).strip() == "":
        # Expect either a numeric zero (success) or a non-empty error code.
        # Empty string / None without a valid order/position means the broker
        # rejected the request silently — treat as error.
        has_order = hasattr(resp, "order") and resp.order is not None
        has_position = hasattr(resp, "position") and resp.position is not None
        if not (has_order or has_position):
            raise RuntimeError(f"[{ctx}] broker rejected request (empty response)")
        return
    if str(code).strip() != "":
        code = int(code)
    if code != 0:
        raise RuntimeError(f"[{ctx}] errorCode={code} {desc}")


class _SpotWaiter:
    def __init__(self, sym_id):
        self.sym_id = sym_id
        self.d = defer.Deferred()
        self.done = False

    def _cb(self, inner):
        if self.done:
            return
        if (hasattr(inner, "symbolId") and
                inner.symbolId == self.sym_id and
                hasattr(inner, "bid")):
            self.done = True
            self.d.callback(inner)


class CtraderSession:
    def __init__(self):
        self.client = None
        self.account_id = None
        self._closed_positions = set()
        self.spot_cache = {}
        self._lock = defer.DeferredLock()
        self.last_positions = []
        self._last_positions = []

    # ── send ──────────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def _send(self, req, timeout=15):
        d = self._lock.acquire()
        d.addCallback(lambda _: self.client.send(req, responseTimeoutInSeconds=timeout))
        d.addBoth(lambda r: (self._lock.release(), r)[1])
        res = yield d
        defer.returnValue(res)

    # ── spot callback ──────────────────────────────────────────────────
    def _on_msg(self, client, msg):
        try:
            inner = _unwrap(msg)
        except Exception:
            return
        if (hasattr(inner, "symbolId") and
                hasattr(inner, "bid") and
                hasattr(inner, "ask")):
            self.spot_cache[inner.symbolId] = (
                inner.bid, inner.ask, inner.timestamp
            )

    # ── subscribe spots ────────────────────────────────────────────────
    def subscribe_persistent(self, symbol_id):
        req = ProtoMsgs.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        self.client.send(req, responseTimeoutInSeconds=10)

    def latest_spot(self, symbol_id):
        return self.spot_cache.get(symbol_id)

    # ── connect ────────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def connect(self):
        host = (EndPoints.PROTOBUF_LIVE_HOST if
                config.ENVIRONMENT.strip().lower() == "live"
                else EndPoints.PROTOBUF_DEMO_HOST)
        self.client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setMessageReceivedCallback(self._on_msg)
        self.client.setConnectedCallback(lambda c: None)
        self.client.startService()
        conn = self.client.whenConnected(failAfterFailures=1)
        yield conn.addTimeout(config.CONNECT_TIMEOUT, reactor)
        defer.returnValue(host)

    # ── auth 3-step ────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def authenticate(self, access_token):
        # 1. app auth
        req = ProtoMsgs.ProtoOAApplicationAuthReq(
            clientId=config.APP_CLIENT_ID.strip(),
            clientSecret=config.APP_CLIENT_SECRET.strip())
        res = yield self._send(req, 15)
        res = _unwrap(res)
        _check_error(res, "app auth")

        # 2. get accounts
        req = ProtoMsgs.ProtoOAGetAccountListByAccessTokenReq(
            accessToken=access_token)
        res = yield self._send(req, 15)
        res = _unwrap(res)
        _check_error(res, "account list")
        accounts = list(res.ctidTraderAccount)
        if not accounts:
            raise RuntimeError("no accounts linked to this token")

        want_live = config.ENVIRONMENT.strip().lower() == "live"
        match = [a for a in accounts if bool(a.isLive) == want_live]
        if not match:
            match = accounts
        target = match[0]

        # 3. account auth
        req = ProtoMsgs.ProtoOAAccountAuthReq(
            ctidTraderAccountId=target.ctidTraderAccountId,
            accessToken=access_token)
        res = yield self._send(req, 15)
        res = _unwrap(res)
        _check_error(res, "account auth")
        self.account_id = res.ctidTraderAccountId
        defer.returnValue(self.account_id)

    # ── trader info ─────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def get_trader(self):
        req = ProtoMsgs.ProtoOATraderReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, 30)
        res = _unwrap(res)
        defer.returnValue(res.trader)

    # ── find symbol ─────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def find_symbol(self, name):
        req = ProtoMsgs.ProtoOASymbolsListReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, 15)
        res = _unwrap(res)
        for sym in res.symbol:
            if sym.symbolName == name:
                defer.returnValue(sym.symbolId)
        raise RuntimeError("symbol not found: " + name)

    # ── symbol info ─────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def symbol_info(self, symbol_id):
        req = ProtoMsgs.ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        res = yield self._send(req, 15)
        res = _unwrap(res)
        for sym in res.symbol:
            if sym.symbolId == symbol_id:

                def _g(n, d=0):
                    f = sym.DESCRIPTOR.fields_by_name.get(n)
                    return getattr(sym, n, 0) if f else d

                info = {
                    "digits": sym.digits,
                    "lotSize": sym.lotSize,
                    "minVolume": sym.minVolume,
                    "stepVolume": sym.stepVolume,
                    "pipSize": _g("pipSize"),
                    "pipPosition": _g("pipPosition"),
                    "minDistance": _g("minDistance"),
                    "minStopLossDistance": _g("minStopLossDistance"),
                    "minTakeProfitDistance": _g("minTakeProfitDistance"),
                }
                defer.returnValue(info)
        raise RuntimeError("symbol details not returned for id " +
                           str(symbol_id))

    # ── get spot (wait for first tick) ────────────────────────────────
    @defer.inlineCallbacks
    def get_spot(self, symbol_id, timeout=12):
        waiter = _SpotWaiter(symbol_id)
        self.client.setMessageReceivedCallback(
            lambda c, m: waiter._cb(_unwrap(m)))
        req = ProtoMsgs.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        yield self._send(req, 10)
        ev = yield waiter.d.addTimeout(timeout, reactor)
        defer.returnValue((ev.bid, ev.ask, ev.timestamp))

    # ── open market order ─────────────────────────────────────────────
    @defer.inlineCallbacks
    def open_market(self, symbol_id, side, volume,
                    sl=None, tp=None, label="", comment=""):
        cls = ProtoMsgs.ProtoOANewOrderReq
        side_enum = (cls.DESCRIPTOR.fields_by_name["tradeSide"]
                     .enum_type.values_by_name["SELL"]
                     .number)
        if str(side).upper() == "BUY":
            side_enum = (cls.DESCRIPTOR.fields_by_name["tradeSide"]
                         .enum_type.values_by_name["BUY"].number)
        req = ProtoMsgs.ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.tradeSide = side_enum
        req.orderType = 1  # MARKET
        req.volume = volume
        req.label = label or random_label()
        req.comment = comment or ""
        # Note: SL/TP not sent — broker rejects them (TRADING_BAD_STOPS).
        # Closure relies solely on internal software layers.
        res = yield self._send(req, 30)
        res = _unwrap(res)
        # DEBUG: print raw response fields before _check_error
        code_val = getattr(res, "errorCode", "N/A")
        desc_val = getattr(res, "error_description", "") or getattr(res, "message", "")
        print(f"DEBUG open_market: errorCode={code_val!r} desc={desc_val!r}", flush=True)
        _check_error(res, "open_market")
        # Validate response actually contains a real order
        if not (hasattr(res, "order") and res.order is not None and
                getattr(res.order, "executionPrice", None) is not None):
            raise RuntimeError("open_market: broker returned empty/invalid order "
                               f"(executionPrice={getattr(res.order, 'executionPrice', None)!r})")
        defer.returnValue(res)

    # ── close position ────────────────────────────────────────────────
    @defer.inlineCallbacks
    def close_position(self, position_id, volume=None,
                       max_retries=3, delay_sec=2.0):
        if volume is None:
            positions = None
            try:
                positions = yield self.open_positions(self.account_id)
            except Exception as exc:
                print(f"close: reconcile fallback: {exc!r}")
                positions = getattr(self, "_last_positions", None) or []
            match = [p for p in positions
                     if p.positionId == position_id]
            if not match:
                raise RuntimeError(
                    f"position {position_id} not found in positions list")
            vol = getattr(match[0].tradeData, "volume", None)
            if vol is None:
                raise RuntimeError(
                    f"cannot determine volume for position {position_id}")
            volume = vol
        vol_int = int(round(volume))
        for attempt in range(1, max_retries + 1):
            req = ProtoMsgs.ProtoOAClosePositionReq()
            req.ctidTraderAccountId = self.account_id
            req.positionId = position_id
            req.volume = vol_int
            try:
                res = yield self._send(req, 15)
                res = _unwrap(res)
                _check_error(res, f"close #{attempt}")
                self._closed_positions.add(position_id)
                defer.returnValue(res)
            except Exception as exc:
                if attempt == max_retries:
                    print(f"close_position failed after "
                          f"{max_retries} retries: {exc!r}")
                    raise
                print(f"close attempt {attempt}/{max_retries} failed: "
                      f"{exc!r} → retry in {delay_sec}s")
                yield _task.deferLater(reactor, delay_sec, lambda: None)

    # ── set SL/TP ────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def set_sltp(self, position_id, sl, tp):
        req = ProtoMsgs.ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = self.account_id
        req.positionId = position_id
        req.stopLoss = sl
        req.takeProfit = tp
        res = yield self._send(req, 15)
        res = _unwrap(res)
        _check_error(res, "set_sltp")
        defer.returnValue(res)

    # ── list open positions ───────────────────────────────────────────
    @defer.inlineCallbacks
    def open_positions(self, account_id=None, max_age=None):
        aid = account_id or self.account_id
        now = time.time()
        start = now - (max_age if max_age else 300.0)
        req = ProtoMsgs.ProtoOAOrderListReq()
        req.ctidTraderAccountId = aid
        req.fromTimestamp = int(start * 1000)
        req.toTimestamp = int(now * 1000)
        try:
            res = yield self._send(req, 15)
            res = _unwrap(res)
            if hasattr(res, 'order'):
                self._last_positions = list(res.order)
                defer.returnValue(self._last_positions)
            else:
                self._last_positions = []
                defer.returnValue([])
        except Exception as exc:
            print(f"open_positions send failed: {exc!r}")
            self._last_positions = []
            defer.returnValue([])

    # ── stop ─────────────────────────────────────────────────────────
    def stop(self):
        try:
            if self.client is not None:
                self.client.stopService()
        except Exception:
            pass
