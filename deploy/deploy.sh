#!/bin/bash
# ============================================
# 🎌 Anime Bot — Serverda yangilash skripti
# ============================================
# Ishlatish: bash deploy.sh
#
# ⚠ MUHIM: anime_pro.db (ma'lumotlar bazasi) 
# .gitignore da bo'lgani uchun git pull uni 
# O'CHIRMAYDI. Xavfsiz!
# ============================================

set -e

echo "🔄 Yangilash boshlandi..."

# 1. O'zgarishlarni pull qilish
echo "📥 Git pull..."
cd "$(dirname "$0")"
git pull origin main

# 2. Paketlarni yangilash (agar yangi qo'shilgan bo'lsa)
echo "📦 Paketlar tekshirilmoqda..."
pip install -r requirements.txt --quiet

# 3. Botni qayta ishga tushirish (systemd bilan)
if systemctl is-active --quiet anime_bot 2>/dev/null; then
    echo "🔁 Bot qayta ishga tushirilmoqda (systemd)..."
    sudo systemctl restart anime_bot
    echo "✅ Bot qayta ishga tushdi!"
    sudo systemctl status anime_bot --no-pager
else
    echo "ℹ️  systemd service topilmadi."
    echo "   Qo'lda ishga tushirish: python bot.py"
    echo ""
    echo "   Systemd service yaratish uchun:"
    echo "   sudo cp deploy/anime_bot.service /etc/systemd/system/"
    echo "   sudo systemctl enable anime_bot"
    echo "   sudo systemctl start anime_bot"
fi

echo ""
echo "✅ Yangilash tugadi!"
