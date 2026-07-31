#!/usr/bin/env python3
"""
O365 Mail Sender
================
โปรแกรมส่งอีเมลผ่าน Office 365 รองรับ:
  - เทมเพลตอีเมล (HTML/Text) พร้อมตัวแปร (Jinja2)
  - กลุ่มผู้รับ (config/groups.json)
  - ส่งผ่าน Microsoft Graph API (แนะนำ) หรือ SMTP (สำรอง)
  - แนบไฟล์ได้

ตัวอย่างการใช้งาน:
  python send_mail.py --template welcome --group it-team --subject "ยินดีต้อนรับ" --data name="สมชาย"
  python send_mail.py --template report --to someone@example.com --subject "รายงาน" --attach report.pdf
  python send_mail.py --list-groups
  python send_mail.py --list-templates
"""

import argparse
import base64
import json
import mimetypes
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
GROUPS_FILE = BASE_DIR / "config" / "groups.json"

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
GRAPH_SENDMAIL_ME_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
TOKEN_CACHE_FILE = BASE_DIR / ".token_cache.json"
# ค่าเริ่มต้นสำหรับโหมด device: Client ID ของ Microsoft Graph Command Line Tools
# (แอปทางการของ Microsoft) ทำให้ใช้งานได้โดยไม่ต้องลงทะเบียนแอปใน Azure เอง
DEFAULT_DEVICE_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_groups() -> dict:
    if not GROUPS_FILE.exists():
        return {}
    with open(GROUPS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("groups", {})


def resolve_recipients(groups_arg: list[str], to_arg: list[str]) -> list[str]:
    groups = load_groups()
    recipients: list[str] = []
    for name in groups_arg:
        if name not in groups:
            sys.exit(f"[ERROR] ไม่พบกลุ่ม '{name}' ใน {GROUPS_FILE} (มีกลุ่ม: {', '.join(groups) or '-'})")
        recipients.extend(groups[name])
    recipients.extend(to_arg)
    # กันอีเมลซ้ำ โดยรักษาลำดับเดิม
    seen = set()
    unique = []
    for r in recipients:
        key = r.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(r.strip())
    return unique


def render_template(template_name: str, data: dict) -> tuple[str, str]:
    """คืนค่า (body, content_type) — รองรับ .html และ .txt"""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    for ext, ctype in ((".html", "HTML"), (".txt", "Text")):
        candidate = template_name if template_name.endswith(ext) else template_name + ext
        if (TEMPLATE_DIR / candidate).exists():
            body = env.get_template(candidate).render(**data)
            return body, ctype
    available = sorted(p.name for p in TEMPLATE_DIR.glob("*") if p.suffix in (".html", ".txt"))
    sys.exit(f"[ERROR] ไม่พบเทมเพลต '{template_name}' ใน {TEMPLATE_DIR} (มี: {', '.join(available) or '-'})")


def parse_data_args(pairs: list[str]) -> dict:
    data = {}
    for pair in pairs:
        if "=" not in pair:
            sys.exit(f"[ERROR] --data ต้องอยู่ในรูปแบบ key=value (ได้รับ: '{pair}')")
        key, value = pair.split("=", 1)
        data[key.strip()] = value
    return data


# ---------------------------------------------------------------------------
# Microsoft Graph API sender
# ---------------------------------------------------------------------------

def get_graph_token() -> str:
    tenant_id = os.environ["O365_TENANT_ID"]
    client_id = os.environ["O365_CLIENT_ID"]
    client_secret = os.environ["O365_CLIENT_SECRET"]
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": GRAPH_SCOPE,
    }, timeout=30)
    if resp.status_code != 200:
        sys.exit(f"[ERROR] ขอ token ไม่สำเร็จ ({resp.status_code}): {resp.text}")
    return resp.json()["access_token"]


def build_graph_attachments(paths: list[str]) -> list[dict]:
    attachments = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            sys.exit(f"[ERROR] ไม่พบไฟล์แนบ: {p}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": path.name,
            "contentType": content_type,
            "contentBytes": base64.b64encode(path.read_bytes()).decode(),
        })
    return attachments


def send_via_graph(sender: str, recipients: list[str], cc: list[str], subject: str,
                   body: str, content_type: str, attach: list[str]) -> None:
    token = get_graph_token()
    message = {
        "subject": subject,
        "body": {"contentType": content_type, "content": body},
        "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
    }
    if cc:
        message["ccRecipients"] = [{"emailAddress": {"address": r}} for r in cc]
    if attach:
        message["attachments"] = build_graph_attachments(attach)

    resp = requests.post(
        GRAPH_SENDMAIL_URL.format(sender=sender),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": message, "saveToSentItems": True},
        timeout=60,
    )
    if resp.status_code != 202:
        sys.exit(f"[ERROR] ส่งเมลไม่สำเร็จ ({resp.status_code}): {resp.text}")


# ---------------------------------------------------------------------------
# Device Login sender (ล็อกอินผ่านเบราว์เซอร์ด้วยตัวเอง — ไม่ต้องใช้ secret)
# ---------------------------------------------------------------------------

def get_device_token() -> str:
    try:
        import msal
    except ImportError:
        sys.exit("[ERROR] โหมด device ต้องติดตั้ง msal ก่อน: pip install msal")

    client_id = os.environ.get("O365_CLIENT_ID") or DEFAULT_DEVICE_CLIENT_ID
    tenant = os.environ.get("O365_TENANT_ID", "organizations")

    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        cache.deserialize(TOKEN_CACHE_FILE.read_text())

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(["Mail.Send"], account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=["Mail.Send"])
        if "user_code" not in flow:
            sys.exit(f"[ERROR] เริ่ม device login ไม่สำเร็จ: {json.dumps(flow, ensure_ascii=False)}")
        print("\n" + "=" * 60)
        print(flow["message"])
        print("=" * 60 + "\n")
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        TOKEN_CACHE_FILE.write_text(cache.serialize())
        TOKEN_CACHE_FILE.chmod(0o600)

    if "access_token" not in result:
        sys.exit(f"[ERROR] ล็อกอินไม่สำเร็จ: {result.get('error_description', result)}")
    return result["access_token"]


def send_via_device(recipients: list[str], cc: list[str], subject: str,
                    body: str, content_type: str, attach: list[str]) -> None:
    token = get_device_token()
    message = {
        "subject": subject,
        "body": {"contentType": content_type, "content": body},
        "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
    }
    if cc:
        message["ccRecipients"] = [{"emailAddress": {"address": r}} for r in cc]
    if attach:
        message["attachments"] = build_graph_attachments(attach)

    resp = requests.post(
        GRAPH_SENDMAIL_ME_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": message, "saveToSentItems": True},
        timeout=60,
    )
    if resp.status_code != 202:
        sys.exit(f"[ERROR] ส่งเมลไม่สำเร็จ ({resp.status_code}): {resp.text}")


# ---------------------------------------------------------------------------
# SMTP sender (สำรอง — ต้องเปิด SMTP AUTH ใน O365)
# ---------------------------------------------------------------------------

def send_via_smtp(sender: str, recipients: list[str], cc: list[str], subject: str,
                  body: str, content_type: str, attach: list[str]) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.office365.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", sender)
    password = os.environ["SMTP_PASSWORD"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    subtype = "html" if content_type == "HTML" else "plain"
    msg.attach(MIMEText(body, subtype, "utf-8"))

    for p in attach:
        path = Path(p)
        if not path.exists():
            sys.exit(f"[ERROR] ไม่พบไฟล์แนบ: {p}")
        part = MIMEApplication(path.read_bytes(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(sender, recipients + cc, msg.as_string())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv(BASE_DIR / ".env")

    parser = argparse.ArgumentParser(description="ส่งอีเมลผ่าน Office 365 ด้วยเทมเพลตและกลุ่มเมล")
    parser.add_argument("--template", "-t", help="ชื่อเทมเพลตใน templates/ เช่น welcome")
    parser.add_argument("--group", "-g", action="append", default=[], help="ชื่อกลุ่มผู้รับ (ระบุซ้ำได้)")
    parser.add_argument("--to", action="append", default=[], help="อีเมลผู้รับเพิ่มเติม (ระบุซ้ำได้)")
    parser.add_argument("--cc", action="append", default=[], help="อีเมล CC (ระบุซ้ำได้)")
    parser.add_argument("--subject", "-s", help="หัวข้ออีเมล")
    parser.add_argument("--data", "-d", action="append", default=[], metavar="KEY=VALUE",
                        help="ตัวแปรสำหรับเทมเพลต เช่น --data name=สมชาย")
    parser.add_argument("--attach", "-a", action="append", default=[], help="ไฟล์แนบ (ระบุซ้ำได้)")
    parser.add_argument("--mode", choices=["device", "graph", "smtp"], default=os.environ.get("MAIL_MODE", "device"),
                        help="วิธีส่ง: device (ค่าเริ่มต้น — ล็อกอินผ่านเบราว์เซอร์เอง), graph หรือ smtp")
    parser.add_argument("--dry-run", action="store_true", help="แสดงตัวอย่างโดยไม่ส่งจริง")
    parser.add_argument("--list-groups", action="store_true", help="แสดงรายชื่อกลุ่มทั้งหมด")
    parser.add_argument("--list-templates", action="store_true", help="แสดงรายชื่อเทมเพลตทั้งหมด")
    args = parser.parse_args()

    if args.list_groups:
        for name, members in load_groups().items():
            print(f"{name} ({len(members)} คน)")
            for m in members:
                print(f"  - {m}")
        return

    if args.list_templates:
        for p in sorted(TEMPLATE_DIR.glob("*")):
            if p.suffix in (".html", ".txt"):
                print(p.name)
        return

    if not args.template or not args.subject:
        parser.error("ต้องระบุ --template และ --subject")
    if not args.group and not args.to:
        parser.error("ต้องระบุผู้รับอย่างน้อย 1 ราย ผ่าน --group หรือ --to")

    recipients = resolve_recipients(args.group, args.to)
    data = parse_data_args(args.data)
    body, content_type = render_template(args.template, data)
    sender = os.environ.get("O365_SENDER", "")
    # โหมด device ใช้บัญชีที่ล็อกอิน จึงไม่จำเป็นต้องตั้ง O365_SENDER
    if not sender and not args.dry_run and args.mode != "device":
        sys.exit("[ERROR] กรุณาตั้งค่า O365_SENDER ใน .env (อีเมลผู้ส่ง)")

    print(f"ผู้ส่ง   : {sender or ('(บัญชีที่ล็อกอิน)' if args.mode == 'device' else '(ยังไม่ได้ตั้งค่า)')}")
    print(f"ผู้รับ   : {', '.join(recipients)}")
    if args.cc:
        print(f"CC      : {', '.join(args.cc)}")
    print(f"หัวข้อ  : {args.subject}")
    print(f"เทมเพลต: {args.template} ({content_type})")
    if args.attach:
        print(f"ไฟล์แนบ: {', '.join(args.attach)}")

    if args.dry_run:
        print("\n--- ตัวอย่างเนื้อหา (dry-run ไม่ส่งจริง) ---")
        print(body)
        return

    if args.mode == "graph":
        send_via_graph(sender, recipients, args.cc, args.subject, body, content_type, args.attach)
    elif args.mode == "device":
        send_via_device(recipients, args.cc, args.subject, body, content_type, args.attach)
    else:
        send_via_smtp(sender, recipients, args.cc, args.subject, body, content_type, args.attach)

    print(f"\n[OK] ส่งอีเมลสำเร็จ ({args.mode}) ถึงผู้รับ {len(recipients)} ราย")


if __name__ == "__main__":
    main()
