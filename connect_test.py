import json
import sys

import config
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAAccountAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
)
from twisted.internet import reactor

host = (
    EndPoints.PROTOBUF_LIVE_HOST
    if config.ENVIRONMENT.strip().lower() == "live"
    else EndPoints.PROTOBUF_DEMO_HOST
)


def load_token():
    try:
        with open(config.TOKEN_FILE, encoding="utf-8") as f:
            token = json.load(f)
    except FileNotFoundError:
        print("لا يوجد token.json. شغّل auth_tool.py أولاً.")
        sys.exit(1)
    access = token.get("accessToken", "")
    if not access:
        print("token.json لا يحتوي على accessToken صالح.")
        sys.exit(1)
    return access


TOKEN = load_token()
AUTHORIZED = False


def on_error(failure):
    print("خطأ:", failure)
    reactor.callLater(1, reactor.stop)


def on_app_auth_res(raw):
    global AUTHORIZED
    res = Protobuf.extract(raw)
    if hasattr(res, "errorCode") and res.errorCode:
        print("رفض الوصول من تطبيقك:", res)
        reactor.callLater(1, reactor.stop)
        return
    AUTHORIZED = True
    print("الطبقة 1: مصادقة التطبيق تمت بنجاح.")
    req = ProtoOAGetAccountListByAccessTokenReq()
    req.accessToken = TOKEN
    d = client.send(req)
    d.addCallback(on_account_list_res)
    d.addErrback(on_error)


def on_account_list_res(raw):
    res = Protobuf.extract(raw)
    accounts = list(res.ctidTraderAccount)
    if not accounts:
        print("لا توجد حسابات مقرونة بهذا التوكن.")
        reactor.callLater(1, reactor.stop)
        return
    print("الطبقة 2: جلب قائمة الحسابات تم بنجاح.")
    for acc in accounts:
        mode = "live" if acc.isLive else "demo"
        print(
            f"    ctidTraderAccountId={acc.ctidTraderAccountId} | "
            f"mode={mode} | login={acc.traderLogin}"
        )
    target = accounts[0]
    for acc in accounts:
        if not acc.isLive:
            target = acc
            break
    print("اختيار المصادقة على الحساب:", target.ctidTraderAccountId)
    req = ProtoOAAccountAuthReq()
    req.ctidTraderAccountId = target.ctidTraderAccountId
    req.accessToken = TOKEN
    d = client.send(req)
    d.addCallback(on_account_auth_res)
    d.addErrback(on_error)


def on_account_auth_res(raw):
    res = Protobuf.extract(raw)
    print("الطبقة 3: مصادقة الحساب تمت بنجاح لحساب:", res.ctidTraderAccountId)
    print("الاتصال بالسيرفر:", host, "| المنفذ:", EndPoints.PROTOBUF_PORT)
    print("البنية الثلاثية كاملة بنجاح")
    reactor.callLater(1, reactor.stop)


def connected(client):
    print("تم الاتصال بالسيرفر:", host)
    req = ProtoOAApplicationAuthReq()
    req.clientId = config.APP_CLIENT_ID.strip()
    req.clientSecret = config.APP_CLIENT_SECRET.strip()
    d = client.send(req)
    d.addCallback(on_app_auth_res)
    d.addErrback(on_error)


def disconnected(client, reason):
    print("انقطع الاتصال:", reason)
    reactor.callLater(1, reactor.stop)


client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
client.setConnectedCallback(connected)
client.setDisconnectedCallback(disconnected)
client.startService()
reactor.run()