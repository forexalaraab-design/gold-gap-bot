# -*- coding: utf-8 -*-
"""
cbot.py — غلاف cTrader Open API (اتصال + مصادقة + رمز + صفقات)
يدعم: اتصال TCP، مصادقة ثلاثية، بحث عن رمز، معلومات الرمز،
       الاشتراك في الأسعار، الإغلاق مع استعادة volume تلقائي، reconcile.
"""

import random
import string
import time
import config
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages import OpenApiMessages_pb2 as ProtoMsgs
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as Models
from twisted.internet import reactor, defer
from twisted.internet import task as _task


# =============================================================================
# مساعدة
# =============================================================================

def _side(v):
    return Models.ProtoOATradeSide.DESCRIPTOR.values_by_name[v].number


def random_label(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _unwrap(message):
    return Protobuf.extract(message)


def _check_error(resp, context):
    code = getattr(resp, "errorCode", 0)
    if code != 0:
        desc = (getattr(resp, "error_description", "") or
                getattr(resp, "message", "") or "")
        raise RuntimeError(f"[{context}] errorCode={code} {desc}")


# =============================================================================
# انتظار تسجيل سعر واحد
# =============================================================================

class _WsWaiter:
    def __init__(self, symbol_id):
        self.symbol_id = symbol_id
        self.deferred = defer.Deferred()
        self.received = False

    def _on_msg(self, inner):
        if self.received:
            return
        if (hasattr(inner, "symbolId") and
                inner.symbolId == self.symbol_id and
                hasattr(inner, "bid")):
            self.received = True
            self.deferred.callback(inner)


# =============================================================================
# الجلسة
# =============================================================================

class CtraderSession:
    def __init__(self):
        self.client = None
        self.account_id = None
        self.spot_cache = {}
        self._send_lock = defer.DeferredLock()
        self._closed_positions = set()

    # ── إرسال آمن (يحمي من التداخل) ──────────────────────────────
    @defer.inlineCallbacks
    def _send(self, req, responseTimeoutInSeconds=15):
        d = self._send_lock.acquire()
        d.addCallback(
            lambda _: self.client.send(
                req, responseTimeoutInSeconds=responseTimeoutInSeconds
            )
        )
        d.addBoth(lambda r: (self._send_lock.release(), r)[1])
        res = yield d
        defer.returnValue(res)

    # ── استقبال الأسعار ────────────────────────────────────────────
    def _on_received(self, client, message):
        try:
            inner = _unwrap(message)
        except Exception:
            return
        if (hasattr(inner, "symbolId") and
                hasattr(inner, "bid") and
                hasattr(inner, "ask")):
            self.spot_cache[inner.symbolId] = (
                inner.bid, inner.ask, inner.timestamp
            )

    # ── الاشتراك في الأسعار (يستدعيه live.py ويستخدم latest_spot) ──
    def subscribe_persistent(self, symbol_id):
        req = ProtoMsgs.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        self.client.send(req, responseTimeoutInSeconds=10)

    def latest_spot(self, symbol_id):
        return self.spot_cache.get(symbol_id)

    # ── الاتصال TCP ────────────────────────────────────────────────
    @defer.inlineCallbacks
    def connect(self):
        host = (
            EndPoints.PROTOBUF_LIVE_HOST
            if config.ENVIRONMENT.strip().lower() == "live"
            else EndPoints.PROTOBUF_DEMO_HOST
        )
        self.client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setMessageReceivedCallback(self._on_received)
        self.client.setConnectedCallback(lambda c: None)
        self.client.startService()
        conn = self.client.whenConnected(failAfterFailures=1)
        yield conn.addTimeout(config.CONNECT_TIMEOUT, reactor)
        defer.returnValue(host)

    # ── المصادقة (ثلاث طبقات) ─────────────────────────────────────
    @defer.inlineCallbacks
    def authenticate(self, access_token):
        req = Models.ProtoOAApplicationAuthReq(
            clientId=config.APP_CLIENT_ID.strip(),
            clientSecret=config.APP_CLIENT_SECRET.strip(),
        )
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "app auth")

        req = Models.ProtoOAGetAccountListByAccessTokenReq(
            accessToken=access_token
        )
        res = yield self._send(req, responseTimeoutInSeconds=15)
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

        req = Models.ProtoOAAccountAuthReq(
            ctidTraderAccountId=target.ctidTraderAccountId,
            accessToken=access_token,
        )
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "account auth")
        self.account_id = res.ctidTraderAccountId
        defer.returnValue(self.account_id)

    # ── معلومات الحساب ─────────────────────────────────────────────
    @defer.inlineCallbacks
    def get_trader(self):
        req = Models.ProtoOATraderReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, responseTimeoutInSeconds=30)
        res = _unwrap(res)
        defer.returnValue(res.trader)

    # ── البحث عن رمز ───────────────────────────────────────────────
    @defer.inlineCallbacks
    def find_symbol(self, name):
        req = Models.ProtoOASymbolsListReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        for sym in res.symbol:
            if sym.symbolName == name:
                defer.returnValue(sym.symbolId)
        raise RuntimeError("symbol not found: " + name)

    # ── معلومات الرمز ──────────────────────────────────────────────
    @defer.inlineCallbacks
    def symbol_info(self, symbol_id):
        req = Models.ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        for sym in res.symbol:
            if sym.symbolId == symbol_id:

                def _g(name, default=0):
                    f = sym.DESCRIPTOR.fields_by_name.get(name)
                    return getattr(sym, name, 0) if f is not None else default

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
        raise RuntimeError("symbol details not returned for id " + str(symbol_id))

    # ── سعر فوري (ينتظر أول رسالة) ──────────────────────────────
    @defer.inlineCallbacks
    def get_spot(self, symbol_id, timeout=12):
        waiter = _WsWaiter(symbol_id)
        self.client.setMessageReceivedCallback(
            lambda c, m: waiter._on_msg(_unwrap(m))
        )
        req = ProtoMsgs.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        yield self._send(req, responseTimeoutInSeconds=10)
        ev = yield waiter.deferred.addTimeout(timeout, reactor)
        defer.returnValue((ev.bid, ev.ask, ev.timestamp))

    # ── أوامر السوق ────────────────────────────────────────────────
    @defer.inlineCallbacks
    def open_market(self, symbol_id, side, volume,
                    sl=None, tp=None, label="",
                    comment=""):
        cls = Models.ProtoOATradeSide
        side_enum = cls.SELL if str(side).upper() == "SELL" else cls.BUY
        req = Models.ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.tradeSide = side_enum
        req.volume = volume
        req.label = label or random_label()
        req.comment = comment or ""
        if sl is not None:
            req.stopLoss = sl
        if tp is not None:
            req.takeProfit = tp
        res = yield self._send(req, responseTimeoutInSeconds=30)
        res = _unwrap(res)
        _check_error(res, "open_market")
        defer.returnValue(res)

    # ── إغلاق صفقة مع استعادة volume تلقائي ─────────────────────
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
                    f"position {position_id} not found in positions list"
                )
            vol = getattr(match[0].tradeData, "volume", None)
            if vol is None:
                raise RuntimeError(
                    f"cannot determine volume for position {position_id}"
                )
            volume = vol
        vol_int = int(round(volume))
        for attempt in range(1, max_retries + 1):
            req = Models.ProtoOAClosePositionReq()
            req.ctidTraderAccountId = self.account_id
            req.positionId = position_id
            req.volume = vol_int
            try:
                res = yield self._send(req, responseTimeoutInSeconds=15)
                res = _unwrap(res)
                _check_error(res, f"close #{attempt}")
                self._closed_positions.add(position_id)
                defer.returnValue(res)
            except Exception as exc:
                if attempt == max_retries:
                    print(f"close_position failed after {max_retries} retries: "
                          f"{exc!r}")
                    raise
                print(f"close attempt {attempt}/{max_retries} failed: {exc!r} "
                      f"→ retry in {delay_sec}s")
                yield _task.deferLater(reactor, delay_sec, lambda: None)

    # ── تعديل SL/TP ────────────────────────────────────────────────
    @defer.inlineCallbacks
    def set_sltp(self, position_id, sl, tp):
        req = Models.ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = self.account_id
        req.positionId = position_id
        req.stopLoss = sl
        req.takeProfit = tp
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "set_sltp")
        defer.returnValue(res)

    # ── قائمة الصفقات المفتوحة ────────────────────────────────────
    @defer.inlineCallbacks
    def open_positions(self, account_id=None, max_age=None):
        aid = account_id or self.account_id
        start = time.time() - (max_age if max_age else 300.0)
        req = ProtoMsgs.ProtoOAOrderListReq()
        req.ctidTraderAccountId = aid
        req.startTime = int(start * 1000)
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        defer.returnValue(list(res.order))

    # ── إيقاف الخدمة ───────────────────────────────────────────────
    def stop(self):
        try:
            if self.client is not None:
                self.client.stopService()
        except Exception:
            pass
