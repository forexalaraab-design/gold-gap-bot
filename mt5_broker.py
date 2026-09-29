# -*- coding: utf-8 -*-
"""
mt5_broker.py — MT5 execution wrapper over MetaTrader5 python pkg.

ما يحلّه مقابل cbot.py (cTrader):
  * FP Markets cTrader رفض وقوف سيرفر (TRADING_BAD_STOPS) بكل الوحدات،
    فالحماية كانت برمجية فقط → تسرب خسائر (-3..-24) بين دورات الاقتراع.
  * MT5 (Fusion Markets / FusionMarkets-Demo منذ 2026-09-28) يقبل SL/TP
    من لحظة الفتح — السيرفر هو الضامن حتى لو بقي البوت غير متصل.
    التريلنج/الحدود تُرسل عبر order_modify ولكل تغيير يُحفظ عند السيرفر
    فور قبوله. (تحق من الرمز الحقيقي عبر symbol_properties — Fusion
    يستخدم XAUUSD لا XAUUSD.r.)

التمويه (قواعد القسم 0/1 من AGENTS.md):
  * لا يظهر في أي حقل يُرسل: gap / yahoo / momentum / bot / auto …
  * comment="" دائماً، والملصقات أسماء بشرية عبر main._human_label().
  * SL/TP/الحجم/الاقتراع تُشوَّش بدوال البشرنة نفسها (main.*).

تابع ولا تُغيّر توقيعات هذه الدوال العامة:
  initialize / shutdown / account_info / open_position / close_position /
  positions_get / modify_sl_tp / tick / symbol_properties.
"""

import os
import random
import time

import main as _main
import config


def _human_label():
    """ملصق بشري — يعيد توجيه البشرنة نفسها (لا رمز آلي)."""
    try:
        return _main._human_label()
    except Exception:
        import random as _r
        return _r.choice(("gold", "afx", "prime", "alpha", "delta")) + " " + \
               _r.choice(("main", "one", "core", "fifth", "south"))


def _mt5():
    """import بالحاجة — يبقى الملف يعمل حتى لو لم يُثبَّت MetaTrader5 محلياً."""
    import MetaTrader5 as mt5
    return mt5


def initialize(login=None, password=None, server=None, path=None):
    """تفعيل الاتصال بالترمنال MT5 المحلي.

    المسار إلزامي عبر path أو MT5_TERMINAL_PATH/MT5_PATH. وضع portable
    (البيانات بجانب التيرمنال لا AppData) هو الوصفة الموثقة لتشغيل CI
    headless (Joaopeuko/Mql5-Python-Integration + mql5 forum #4): يفادي
    مشاكل permission/UAC ويُقلع بلا واجهة. إن مُررت الاعتمادات نستخدم
    login() صريحةً بعد الالتحاق بدل حوار تسجيل دخول يعمل على واجهة —
    لا على runner بلا واجهة.
    """
    mt5 = _mt5()
    if login is not None and not isinstance(login, int):
        try:
            login = int(str(login).strip())
        except (TypeError, ValueError):
            return False, {"error": (-2, "Invalid \"login\" argument"),
                           "detail": f"non-numeric login: {login!r}"}
    portable = os.environ.get("MT5_PORTABLE", "0") in ("1", "true", "True")
    path = path or os.environ.get("MT5_TERMINAL_PATH") \
        or os.environ.get("MT5_PATH") or None
    last = None
    for attempt in range(1, 6):
        last = None
        # الوصفة الموثقة من مشروع يشتغل على windows-latest
        # (Joaopeuko/Mql5-Python-Integration tests/integration):
        #   mt5.initialize(login=…, password=…, server=…, path=…) — نداء
        # واحد بالاعتمادات، لا attach ثم mt5.login()، يُعاد 10 مرات حتى
        # يجيب التيرمنال. مع /portable /headless للـ CI لا يظهر حوار.
        if login is not None:
            ok_in = mt5.initialize(path=path, login=login,
                                   password=password, server=server,
                                   portable=portable, timeout=100000)
        else:
            ok_in = mt5.initialize(path=path if path else None,
                                   portable=portable, timeout=100000)
        if ok_in:
            return True, {}
        last = mt5.last_error()
        try:
            mt5.shutdown()
        except Exception:
            pass
        print(f"mt5 initialize attempt {attempt}/5 failed: "
              f"{last} — retrying…", flush=True)
        time.sleep(5.0 * attempt)
    return False, {"error": last, "detail": "initialize failed"}


def shutdown():
    try:
        _mt5().shutdown()
    except Exception:
        pass


def account_info():
    """معلومة الحساب: balance, equity, currency, server, login."""
    mt5 = _mt5()
    acc = mt5.account_info()
    if acc is None:
        return None
    return {
        "login": acc.login,
        "server": acc.server,
        "currency": acc.currency,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "leverage": acc.leverage,
        "name": getattr(acc, "name", ""),
    }


def symbol_properties(symbol=None):
    """مواصفات الرمز: digits, point, tick_value (بالعملة), spread قياسي."""
    mt5 = _mt5()
    s = symbol or config.SYMBOL
    info = mt5.symbol_info(s)
    if info is None:
        return None
    tick = mt5.symbol_info_tick(s)
    # spread يُقرأ من symbol_info (يجمعه التيرمنال) — كائن Tick لا يحمله.
    return {
        "symbol": s,
        "digits": info.digits,
        "point": info.point,
        "trade_tick_value": info.trade_tick_value,
        "trade_tick_size": info.trade_tick_size,
        "volume_min": info.volume_min,
        "volume_step": info.volume_step,
        "spread_points": getattr(info, "spread", None),
        "bid": tick.bid if tick else info.bid,
        "ask": tick.ask if tick else info.ask,
    }


def tick(symbol=None):
    """آخر سعر bid/ask/مؤخر — يرجع مباشرة من التيرمنال (بدل gold-api)."""
    mt5 = _mt5()
    s = symbol or config.SYMBOL
    t = mt5.symbol_info_tick(s)
    if t is None:
        return None
    return {"symbol": s, "bid": t.bid, "ask": t.ask, "last": t.last,
            "time_msc": t.time_msc}


def positions_list(pos):
    """تحويل نتائج positions_get من التيرمنال إلى dictات نظيفة (استثناء-safe)."""
    out = []
    for p in (pos or []):
        out.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "side": "buy" if p.type == 0 else "sell",
            "volume": p.volume,
            "open_price": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "pnl_usd": getattr(p, "profit", 0.0),
            "commission": getattr(p, "commission", 0.0),
            "swap": getattr(p, "swap", 0.0),
            "comment": getattr(p, "comment", ""),
            "magic": getattr(p, "magic", 0),
            "open_time": p.time,
        })
    return out


def positions_get(symbol=None):
    """الصفقات المفتوحة — عوضاً عن open_positions في cbot.

    يعتمد على positions_get المباشر (أدق من OrderList: يشمل الصفقات
    المكتسبة بلا تتبع محلي). يرجع قائمة dictات نظيفة.
    """
    mt5 = _mt5()
    kwargs = {"symbol": symbol} if symbol else {}
    try:
        pos = mt5.positions_get(**kwargs)
    except Exception:
        return []
    if pos is None:
        return []
    return positions_list(pos)


def broker_open_position_ids(symbol=None):
    """طلبات الفتح النشطة للرمز — منع التعدد الصارم قبل أي فتح.

    حارس الوسيط (2026-09-22): لا تُفتح صفقة ثانية أبداً مهما انفرطت
    الحالة المحلية — هنا نقرأ من MT5 مباشرة. أمر الفتح النشط بلا أمر
    إغلاق مقابل لوذاك positionId = صفقة حية على الرمز، فيُمنع الفتح.
    يرجع قائمة tickets (تكتب أرقاماً موجبة دائماً من السيرفر).
    """
    out = []
    for p in positions_get(symbol):
        t = p.get("ticket")
        if t not in (None, 0):
            out.append(str(t))
    return out


def _volume_units(lot):
    """تحويل اللوت إلى وحدات رقم تصريح volume في MT5 (0.01..)."""
    return round(max(0.01, float(lot)), 2)


def _side_code(side):
    """0 = buy, 1 = sell (دالة أوامر MT5)."""
    return "BUY" if str(side).lower() in ("buy", "0") else "SELL"


def open_position(symbol, side, volume, sl=None, tp=None, comment="",
                  magic=None):
    """فتح صفقة سوقية مع SL/TP سيرفر فوراً — الالتزام الجذري.

    MT5 يقبل sl/tp من لحظة الطلب (عكس cTrader). تُشوَّش SL/TP حسب
    قاعدة البشرنة قبل الإرسال. تُرجع ticket مع acknowledgement.
    """
    mt5 = _mt5()
    s = symbol or config.SYMBOL
    lot = _volume_units(volume if volume else config.LOT)
    order_type = mt5.ORDER_TYPE_BUY if str(side).lower() in ("buy", "0") \
        else mt5.ORDER_TYPE_SELL
    info = mt5.symbol_info(s)
    if info is None:
        return None, "symbol_info failed"
    if not info.trade_mode in (mt5.SYMBOL_TRADE_MODE_FULL,):
        descript = getattr(info, "description", "mode=%s" % info.trade_mode)
        return None, "trade_mode not FULL: %s" % descript
    tick_ = mt5.symbol_info_tick(s)
    if tick_ is None:
        return None, "no tick for symbol"
    price = tick_.ask if order_type == mt5.ORDER_TYPE_BUY else tick_.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": s,
        "volume": lot,
        "type": order_type,
        "price": price,
        "deviation": 30,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "comment": comment,
    }
    if sl is not None:
        request["sl"] = float(sl)
    if tp is not None:
        request["tp"] = float(tp)
    res = mt5.order_send(request)
    if res is None:
        return None, "order_send returned None (err=%s)" % (mt5.last_error(),)
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return None, "retcode=%s" % res.retcode
    return res.order, "ok"


def close_position(symbol, side, volume, comment="", ticket=None):
    """إغلاق صفقة مفتوحة بعكس الاتجاه بنفس الحجم.

    يُرسل أمر DEAL مع ضبط 'position' برقم التذكرة الفعلي (MT5 يرفض
    إغلاقاً بلا position). إن مُرر ticket يُغلق تلك الصفقة بالضبط؛ وإلا
    يُغلق المنصوص عليها الأولى. لا نضع sl/tp عند الإغلاق. comment فارغ.
    """
    mt5 = _mt5()
    s = symbol or config.SYMBOL
    side = str(side).lower()
    order_type = mt5.ORDER_TYPE_SELL if side in ("buy", "0") \
        else mt5.ORDER_TYPE_BUY
    lot = _volume_units(volume if volume else config.LOT)

    if ticket is not None:
        sel = mt5.positions_get(ticket=ticket)
        positions = positions_list(sel)
    else:
        positions = positions_get(s)
    if not positions:
        return None, "no open position to close"
    pos = positions[0]
    ticket = pos["ticket"]
    # حجم الإغلاق لا يتجاوز حجم الصفقة الفعلية
    close_lot = min(lot, pos["volume"])

    tick_ = mt5.symbol_info_tick(s)
    if tick_ is None:
        return None, "no tick"
    price = tick_.bid if order_type == mt5.ORDER_TYPE_SELL else tick_.ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": s,
        "volume": close_lot,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 30,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "comment": comment,
    }
    res = mt5.order_send(request)
    if res is None:
        return None, "order_send None"
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return None, "retcode=%s (ret=done?)" % res.retcode
    return res.order, "ok"


def modify_sl_tp(position_ticket, sl=None, tp=None):
    """تعديل سيرفر SL/TP لصفقة مفتوحة (التريلنج والخروج المسيطر).

    يُرسل TRADE_ACTION_SLTP بالأرقام الجديدة — يُطبَّق سيرفراً فور
    قبوله، فيبقى الحارس النشط بين الدورات حتى لو لم يعد البوت لاحقاً.
    """
    mt5 = _mt5()
    pos = mt5.positions_get(ticket=position_ticket)
    if pos is None or len(pos) == 0:
        return None, "position not found"
    p = pos[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": p.symbol,
        "position": position_ticket,
        "sl": float(sl) if sl is not None else p.sl,
        "tp": float(tp) if tp is not None else p.tp,
    }
    res = mt5.order_send(request)
    if res is None:
        return None, "modify returned None"
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return None, "modify retcode=%s" % res.retcode
    return res.order, "ok"


def jitter_protected_sltp(base_sl_usd, base_tp_usd, mid):
    """SL/TP نهائيان للتخابث البشري: ±HUMAN_SL_TP_JITTER_USD حول الأساس.

    mid سعر المنصة الحالي؛ SL/TP بالسعر المطلق. يبقى الاستثناء صارماً
    بلا تشتت: MAX_LOSS وحدود الأمان تُرسل كما هي من المتصل (لا نعرفها هنا).
    """
    j = config.HUMAN_SL_TP_JITTER_USD if config.HUMANIZE_ON else 0.0
    sl = base_sl_usd + random.uniform(-j, j)
    tp = base_tp_usd + random.uniform(-j, j)
    return sl, tp


class BrokerError(Exception):
    pass