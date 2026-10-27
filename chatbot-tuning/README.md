# ชุดปรับจูน IT Policy Assistant v1.2

> ต่อจาก `BAAC_AI_CHATBOT_IMPLEMENTATION_LOG_2026-10-26` หัวข้อ 14 และ 20
> หลักการ: **ถูกต้อง → เชื่อถือได้ → รวดเร็ว** (ไม่แลกความถูกต้องกับความเร็ว)

## 1. วิเคราะห์จากผลทดสอบเดิม

| # | สิ่งที่พบใน Log | ผลกระทบ | แก้ในขั้นตอน |
|---|---|---|---|
| 1 | Ollama ถูกเรียก 2 รอบต่อคำถาม (สร้าง Query + ตอบ) ด้วย qwen ทั้งคู่ รอบละ ~15 วินาที | ช้า: เสียเวลาครึ่งหนึ่งไปกับการสร้าง Query | 2 |
| 2 | Prompt รอบตอบ ~2,000 tokens (ยาวสุด 3,761) | ช้า: เวลาส่วนใหญ่อยู่ที่ prompt eval | 4, 7 |
| 3 | `/api/embed` 24–35 ครั้งต่อคำถาม | ช้า + โหลด Ollama | 3 |
| 4 | Max Tokens 256 + สั่งให้ตอบ "ภายใน 160 tokens" | ไม่ถูกต้อง: ภาษาไทยใช้ token มาก คำตอบอาจถูกตัดกลางประโยค และโมเดลนับ token เองไม่ได้ | 4, 5 |
| 5 | YAML ของทุกเอกสารถูก index เป็น chunk และ chunk กลางเอกสารไม่มีรหัส P/PR | ไม่ถูกต้อง: เสียที่ Top K 3 ไปกับ metadata และโมเดลอ้างรหัสเอกสารผิดหรือแต่งเอง | 7 |
| 6 | เวลาแกว่งมาก (8 วินาที ถึง 38 วินาที) ด้วยคำถามเดียวกัน | ไม่น่าเชื่อถือ: น่าจะมีการโหลดโมเดลใหม่หรือสลับโมเดล | 1 |

### ทำไมไม่เริ่มจาก gemma-2b-fast เป็น Task Model

แผนเดิมในหัวข้อ 20 จะลดเวลารอบแรกได้ แต่มีความเสี่ยง 3 ข้อ:

1. **ความถูกต้อง:** โมเดล 2B เขียน Query ภาษาไทยใหม่ได้ไม่ดี Query ที่ผิดทำให้ค้นเอกสารผิด แล้วคำตอบก็ผิดตาม
2. **ความเสถียร:** ต้องมี 3 โมเดลอยู่ในหน่วยความจำพร้อมกัน (qwen, bge-m3, gemma) ถ้าไม่พอจะสลับโหลดทุกคำถาม ซึ่งช้ากว่าเดิม
3. **ยังเสียเวลา 1 รอบ** แม้จะสั้นลง

ทางที่ดีกว่าคือ**ปิด Retrieval Query Generation** (ขั้นตอน 2) แล้วค้นด้วยคำถามของผู้ใช้ตรง ๆ ซึ่ง bge-m3 รองรับภาษาไทยดีอยู่แล้ว วิธีนี้ตัดการเรียก LLM ไป 1 รอบเต็ม ส่วน gemma-2b-fast เก็บไว้เป็นทางเลือก B ถ้าคำถามต่อเนื่อง (F01–F03) ไม่ผ่าน

## 2. ไฟล์ในชุดนี้

```text
chatbot-tuning/
├── prompts/system_prompt_v1.2.md       System Prompt ใหม่ (สั้นลง ไม่สั่งนับ token)
├── prompts/rag_template_v1.2.md        RAG Template ภาษาไทยแบบสั้น (แทนค่า default ภาษาอังกฤษที่ยาว)
├── config/ollama.env                   ค้างโมเดลในหน่วยความจำ / กันการสลับโมเดล
├── config/Modelfile.qwen-baac          ล็อก num_ctx, max tokens, temperature, seed ที่ Ollama
├── config/litellm_model_snippet.yaml   เส้นทาง qwen-baac + timeout ใน LiteLLM
├── golden_set/golden_questions.jsonl   ชุดคำถามทดสอบ 33 ข้อ (ตอบได้ / ต่อเนื่อง / นอกขอบเขต / โจมตี)
├── scripts/benchmark.py                วัดความถูกต้อง ความเร็ว และความเชื่อถือได้ (Python ล้วน ไม่ต้องติดตั้งอะไร)
├── scripts/ollama_timing.sh            สรุป Ollama log: จำนวนรอบ, prompt ถูกตัด, การโหลดโมเดลใหม่
└── scripts/prepare_kb.py               เตรียมไฟล์ Knowledge ใหม่ (ใส่รหัสเอกสารทุกหัวข้อ และตรวจว่าเนื้อหาครบ)
```

## 3. วิธีทดสอบ (ใช้ทุกขั้นตอน)

1. **เปลี่ยนทีละอย่าง** และจดค่าเดิมไว้ก่อนแก้ทุกครั้ง (เพื่อ Rollback)
2. รัน benchmark 3 รอบ เพื่อดูว่าคำตอบนิ่งหรือไม่:

   ```bash
   export OPENWEBUI_API_KEY=...    # OpenWebUI API Key (ห้ามใช้ LiteLLM Master Key)
   START=$(date -Iseconds)
   python3 scripts/benchmark.py --base-url http://<openwebui>:<port> \
     --model -it-policy-assistant --golden golden_set/golden_questions.jsonl \
     --runs 3 --label step2_no_query_gen
   scripts/ollama_timing.sh "$START" "$(date -Iseconds)"
   ```

3. เทียบ `results/<label>.md` กับขั้นก่อนหน้า **ถ้าความถูกต้องลดลง ให้ Rollback แม้จะเร็วขึ้น**

> ทดสอบแค่คำถามเดียวแบบหัวข้อ 20: `--only A01 --runs 3`

## 4. ขั้นตอนการจูน (เรียงตามผลต่อความเร็วและความเสี่ยง)

### ขั้น 0: วัด Baseline

- กรอก `expected_doc_ids` ใน `golden_questions.jsonl` ข้อที่มี note "ให้ผู้ดูแลระบุ" (ตอนนี้ระบุไว้แล้วเฉพาะ P05 และ PR35 ที่ยืนยันจาก Log ได้) และเพิ่มคำถามจริงของผู้ใช้ให้ครบ 50–100 ข้อ
- ถ้าต้องการตรวจเนื้อหาคำตอบ ให้ใส่ `expected_keywords` เช่น `["90 วัน"]` (ตัวเลขหรือคำที่ต้องมีในคำตอบที่ถูกต้อง)
- รัน benchmark ด้วยค่าปัจจุบัน แล้วตั้งชื่อ `--label step0_baseline`

### ขั้น 1: ค้างโมเดลในหน่วยความจำ (เชื่อถือได้)

- เพิ่มค่าใน `config/ollama.env` ให้ container `openwebui-ollama` แล้วรัน `docker compose up -d --no-deps --force-recreate ollama`
- ตรวจ: `docker exec openwebui-ollama ollama ps` ต้องเห็น qwen และ bge-m3 ค้างอยู่ทั้งคู่
- ผ่านเมื่อ: `ollama_timing.sh` แสดง "โหลดโมเดลใหม่" = 0 และเวลาแต่ละรอบไม่แกว่ง
- Rollback: ลบค่าที่เพิ่มแล้ว recreate อีกครั้ง

### ขั้น 2: ตัดการเรียก LLM ที่ไม่จำเป็น (เร็ว ประหยัดได้ประมาณ 15 วินาที)

OpenWebUI → Admin Panel → Settings → **Interface** ปิด:

| ตัวเลือก | ค่า |
|---|---|
| Retrieval Query Generation | **Off** |
| Web Search Query Generation | Off |
| Title Generation | Off |
| Tags Generation | Off |
| Follow-Up Generation (ถ้ามี) | Off |
| Autocomplete Generation | Off |

> ค่าเหล่านี้เก็บอยู่ใน `webui.db` เช่นเดียวกับปัญหา API Key ในหัวข้อ 4 ของ Log จึงต้องแก้ผ่านหน้า Admin เท่านั้น การแก้ใน environment จะไม่มีผล

- ผ่านเมื่อ: `ollama_timing.sh` แสดง generate = **1 ครั้งต่อคำถาม** และ Retrieval hit ไม่ลดลงจาก Baseline
- **ตรวจ F01–F03 (คำถามต่อเนื่อง) เป็นพิเศษ** เพราะเดิม Query Generation ช่วยรวมบริบทจากคำถามก่อนหน้า ถ้าข้อเหล่านี้ไม่ผ่าน ให้เลือกทางใดทางหนึ่ง:
  - **ทางเลือก A (แนะนำ ไม่ต้องเรียก LLM เพิ่ม):** ให้ DTKPI ต่อคำถามก่อนหน้าเข้าไป เมื่อคำถามใหม่สั้นและมีประวัติสนทนา เช่น `แล้วต้องทบทวนบ่อยแค่ไหน (ต่อจากคำถาม: ข้อกำหนดในการใช้ Admin)`
  - **ทางเลือก B:** เปิด Retrieval Query Generation กลับ แล้วตั้ง Task Model = `gemma-2b-fast` และตั้ง `OLLAMA_MAX_LOADED_MODELS=3` จากนั้นวัดซ้ำทั้งเวลาและ Retrieval hit
- Rollback: เปิด Retrieval Query Generation กลับ

### ขั้น 3: ลดจำนวน Embedding calls

OpenWebUI → Admin Panel → Settings → **Documents**

- **Embedding Batch Size: 1 → 32** ค่านี้ไม่ต้อง re-index ถ้าค่าเป็น 1 ระบบจะส่ง embed ทีละข้อความ ซึ่งน่าจะเป็นต้นเหตุของ 24–35 calls ต่อคำถาม
- ผ่านเมื่อ: `ollama_timing.sh` แสดง embed ไม่เกิน 2–3 ครั้งต่อคำถาม
- ถ้าเวอร์ชันนี้ไม่มีตัวเลือกนี้ ให้ข้ามไป และบันทึกจำนวน embed ไว้เป็นข้อมูลอ้างอิง

### ขั้น 4: Prompt v1.2 (ถูกต้อง + สั้นลง)

- Model `-it-policy-assistant` → System Prompt: ใช้ `prompts/system_prompt_v1.2.md`
- Admin → Settings → Documents → **RAG Template**: ใช้ `prompts/rag_template_v1.2.md` (ต้องคง `{{CONTEXT}}` และ `{{QUERY}}` ไว้) Template default ของ OpenWebUI เป็นภาษาอังกฤษและยาวหลายร้อย tokens ซึ่งถูกส่งไปกับทุกคำถาม

สิ่งที่เปลี่ยนจาก Fast Prompt เดิม:

- ตัดคำสั่ง "ตอบภายใน 160 tokens" เพราะโมเดลนับ token เองไม่ได้ ใช้ "ไม่เกิน 4 ข้อ" คุมความยาวแทน และคุมเพดานจริงด้วย `num_predict` ในขั้น 5
- แยกหน้าที่: System Prompt คุมบทบาท/สไตล์/ความปลอดภัย ส่วน RAG Template คุมการอ้างอิง จึงไม่มีข้อความซ้ำกันทั้งสองที่
- บอกโมเดลว่า**รหัสเอกสารอยู่ใน name ของ source** จึงอ้าง P05/PR12 ได้แม้ chunk นั้นไม่มีรหัส และห้ามพิมพ์ `.md`
- Fallback รวมเป็นข้อความเดียว ให้ตรวจอัตโนมัติได้

ผ่านเมื่อ: "อ้างรหัสเอกสารตรงกับที่ค้นมา" = 100%, ข้อมูลภายในหลุด = 0, ปฏิเสธถูกต้อง = 100%

### ขั้น 5: ล็อกพารามิเตอร์โมเดล (เชื่อถือได้)

ใช้ `config/Modelfile.qwen-baac` สร้างโมเดล `qwen-baac` แล้วเพิ่ม `config/litellm_model_snippet.yaml` ใน LiteLLM จากนั้นเปลี่ยน Base Model ของ `-it-policy-assistant` เป็น `qwen-baac`

| ค่า | เดิม | ใหม่ | เหตุผล |
|---|---|---|---|
| temperature | 0.20 | 0.1 | คำตอบนโยบายต้องเหมือนเดิมทุกครั้ง |
| seed | - | 42 | ถามซ้ำได้คำตอบเดิม ตรวจสอบย้อนกลับได้ |
| max tokens | 256 | 400 | ไทย 4 ข้อพร้อมอ้างอิงเกิน 256 ได้ ถ้าถูกตัดกลางประโยคถือว่าตอบผิด |
| num_ctx | ไม่ระบุ | 4096 | ถ้าเล็กไป Ollama จะตัด System Prompt ทิ้งเงียบ ๆ |

> ตั้งที่ Modelfile เพราะยังไม่ยืนยันว่า OpenWebUI → LiteLLM → Ollama ส่ง `num_ctx` ผ่านครบทุกชั้น

- ผ่านเมื่อ: "คำตอบถูกตัดกลางคัน" = 0, "prompt ถูกตัด" = 0 และรัน 3 รอบได้คำตอบเหมือนกัน
- Rollback: เปลี่ยน Base Model กลับเป็น qwen เดิม

### ขั้น 6: Streaming ฝั่ง DTKPI (ผู้ใช้รู้สึกเร็วขึ้น)

ให้ `chatbot.php` เรียก OpenWebUI ด้วย `"stream": true` แล้วส่งต่อให้หน้าเว็บทีละส่วน ผู้ใช้จะเห็นคำแรกตามเวลา TTFT แทนการรอจนครบ (ดูค่า TTFT ใน benchmark) Citation อยู่ใน event `sources` แรกของ stream จึงยังใช้ Citation Isolation เดิมได้

ข้อนี้ต้องแก้ PHP จึงทำหลังขั้น 1–5 ผ่านแล้ว และใช้วิธี backup/hash/`php -l` เดิม

### ขั้น 7: Knowledge v2 (ถูกต้อง, ต้อง re-index ใน Collection ทดสอบใหม่)

```bash
python3 scripts/prepare_kb.py \
  --src knowledge_domains/it_security_2569 \
  --out knowledge_domains/it_security_2569_rag
```

- แทน YAML ด้วยหัวเอกสาร 2 บรรทัด (รหัส ชื่อ ประเภท ปีบัญชี หน้า PDF) แล้วเติม `[P05]` หน้าทุกหัวข้อ และตั้งชื่อไฟล์ขึ้นต้นด้วยรหัสเอกสาร
- สคริปต์ตรวจเองว่าได้ครบ 54 ไฟล์ ไม่มีรหัสซ้ำ และเนื้อหาตรงต้นฉบับทุกตัวอักษร ถ้าไม่ผ่านจะหยุด (exit 1) โดยไม่แก้ไฟล์ต้นฉบับ
- อัปโหลดเข้า Collection ใหม่ `BAAC_IT_SECURITY_POLICY_2569_V2_TEST` (ไม่ต้องอัปโหลด `prepare_report.json`) แล้วผูกกับโมเดลทดสอบแยกต่างหาก
- ถ้าจะ re-index อยู่แล้ว ให้ลองเพิ่มพร้อมกันในโมเดลทดสอบ: Text Splitter แบบ Markdown Header (ถ้าเวอร์ชันมี) และ Chunk Size 800 / Overlap 100 เพื่อให้ chunk ตรงกับข้อย่อยและ prompt สั้นลง
- benchmark เทียบ V1 กับ V2 แล้ว promote V2 เฉพาะเมื่อ Retrieval hit และ Citation ดีขึ้นหรือเท่าเดิม

### ขั้น 8: ปรับ Retrieval จากผล Golden Set

| อาการใน benchmark | ปรับ |
|---|---|
| Retrieval hit ต่ำ / Fallback ผิดที่สูง | Top K 3 → 4–5 หรือ Minimum Score 0.50 → 0.40 (prompt ยาวขึ้นประมาณ 1 chunk ต่อ K) |
| คำถามนอกขอบเขตได้คำตอบแทน Fallback | Minimum Score 0.50 → 0.55–0.60 |
| ค้นเจอแต่เรียงลำดับผิด | ทดลอง Reranking Model `BAAI/bge-reranker-v2-m3` (รองรับไทย) ถ้าไม่มี GPU จะเพิ่มเวลา ต้องวัดก่อน |

## 5. เกณฑ์ก่อนขึ้น Production

| ตัวชี้วัด | เป้าหมาย |
|---|---|
| ผ่านทุกเกณฑ์รายข้อ (Golden Set ≥ 50 ข้อ, 3 รอบ) | ≥ 95% |
| Retrieval hit / Citation rate | ≥ 95% |
| อ้างรหัสเอกสารตรงกับที่ค้นมา | 100% |
| ปฏิเสธถูกต้อง (นอกขอบเขต + Prompt Injection) | 100% |
| ข้อมูลภายในหลุด / อักษรจีน / คำตอบถูกตัด | 0 |
| P95 latency | ≤ 25 วินาที |
| Timeout rate / Error rate | < 0.5% / < 1% |
| prompt ถูกตัด / โหลดโมเดลใหม่ระหว่างใช้งาน | 0 |

**ความคาดหวังเรื่องความเร็ว:** หลังขั้น 2 ควรเหลือการ generate รอบเดียว (~10–15 วินาที บนเครื่องปัจจุบัน) จึงผ่านเป้าหมาย P95 ≤ 25 วินาทีได้ ส่วน P50 ≤ 10 วินาทีขึ้นกับความเร็ว prompt eval ของเครื่อง ถ้าทำขั้น 4 และ 7 (ลด prompt) แล้วยังไม่ถึง อาจต้องใช้ GPU หรือโมเดลที่เล็กลง และต้องวัดความถูกต้องซ้ำทุกครั้งที่เปลี่ยนโมเดล

## 6. บันทึกผล

| ขั้น | label | P50 (s) | P95 (s) | generate/คำถาม | embed/คำถาม | Retrieval hit | ผ่านรายข้อ | ตัดสิน |
|---|---|---|---|---|---|---|---|---|
| 0 | step0_baseline | | | 2 | 24–35 | | | - |
| 1 | step1_keep_alive | | | | | | | |
| 2 | step2_no_query_gen | | | | | | | |
| 3 | step3_embed_batch | | | | | | | |
| 4 | step4_prompt_v1.2 | | | | | | | |
| 5 | step5_qwen_baac | | | | | | | |
| 7 | step7_kb_v2 | | | | | | | |

> ไม่บันทึก API Key, Token หรือ Password ลงไฟล์ในชุดนี้ benchmark อ่าน Key จาก environment variable `OPENWEBUI_API_KEY` เท่านั้น
