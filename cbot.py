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

    @defer.inlineCallbacks
    def _send(self, req, timeout=30):
        # Serialize all request/response pairs through a lock. The client fetch
        # (getWaiter/matchResponse) is not safe under concurrent sends, which
        # caused requests (close_position, reconcile) to hang 30s then TimeoutError.
        d = self._send_lock.acquire()
        d.addCallback(lambda _: self.client.send(req, responseTimeoutInSeconds=timeout))
        d.addBoth(lambda r: (self._send_lock.release(), r)[1])
        res = yield d
        defer.returnValue(res)

    def _on_received(self, client, message):
        try:
            inner = _unwrap(message)
        except Exception:
            return
        # always cache latest live tick for spot symbols
        if hasattr(inner, "symbolId") and hasattr(inner, "bid") and hasattr(inner, "ask"):
            self.spot_cache[inner.symbolId] = (inner.bid, inner.ask, inner.timestamp)
        # resolve a pending one-shot price wait if it matches
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

    # ---------------------------------------------------------------- connect
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

    # ---------------------------------------------------------------- auth
    @defer.inlineCallbacks
    def authenticate(self, access_token):
        res = _unwrap((yield self._send(ProtoOAApplicationAuthReq(
            clientId=config.APP_CLIENT_ID.strip(),
            clientSecret=config.APP_CLIENT_SECRET.strip()), responseTimeoutInSeconds=15)))
        _check_error(res, "app auth")

        res = _unwrap((yield self._send(ProtoOAGetAccountListByAccessTokenReq(
            accessToken=access_token), responseTimeoutInSeconds=15)))
        _check_error(res, "account list")
        accounts = list(res.ctidTraderAccount)
        if not accounts:
            raise RuntimeError("no accounts linked to this token")

        want_live = config.ENVIRONMENT.strip().lower() == "live"
        match = [a for a in accounts if bool(a.isLive) == want_live]
        if not match:
            match = accounts
        target = match[0]

        res = _unwrap((yield self._send(ProtoOAAccountAuthReq(
            ctidTraderAccountId=target.ctidTraderAccountId,
            accessToken=access_token), responseTimeoutInSeconds=15)))
        _check_error(res, "account auth")
        self.account_id = res.ctidTraderAccountId
        defer.returnValue(self.account_id)

    # ---------------------------------------------------------------- account info
    @defer.inlineCallbacks
    def get_trader(self):
        res = _unwrap((yield self._send(ProtoOATraderReq(
            ctidTraderAccountId=self.account_id), responseTimeoutInSeconds=30)))
        defer.returnValue(res.trader)

    # ---------------------------------------------------------------- symbol
    @defer.inlineCallbacks
    def find_symbol(self, name):
        res = _unwrap((yield self._send(ProtoOASymbolsListReq(
            ctidTraderAccountId=self.account_id), responseTimeoutInSeconds=15)))
        for sym in res.symbol:
            if sym.symbolName == name:
                defer.returnValue(sym.symbolId)
        raise RuntimeError("symbol not found: " + name)

    @defer.inlineCallbacks
    def symbol_info(self, symbol_id):
        req = ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)  # repeated field in this schema
        res = _unwrap((yield self._send(req, 15)))
        for sym in res.symbol:
            if sym.symbolId == symbol_id:
                def _g(name, default=0):
                    f = sym.DESCRIPTOR.fields_by_name.get(name)
                    return getattr(sym, name, 0) if f is not None else default
                defer.returnValue({
                    "digits": sym.digits,
                    "lotSize": sym.lotSize,
                    "minVolume": sym.minVolume,
                    "stepVolume": sym.stepVolume,
                    "pipSize": _g("pipSize"),
                    "pipPosition": _g("pipPosition"),
                    "minDistance": _g("minDistance"),
                    "minStopLossDistance": _g("minStopLossDistance"),
                    "minTakeProfitDistance": _g("minTakeProfitDistance"),
                })
        raise RuntimeError("symbol details not returned for id " + str(symbol_id))

    # ---------------------------------------------------------------- price
    @defer.inlineCallbacks
    def get_spot(self, symbol_id, timeout=12):
        self.waiter = _WsWaiter(symbol_id)
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(symbol_id)  # repeated field in this schema
        req.subscribeToSpotTimestamp = int(time.time() * 1000)
        yield self.client.send(req, responseTimeoutInSeconds=10)
        ev = yield self.waiter.deferred.addTimeout(timeout, reactor)
        self.waiter = None
        try:
            unsub = ProtoOAUnsubscribeSpotsReq()
            unsub.ctidTraderAccountId = self.account_id
            unsub.symbolId.append(symbol_id)
            yield self.client.send(unsub, responseTimeoutInSeconds=5)
        except Exception:
            pass
        defer.returnValue((ev.bid, ev.ask, ev.timestamp))

    # ---------------------------------------------------------------- positions
    @defer.inlineCallbacks
    def open_positions(self, symbol_id, max_age=0.0):
        import time as _t
        now = _t.time()
        ctx = getattr(self, "_pos_cache", None)
        if max_age and ctx and (now - ctx[0]) < max_age:
            defer.returnValue(list(ctx[1]))
        res = _unwrap((yield self._send(ProtoOAReconcileReq(
            ctidTraderAccountId=self.account_id), responseTimeoutInSeconds=30)))
        open_flags = (
            Models.ProtoOAPositionStatus.POSITION_STATUS_OPEN,
            Models.ProtoOAPositionStatus.POSITION_STATUS_CREATED,
        )
        found = [p for p in res.position
                 if p.tradeData.symbolId == symbol_id and p.positionStatus in open_flags]
        self._pos_cache = (_t.time(), list(found))
        defer.returnValue(found)

    @property
    def last_positions(self):
        return list(getattr(self, "_pos_cache", (0, []))[1])

    @defer.inlineCallbacks
    def open_market(self, symbol_id, side, volume, sl=None, tp=None, label=None, comment=""):
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.orderType = Models.ProtoOAOrderType.MARKET
        req.tradeSide = _side(side)
        req.volume = volume
        req.timeInForce = Models.ProtoOATimeInForce.IMMEDIATE_OR_CANCEL
        req.label = label if label else random_label()
        req.comment = comment
        res = _unwrap((yield self._send(req, 15)))
        _check_error(res, "new order")
        if sl is not None or tp is not None:
            try:
                yield self.set_sltp(res.position.positionId, sl, tp)
            except Exception as exc:
                print("WARN: could not set SL/TP after open:", repr(exc))
        # keep the open-position cache truthful so the strategy never thinks
        # there is no open position right after WE opened one (would double-open).
        import time as _t
        if res.position is not None:
            symid = res.position.tradeData.symbolId
            lst = list(getattr(self, "_pos_cache", (0, []))[1])
            lst = [p for p in lst if p.positionId != res.position.positionId]
            lst.append(res.position)
            self._pos_cache = (_t.time(), lst)
        defer.returnValue(res)

    @defer.inlineCallbacks
    def set_sltp(self, position_id, sl=None, tp=None):
        req = ProtoOAAmendPositionSLTPReq(
            ctidTraderAccountId=self.account_id,
            positionId=position_id,
            stopLoss=sl,
            takeProfit=tp,
        )
        res = _unwrap((yield self._send(req, 15)))
        _check_error(res, "amend sl/tp")
        defer.returnValue(res)

    @defer.inlineCallbacks
    def close_position(self, position_id, volume=None):
        req = ProtoOAClosePositionReq(ctidTraderAccountId=self.account_id, positionId=position_id)
        if volume is not None:
            req.volume = volume
        res = _unwrap((yield self._send(req, 30)))
        _check_error(res, "close position")
        # drop the closed position from the cache so it cannot block a new open.
        import time as _t
        lst = list(getattr(self, "_pos_cache", (0, []))[1])
        lst = [p for p in lst if p.positionId != position_id]
        self._pos_cache = (_t.time(), lst)
        defer.returnValue(res)

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