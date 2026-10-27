#!/usr/bin/env bash
# สรุป Ollama log ช่วงเวลาที่ทดสอบ: จำนวนการเรียก, เวลาแต่ละรอบ, prompt ถูกตัด, โหลดโมเดลใหม่
# ใช้: ./ollama_timing.sh "2026-10-27T10:00:00+07:00" "2026-10-27T10:05:00+07:00" [container]
set -euo pipefail
SINCE=${1:?since เช่น 2026-10-27T10:00:00+07:00}
UNTIL=${2:?until}
C=${3:-openwebui-ollama}
LOG=$(docker logs --since "$SINCE" --until "$UNTIL" "$C" 2>&1)

count() { grep -cE "$1" <<<"$LOG" || true; }

echo "== จำนวนการเรียก =="
echo "embed    : $(count 'POST +"/api/embed')"
echo "generate : $(count 'POST +"/api/(generate|chat)"')   (ควรเป็น 1 ต่อคำถาม หลังปิด Query Generation)"
echo
echo "== เวลาแต่ละรอบ generate/chat =="
grep -E 'POST +"/api/(generate|chat)"' <<<"$LOG" | awk -F'|' '{gsub(/ /,"",$3); print "  " $3}' || true
echo
echo "== prompt/eval timing (ถ้ามีใน log) =="
grep -E 'prompt eval time|^.*eval time|total time' <<<"$LOG" | tail -n 20 || true
echo
echo "== ความเสี่ยง =="
echo "prompt ถูกตัด (num_ctx เล็กไป)     : $(count 'truncating input prompt|input truncated')   (ต้องเป็น 0)"
echo "โหลดโมเดลใหม่ (สลับโมเดล/หลุด keep_alive): $(count 'llama runner started|loading model|starting llama server')   (ต้องเป็น 0 ระหว่างทดสอบ)"
echo
echo "== โมเดลที่ค้างอยู่ตอนนี้ =="
docker exec "$C" ollama ps
