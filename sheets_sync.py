#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مزامنة حقيقية مع Google Sheets عبر Service Account — إضافة صفوف آمنة (append)
إلى شيت "السجل اليومي" بدون استبدال الملف كامل.

غير مُفعَّلة تلقائياً إلا لو المتغيّرات البيئية دي موجودة:
  - GOOGLE_SHEET_ID              : معرّف ملف Google Sheet (من الرابط)
  - GOOGLE_SERVICE_ACCOUNT_JSON  : محتوى ملف مفتاح الـ Service Account (JSON كامل كنص واحد)

لو المتغيرات مش موجودة، كل الدوال هنا "no-op" آمنة (بترجع False/تتجاهل) —
عشان الباك إند يفضل شغال طبيعي حتى قبل إعداد الربط.
"""
import os
import json
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "nest.db")
LOG_SHEET_NAME = "السجل اليومي"
LOG_APPEND_RANGE = f"'{LOG_SHEET_NAME}'!A:I"

BRANCH_SOURCE_LABEL = "تطبيق Nest التفاعلي"


def is_configured() -> bool:
    return bool(os.environ.get("GOOGLE_SHEET_ID") and os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build("sheets", "v4", credentials=creds)


@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _init_sync_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sheets_sync_log (
            ref TEXT PRIMARY KEY,
            synced_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _build_rows(reports, wastes):
    rows = []
    for rep in reports:
        ref = f"shift-report-{rep['id']}"
        detail = (
            f"تقرير وردية آلي — مبيعات {rep['total_sales']:,.0f} ج.م "
            f"({rep['invoices_count']} فاتورة)"
            + (f"، هدر {rep['waste_percentage']}%" if rep['waste_percentage'] is not None else "")
            + (f"، التزام ريسبي {rep['recipe_compliance_percentage']}%" if rep['recipe_compliance_percentage'] is not None else "")
            + (f"، سلامة غذاء {rep['food_safety_score']}%" if rep['food_safety_score'] is not None else "")
        )
        rows.append((ref, rep["created_at"] or "", [
            "", rep["report_date"], (rep["created_at"] or "")[11:16], rep["branch"],
            BRANCH_SOURCE_LABEL, "مبيعات-إيرادات", detail, rep["notes"] or "", rep["manager_name"],
        ]))
    for w in wastes:
        ref = f"waste-entry-{w['id']}"
        detail = (
            f"تسجيل هدر آلي — {w['item_name']}: {w['quantity']:g} {w['unit']} "
            f"(السبب: {w['reason']})"
            + (f"، تكلفة تقديرية {w['estimated_cost']:,.0f} ج.م" if w['estimated_cost'] is not None else "")
        )
        rows.append((ref, w["created_at"] or "", [
            "", w["entry_date"], (w["created_at"] or "")[11:16], w["branch"],
            BRANCH_SOURCE_LABEL, "مخزون", detail, w["notes"] or "", w["recorded_by"],
        ]))
    rows.sort(key=lambda r: r[1])
    return rows


def sync_unsynced_rows() -> dict:
    """
    يقرأ تقارير الوردية وتسجيلات الهدر اللي لسه ما اتزامنتش مع Google Sheets،
    يضيفهم كصفوف جديدة (append، بدون لمس أي صف موجود)، ويسجّل نجاح المزامنة محلياً
    عشان ما يتكررش. يرجع dict فيه عدد الصفوف المُضافة أو سبب عدم التفعيل.
    """
    if not is_configured():
        return {"status": "not_configured", "added": 0,
                "message": "GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON غير مضبوطة بعد."}

    with _get_conn() as conn:
        _init_sync_table(conn)
        reports = conn.execute("SELECT * FROM shift_reports ORDER BY id ASC").fetchall()
        wastes = conn.execute("SELECT * FROM waste_entries ORDER BY id ASC").fetchall()
        synced = {r["ref"] for r in conn.execute("SELECT ref FROM sheets_sync_log").fetchall()}

        all_rows = _build_rows(reports, wastes)
        new_rows = [(ref, values) for ref, _, values in all_rows if ref not in synced]

        if not new_rows:
            return {"status": "ok", "added": 0, "message": "كل البيانات مُزامنة بالفعل."}

        service = _get_service()
        sheet_id = os.environ["GOOGLE_SHEET_ID"]
        body = {"values": [values for _, values in new_rows]}
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=LOG_APPEND_RANGE,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "INSERT OR IGNORE INTO sheets_sync_log (ref, synced_at) VALUES (?,?)",
            [(ref, now) for ref, _ in new_rows],
        )
        conn.commit()

    return {"status": "ok", "added": len(new_rows), "message": f"تمت إضافة {len(new_rows)} صف/صفوف إلى Google Sheets فعلياً."}
