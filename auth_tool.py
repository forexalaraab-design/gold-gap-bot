import json
import sys
import webbrowser
from urllib.parse import parse_qs, urlparse

import config
from ctrader_open_api import Auth


def extract_code(raw):
    raw = raw.strip()
    if not raw:
        return ""
    if "code=" in raw:
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        if "code" in params and params["code"]:
            return params["code"][0].strip()
    return raw


def main():
    client_id = config.APP_CLIENT_ID.strip()
    client_secret = config.APP_CLIENT_SECRET.strip()
    redirect_uri = config.APP_REDIRECT_URI.strip()

    if client_id.startswith("ضع-") or client_secret.startswith("ضع-"):
        print("قم أولاً بملء APP_CLIENT_ID و APP_CLIENT_SECRET في ملف config.py")
        sys.exit(1)

    auth = Auth(client_id, client_secret, redirect_uri)
    auth_uri = auth.getAuthUri()
    print("افتح الرابط التالي في المتصفح وسجّل الدخول بمعرف cTrader ID الخاص بك:")
    print(auth_uri)
    webbrowser.open_new(auth_uri)

    code = extract_code(input("\nالصق العنوان الكامل أو الكود الذي يظهر بعد ?code= في المتصفح: "))
    if not code:
        print("لا يوجد كود صالح")
        sys.exit(1)

    token = auth.getToken(code)
    if "accessToken" not in token:
        print("فشل الحصول على التوكن. الرد:")
        print(json.dumps(token, ensure_ascii=False, indent=2))
        print()
        print("تحقق من الأسباب التالية ثم أعد المحاولة:")
        print("1. الصقة فقط ما يلي code= (أو العنوان الكامل كاملاً، سأستخرجه).")
        print("2. تأكد أن Client Secret مطابق تماماً لما في لوحة التطبيق (بدون مسافات).")
        print("3. تأكد أن الرابط المسجّل في التطبيق هو بالضبط: " + redirect_uri)
        print("4. الكود يصلح لفترة قصيرة (~60 ثانية) — أعد التشغيل وأكمل بسرعة.")
        sys.exit(1)

    with open(config.TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token, f, ensure_ascii=False, indent=2)

    print("تم حفظ التوكن في:", config.TOKEN_FILE)
    print("accessTokenExpiresIn:", token.get("accessTokenExpiresIn"))
    print("refreshTokenExpiresIn:", token.get("refreshTokenExpiresIn"))
    print("ملاحظة: لا ترفع ملف token.json إلى أي مستودع عام.")


if __name__ == "__main__":
    main()