# O365 Mail Sender

โปรแกรมส่งอีเมลผ่าน Office 365 เขียนด้วย Python รองรับ **เทมเพลตอีเมล** และ **กลุ่มผู้รับ**

## คุณสมบัติ

- ส่งเมลผ่าน **Microsoft Graph API** (แนะนำ) หรือ **SMTP** (สำรอง)
- เทมเพลตอีเมลแบบ HTML และ Text พร้อมตัวแปร (Jinja2) ในโฟลเดอร์ `templates/`
- กลุ่มผู้รับกำหนดใน `config/groups.json` เลือกส่งได้ทีละหลายกลุ่ม
- แนบไฟล์ได้, CC ได้, มีโหมด `--dry-run` ดูตัวอย่างก่อนส่งจริง

## ติดตั้ง

```bash
pip install -r requirements.txt
cp .env.example .env   # แล้วแก้ไขค่าใน .env ให้ถูกต้อง
```

## ตั้งค่า Microsoft Graph API (โหมดแนะนำ)

1. เข้า [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **New registration**
2. หลังสร้างแอปแล้ว จดค่า **Tenant ID** และ **Client ID**
3. ไปที่ **Certificates & secrets** → สร้าง **Client secret** แล้วจดค่าไว้
4. ไปที่ **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions** → เลือก **Mail.Send** → กด **Grant admin consent**
5. นำค่าทั้ง 3 ไปใส่ใน `.env`

> แนะนำให้ทำ [Application Access Policy](https://learn.microsoft.com/en-us/graph/auth-limit-mailbox-access) จำกัดให้แอปส่งได้เฉพาะบัญชีผู้ส่งที่กำหนด

## ตั้งค่า SMTP (โหมดสำรอง)

ตั้ง `MAIL_MODE=smtp` ใน `.env` พร้อม `SMTP_USER` / `SMTP_PASSWORD`
(บัญชีต้องเปิด **Authenticated SMTP** ใน Microsoft 365 admin center และหากเปิด MFA ต้องใช้ App Password)

## การใช้งาน

```bash
# ส่งเทมเพลต welcome ไปยังกลุ่ม it-team
python send_mail.py --template welcome --group it-team \
  --subject "ยินดีต้อนรับ" --data name=สมชาย --data team=IT

# ส่งหลายกลุ่ม + ผู้รับเพิ่มเติม + ไฟล์แนบ
python send_mail.py -t notify -g it-team -g hr-team --to boss@example.com \
  -s "ประกาศ" -d message="ระบบจะปิดปรับปรุงวันเสาร์นี้" -a report.pdf

# ดูตัวอย่างก่อนส่งจริง
python send_mail.py -t welcome -g it-team -s "ทดสอบ" -d name=สมชาย --dry-run

# ดูรายชื่อกลุ่ม / เทมเพลตทั้งหมด
python send_mail.py --list-groups
python send_mail.py --list-templates
```

## เพิ่มกลุ่มเมล

แก้ไข `config/groups.json`:

```json
{
  "groups": {
    "ชื่อกลุ่ม": ["email1@example.com", "email2@example.com"]
  }
}
```

## เพิ่มเทมเพลต

สร้างไฟล์ `.html` หรือ `.txt` ใน `templates/` ใช้ตัวแปรด้วย `{{ ชื่อตัวแปร }}`
แล้วส่งค่าผ่าน `--data ชื่อตัวแปร=ค่า`

## โครงสร้างโปรเจกต์

```
├── send_mail.py        # โปรแกรมหลัก
├── config/
│   └── groups.json     # กลุ่มผู้รับ
├── templates/
│   ├── welcome.html    # เทมเพลตตัวอย่าง (HTML)
│   └── notify.txt      # เทมเพลตตัวอย่าง (Text)
├── .env.example        # ตัวอย่างไฟล์ตั้งค่า (คัดลอกเป็น .env)
└── requirements.txt
```
