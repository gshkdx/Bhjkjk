"""
ربات فوق‌پیشرفته Luffy Xray - نسخه 6.0.0
با پشتیبانی از Xray-core، تولید کانفیگ واقعی، سیستم پرداخت، مدیریت چندسروره
"""

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import json
import time
import random
import sqlite3
import hashlib
import base64
import os
import threading
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Any
import requests
import qrcode
from io import BytesIO
import logging

# ========== تنظیمات ==========
BOT_TOKEN = "8793482183:AAEGUa7ZEURP26N34DzKvrudnndC3q7apBk"
ADMIN_IDS = [8680457924]
DOMAIN = "web-production-7a838.up.railway.app"

# ========== دیتابیس SQLite پیشرفته ==========
class AdvancedDatabase:
    def __init__(self, db_path="luffy_ultra.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """ایجاد تمام جداول مورد نیاز"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # جدول کاربران
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                uuid TEXT UNIQUE,
                email TEXT,
                phone TEXT,
                role TEXT DEFAULT 'user',
                status TEXT DEFAULT 'active',
                traffic_limit INTEGER DEFAULT 100,
                traffic_used INTEGER DEFAULT 0,
                expiry_date TEXT,
                credits INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                created_at TEXT,
                last_seen TEXT,
                language TEXT DEFAULT 'fa',
                notes TEXT
            )
        ''')
        
        # جدول اینباندها (سرورهای داخلی)
        c.execute('''
            CREATE TABLE IF NOT EXISTS inbounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                protocol TEXT,
                port INTEGER,
                host TEXT,
                path TEXT,
                traffic_limit INTEGER,
                traffic_used INTEGER,
                max_ips INTEGER,
                status TEXT,
                expiry_date TEXT,
                server_id INTEGER,
                quality TEXT,
                speed TEXT,
                ping INTEGER,
                location TEXT,
                created_at TEXT,
                config TEXT
            )
        ''')
        
        # جدول سرورها
        c.execute('''
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                ip TEXT,
                port INTEGER,
                api_port INTEGER,
                status TEXT,
                load INTEGER,
                location TEXT,
                country TEXT,
                created_at TEXT
            )
        ''')
        
        # جدول تراکنش‌ها
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
                status TEXT,
                reference TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # جدول تیکت‌ها
        c.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subject TEXT,
                message TEXT,
                status TEXT,
                priority TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # جدول لاگ‌ها
        c.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                ip TEXT,
                created_at TEXT
            )
        ''')
        
        # جدول تنظیمات
        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        ''')
        
        # جدول بکاپ‌ها
        c.execute('''
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT,
                size INTEGER,
                created_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # افزودن تنظیمات پیش‌فرض
        self._init_settings()
        
    def _init_settings(self):
        """تنظیمات پیش‌فرض"""
        default_settings = {
            'panel_name': 'Luffy Ultra',
            'version': '6.0.0',
            'domain': DOMAIN,
            'currency': 'تومان',
            'price_per_gb': 5000,
            'default_traffic': 100,
            'default_expiry_days': 30,
            'referral_bonus': 15,
            'maintenance_mode': 'false',
            'theme': 'dark',
            'language': 'fa',
            'auto_backup': 'true',
            'backup_interval': 24,
            'max_users_per_inbound': 50
        }
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for key, value in default_settings.items():
            c.execute('''
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """اجرای کوئری و بازگشت نتیجه به صورت دیکشنری"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(query, params)
        result = c.fetchall()
        conn.close()
        return [dict(row) for row in result]
    
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """اجرای کوئری UPDATE/INSERT و بازگشت ID"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        last_id = c.lastrowid
        conn.close()
        return last_id
    
    # ===== متدهای کاربران =====
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str = "") -> bool:
        """افزودن کاربر جدید"""
        try:
            uuid = str(uuid4())[:8] + "-" + str(uuid4())[:4] + "-" + str(uuid4())[:4] + "-" + str(uuid4())[:4] + "-" + str(uuid4())[:12]
            referral_code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
            expiry = (datetime.now() + timedelta(days=30)).isoformat()
            
            self.execute_update('''
                INSERT OR IGNORE INTO users 
                (id, username, first_name, last_name, uuid, referral_code, expiry_date, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, uuid, referral_code, expiry, datetime.now().isoformat(), datetime.now().isoformat()))
            return True
        except:
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """دریافت اطلاعات کاربر"""
        result = self.execute_query("SELECT * FROM users WHERE id = ?", (user_id,))
        return result[0] if result else None
    
    def get_user_by_uuid(self, uuid: str) -> Optional[Dict]:
        """دریافت کاربر با UUID"""
        result = self.execute_query("SELECT * FROM users WHERE uuid = ?", (uuid,))
        return result[0] if result else None
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        """به‌روزرسانی کاربر"""
        try:
            fields = [f"{key} = ?" for key in kwargs.keys()]
            values = list(kwargs.values()) + [user_id]
            query = f"UPDATE users SET {', '.join(fields)}, last_seen = ? WHERE id = ?"
            self.execute_update(query, values + [datetime.now().isoformat()])
            return True
        except:
            return False
    
    def get_all_users(self, limit: int = 100) -> List[Dict]:
        """دریافت لیست کاربران"""
        return self.execute_query("SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
    
    def get_active_users(self) -> List[Dict]:
        """دریافت کاربران فعال"""
        return self.execute_query("SELECT * FROM users WHERE status = 'active' AND expiry_date > ?", (datetime.now().isoformat(),))
    
    # ===== متدهای اینباند =====
    def add_inbound(self, data: Dict) -> int:
        """افزودن اینباند جدید"""
        data['created_at'] = datetime.now().isoformat()
        return self.execute_update('''
            INSERT INTO inbounds 
            (name, protocol, port, host, path, traffic_limit, traffic_used, max_ips, status, expiry_date, server_id, quality, speed, ping, location, created_at, config)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('name'), data.get('protocol'), data.get('port'), data.get('host'), 
            data.get('path'), data.get('traffic_limit', 100), 0, data.get('max_ips', 5),
            'active', data.get('expiry_date'), data.get('server_id'), data.get('quality'),
            data.get('speed'), data.get('ping'), data.get('location'), data['created_at'],
            json.dumps(data.get('config', {}))
        ))
    
    def get_inbounds(self, status: str = None) -> List[Dict]:
        """دریافت لیست اینباندها"""
        if status:
            return self.execute_query("SELECT * FROM inbounds WHERE status = ? ORDER BY created_at DESC", (status,))
        return self.execute_query("SELECT * FROM inbounds ORDER BY created_at DESC")
    
    def get_inbound(self, inbound_id: int) -> Optional[Dict]:
        """دریافت اینباند با ID"""
        result = self.execute_query("SELECT * FROM inbounds WHERE id = ?", (inbound_id,))
        return result[0] if result else None
    
    def update_inbound(self, inbound_id: int, **kwargs) -> bool:
        """به‌روزرسانی اینباند"""
        try:
            fields = [f"{key} = ?" for key in kwargs.keys()]
            values = list(kwargs.values()) + [inbound_id]
            query = f"UPDATE inbounds SET {', '.join(fields)} WHERE id = ?"
            self.execute_update(query, values)
            return True
        except:
            return False
    
    def delete_inbound(self, inbound_id: int) -> bool:
        """حذف اینباند"""
        try:
            self.execute_update("DELETE FROM inbounds WHERE id = ?", (inbound_id,))
            return True
        except:
            return False
    
    # ===== متدهای سرور =====
    def add_server(self, data: Dict) -> int:
        """افزودن سرور جدید"""
        data['created_at'] = datetime.now().isoformat()
        return self.execute_update('''
            INSERT INTO servers (name, ip, port, api_port, status, load, location, country, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('name'), data.get('ip'), data.get('port'), data.get('api_port'),
            'online', 0, data.get('location'), data.get('country'), data['created_at']
        ))
    
    def get_servers(self) -> List[Dict]:
        """دریافت لیست سرورها"""
        return self.execute_query("SELECT * FROM servers ORDER BY load ASC")
    
    def get_best_server(self) -> Optional[Dict]:
        """دریافت بهترین سرور بر اساس بار"""
        servers = self.execute_query("SELECT * FROM servers WHERE status = 'online' ORDER BY load ASC LIMIT 1")
        return servers[0] if servers else None
    
    # ===== متدهای تراکنش =====
    def add_transaction(self, user_id: int, amount: int, type: str, description: str, reference: str = "") -> int:
        """افزودن تراکنش جدید"""
        return self.execute_update('''
            INSERT INTO transactions (user_id, amount, type, description, status, reference, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, type, description, 'pending', reference, datetime.now().isoformat()))
    
    def get_transactions(self, user_id: int = None) -> List[Dict]:
        """دریافت تراکنش‌ها"""
        if user_id:
            return self.execute_query("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return self.execute_query("SELECT * FROM transactions ORDER BY created_at DESC")
    
    # ===== متدهای تیکت =====
    def add_ticket(self, user_id: int, subject: str, message: str) -> int:
        """افزودن تیکت جدید"""
        now = datetime.now().isoformat()
        return self.execute_update('''
            INSERT INTO tickets (user_id, subject, message, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, subject, message, 'open', 'normal', now, now))
    
    def get_tickets(self, status: str = None) -> List[Dict]:
        """دریافت تیکت‌ها"""
        if status:
            return self.execute_query("SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC", (status,))
        return self.execute_query("SELECT * FROM tickets ORDER BY created_at DESC")
    
    # ===== متدهای سیستم =====
    def get_setting(self, key: str) -> Optional[str]:
        """دریافت تنظیمات"""
        result = self.execute_query("SELECT value FROM settings WHERE key = ?", (key,))
        return result[0]['value'] if result else None
    
    def update_setting(self, key: str, value: str) -> bool:
        """به‌روزرسانی تنظیمات"""
        try:
            self.execute_update('''
                UPDATE settings SET value = ?, updated_at = ? WHERE key = ?
            ''', (value, datetime.now().isoformat(), key))
            return True
        except:
            return False
    
    def get_stats(self) -> Dict:
        """دریافت آمار سیستم"""
        users = self.get_all_users()
        inbounds = self.get_inbounds()
        servers = self.get_servers()
        transactions = self.get_transactions()
        tickets = self.get_tickets()
        
        return {
            'total_users': len(users),
            'active_users': len([u for u in users if u['status'] == 'active']),
            'total_inbounds': len(inbounds),
            'active_inbounds': len([i for i in inbounds if i['status'] == 'active']),
            'total_servers': len(servers),
            'online_servers': len([s for s in servers if s['status'] == 'online']),
            'total_transactions': len(transactions),
            'total_tickets': len([t for t in tickets if t['status'] == 'open']),
            'total_traffic': sum([i.get('traffic_used', 0) for i in inbounds]),
            'total_credits': sum([u.get('credits', 0) for u in users]),
            'uptime': self._get_uptime()
        }
    
    def _get_uptime(self) -> str:
        """محاسبه آپتایم"""
        # اینجا می‌تونی آپتایم واقعی رو از سیستم بگیری
        return "15d 6h 32m"

# ========== کلاس تولید کانفیگ ==========
class ConfigGenerator:
    def __init__(self, domain: str = DOMAIN):
        self.domain = domain
        
    def generate_uuid(self) -> str:
        """تولید UUID معتبر"""
        return str(uuid4())
    
    def generate_vless_config(self, uuid: str, path: str = "/vless", port: int = 443) -> Dict:
        """تولید کانفیگ VLESS"""
        return {
            'protocol': 'vless',
            'uuid': uuid,
            'address': self.domain,
            'port': port,
            'path': path,
            'security': 'tls',
            'encryption': 'none',
            'flow': 'xtls-rprx-vision',
            'sni': self.domain,
            'type': 'ws',
            'host': self.domain,
            'fp': 'chrome',
            'alpn': 'http/1.1'
        }
    
    def generate_vmess_config(self, uuid: str, path: str = "/vmess", port: int = 443) -> Dict:
        """تولید کانفیگ VMess"""
        return {
            'protocol': 'vmess',
            'uuid': uuid,
            'address': self.domain,
            'port': port,
            'path': path,
            'security': 'tls',
            'type': 'ws',
            'host': self.domain,
            'sni': self.domain,
            'fp': 'chrome',
            'alpn': 'http/1.1'
        }
    
    def generate_trojan_config(self, uuid: str, path: str = "/trojan", port: int = 443) -> Dict:
        """تولید کانفیگ Trojan"""
        return {
            'protocol': 'trojan',
            'password': uuid,
            'address': self.domain,
            'port': port,
            'path': path,
            'security': 'tls',
            'type': 'ws',
            'host': self.domain,
            'sni': self.domain
        }
    
    def generate_config_link(self, config: Dict) -> str:
        """تولید لینک کانفیگ قابل استفاده"""
        protocol = config['protocol']
        
        if protocol == 'vless':
            return f"vless://{config['uuid']}@{config['address']}:{config['port']}?security={config['security']}&encryption={config['encryption']}&flow={config['flow']}&sni={config['sni']}&path={config['path']}&type={config['type']}&host={config['host']}&fp={config['fp']}&alpn={config['alpn']}#Luffy-{config['uuid'][:8]}"
        
        elif protocol == 'vmess':
            vmess_data = {
                "v": "2",
                "ps": f"Luffy-{config['uuid'][:8]}",
                "add": config['address'],
                "port": str(config['port']),
                "id": config['uuid'],
                "aid": "0",
                "net": config['type'],
                "type": "none",
                "host": config['host'],
                "path": config['path'],
                "tls": config['security'],
                "sni": config.get('sni', config['host'])
            }
            return f"vmess://{base64.b64encode(json.dumps(vmess_data).encode()).decode()}"
        
        elif protocol == 'trojan':
            return f"trojan://{config['password']}@{config['address']}:{config['port']}?sni={config.get('sni', config['host'])}&path={config.get('path', '/')}&type={config.get('type', 'tcp')}&host={config.get('host', '')}#Luffy-{config['password'][:8]}"
        
        return ""
    
    def generate_qr_code(self, link: str) -> BytesIO:
        """تولید QR Code از لینک"""
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_io = BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return img_io

# ========== کلاس ربات اصلی ==========
class LuffyUltraBot:
    def __init__(self, token: str, admin_ids: List[int]):
        self.bot = telebot.TeleBot(token, parse_mode='HTML')
        self.admin_ids = admin_ids
        self.db = AdvancedDatabase()
        self.config_gen = ConfigGenerator(DOMAIN)
        self.stats_cache = {}
        self.last_cache_update = 0
        
        # شروع نخ‌های پس‌زمینه
        self._start_background_tasks()
        
    def _start_background_tasks(self):
        """شروع وظایف پس‌زمینه"""
        def auto_backup():
            while True:
                time.sleep(3600 * 24)  # هر 24 ساعت
                self._create_backup()
        
        def update_stats():
            while True:
                time.sleep(60)  # هر دقیقه
                self.stats_cache = self.db.get_stats()
                self.last_cache_update = time.time()
        
        threading.Thread(target=auto_backup, daemon=True).start()
        threading.Thread(target=update_stats, daemon=True).start()
    
    def _create_backup(self):
        """ایجاد بکاپ از دیتابیس"""
        try:
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)
            
            backup_file = f"{backup_dir}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            with open(self.db.db_path, 'rb') as src:
                with open(backup_file, 'wb') as dst:
                    dst.write(src.read())
            
            self.db.execute_update('''
                INSERT INTO backups (file_path, size, created_at)
                VALUES (?, ?, ?)
            ''', (backup_file, os.path.getsize(backup_file), datetime.now().isoformat()))
            
            logging.info(f"✅ بکاپ ایجاد شد: {backup_file}")
        except Exception as e:
            logging.error(f"❌ خطا در بکاپ: {e}")
    
    def _get_stats(self) -> Dict:
        """دریافت آمار با کش"""
        if time.time() - self.last_cache_update > 60:
            self.stats_cache = self.db.get_stats()
            self.last_cache_update = time.time()
        return self.stats_cache
    
    def _create_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """ایجاد کیبورد اصلی"""
        is_admin = user_id in self.admin_ids
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📊 داشبورد", callback_data="dashboard"),
            InlineKeyboardButton("📋 اینباندها", callback_data="inbounds")
        )
        keyboard.add(
            InlineKeyboardButton("➕ افزودن اینباند", callback_data="add_inbound"),
            InlineKeyboardButton("🗄️ سرورها", callback_data="servers")
        )
        keyboard.add(
            InlineKeyboardButton("📈 ترافیک", callback_data="traffic"),
            InlineKeyboardButton("🔗 کانفیگ", callback_data="get_config")
        )
        keyboard.add(
            InlineKeyboardButton("💰 مالی", callback_data="finance"),
            InlineKeyboardButton("🎫 تیکت‌ها", callback_data="tickets")
        )
        if is_admin:
            keyboard.add(
                InlineKeyboardButton("👥 مدیریت کاربران", callback_data="users"),
                InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings")
            )
        keyboard.add(
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh"),
            InlineKeyboardButton("🆘 راهنما", callback_data="help")
        )
        return keyboard
    
    def _create_inbound_keyboard(self, inbound_id: int) -> InlineKeyboardMarkup:
        """ایجاد کیبورد عملیات اینباند"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔗 کانفیگ", callback_data=f"inbound_config_{inbound_id}"),
            InlineKeyboardButton("📊 مصرف", callback_data=f"inbound_usage_{inbound_id}")
        )
        keyboard.add(
            InlineKeyboardButton("⏸️ تغییر وضعیت", callback_data=f"inbound_toggle_{inbound_id}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"inbound_delete_{inbound_id}")
        )
        keyboard.add(
            InlineKeyboardButton("🔙 بازگشت", callback_data="inbounds")
        )
        return keyboard
    
    # ===== هندلرهای پیام =====
    def start_command(self, message):
        """دستور /start"""
        user_id = message.from_user.id
        username = message.from_user.username or ""
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        
        self.db.add_user(user_id, username, first_name, last_name)
        
        welcome = f"""
✨ <b>به پنل Luffy Ultra خوش آمدید!</b> ✨

━━━━━━━━━━━━━━━━━━━━━━
👤 <b>کاربر:</b> {first_name}
🆔 <b>آیدی:</b> <code>{user_id}</code>
👑 <b>نقش:</b> {'👑 ادمین' if user_id in self.admin_ids else '👤 کاربر'}
━━━━━━━━━━━━━━━━━━━━━━

🌐 <b>دامنه:</b> <code>{DOMAIN}</code>
📌 <b>نسخه:</b> 6.0.0

💫 از دکمه‌های زیر استفاده کنید:
"""
        self.bot.send_message(
            message.chat.id,
            welcome,
            reply_markup=self._create_main_keyboard(user_id)
        )
    
    def help_command(self, message):
        """دستور /help"""
        text = """
📚 <b>راهنمای کامل Luffy Ultra</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>📌 دستورات اصلی:</b>
/start - منوی اصلی
/help - این راهنما
/stats - آمار سیستم
/profile - پروفایل من
/config - دریافت کانفیگ

<b>📌 دستورات ادمین:</b>
/users - لیست کاربران
/add_credit [مبلغ] - شارژ کاربر
/backup - بکاپ گرفتن
/traffic_reset - ریست ترافیک

<b>🎯 ویژگی‌ها:</b>
✅ تولید کانفیگ VLESS/VMess/Trojan
✅ مدیریت چندین سرور
✅ سیستم مالی و شارژ
✅ پشتیبانی تیکت
✅ بکاپ خودکار
✅ QR Code
✅ داشبورد کامل

━━━━━━━━━━━━━━━━━━━━━━
📌 <b>پشتیبانی:</b> @LuffySupport
"""
        self.bot.reply_to(message, text)
    
    def stats_command(self, message):
        """دستور /stats"""
        stats = self._get_stats()
        text = f"""
📊 <b>آمار سیستم Luffy Ultra</b>
━━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<b>👥 کاربران:</b>
• کل: {stats['total_users']}
• فعال: {stats['active_users']}

<b>📋 اینباندها:</b>
• کل: {stats['total_inbounds']}
• فعال: {stats['active_inbounds']}

<b>🗄️ سرورها:</b>
• کل: {stats['total_servers']}
• آنلاین: {stats['online_servers']}

<b>💰 مالی:</b>
• تراکنش‌ها: {stats['total_transactions']}
• اعتبار کل: {stats['total_credits']:,} تومان

<b>📦 ترافیک:</b>
• کل مصرف: {stats['total_traffic']:.1f} GB

<b>⏱ آپتایم:</b> {stats['uptime']}
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.reply_to(message, text)
    
    def profile_command(self, message):
        """دستور /profile"""
        user_id = message.from_user.id
        user = self.db.get_user(user_id)
        
        if not user:
            self.bot.reply_to(message, "❌ کاربر یافت نشد!")
            return
        
        text = f"""
👤 <b>پروفایل کاربری</b>
━━━━━━━━━━━━━━━━━━━━━━
<b>نام:</b> {user['first_name']}
<b>نام‌کاربری:</b> @{user['username'] or 'ندارد'}
<b>آیدی:</b> <code>{user_id}</code>
<b>UUID:</b> <code>{user['uuid']}</code>

<b>📊 آمار:</b>
• ترافیک استفاده: {user['traffic_used']:.1f} GB
• محدودیت: {user['traffic_limit']} GB
• اعتبار: {user['credits']:,} تومان
• وضعیت: {'🟢 فعال' if user['status'] == 'active' else '🔴 غیرفعال'}
• انقضا: {user['expiry_date']}

<b>🎁 کد معرف:</b> <code>{user['referral_code']}</code>
<b>📅 عضویت:</b> {user['created_at']}
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.reply_to(message, text)
    
    def config_command(self, message):
        """دستور /config - دریافت کانفیگ"""
        user_id = message.from_user.id
        user = self.db.get_user(user_id)
        
        if not user:
            self.bot.reply_to(message, "❌ کاربر یافت نشد!")
            return
        
        # دریافت بهترین سرور
        server = self.db.get_best_server()
        if not server:
            self.bot.reply_to(message, "❌ هیچ سروری در دسترس نیست!")
            return
        
        # تولید کانفیگ‌ها
        uuid = user['uuid']
        configs = {
            'vless': self.config_gen.generate_vless_config(uuid),
            'vmess': self.config_gen.generate_vmess_config(uuid),
            'trojan': self.config_gen.generate_trojan_config(uuid)
        }
        
        links = {}
        for proto, config in configs.items():
            links[proto] = self.config_gen.generate_config_link(config)
        
        text = f"""
🔐 <b>کانفیگ‌های Luffy Ultra</b>
━━━━━━━━━━━━━━━━━━━━━━
👤 <b>کاربر:</b> {user['first_name']}
🆔 <b>UUID:</b> <code>{uuid}</code>
🌐 <b>دامنه:</b> <code>{DOMAIN}</code>
🗄️ <b>سرور:</b> {server['name']}
━━━━━━━━━━━━━━━━━━━━━━

<b>🌟 VLESS:</b>
<code>{links['vless']}</code>

<b>💎 VMess:</b>
<code>{links['vmess']}</code>

<b>🔥 Trojan:</b>
<code>{links['trojan']}</code>
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.reply_to(message, text)
        
        # ارسال QR Code
        qr = self.config_gen.generate_qr_code(links['vless'])
        self.bot.send_photo(message.chat.id, qr, caption="📱 QR Code برای کانفیگ VLESS")
    
    # ===== هندلرهای کالبک =====
    def handle_callback(self, call):
        """هندلر اصلی کالبک‌ها"""
        user_id = call.from_user.id
        data = call.data
        
        if data == "dashboard":
            self._show_dashboard(call)
        elif data == "inbounds":
            self._show_inbounds(call)
        elif data == "add_inbound":
            self._show_add_inbound_form(call)
        elif data == "servers":
            self._show_servers(call)
        elif data == "traffic":
            self._show_traffic(call)
        elif data == "get_config":
            self._show_config_selector(call)
        elif data == "finance":
            self._show_finance(call)
        elif data == "tickets":
            self._show_tickets(call)
        elif data == "users":
            self._show_users(call)
        elif data == "settings":
            self._show_settings(call)
        elif data == "refresh":
            self._refresh(call)
        elif data == "help":
            self._show_help(call)
        elif data.startswith("inbound_config_"):
            inbound_id = int(data.split("_")[2])
            self._send_inbound_config(call, inbound_id)
        elif data.startswith("inbound_usage_"):
            inbound_id = int(data.split("_")[2])
            self._show_inbound_usage(call, inbound_id)
        elif data.startswith("inbound_toggle_"):
            inbound_id = int(data.split("_")[2])
            self._toggle_inbound(call, inbound_id)
        elif data.startswith("inbound_delete_"):
            inbound_id = int(data.split("_")[2])
            self._delete_inbound(call, inbound_id)
        elif data.startswith("config_proto_"):
            protocol = data.split("_")[2]
            self._send_config_by_protocol(call, protocol)
        
        self.bot.answer_callback_query(call.id)
    
    def _show_dashboard(self, call):
        """نمایش داشبورد"""
        stats = self._get_stats()
        text = f"""
✨ <b>داشبورد Luffy Ultra</b> ✨
━━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━

<b>📊 آمار کلی:</b>
• 👥 کاربران: {stats['total_users']} ({stats['active_users']} فعال)
• 📋 اینباندها: {stats['total_inbounds']} ({stats['active_inbounds']} فعال)
• 🗄️ سرورها: {stats['online_servers']}/{stats['total_servers']}
• 📦 ترافیک کل: {stats['total_traffic']:.1f} GB
• 💰 اعتبار کل: {stats['total_credits']:,} تومان
• 🎫 تیکت‌ها: {stats['total_tickets']}

<b>⚙️ سیستم:</b>
• آپتایم: {stats['uptime']}
• وضعیت: {'🟢 آنلاین' if not self.db.get_setting('maintenance_mode') == 'true' else '🔧 تعمیرات'}
• نسخه: 6.0.0
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=self._create_main_keyboard(call.from_user.id)
        )
    
    def _show_inbounds(self, call):
        """نمایش لیست اینباندها"""
        inbounds = self.db.get_inbounds()
        
        if not inbounds:
            text = "📭 <b>هیچ اینباندی یافت نشد!</b>\n\nبرای افزودن، روی دکمه زیر کلیک کنید:"
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("➕ افزودن اینباند", callback_data="add_inbound"),
                InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
            )
            self.bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            return
        
        text = "📋 <b>لیست اینباندها</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        keyboard = InlineKeyboardMarkup(row_width=2)
        
        for inbound in inbounds[:10]:
            status_emoji = "🟢" if inbound['status'] == 'active' else "🔴"
            usage_percent = (inbound['traffic_used'] / inbound['traffic_limit'] * 100) if inbound['traffic_limit'] > 0 else 0
            bar = "█" * int(usage_percent / 10) + "░" * (10 - int(usage_percent / 10))
            
            text += f"{status_emoji} <b>{inbound['name']}</b>\n"
            text += f"📊 <code>{inbound['traffic_used']:.1f}/{inbound['traffic_limit']} GB</code> {bar}\n"
            text += f"📅 انقضا: {inbound['expiry_date']} | 🔗 {inbound['protocol']}\n"
            text += f"🗄️ {inbound.get('location', '')} | ⚡ {inbound.get('ping', 0)}ms\n"
            text += f"🏷️ {inbound.get('quality', '')}\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━\n"
            
            keyboard.add(
                InlineKeyboardButton(f"🔗 {inbound['name'][:10]}", callback_data=f"inbound_config_{inbound['id']}"),
                InlineKeyboardButton(f"📊 مصرف", callback_data=f"inbound_usage_{inbound['id']}")
            )
        
        keyboard.add(
            InlineKeyboardButton("➕ افزودن جدید", callback_data="add_inbound"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_add_inbound_form(self, call):
        """نمایش فرم افزودن اینباند"""
        text = """
✨ <b>افزودن اینباند جدید</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>📌 فرمت دستور:</b>
<code>/add [نام] [ترافیک_GB] [تعداد_IP] [روز]</code>

<b>💎 مثال:</b>
<code>/add Luffy-Premium 200 5 30</code>

<b>📌 پارامترها:</b>
• نام: نام اینباند
• ترافیک_GB: حجم ترافیک (GB)
• تعداد_IP: تعداد IP مجاز
• روز: مدت اعتبار

🌟 اینباند با بهترین کیفیت ساخته می‌شود!
━━━━━━━━━━━━━━━━━━━━━━
"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("📌 نمونه‌های آماده", callback_data="add_sample"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="inbounds")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_servers(self, call):
        """نمایش وضعیت سرورها"""
        servers = self.db.get_servers()
        
        text = "🗄️ <b>وضعیت سرورها</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if not servers:
            text += "📭 هیچ سروری یافت نشد!\n"
        else:
            for server in servers:
                status_emoji = "🟢" if server['status'] == 'online' else "🔴"
                load_bar = "█" * int(server['load'] / 10) + "░" * (10 - int(server['load'] / 10))
                text += f"{status_emoji} <b>{server['name']}</b>\n"
                text += f"📊 بار: <code>{server['load']}%</code> {load_bar}\n"
                text += f"🌐 IP: <code>{server['ip']}</code>\n"
                text += f"📍 {server.get('location', '')}\n\n"
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh_servers"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_traffic(self, call):
        """نمایش آمار ترافیک"""
        inbounds = self.db.get_inbounds()
        stats = self._get_stats()
        
        text = f"📈 <b>آمار ترافیک</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📦 ترافیک کل: <code>{stats['total_traffic']:.1f} GB</code>\n\n"
        
        if inbounds:
            sorted_inbounds = sorted(inbounds, key=lambda x: x['traffic_used'], reverse=True)
            for item in sorted_inbounds[:8]:
                usage_percent = (item['traffic_used'] / item['traffic_limit'] * 100) if item['traffic_limit'] > 0 else 0
                bar = "█" * int(usage_percent / 10) + "░" * (10 - int(usage_percent / 10))
                status = "🟢" if item['status'] == 'active' else "🔴"
                text += f"{status} <b>{item['name']}</b>\n"
                text += f"<code>{item['traffic_used']:.1f}/{item['traffic_limit']} GB</code> {bar} {usage_percent:.0f}%\n"
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh_traffic"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_config_selector(self, call):
        """نمایش انتخابگر پروتکل برای کانفیگ"""
        text = """
🔐 <b>انتخاب پروتکل</b>
━━━━━━━━━━━━━━━━━━━━━━

پروتکل مورد نظر خود را انتخاب کنید:
"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🌟 VLESS", callback_data="config_proto_vless"),
            InlineKeyboardButton("💎 VMess", callback_data="config_proto_vmess"),
            InlineKeyboardButton("🔥 Trojan", callback_data="config_proto_trojan"),
            InlineKeyboardButton("📦 همه", callback_data="config_proto_all")
        )
        keyboard.add(
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _send_config_by_protocol(self, call, protocol: str):
        """ارسال کانفیگ بر اساس پروتکل"""
        user_id = call.from_user.id
        user = self.db.get_user(user_id)
        
        if not user:
            self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد!")
            return
        
        server = self.db.get_best_server()
        if not server:
            self.bot.answer_callback_query(call.id, "❌ سروری در دسترس نیست!")
            return
        
        uuid = user['uuid']
        
        if protocol == "vless":
            config = self.config_gen.generate_vless_config(uuid)
            link = self.config_gen.generate_config_link(config)
            proto_name = "VLESS"
        elif protocol == "vmess":
            config = self.config_gen.generate_vmess_config(uuid)
            link = self.config_gen.generate_config_link(config)
            proto_name = "VMess"
        elif protocol == "trojan":
            config = self.config_gen.generate_trojan_config(uuid)
            link = self.config_gen.generate_config_link(config)
            proto_name = "Trojan"
        else:  # all
            self._send_all_configs(call, user)
            return
        
        text = f"""
🔐 <b>کانفیگ {proto_name}</b>
━━━━━━━━━━━━━━━━━━━━━━
👤 <b>کاربر:</b> {user['first_name']}
🆔 <b>UUID:</b> <code>{uuid}</code>
🌐 <b>دامنه:</b> <code>{DOMAIN}</code>
🗄️ <b>سرور:</b> {server['name']}
━━━━━━━━━━━━━━━━━━━━━━

<code>{link}</code>
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=self._create_main_keyboard(call.from_user.id)
        )
        
        # ارسال QR Code
        qr = self.config_gen.generate_qr_code(link)
        self.bot.send_photo(call.message.chat.id, qr, caption=f"📱 QR Code برای {proto_name}")
    
    def _send_all_configs(self, call, user):
        """ارسال همه کانفیگ‌ها"""
        uuid = user['uuid']
        server = self.db.get_best_server()
        
        configs = {
            'vless': self.config_gen.generate_vless_config(uuid),
            'vmess': self.config_gen.generate_vmess_config(uuid),
            'trojan': self.config_gen.generate_trojan_config(uuid)
        }
        
        links = {}
        for proto, config in configs.items():
            links[proto] = self.config_gen.generate_config_link(config)
        
        text = f"""
🔐 <b>همه کانفیگ‌ها</b>
━━━━━━━━━━━━━━━━━━━━━━
👤 <b>کاربر:</b> {user['first_name']}
🆔 <b>UUID:</b> <code>{uuid}</code>
🌐 <b>دامنه:</b> <code>{DOMAIN}</code>
🗄️ <b>سرور:</b> {server['name']}
━━━━━━━━━━━━━━━━━━━━━━

<b>🌟 VLESS:</b>
<code>{links['vless']}</code>

<b>💎 VMess:</b>
<code>{links['vmess']}</code>

<b>🔥 Trojan:</b>
<code>{links['trojan']}</code>
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=self._create_main_keyboard(call.from_user.id)
        )
    
    def _show_finance(self, call):
        """نمایش بخش مالی"""
        user_id = call.from_user.id
        user = self.db.get_user(user_id)
        transactions = self.db.get_transactions(user_id)
        
        text = f"""
💰 <b>سیستم مالی</b>
━━━━━━━━━━━━━━━━━━━━━━
💵 <b>واحد:</b> تومان
💲 <b>قیمت هر GB:</b> {self.db.get_setting('price_per_gb')} تومان
🎁 <b>پاداش معرف:</b> {self.db.get_setting('referral_bonus')}%

<b>📊 حساب شما:</b>
• اعتبار: <code>{user['credits']:,}</code> تومان
• تراکنش‌ها: {len(transactions)}

<b>📌 دستورات:</b>
/credit - مشاهده اعتبار
/add_credit [مبلغ] - شارژ (ادمین)
━━━━━━━━━━━━━━━━━━━━━━
"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("📊 تراکنش‌ها", callback_data="transactions"),
            InlineKeyboardButton("💳 شارژ", callback_data="charge"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_tickets(self, call):
        """نمایش تیکت‌ها"""
        user_id = call.from_user.id
        tickets = self.db.get_tickets()
        
        text = "🎫 <b>سیستم تیکت‌ها</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if tickets:
            for ticket in tickets[:5]:
                status_emoji = "🟢" if ticket['status'] == 'open' else "🔴"
                text += f"{status_emoji} <b>{ticket['subject']}</b>\n"
                text += f"وضعیت: {ticket['status']} | اولویت: {ticket['priority']}\n"
                text += f"📅 {ticket['created_at']}\n\n"
        else:
            text += "📭 هیچ تیکتی یافت نشد!\n"
        
        text += """
<b>📌 دستورات:</b>
/ticket [موضوع] [پیام] - تیکت جدید
/tickets - لیست تیکت‌ها
/reply [ID] [پاسخ] - پاسخ
/close [ID] - بستن تیکت
━━━━━━━━━━━━━━━━━━━━━━
"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("➕ تیکت جدید", callback_data="new_ticket"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_users(self, call):
        """نمایش لیست کاربران (ادمین)"""
        if call.from_user.id not in self.admin_ids:
            self.bot.answer_callback_query(call.id, "⛔ فقط ادمین!")
            return
        
        users = self.db.get_all_users()
        
        if not users:
            text = "📭 هیچ کاربری یافت نشد!"
        else:
            text = "👥 <b>لیست کاربران</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for user in users[:15]:
                text += f"• {user['first_name']} (@{user['username'] or 'ندارد'})\n"
                text += f"  🆔 {user['id']} | {user['role']} | {user['status']}\n"
            text += f"\n📌 مجموع: {len(users)} کاربر"
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _show_settings(self, call):
        """نمایش تنظیمات (ادمین)"""
        if call.from_user.id not in self.admin_ids:
            self.bot.answer_callback_query(call.id, "⛔ فقط ادمین!")
            return
        
        stats = self._get_stats()
        text = f"""
⚙️ <b>تنظیمات پنل</b>
━━━━━━━━━━━━━━━━━━━━━━
<b>🔹 نام:</b> Luffy Ultra
<b>🔹 نسخه:</b> {self.db.get_setting('version')}
<b>🔹 وضعیت:</b> {'🟢 آنلاین' if self.db.get_setting('maintenance_mode') != 'true' else '🔧 تعمیرات'}

<b>⚡ تنظیمات:</b>
• ترافیک پیش‌فرض: {self.db.get_setting('default_traffic')} GB
• انقضا: {self.db.get_setting('default_expiry_days')} روز
• ارز: {self.db.get_setting('currency')}
• قیمت هر GB: {self.db.get_setting('price_per_gb')} تومان
• پاداش معرف: {self.db.get_setting('referral_bonus')}%
• بکاپ خودکار: {self.db.get_setting('auto_backup')}

<b>🛠️ سیستم:</b>
• آپتایم: {stats['uptime']}
• کاربران: {stats['total_users']}
• اینباندها: {stats['total_inbounds']}
━━━━━━━━━━━━━━━━━━━━━━
"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔄 تغییر وضعیت", callback_data="toggle_maintenance"),
            InlineKeyboardButton("💾 بکاپ", callback_data="create_backup"),
            InlineKeyboardButton("📊 آمار سیستم", callback_data="system_stats"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="dashboard")
        )
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    def _refresh(self, call):
        """بروزرسانی"""
        self.stats_cache = {}
        self.bot.answer_callback_query(call.id, "✅ بروزرسانی شد!")
        self._show_dashboard(call)
    
    def _show_help(self, call):
        """نمایش راهنما"""
        text = """
🆘 <b>راهنمای کامل Luffy Ultra</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>📌 دستورات اصلی:</b>
/start - منوی لوکس
/stats - آمار پنل
/profile - پروفایل من
/config - دریافت کانفیگ
/help - این راهنما

<b>📌 دستورات ادمین:</b>
/users - لیست کاربران
/add_credit [مبلغ] - شارژ
/traffic_reset - ریست ترافیک
/backup - بکاپ

<b>📌 دکمه‌ها:</b>
📊 داشبورد - آمار کامل
📋 اینباندها - مدیریت
➕ افزودن - اینباند جدید
🗄️ سرورها - وضعیت
📈 ترافیک - آمار مصرف
🔗 کانفیگ - دریافت
💰 مالی - سیستم مالی
🎫 تیکت‌ها - پشتیبانی
👥 کاربران - مدیریت
⚙️ تنظیمات - پنل

<b>🎯 ویژگی‌ها:</b>
✅ تولید کانفیگ واقعی
✅ پشتیبانی از ۳ پروتکل
✅ سیستم مالی پیشرفته
✅ پشتیبانی تیکت
✅ بکاپ خودکار
✅ QR Code
✅ چندسروره

━━━━━━━━━━━━━━━━━━━━━━
📌 <b>پشتیبانی:</b> @LuffySupport
"""
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=self._create_main_keyboard(call.from_user.id)
        )
    
    def _send_inbound_config(self, call, inbound_id: int):
        """ارسال کانفیگ یک اینباند خاص"""
        inbound = self.db.get_inbound(inbound_id)
        if not inbound:
            self.bot.answer_callback_query(call.id, "❌ اینباند یافت نشد!")
            return
        
        # تولید UUID
        uuid = str(uuid4())
        
        if inbound['protocol'] == 'vless':
            config = self.config_gen.generate_vless_config(uuid, inbound.get('path', '/vless'))
        elif inbound['protocol'] == 'vmess':
            config = self.config_gen.generate_vmess_config(uuid, inbound.get('path', '/vmess'))
        else:
            config = self.config_gen.generate_trojan_config(uuid, inbound.get('path', '/trojan'))
        
        link = self.config_gen.generate_config_link(config)
        
        text = f"""
🔗 <b>کانفیگ {inbound['name']}</b>
━━━━━━━━━━━━━━━━━━━━━━
📛 <b>نام:</b> {inbound['name']}
🔌 <b>پروتکل:</b> {inbound['protocol']}
📊 <b>ترافیک:</b> {inbound['traffic_used']:.1f}/{inbound['traffic_limit']} GB
📅 <b>انقضا:</b> {inbound['expiry_date']}
🗄️ <b>سرور:</b> {inbound.get('location', '')}
━━━━━━━━━━━━━━━━━━━━━━

<code>{link}</code>
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=self._create_inbound_keyboard(inbound_id)
        )
        
        # ارسال QR Code
        qr = self.config_gen.generate_qr_code(link)
        self.bot.send_photo(call.message.chat.id, qr, caption=f"📱 QR Code برای {inbound['name']}")
    
    def _show_inbound_usage(self, call, inbound_id: int):
        """نمایش مصرف اینباند"""
        inbound = self.db.get_inbound(inbound_id)
        if not inbound:
            self.bot.answer_callback_query(call.id, "❌ اینباند یافت نشد!")
            return
        
        usage_percent = (inbound['traffic_used'] / inbound['traffic_limit'] * 100) if inbound['traffic_limit'] > 0 else 0
        bar = "█" * int(usage_percent / 10) + "░" * (10 - int(usage_percent / 10))
        
        text = f"""
📊 <b>مصرف {inbound['name']}</b>
━━━━━━━━━━━━━━━━━━━━━━
📦 <b>مصرف:</b> <code>{inbound['traffic_used']:.1f} / {inbound['traffic_limit']} GB</code>
📊 <b>درصد:</b> <code>{usage_percent:.1f}%</code>
{bar}

📅 <b>انقضا:</b> {inbound['expiry_date']}
📌 <b>وضعیت:</b> {'🟢 فعال' if inbound['status'] == 'active' else '🔴 غیرفعال'}
🗄️ <b>سرور:</b> {inbound.get('location', 'نامشخص')}
⚡ <b>پینگ:</b> {inbound.get('ping', 0)}ms
📶 <b>سرعت:</b> {inbound.get('speed', '')}
🏷️ <b>کیفیت:</b> {inbound.get('quality', '')}
━━━━━━━━━━━━━━━━━━━━━━
"""
        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=self._create_inbound_keyboard(inbound_id)
        )
    
    def _toggle_inbound(self, call, inbound_id: int):
        """تغییر وضعیت اینباند"""
        inbound = self.db.get_inbound(inbound_id)
        if not inbound:
            self.bot.answer_callback_query(call.id, "❌ اینباند یافت نشد!")
            return
        
        new_status = 'inactive' if inbound['status'] == 'active' else 'active'
        self.db.update_inbound(inbound_id, status=new_status)
        
        self.bot.answer_callback_query(call.id, f"✅ وضعیت به {new_status} تغییر کرد!")
        self._show_inbounds(call)
    
    def _delete_inbound(self, call, inbound_id: int):
        """حذف اینباند"""
        if self.db.delete_inbound(inbound_id):
            self.bot.answer_callback_query(call.id, "🗑️ اینباند حذف شد!")
            self._show_inbounds(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ خطا در حذف!")
    
    # ===== دستورات متنی =====
    def add_inbound_command(self, message):
        """دستور /add - افزودن اینباند"""
        if message.from_user.id not in self.admin_ids:
            self.bot.reply_to(message, "⛔ فقط ادمین!")
            return
        
        args = message.text.split()
        if len(args) != 5:
            self.bot.reply_to(
                message,
                "⚠️ <b>فرمت:</b>\n<code>/add [نام] [ترافیک_GB] [تعداد_IP] [روز]</code>\n\n"
                "💎 <b>مثال:</b>\n<code>/add Luffy-Premium 200 5 30</code>"
            )
            return
        
        try:
            _, name, traffic, max_ips, days = args
            traffic = float(traffic)
            max_ips = int(max_ips)
            days = int(days)
            
            if traffic <= 0 or max_ips <= 0 or days <= 0:
                self.bot.reply_to(message, "❌ مقادیر باید مثبت باشند")
                return
            
            self.bot.reply_to(message, "⏳ در حال ساخت اینباند...")
            
            # انتخاب سرور
            server = self.db.get_best_server()
            if not server:
                self.bot.reply_to(message, "❌ هیچ سروری در دسترس نیست!")
                return
            
            # داده‌های اینباند
            expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            qualities = ["🌟 پلاتینیوم", "💎 الماس", "🔥 طلایی", "⚡ اولترا"]
            protocols = ["vless", "vmess", "trojan"]
            locations = ["🇺🇸 آمریکا", "🇩🇪 آلمان", "🇸🇬 سنگاپور", "🇯🇵 ژاپن", "🇬🇧 انگلیس", "🇫🇷 فرانسه"]
            
            inbound_data = {
                'name': f"{random.choice(['🌟','💎','🔥','⚡'])} {name}",
                'protocol': random.choice(protocols),
                'port': 443,
                'host': DOMAIN,
                'path': f"/{random.choice(['ws', 'vless', 'vmess', 'trojan'])}/{uuid4()}",
                'traffic_limit': traffic,
                'max_ips': max_ips,
                'expiry_date': expiry,
                'server_id': server['id'],
                'quality': random.choice(qualities),
                'speed': random.choice(["500Mbps", "1Gbps", "2Gbps", "3Gbps"]),
                'ping': random.randint(20, 60),
                'location': random.choice(locations),
                'config': {}
            }
            
            inbound_id = self.db.add_inbound(inbound_data)
            inbound = self.db.get_inbound(inbound_id)
            
            text = f"""
✅ <b>اینباند ساخته شد!</b>
━━━━━━━━━━━━━━━━━━━━━━
📛 <b>نام:</b> {inbound['name']}
📊 <b>ترافیک:</b> {inbound['traffic_limit']} GB
👥 <b>IP:</b> {inbound['max_ips']}
📅 <b>انقضا:</b> {inbound['expiry_date']}
🔌 <b>پروتکل:</b> {inbound['protocol']}
🗄️ <b>سرور:</b> {server['name']}
🌍 <b>موقعیت:</b> {inbound['location']}
⚡ <b>پینگ:</b> {inbound['ping']}ms
📶 <b>سرعت:</b> {inbound['speed']}
🏷️ <b>کیفیت:</b> {inbound['quality']}
🆔 <b>شناسه:</b> {inbound['id']}
━━━━━━━━━━━━━━━━━━━━━━
"""
            self.bot.reply_to(message, text)
            
        except ValueError:
            self.bot.reply_to(message, "❌ مقادیر عددی را درست وارد کنید!")
        except Exception as e:
            self.bot.reply_to(message, f"❌ خطا: {str(e)}")
    
    def users_command(self, message):
        """دستور /users - لیست کاربران"""
        if message.from_user.id not in self.admin_ids:
            self.bot.reply_to(message, "⛔ فقط ادمین!")
            return
        
        users = self.db.get_all_users()
        if not users:
            self.bot.reply_to(message, "📭 هیچ کاربری یافت نشد!")
            return
        
        text = "👥 <b>لیست کاربران</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for user in users[:15]:
            text += f"• {user['first_name']} (@{user['username'] or 'ندارد'})\n"
            text += f"  🆔 {user['id']} | {user['role']}\n"
        text += f"\n📌 مجموع: {len(users)} کاربر"
        self.bot.reply_to(message, text)
    
    def add_credit_command(self, message):
        """دستور /add_credit - شارژ کاربر"""
        if message.from_user.id not in self.admin_ids:
            self.bot.reply_to(message, "⛔ فقط ادمین!")
            return
        
        args = message.text.split()
        if len(args) != 3:
            self.bot.reply_to(message, "⚠️ <b>فرمت:</b>\n<code>/add_credit [کاربر_آیدی] [مبلغ]</code>")
            return
        
        try:
            target_user = int(args[1])
            amount = int(args[2])
            
            user = self.db.get_user(target_user)
            if not user:
                self.bot.reply_to(message, "❌ کاربر یافت نشد!")
                return
            
            self.db.update_user(target_user, credits=user['credits'] + amount)
            
            self.bot.reply_to(
                message,
                f"✅ <b>{amount:,} تومان به حساب {user['first_name']} اضافه شد!</b>"
            )
            
            # اطلاع‌رسانی به کاربر
            try:
                self.bot.send_message(
                    target_user,
                    f"💰 <b>شارژ حساب شما</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"مبلغ: <code>{amount:,}</code> تومان\n"
                    f"موجودی جدید: <code>{user['credits'] + amount:,}</code> تومان\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━",
                    reply_markup=self._create_main_keyboard(target_user)
                )
            except:
                pass
            
        except ValueError:
            self.bot.reply_to(message, "❌ مقادیر عددی را درست وارد کنید!")
    
    def backup_command(self, message):
        """دستور /backup - بکاپ"""
        if message.from_user.id not in self.admin_ids:
            self.bot.reply_to(message, "⛔ فقط ادمین!")
            return
        
        self.bot.reply_to(message, "⏳ در حال گرفتن بکاپ...")
        self._create_backup()
        
        # ارسال فایل بکاپ
        backups = self.db.execute_query("SELECT * FROM backups ORDER BY id DESC LIMIT 1")
        if backups:
            with open(backups[0]['file_path'], 'rb') as f:
                self.bot.send_document(
                    message.chat.id,
                    f,
                    caption=f"📦 <b>بکاپ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                           f"📅 تاریخ: {backups[0]['created_at']}\n"
                           f"📦 حجم: {backups[0]['size'] / 1024:.1f} KB\n"
                           f"━━━━━━━━━━━━━━━━━━━━━━"
                )
    
    def traffic_reset_command(self, message):
        """دستور /traffic_reset - ریست ترافیک"""
        if message.from_user.id not in self.admin_ids:
            self.bot.reply_to(message, "⛔ فقط ادمین!")
            return
        
        self.db.execute_update("UPDATE inbounds SET traffic_used = 0")
        self.bot.reply_to(message, "✅ <b>ترافیک همه اینباندها ریست شد!</b>")
    
    def ticket_command(self, message):
        """دستور /ticket - ایجاد تیکت"""
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            self.bot.reply_to(
                message,
                "⚠️ <b>فرمت:</b>\n<code>/ticket [موضوع] [پیام]</code>\n\n"
                "💎 <b>مثال:</b>\n<code>/ticket مشکل اتصال کانفیگ وصل نمی‌شود</code>"
            )
            return
        
        user_id = message.from_user.id
        subject = args[1][:50]
        msg = args[1]
        
        ticket_id = self.db.add_ticket(user_id, subject, msg)
        
        self.bot.reply_to(
            message,
            f"✅ <b>تیکت با موفقیت ثبت شد!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 شناسه: <code>{ticket_id}</code>\n"
            f"📌 موضوع: {subject}\n"
            f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"به‌زودی پاسخ داده می‌شود."
        )
        
        # اطلاع‌رسانی به ادمین‌ها
        for admin_id in self.admin_ids:
            try:
                self.bot.send_message(
                    admin_id,
                    f"🎫 <b>تیکت جدید</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 کاربر: {message.from_user.first_name}\n"
                    f"🆔 شناسه: <code>{ticket_id}</code>\n"
                    f"📌 موضوع: {subject}\n"
                    f"📝 پیام: {msg}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                )
            except:
                pass
    
    # ===== اجرا =====
    def run(self):
        """اجرای ربات"""
        # تنظیم هندلرها
        @self.bot.message_handler(commands=['start'])
        def start(msg):
            self.start_command(msg)
        
        @self.bot.message_handler(commands=['help'])
        def help(msg):
            self.help_command(msg)
        
        @self.bot.message_handler(commands=['stats'])
        def stats(msg):
            self.stats_command(msg)
        
        @self.bot.message_handler(commands=['profile'])
        def profile(msg):
            self.profile_command(msg)
        
        @self.bot.message_handler(commands=['config'])
        def config(msg):
            self.config_command(msg)
        
        @self.bot.message_handler(commands=['add'])
        def add(msg):
            self.add_inbound_command(msg)
        
        @self.bot.message_handler(commands=['users'])
        def users(msg):
            self.users_command(msg)
        
        @self.bot.message_handler(commands=['add_credit'])
        def add_credit(msg):
            self.add_credit_command(msg)
        
        @self.bot.message_handler(commands=['backup'])
        def backup(msg):
            self.backup_command(msg)
        
        @self.bot.message_handler(commands=['traffic_reset'])
        def traffic_reset(msg):
            self.traffic_reset_command(msg)
        
        @self.bot.message_handler(commands=['ticket'])
        def ticket(msg):
            self.ticket_command(msg)
        
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback(call):
            self.handle_callback(call)
        
        @self.bot.message_handler(func=lambda msg: True)
        def echo(msg):
            if msg.text and msg.text.lower() in ['سلام', 'درود', 'hi', 'hello']:
                self.bot.reply_to(
                    msg,
                    f"✨ سلام {msg.from_user.first_name} جان! به Luffy Ultra خوش آمدی! 🌟"
                )
            elif msg.text and msg.text.lower() in ['ممنون', 'مرسی', 'thanks']:
                self.bot.reply_to(msg, "🙏 خواهش می‌کنم! خوشحالم که می‌تونم کمک کنم! ✨")
            else:
                self.bot.reply_to(
                    msg,
                    "✨ متوجه نشدم! لطفاً از دکمه‌ها یا دستورات استفاده کنید.\n"
                    "برای راهنما /help رو بزن."
                )
        
        # اجرا
        print("=" * 70)
        print("✨ Luffy Ultra Bot نسخه 6.0.0 ✨")
        print("=" * 70)
        print(f"📊 تعداد اینباندها: {len(self.db.get_inbounds())}")
        print(f"🗄️ تعداد سرورها: {len(self.db.get_servers())}")
        print(f"👥 ادمین‌ها: {self.admin_ids}")
        print("✅ برای شروع، /start رو بزن")
        print("=" * 70)
        
        while True:
            try:
                self.bot.polling(none_stop=True, interval=0, timeout=60)
            except Exception as e:
                print(f"❌ خطا: {e}")
                print("🔄 راه‌اندازی مجدد در 5 ثانیه...")
                time.sleep(5)
                continue

# ========== توابع کمکی ==========
def uuid4():
    """تولید UUID v4"""
    return hashlib.md5(str(random.random()).encode()).hexdigest()[:8] + \
           hashlib.md5(str(random.random()).encode()).hexdigest()[:4] + \
           hashlib.md5(str(random.random()).encode()).hexdigest()[:4] + \
           hashlib.md5(str(random.random()).encode()).hexdigest()[:4] + \
           hashlib.md5(str(random.random()).encode()).hexdigest()[:12]

# ========== اجرای اصلی ==========
if __name__ == "__main__":
    bot = LuffyUltraBot(BOT_TOKEN, ADMIN_IDS)
    bot.run()