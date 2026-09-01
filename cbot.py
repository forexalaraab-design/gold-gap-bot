# -*- coding: utf-8 -*-
"""
cbot.py — غلاف cTrader Open API المت 강화된 (إغلاق + reconcile + متابعة)
يدعم: اتصال، مصادقة، رمز، أسعار، صفقات، إغلاق مع volume حتمي، reconcile.
"""

import random
import string
import time
import config
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAAccountAuthReq,
    ProtoOASymbolsListReq,
    ProtoOASymbolByIdReq,
    ProtoOASubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOANewOrderReq,
    ProtoOAClosePositionReq,
    ProtoOAReconcileReq,
    ProtoOATraderReq,
    ProtoOAAmendPositionSLTPReq,
)
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as Models
from twisted.internet import reactor, defer
from twisted.internet import task as _task


def _side(v):
    return Models.ProtoOATradeSide.DESCRIPTOR.values_by_name[v].number


def random_label(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _unwrap(message):
    return Protobuf.extract(message)


class CtraderSession:
    def __init__(self):
        self.client = None
        self.account_id = None
        self.waiter = None
        self.spot_cache = {}
        self._pos_cache = None
        self._send_lock = defer.DeferredLock()
        self._closed_positions = set()

    # ── إرسال آمن (أقفال لمنع التداخل) ──────────────────────────────
    @defer.inlineCallbacks
    def _send(self, req, responseTimeoutInSeconds=30):
        d = self._send_lock.acquire()
        d.addCallback(
            lambda _: self.client.send(
                req, responseTimeoutInSeconds=responseTimeoutInSeconds
            )
        )
        d.addBoth(lambda r: (self._send_lock.release(), r)[1])
        res = yield d
        defer.returnValue(res)

    # ── استقبال الرسائل ──────────────────────────────────────────────
    def _on_received(self, client, message):
        try:
            inner = _unwrap(message)
        except Exception:
            return
        if hasattr(inner, "symbolId") and hasattr(inner, "bid") and hasattr(inner, "ask"):
            self.spot_cache[inner.symbolId] = (inner.bid, inner.ask, inner.timestamp)
        if self.waiter is not None and not self.waiter.deferred.called:
            if hasattr(inner, "symbolId") and inner.symbolId == self.waiter.symbol_id:
                self.waiter.deferred.callback(inner)

    def latest_spot(self, symbol_id):
        return self.spot_cache.get(symbol_id)

    def subscribe_persistent(self, symbol_id):
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        self.client.send(req, responseTimeoutInSeconds=10)

    # ── الاتصال ─────────────────────────────────────────────────────
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

    # ── المصادقة (ثلاث طبقات) ──────────────────────────────────────
    @defer.inlineCallbacks
    def authenticate(self, access_token):
        req = ProtoOAApplicationAuthReq(
            clientId=config.APP_CLIENT_ID.strip(),
            clientSecret=config.APP_CLIENT_SECRET.strip(),
        )
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "app auth")

        req = ProtoOAGetAccountListByAccessTokenReq(accessToken=access_token)
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

        req = ProtoOAAccountAuthReq(
            ctidTraderAccountId=target.ctidTraderAccountId,
            accessToken=access_token,
        )
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "account auth")
        self.account_id = res.ctidTraderAccountId
        defer.returnValue(self.account_id)

    # ── معلومات الحساب ──────────────────────────────────────────────
    @defer.inlineCallbacks
    def get_trader(self):
        req = ProtoOATraderReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, responseTimeoutInSeconds=30)
        res = _unwrap(res)
        defer.returnValue(res.trader)

    # ── البحث عن رمز ────────────────────────────────────────────────
    @defer.inlineCallbacks
    def find_symbol(self, name):
        req = ProtoOASymbolsListReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        for sym in res.symbol:
            if sym.symbolName == name:
                defer.returnValue(sym.symbolId)
        raise RuntimeError("symbol not found: " + name)

    # ── معلومات الرمز ───────────────────────────────────────────────
    @defer.inlineCallbacks
    def symbol_info(self, symbol_id):
        req = ProtoOASymbolByIdReq()
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

    # ── سعر فوري ────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def get_spot(self, symbol_id, timeout=12):
        self.waiter = _WsWaiter(symbol_id)
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        yield self._send(req, responseTimeoutInSeconds=10)
        ev = yield self.waiter.deferred.addTimeout(timeout, reactor)
        self.waiter = None
        try:
            unsub = ProtoOAUnsubscribeSpotsReq()
            unsub.ctidTraderAccountId = self.account_id
            unsub.symbolId.append(symbol_id)
            yield self._send(unsub, responseTimeoutInSeconds=5)
        except Exception:
            pass
        defer.returnValue((ev.bid, ev.ask, ev.timestamp))

    # ── صفقات مفتوحة ───────────────────────────────────────────────
    @defer.inlineCallbacks
    def open_positions(self, symbol_id, max_age=0.0):
        import time as _t
        now = _t.time()
        ctx = getattr(self, "_pos_cache", None)
        if max_age and ctx and (now - ctx[0]) < max_age:
            defer.returnValue(list(ctx[1]))
        req = ProtoOAReconcileReq(ctidTraderAccountId=self.account_id)
        res = yield self._send(req, responseTimeoutInSeconds=30)
        res = _unwrap(res)
        open_flags = (
            Models.ProtoOAPositionStatus.POSITION_STATUS_OPEN,
            Models.ProtoOAPositionStatus.POSITION_STATUS_CREATED,
        )
        found = [
            p
            for p in res.position
            if p.tradeData.symbolId == symbol_id and p.positionStatus in open_flags
        ]
        self._pos_cache = (_t.time(), list(found))
        defer.returnValue(found)

    @property
    def last_positions(self):
        return list(getattr(self, "_pos_cache", (0, []))[1])

    # ── إيجاد volume position (إجباري للإغلاق) ─────────────────────
    @defer.inlineCallbacks
    def resolve_position_volume(self, position_id, attempts=3):
        """إيجاد volume position عبر cache → reconcile → القيمة الافتراضية."""
        # 1. cache
        for p in self.last_positions:
            if p.positionId == position_id:
                vol = getattr(p.tradeData, "volume", None)
                if vol:
                    defer.returnValue(vol)
        # 2. reconcile مع إعادة محاولة
        for attempt in range(attempts):
            try:
                req = ProtoOAReconcileReq(ctidTraderAccountId=self.account_id)
                res = yield self._send(req, responseTimeoutInSeconds=30)
                res = _unwrap(res)
                for p in res.position:
                    if p.positionId == position_id:
                        vol = getattr(p.tradeData, "volume", None)
                        if vol:
                            defer.returnValue(vol)
                break
            except Exception as exc:
                if attempt < attempts - 1:
                    yield _task.deferLater(reactor, 2, lambda: None)
                else:
                    print(
                        "WARN _resolve_position_volume exhaust: ", repr(exc)
                    )
        # 3. افتراضي (0.01 لوت = volume 100 ل XAUUSD)
        defer.returnValue(100)

    # ── فتح صفقة ────────────────────────────────────────────────────
    @defer.inlineCallbacks
    def open_market(
        self, symbol_id, side, volume, sl=None, tp=None,
        label=None, comment="",
    ):
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.orderType = Models.ProtoOAOrderType.MARKET
        req.tradeSide = _side(side)
        req.volume = volume
        req.timeInForce = Models.ProtoOATimeInForce.IMMEDIATE_OR_CANCEL
        req.label = label if label else random_label()
        req.comment = comment
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "new order")
        if sl is not None or tp is not None:
            try:
                yield self.set_sltp(res.position.positionId, sl, tp)
            except Exception as exc:
                print("WARN: could not set SL/TP after open:", repr(exc))
        # تحديث cache
        import time as _t
        if res.position is not None:
            lst = list(getattr(self, "_pos_cache", (0, []))[1])
            lst = [p for p in lst if p.positionId != res.position.positionId]
            lst.append(res.position)
            self._pos_cache = (_t.time(), lst)
        defer.returnValue(res)

    # ── تعديل SL/TP ─────────────────────────────────────────────────
    @defer.inlineCallbacks
    def set_sltp(self, position_id, sl=None, tp=None):
        req = ProtoOAAmendPositionSLTPReq(
            ctidTraderAccountId=self.account_id,
            positionId=position_id,
            stopLoss=sl,
            takeProfit=tp,
        )
        res = yield self._send(req, responseTimeoutInSeconds=15)
        res = _unwrap(res)
        _check_error(res, "amend sl/tp")
        defer.returnValue(res)

    # ── إغلاق صفقة ──────────────────────────────────────────────────
    @defer.inlineCallbacks
    def close_position(self, position_id, volume=None, max_retries=3):
        """إغلاق صفقة مع إيجاد volume وتتأكد من وجوده.

        يضمن أن req.volume مُعيّن قبل الإرسال (proto2 required field).
        """
        # 1. إيجاد volume
        if volume is None:
            for p in self.last_positions:
                if p.positionId == position_id:
                    vol = getattr(p.tradeData, "volume", None)
                    if vol:
                        volume = vol
                        break
        if volume is None:
            try:
                req = ProtoOAReconcileReq(ctidTraderAccountId=self.account_id)
                res = yield self._send(req, responseTimeoutInSeconds=30)
                res = _unwrap(res)
                for p in res.position:
                    if p.positionId == position_id:
                        vol = getattr(p.tradeData, "volume", None)
                        if vol:
                            volume = vol
                            break
            except Exception as exc:
                print("reconcile-for-close WARN:", repr(exc))
        if volume is None:
            # افتراضي: 0.01 لوت ل XAUUSD = volume 100
            volume = 100
            print(
                "INFO close_position default volume=100 "
                f"for position {position_id}"
            )
        # 2. إغلاق مع إعادة محاولة
        last_exc = None
        for attempt in range(max_retries):
            try:
                req = ProtoOAClosePositionReq(
                    ctidTraderAccountId=self.account_id,
                    positionId=position_id,
                )
                req.volume = volume
                res = yield self._send(req, responseTimeoutInSeconds=30)
                res = _unwrap(res)
                _check_error(res, "close position")
                # تحديث cache
                import time as _t
                lst = list(getattr(self, "_pos_cache", (0, []))[1])
                lst = [p for p in lst if p.positionId != position_id]
                self._pos_cache = (_t.time(), lst)
                self._closed_positions.add(position_id)
                defer.returnValue(res)
            except Exception as exc:
                last_exc = exc
                print(
                    f"close_position(attempt {attempt+1}/{max_retries}) "
                    f"failed: {exc!r}"
                )
                if attempt < max_retries - 1:
                    yield _task.deferLater(reactor, 3, lambda: None)
        raise RuntimeError(
            f"close_position({position_id}) failed after "
            f"{max_retries} attempts: {last_exc!r}"
        )

    # ── إغلاق قسري (أخير) ──────────────────────────────────────────
    @defer.inlineCallbacks
    def force_close_position(self, position_id):
        """إغلاق抜esis بغض النظر عن الحالة — last resort."""
        if position_id in self._closed_positions:
            defer.returnValue(None)
        try:
            vol = yield self.resolve_position_volume(position_id, attempts=2)
            if vol is None:
                vol = 100
            yield self.close_position(position_id, volume=vol, max_retries=2)
        except Exception as exc:
            print(f"force_close_position WARN {position_id}: {exc!r}")

    def stop(self):
        try:
            self.client.stopService()
        except Exception:
            pass


def _check_error(res, where):
    if res.DESCRIPTOR.fields_by_name.get("errorCode") is None:
        return
    code = getattr(res, "errorCode", None)
    if code:
        raise RuntimeError(f"{where} rejected by server: errorCode={code}")


class _WsWaiter:
    def __init__(self, symbol_id):
        self.symbol_id = symbol_id
        self.deferred = defer.Deferred()
