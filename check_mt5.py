#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_mt5.py — تحقق من حالة MT5 والحساب والصفقات
"""
import sys
import os
from datetime import datetime, timezone

# تأكد من تحميل MT5 من المسار الصحيح
sys.path.insert(0, os.path.expanduser("~"))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌ MetaTrader5 غير مثبت")
    print("ثبته بالأمر:")
    print("  pip install MetaTrader5")
    sys.exit(1)

# بيانات الحساب من config_local.py
LOGIN = 490512
PASSWORD = "Ahmad$0988"
SERVER = "FusionMarkets-Demo"
PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

def main():
    print("=" * 60)
    print("تحقق من MT5")
    print("=" * 60)
    print()

    # 1. تهيئة MT5
    print("1. تهيئة MT5...")
    if PATH and os.path.exists(PATH):
        ok = mt5.initialize(PATH, login=LOGIN, password=PASSWORD, server=SERVER)
    else:
        ok = mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER)

    if not ok:
        err = mt5.last_error()
        print(f"   ❌ فشل الاتصال: {err}")
        print("تأكد من:")
        print("  - MT5 مثبت على هذا الجهاز")
        print("  - الحساب مفتوح على FusionMarkets-Demo")
        print("  - كلمة السر صحيحة")
        mt5.shutdown()
        sys.exit(1)

    print("   ✅ تم الاتصال بـ MT5")
    print()

    # 2. معلومات الحساب
    print("2. معلومات الحساب...")
    acc = mt5.account_info()
    if acc is None:
        print("   ❌ لا يمكن جلب معلومات الحساب")
        mt5.shutdown()
        sys.exit(1)

    print(f"   Login:       {acc.login}")
    print(f"   Server:      {acc.server}")
    print(f"   Name:        {acc.name}")
    print(f"   Currency:    {acc.currency}")
    print(f"   Balance:     {acc.balance:.2f}")
    print(f"   Equity:      {acc.equity:.2f}")
    print(f"   Margin:      {acc.margin:.2f}")
    print(f"   Free Margin: {acc.margin_free:.2f}")
    print(f"   Leverage:    1:{acc.leverage}")
    print(f"   Trade Mode:  {acc.trade_mode}")
    print()

    # 3. الصفقات المفتوحة
    print("3. الصفقات المفتوحة...")
    positions = mt5.positions_get()
    if positions is None:
        print("   ❌ خطأ في جلب الصفقات:", mt5.last_error())
        positions = []

    if len(positions) == 0:
        print("   ✅ لا توجد صفقات مفتوحة")
    else:
        print(f"   ⚠️  يوجد {len(positions)} صفقة مفتوحة:")
        print()
        for pos in positions:
            print(f"   ┌─────────────────────────────────────────")
            print(f"   │ Ticket:      {pos.ticket}")
            print(f"   │ Symbol:      {pos.symbol}")
            print(f"   │ Type:        {'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'}")
            print(f"   │ Volume:      {pos.volume}")
            print(f"   │ Open Price:  {pos.price_open:.5f}")
            print(f"   │ Current:     {pos.price_current:.5f}")
            print(f"   │ SL:          {pos.sl}")
            print(f"   │ TP:          {pos.tp}")
            print(f"   │ Profit:      {pos.profit:.2f} {acc.currency}")
            print(f"   │ Swap:        {pos.swap:.2f}")
            print(f"   │ Open Time:   {datetime.fromtimestamp(pos.time, tz=timezone.utc)}")
            print(f"   └─────────────────────────────────────────")
            print()

    # 4. آخر الصفقات المغلقة (آخر 5)
    print("4. آخر الصفقات المغلقة...")
    from_t = int((datetime.now(timezone.utc).timestamp() - 86400 * 30) * 1000)  # آخر 30 يوم
    to_t = int(datetime.now(timezone.utc).timestamp() * 1000)
    deals = mt5.history_deals_get(from_t, to_t, position=positions[0].ticket if positions else None)
    if deals is None:
        deals = mt5.history_deals_get(from_t, to_t)

    if deals is None or len(deals) == 0:
        print("   لا توجد صفقات مغلقة في آخر 30 يوم")
    else:
        print(f"   ✅ يوجد {len(deals)} صفقة مغلقة في آخر 30 يوم")
        print("   آخر 5 صفقات:")
        for d in deals[-5:]:
            dt = datetime.fromtimestamp(d.time, tz=timezone.utc)
            print(f"   - {dt} | {d.symbol} | {'BUY' if d.type == mt5.ORDER_TYPE_BUY else 'SELL'} | "
                  f"Volume={d.volume} | Profit={d.profit:.2f}")

    print()
    print("=" * 60)
    print("التحقق اكتمل")
    print("=" * 60)

    mt5.shutdown()

if __name__ == "__main__":
    main()
