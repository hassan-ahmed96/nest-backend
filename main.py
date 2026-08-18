#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nest Backend — نموذج أولي (Prototype)
أول وظيفة حقيقية: استقبال تقارير الوردية والمبيعات من الفروع.

هذا Backend حقيقي (FastAPI + SQLite) يشتغل فعلياً، لكنه يعمل محلياً داخل
هذه الجلسة فقط (لا استضافة خارجية بعد — بانتظار قرار المستخدم بالاستضافة الحقيقية).
"""
import os
import json
import sqlite3
from datetime import datetime, date, timezone
from typing import Optional, List
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import sheets_sync

DB_PATH = os.path.join(os.path.dirname(__file__), "nest.db")
API_KEY = os.environ.get("NEST_API_KEY", "nest-demo-key-2026")  # مفتاح تجريبي للنموذج الأولي فقط

BRANCHES = [
    "فرع الثورة", "فرع المعادي", "فرع بولاريس",
    "فرع 81", "فرع أوبن إير", "فرع بوينت 6",
]
SHIFTS = ["صباحية", "مسائية"]
WASTE_UNITS = ["كجم", "لتر", "قطعة", "كوب"]
WASTE_REASONS = [
    "انتهاء صلاحية", "خطأ تحضير-استخلاص", "سقوط-كسر", "رفض عميل",
    "خطأ في الطلب", "عينة تجريبية-تذوق", "عطل معدات", "سبب آخر",
]

app = FastAPI(title="Nest Backend — نموذج أولي", version="0.1.0")


# ---------------------------------------------------------------- DB setup
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shift_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT NOT NULL,
                report_date TEXT NOT NULL,
                shift TEXT NOT NULL,
                manager_name TEXT NOT NULL,
                total_sales REAL NOT NULL,
                invoices_count INTEGER NOT NULL,
                waste_percentage REAL,
                recipe_compliance_percentage REAL,
                food_safety_score REAL,
                notes TEXT,
                source TEXT DEFAULT 'Nest API',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS waste_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                reason TEXT NOT NULL,
                estimated_cost REAL,
                recorded_by TEXT NOT NULL,
                notes TEXT,
                source TEXT DEFAULT 'Nest API',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_date TEXT NOT NULL UNIQUE,
                summary_json TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
        """)
        conn.commit()

init_db()


# ---------------------------------------------------------------- Daily digest job
def generate_daily_digest(for_date: Optional[str] = None) -> dict:
    """
    يولّد ملخصاً يومياً (إجمالي مبيعات، عدد تقارير، إجمالي هدر وتكلفته، تفصيل لكل فرع)
    ويحفظه في جدول daily_digests. يُستدعى تلقائياً كل يوم الساعة 23:55 (توقيت UTC)
    عبر APScheduler، ويمكن استدعاؤه يدوياً أيضاً لأي تاريخ عبر /api/daily-digests/generate.
    """
    target_date = for_date or datetime.now(timezone.utc).date().isoformat()
    with get_conn() as conn:
        reports = conn.execute(
            "SELECT * FROM shift_reports WHERE report_date = ?", (target_date,)
        ).fetchall()
        wastes = conn.execute(
            "SELECT * FROM waste_entries WHERE entry_date = ?", (target_date,)
        ).fetchall()

        by_branch = {}
        for b in BRANCHES:
            by_branch[b] = {"total_sales": 0.0, "shift_reports": 0, "waste_items": 0, "waste_cost": 0.0}
        total_sales = 0.0
        for r in reports:
            total_sales += r["total_sales"]
            by_branch[r["branch"]]["total_sales"] += r["total_sales"]
            by_branch[r["branch"]]["shift_reports"] += 1
        total_waste_cost = 0.0
        for w in wastes:
            cost = w["estimated_cost"] or 0
            total_waste_cost += cost
            by_branch[w["branch"]]["waste_items"] += 1
            by_branch[w["branch"]]["waste_cost"] += cost

        summary = {
            "date": target_date,
            "total_shift_reports": len(reports),
            "total_sales": round(total_sales, 2),
            "total_waste_entries": len(wastes),
            "total_waste_cost": round(total_waste_cost, 2),
            "by_branch": by_branch,
        }
        generated_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO daily_digests (digest_date, summary_json, generated_at) VALUES (?,?,?) "
            "ON CONFLICT(digest_date) DO UPDATE SET summary_json=excluded.summary_json, generated_at=excluded.generated_at",
            (target_date, json.dumps(summary, ensure_ascii=False), generated_at),
        )
        conn.commit()
    return summary


def daily_job():
    """يشتغل تلقائياً كل يوم: يولّد الملخص اليومي، ثم (لو Google Sheets مُعدّة) يزامن الصفوف الجديدة فعلياً."""
    generate_daily_digest()
    if sheets_sync.is_configured():
        sheets_sync.sync_unsynced_rows()


scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(daily_job, CronTrigger(hour=23, minute=55), id="daily_digest_job", replace_existing=True)
scheduler.start()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def check_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="مفتاح API غير صحيح أو مفقود (X-API-Key)")


# ---------------------------------------------------------------- Schemas
class ShiftReportIn(BaseModel):
    branch: str = Field(..., description="اسم الفرع — يجب أن يطابق أحد الفروع الستة المعتمدة")
    report_date: date
    shift: str = Field(..., description="صباحية أو مسائية")
    manager_name: str
    total_sales: float = Field(..., ge=0)
    invoices_count: int = Field(..., ge=0)
    waste_percentage: Optional[float] = Field(None, ge=0, le=100)
    recipe_compliance_percentage: Optional[float] = Field(None, ge=0, le=100)
    food_safety_score: Optional[float] = Field(None, ge=0, le=100)
    notes: Optional[str] = None
    source: str = "Nest API"

    class Config:
        json_schema_extra = {
            "example": {
                "branch": "فرع المعادي",
                "report_date": "2026-08-17",
                "shift": "مسائية",
                "manager_name": "أحمد سمير",
                "total_sales": 8400,
                "invoices_count": 132,
                "waste_percentage": 1.8,
                "recipe_compliance_percentage": 96,
                "food_safety_score": 92,
                "notes": "وردية عادية بدون ملاحظات",
            }
        }


class ShiftReportOut(ShiftReportIn):
    id: int
    created_at: str


class WasteEntryIn(BaseModel):
    branch: str = Field(..., description="اسم الفرع — يجب أن يطابق أحد الفروع الستة المعتمدة")
    entry_date: date
    item_name: str = Field(..., description="اسم الصنف/المكوّن المهدر")
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., description="كجم / لتر / قطعة / كوب")
    reason: str = Field(..., description="سبب الهدر")
    estimated_cost: Optional[float] = Field(None, ge=0, description="التكلفة التقديرية (ج.م)")
    recorded_by: str
    notes: Optional[str] = None
    source: str = "Nest API"

    class Config:
        json_schema_extra = {
            "example": {
                "branch": "فرع بولاريس",
                "entry_date": "2026-08-17",
                "item_name": "حليب كامل الدسم",
                "quantity": 2.5,
                "unit": "لتر",
                "reason": "انتهاء صلاحية",
                "estimated_cost": 75,
                "recorded_by": "قائد الوردية",
                "notes": "تم التخلص منه حسب بروتوكول سلامة الغذاء",
            }
        }


class WasteEntryOut(WasteEntryIn):
    id: int
    created_at: str


# ---------------------------------------------------------------- Routes
@app.get("/", response_class=HTMLResponse)
def home():
    branch_options = "".join(f'<option value="{b}">{b}</option>' for b in BRANCHES)
    shift_options = "".join(f'<option value="{s}">{s}</option>' for s in SHIFTS)
    unit_options = "".join(f'<option value="{u}">{u}</option>' for u in WASTE_UNITS)
    reason_options = "".join(f'<option value="{r}">{r}</option>' for r in WASTE_REASONS)
    return f"""
    <html dir="rtl" lang="ar">
    <head><meta charset="utf-8"><title>Nest Backend</title>
    <style>
      body{{font-family:Arial;background:#FAF5EC;color:#3B2A22;max-width:640px;margin:30px auto;padding:0 16px}}
      h1{{color:#8D6959}}
      label{{display:block;margin-top:12px;font-weight:bold;font-size:13px}}
      input,select,textarea{{width:100%;padding:8px;border:1px solid #D9CFC2;border-radius:6px;font-family:Arial;margin-top:4px}}
      button{{margin-top:18px;background:#8D6959;color:#fff;border:none;padding:12px 20px;border-radius:8px;font-size:14px;cursor:pointer}}
      #shift-result,#waste-result{{margin-top:16px;padding:12px;border-radius:8px;display:none}}
      .tabs{{display:flex;gap:8px;margin-top:16px}}
      .tab-btn{{padding:8px 16px;border-radius:20px;border:1px solid #D9CFC2;background:#fff;cursor:pointer;font-family:Arial;font-size:13px}}
      .tab-btn.active{{background:#8D6959;color:#fff;border-color:#8D6959}}
      .panel{{display:none}}
      .panel.active{{display:block}}
    </style></head>
    <body>
      <h1>Nest Backend — نموذج أولي</h1>
      <p>نموذج تجريبي لاختبار استقبال بيانات التشغيل مباشرة عبر API حقيقي.</p>
      <div class="tabs">
        <button class="tab-btn active" data-panel="shift-panel">تقرير وردية ومبيعات</button>
        <button class="tab-btn" data-panel="waste-panel">تسجيل هدر</button>
      </div>

      <div class="panel active" id="shift-panel">
        <form id="shift-form">
          <label>الفرع</label><select name="branch">{branch_options}</select>
          <label>التاريخ</label><input type="date" name="report_date" required>
          <label>الوردية</label><select name="shift">{shift_options}</select>
          <label>اسم المسؤول</label><input name="manager_name" required>
          <label>إجمالي المبيعات (ج.م)</label><input type="number" name="total_sales" required>
          <label>عدد الفواتير</label><input type="number" name="invoices_count" required>
          <label>نسبة الهدر %</label><input type="number" step="0.1" name="waste_percentage">
          <label>الالتزام بالريسبي %</label><input type="number" step="0.1" name="recipe_compliance_percentage">
          <label>تقييم سلامة الغذاء %</label><input type="number" step="0.1" name="food_safety_score">
          <label>ملاحظات</label><textarea name="notes" rows="3"></textarea>
          <button type="submit">إرسال التقرير</button>
        </form>
        <div id="shift-result"></div>
      </div>

      <div class="panel" id="waste-panel">
        <form id="waste-form">
          <label>الفرع</label><select name="branch">{branch_options}</select>
          <label>التاريخ</label><input type="date" name="entry_date" required>
          <label>الصنف/المكوّن</label><input name="item_name" required placeholder="مثال: حليب كامل الدسم">
          <label>الكمية</label><input type="number" step="0.01" name="quantity" required>
          <label>الوحدة</label><select name="unit">{unit_options}</select>
          <label>سبب الهدر</label><select name="reason">{reason_options}</select>
          <label>التكلفة التقديرية (ج.م)</label><input type="number" step="0.01" name="estimated_cost">
          <label>سجّله</label><input name="recorded_by" required>
          <label>ملاحظات</label><textarea name="notes" rows="3"></textarea>
          <button type="submit">إرسال تسجيل الهدر</button>
        </form>
        <div id="waste-result"></div>
      </div>

      <script>
        document.querySelectorAll('.tab-btn').forEach(btn => {{
          btn.addEventListener('click', () => {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.panel).classList.add('active');
          }});
        }});

        document.getElementById('shift-form').addEventListener('submit', async (e) => {{
          e.preventDefault();
          const data = Object.fromEntries(new FormData(e.target).entries());
          ['total_sales','invoices_count','waste_percentage','recipe_compliance_percentage','food_safety_score']
            .forEach(k => {{ if(data[k] !== '') data[k] = parseFloat(data[k]); else delete data[k]; }});
          const res = await fetch('/api/shift-reports', {{
            method: 'POST',
            headers: {{'Content-Type':'application/json', 'X-API-Key':'{API_KEY}'}},
            body: JSON.stringify(data)
          }});
          const box = document.getElementById('shift-result');
          box.style.display = 'block';
          if (res.ok) {{
            const j = await res.json();
            box.style.background = '#e5f3e6'; box.textContent = 'تم الحفظ بنجاح — رقم التقرير #' + j.id;
          }} else {{
            box.style.background = '#fbe7e7'; box.textContent = 'خطأ: ' + (await res.text());
          }}
        }});

        document.getElementById('waste-form').addEventListener('submit', async (e) => {{
          e.preventDefault();
          const data = Object.fromEntries(new FormData(e.target).entries());
          ['quantity','estimated_cost'].forEach(k => {{ if(data[k] !== '') data[k] = parseFloat(data[k]); else delete data[k]; }});
          const res = await fetch('/api/waste-entries', {{
            method: 'POST',
            headers: {{'Content-Type':'application/json', 'X-API-Key':'{API_KEY}'}},
            body: JSON.stringify(data)
          }});
          const box = document.getElementById('waste-result');
          box.style.display = 'block';
          if (res.ok) {{
            const j = await res.json();
            box.style.background = '#e5f3e6'; box.textContent = 'تم الحفظ بنجاح — رقم تسجيل الهدر #' + j.id;
          }} else {{
            box.style.background = '#fbe7e7'; box.textContent = 'خطأ: ' + (await res.text());
          }}
        }});
      </script>
    </body></html>
    """


@app.post("/api/shift-reports", response_model=ShiftReportOut)
def create_shift_report(report: ShiftReportIn, x_api_key: Optional[str] = Header(None)):
    check_api_key(x_api_key)
    if report.branch not in BRANCHES:
        raise HTTPException(status_code=422, detail=f"الفرع يجب أن يكون أحد: {', '.join(BRANCHES)}")
    if report.shift not in SHIFTS:
        raise HTTPException(status_code=422, detail=f"الوردية يجب أن تكون أحد: {', '.join(SHIFTS)}")
    created_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO shift_reports
            (branch, report_date, shift, manager_name, total_sales, invoices_count,
             waste_percentage, recipe_compliance_percentage, food_safety_score, notes, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            report.branch, report.report_date.isoformat(), report.shift, report.manager_name,
            report.total_sales, report.invoices_count, report.waste_percentage,
            report.recipe_compliance_percentage, report.food_safety_score, report.notes,
            report.source, created_at
        ))
        conn.commit()
        new_id = cur.lastrowid
    return ShiftReportOut(id=new_id, created_at=created_at, **report.model_dump())


@app.get("/api/shift-reports", response_model=List[ShiftReportOut])
def list_shift_reports(
    branch: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    x_api_key: Optional[str] = Header(None),
):
    check_api_key(x_api_key)
    q = "SELECT * FROM shift_reports WHERE 1=1"
    params = []
    if branch:
        q += " AND branch = ?"
        params.append(branch)
    if date_from:
        q += " AND report_date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        q += " AND report_date <= ?"
        params.append(date_to.isoformat())
    q += " ORDER BY report_date DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [ShiftReportOut(**dict(row)) for row in rows]


@app.get("/api/shift-reports/{report_id}", response_model=ShiftReportOut)
def get_shift_report(report_id: int, x_api_key: Optional[str] = Header(None)):
    check_api_key(x_api_key)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shift_reports WHERE id = ?", (report_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="التقرير غير موجود")
    return ShiftReportOut(**dict(row))


@app.post("/api/waste-entries", response_model=WasteEntryOut)
def create_waste_entry(entry: WasteEntryIn, x_api_key: Optional[str] = Header(None)):
    check_api_key(x_api_key)
    if entry.branch not in BRANCHES:
        raise HTTPException(status_code=422, detail=f"الفرع يجب أن يكون أحد: {', '.join(BRANCHES)}")
    created_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO waste_entries
            (branch, entry_date, item_name, quantity, unit, reason, estimated_cost, recorded_by, notes, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            entry.branch, entry.entry_date.isoformat(), entry.item_name, entry.quantity, entry.unit,
            entry.reason, entry.estimated_cost, entry.recorded_by, entry.notes, entry.source, created_at
        ))
        conn.commit()
        new_id = cur.lastrowid
    return WasteEntryOut(id=new_id, created_at=created_at, **entry.model_dump())


@app.get("/api/waste-entries", response_model=List[WasteEntryOut])
def list_waste_entries(
    branch: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    x_api_key: Optional[str] = Header(None),
):
    check_api_key(x_api_key)
    q = "SELECT * FROM waste_entries WHERE 1=1"
    params = []
    if branch:
        q += " AND branch = ?"
        params.append(branch)
    if date_from:
        q += " AND entry_date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        q += " AND entry_date <= ?"
        params.append(date_to.isoformat())
    q += " ORDER BY entry_date DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [WasteEntryOut(**dict(row)) for row in rows]


@app.get("/api/waste-entries/{entry_id}", response_model=WasteEntryOut)
def get_waste_entry(entry_id: int, x_api_key: Optional[str] = Header(None)):
    check_api_key(x_api_key)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM waste_entries WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="تسجيل الهدر غير موجود")
    return WasteEntryOut(**dict(row))


@app.get("/api/daily-digests")
def list_daily_digests(x_api_key: Optional[str] = Header(None)):
    check_api_key(x_api_key)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM daily_digests ORDER BY digest_date DESC").fetchall()
    return [
        {"date": r["digest_date"], "generated_at": r["generated_at"], **json.loads(r["summary_json"])}
        for r in rows
    ]


@app.post("/api/daily-digests/generate")
def trigger_daily_digest(
    for_date: Optional[date] = Query(None, description="افتراضياً اليوم الحالي (UTC)"),
    x_api_key: Optional[str] = Header(None),
):
    """توليد/إعادة توليد الملخص اليومي فوراً (يدوياً) — نفس المنطق الذي يعمل تلقائياً كل يوم 23:55 UTC."""
    check_api_key(x_api_key)
    summary = generate_daily_digest(for_date.isoformat() if for_date else None)
    return summary


@app.get("/api/sheets-sync-status")
def sheets_sync_status(x_api_key: Optional[str] = Header(None)):
    check_api_key(x_api_key)
    return {
        "configured": sheets_sync.is_configured(),
        "message": "جاهز للمزامنة الفعلية مع Google Sheets." if sheets_sync.is_configured()
                   else "لم تُضبط بعد GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON — راجع GOOGLE_SHEETS_SETUP.md.",
    }


@app.post("/api/sync-to-sheets")
def trigger_sheets_sync(x_api_key: Optional[str] = Header(None)):
    """مزامنة فورية يدوية مع Google Sheets الحقيقي (تحتاج GOOGLE_SHEET_ID و GOOGLE_SERVICE_ACCOUNT_JSON مضبوطة)."""
    check_api_key(x_api_key)
    result = sheets_sync.sync_unsynced_rows()
    if result["status"] == "not_configured":
        raise HTTPException(status_code=412, detail=result["message"])
    return result


@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown(wait=False)


@app.get("/api/branches")
def get_branches():
    return {"branches": BRANCHES}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nest-backend-prototype"}
