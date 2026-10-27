#!/usr/bin/env python3
"""เตรียมไฟล์ Markdown สำหรับอัปโหลดเข้า Knowledge เพื่อให้ Citation แม่นขึ้น

ปัญหาที่แก้:
  - YAML front matter ถูก index เป็น chunk แรกของทุกเอกสาร กินที่ Top K และเป็น noise
  - chunk กลางเอกสารไม่มีรหัสเอกสาร (P05/PR12) โมเดลจึงอ้างอิงผิดหรือแต่งเอง

สิ่งที่ทำ (ไม่แก้ไฟล์ต้นฉบับ เขียนไปโฟลเดอร์ใหม่):
  1. แทน YAML ด้วยหัวเอกสาร 2 บรรทัดที่อ่านได้ (รหัส ชื่อ ประเภท ปีบัญชี หน้า PDF)
  2. เติม [รหัสเอกสาร] หน้าทุกหัวข้อ Markdown (ยกเว้นใน code block)
  3. ตั้งชื่อไฟล์ให้ขึ้นต้นด้วยรหัสเอกสาร เช่น P05_การควบคุมการเข้าถึงระบบและสารสนเทศ.md
  4. ตรวจว่าเนื้อหาเดิมครบทุกตัวอักษร (ถอดสิ่งที่เติมออกแล้วต้องเท่ากับต้นฉบับ)

ตัวอย่าง:
  python3 prepare_kb.py --src knowledge_domains/it_security_2569 --out knowledge_domains/it_security_2569_rag
"""
import argparse
import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
TYPE_TH = {"policy": "นโยบาย", "procedure": "วิธีปฏิบัติ"}


def split_front_matter(text):
    """คืน (dict ของ YAML แบบง่าย, เนื้อหาหลัง YAML)"""
    if not text.startswith("---"):
        raise ValueError("ไม่พบ YAML front matter")
    lines = text.split("\n")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("YAML front matter ไม่ปิด")
    meta, key = {}, None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            meta[key] = [] if val == "" else val.strip('"').strip("'")
        elif key and line.strip().startswith("- "):
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(line.strip()[2:].strip().strip('"').strip("'"))
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return meta, body


def page_text(pages):
    if isinstance(pages, list) and pages:
        nums = sorted(int(p) for p in pages if str(p).isdigit())
        if nums:
            return f"{nums[0]}" if nums[0] == nums[-1] else f"{nums[0]}-{nums[-1]}"
    return "-"


def transform(meta, body):
    doc_id = meta["document_id"]
    tag = f"[{doc_id}] "
    header = (
        f"# {doc_id} {meta.get('document_title_th', '')}".rstrip() + "\n"
        f"รหัสเอกสาร {doc_id} | {TYPE_TH.get(meta.get('document_type'), meta.get('document_type', ''))}"
        f" | ปีบัญชี {meta.get('fiscal_year', '-')} | ฉบับ {meta.get('version', '-')}"
        f" | หน้า PDF {page_text(meta.get('source_pdf_pages'))}\n\n"
    )
    out, in_fence, tagged = [], False, 0
    for line in body.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            out.append(f"{m.group(1)} {tag}{m.group(2)}")
            tagged += 1
        else:
            out.append(line)
    return header, "\n".join(out), tagged


def untransform(new_body, doc_id):
    """ถอด [รหัส] ที่เติมออก เพื่อเทียบกับต้นฉบับ"""
    tag = f"[{doc_id}] "
    lines, in_fence = [], False
    for line in new_body.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m and m.group(2).startswith(tag):
            line = f"{m.group(1)} {m.group(2)[len(tag):]}"
        lines.append(line)
    return "\n".join(lines)


def safe_name(text):
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", text).strip()
    return re.sub(r"\s+", "_", text)[:80]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="โฟลเดอร์ที่มี policies/ และ procedures/")
    ap.add_argument("--out", required=True, help="โฟลเดอร์ผลลัพธ์ (ต้องยังไม่มีหรือว่าง)")
    ap.add_argument("--expect", type=int, default=54, help="จำนวนเอกสารที่ต้องได้")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} มีไฟล์อยู่แล้ว กรุณาใช้โฟลเดอร์ใหม่")
    files = sorted(list((src / "policies").glob("*.md")) + list((src / "procedures").glob("*.md")))
    errors, report, seen = [], [], {}

    for path in files:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        try:
            meta, body = split_front_matter(text)
            doc_id = meta.get("document_id")
            if not doc_id or not re.fullmatch(r"PR?\d{2}", doc_id):
                raise ValueError(f"document_id ไม่ถูกต้อง: {doc_id!r}")
            if doc_id in seen:
                raise ValueError(f"document_id ซ้ำกับ {seen[doc_id]}")
            seen[doc_id] = path.name
            header, new_body, tagged = transform(meta, body)
            if untransform(new_body, doc_id) != body:
                raise ValueError("เนื้อหาหลังแปลงไม่ตรงกับต้นฉบับ")
            if not body.strip():
                raise ValueError("ไม่มีเนื้อหา")
        except ValueError as e:
            errors.append(f"{path.name}: {e}")
            continue
        name = f"{doc_id}_{safe_name(meta.get('document_title_th', path.stem))}.md"
        sub = out / path.parent.name
        sub.mkdir(parents=True, exist_ok=True)
        (sub / name).write_text(header + new_body, encoding="utf-8")
        report.append({"document_id": doc_id, "source": str(path.relative_to(src)),
                       "output": f"{path.parent.name}/{name}", "headings_tagged": tagged,
                       "body_chars": len(body)})

    if len(report) != args.expect:
        errors.append(f"ได้ {len(report)} เอกสาร แต่คาดว่า {args.expect}")
    no_heading = [r["document_id"] for r in report if r["headings_tagged"] == 0]
    out.mkdir(parents=True, exist_ok=True)
    (out / "prepare_report.json").write_text(json.dumps({
        "documents": len(report), "errors": errors,
        "documents_without_headings": no_heading, "files": report,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"เอกสาร: {len(report)} | หัวข้อที่เติมรหัส: {sum(r['headings_tagged'] for r in report)}")
    if no_heading:
        print(f"คำเตือน: ไม่มีหัวข้อในเอกสาร {', '.join(no_heading)} (chunk กลางเอกสารจะไม่มีรหัส)")
    if errors:
        print("ไม่ผ่าน:\n  " + "\n  ".join(errors))
        sys.exit(1)
    print(f"ผ่าน: เนื้อหาครบตรงต้นฉบับทุกไฟล์ -> {out}  (ไม่ต้องอัปโหลด prepare_report.json)")


if __name__ == "__main__":
    main()
