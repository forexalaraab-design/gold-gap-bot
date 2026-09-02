def _print_report(result, state):
    print("\n" + "=" * 60)
    print("تقرير الاختبار النهائي")
    print("=" * 60)
    print(f"  Action: {result.get('action', 'N/A')}")
    if result.get('close_pnl_usd') is not None:
        print(f"  PnL: {result['close_pnl_usd']:.2f} USD")
    err = result.get('error')
    print(f"  الأخطاء: {err if err else 'لا توجد'}")
    warn = result.get('open_positions_warn')
    print(f"  التحذيرات: {warn if warn else 'لا توجد'}")
    if result.get('close_failed'):
        print(f"  فشل الإغلاق: {result['close_failed']}")
    trades = state.get('closed_trades') or []
    print(f"  إجمالي الصفقات المسجلة: {len(trades)}")
