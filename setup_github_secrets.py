#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_github_secrets.py — يضيف أسرار MT5 إلى GitHub Repository
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).parent.resolve()
SECRETS = {
    "MT5_LOGIN": "490512",
    "MT5_PASSWORD": "Ahmad$0988",
    "MT5_SERVER": "FusionMarkets-Demo",
}

def run(cmd, check=True):
    """Run command and return stdout."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return r.stdout.strip(), r.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.returncode

def check_gh_installed():
    """Check if GitHub CLI is installed."""
    stdout, rc = run("gh --version", check=False)
    return rc == 0 and "gh" in stdout.lower()

def check_gh_auth():
    """Check if gh is authenticated."""
    stdout, rc = run("gh auth status", check=False)
    return rc == 0 and "Logged in" in stdout

def setup_gh():
    """Setup GitHub CLI authentication."""
    print("=" * 60)
    print("إعداد GitHub CLI (gh)")
    print("=" * 60)
    print()
    
    if not check_gh_installed():
        print("❌ GitHub CLI (gh) غير مثبت")
        print()
        print("لتثبيت gh، نفذ أحد الأوامر التالية:")
        print("  winget install GitHub.cli")
        print("  أو:")
        print("  choco install gh")
        print("  أو:")
        print("  scoop install gh")
        print()
        print("بعد التثبيت، أعد تشغيل هذا السكربت")
        return False
    
    print("✅ GitHub CLI مثبت")
    print()
    
    if not check_gh_auth():
        print("⚠️  لم تسجل دخول إلى GitHub بعد")
        print()
        print("سيتم فتح نافذة تسجيل الدخول الآن...")
        print("اتبع التعليمات في المتصفح")
        print()
        input("اضغط Enter للمتابعة...")
        
        stdout, rc = run("gh auth login")
        if rc != 0:
            print("❌ فشل تسجيل الدخول")
            return False
        print("✅ تم تسجيل الدخول بنجاح")
    else:
        print("✅ مسجل دخول إلى GitHub")
    
    return True

def get_repo():
    """Get current repository."""
    stdout, rc = run("gh repo view --json nameWithOwner -q .nameWithOwner", check=False)
    if rc == 0 and stdout:
        return stdout.strip()
    
    # Try to get from git remote
    stdout, rc = run("git remote get-url origin", check=False)
    if rc == 0 and stdout:
        url = stdout.strip()
        if "github.com/" in url:
            parts = url.split("github.com/")[-1].replace(".git", "").strip()
            return parts
    
    return None

def add_secrets():
    """Add MT5 secrets to GitHub repository."""
    print()
    print("=" * 60)
    print("إضافة أسرار MT5 إلى GitHub")
    print("=" * 60)
    print()
    
    repo = get_repo()
    if not repo:
        print("❌ لم يتم العثور على مستودع GitHub")
        print("تأكد من أنك في مجلد المشروع:")
        print(f"  cd {REPO_DIR}")
        return False
    
    print(f"📦 المستودع: {repo}")
    print()
    
    # Add each secret
    success = True
    for name, value in SECRETS.items():
        print(f"إضافة {name}...")
        stdout, rc = run(f'gh secret set {name} --body "{value}"')
        if rc == 0:
            print(f"  ✅ {name} = {value[:8]}...")
        else:
            print(f"  ❌ فشل إضافة {name}")
            print(f"     الخطأ: {stdout}")
            success = False
        print()
    
    if success:
        print("=" * 60)
        print("✅ تمت إضافة جميع الأسرار بنجاح!")
        print("=" * 60)
        print()
        print("الأسرار المضافة:")
        for name, value in SECRETS.items():
            print(f"  • {name}: {value[:8]}...")
        print()
        print("الخطوات التالية:")
        print("1. اذهب إلى GitHub → Actions")
        print("2. شغّل workflow 'Multi-Pair Daily Bot' يدوياً للاختبار")
        print("3. أو انتظر حتى 08:00 UTC للتشغيل التلقائي")
        print()
        return True
    else:
        print("❌ فشل إضافة بعض الأسرار")
        return False

def main():
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "إعداد أسرار MT5 - GitHub Actions" + " " * 15 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # Check if we're in the right directory
    if not (REPO_DIR / "multi_bot").exists():
        print("❌ خطأ: لم يتم العثور على مجلد المشروع")
        print(f"تأكد من أنك في: {REPO_DIR}")
        return 1
    
    print(f"📁 مجلد المشروع: {REPO_DIR}")
    print()
    
    # Setup gh if needed
    if not setup_gh():
        return 1
    
    # Add secrets
    if not add_secrets():
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ تم الإلغاء")
        sys.exit(1)
