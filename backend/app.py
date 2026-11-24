"""
个人理财分析系统 - V2 独立后端
Flask + SQLite + DeepSeek AI
"""

import configparser
import csv
import io
import json
import math
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from openai import OpenAI
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

# ── Config ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = Path(BASE_DIR).parent / "frontend" / "dist"
_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(BASE_DIR, "config.ini"), encoding="utf-8")

DB_PATH       = os.path.join(BASE_DIR, "finance.db")
DS_API_KEY    = _cfg.get("deepseek",  "api_key",  fallback="")
DS_BASE_URL   = _cfg.get("deepseek",  "base_url",  fallback="https://api.deepseek.com")
DS_MODEL      = _cfg.get("deepseek",  "model",     fallback="deepseek-chat")
DS_MAX_ADVICE = _cfg.getint("deepseek", "max_tokens_advice", fallback=1200)
DS_MAX_CHAT   = _cfg.getint("deepseek", "max_tokens_chat",   fallback=600)
SRV_PORT      = int(os.getenv("PORT", "5532"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


@app.errorhandler(BadRequest)
def bad_request(error):
    return jsonify({"error": error.description}), 400


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(error):
    return jsonify({"error": "上传文件不得超过 5 MB"}), 413


def json_object():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        raise BadRequest("请求内容必须是 JSON 对象")
    return data


def validate_record(data):
    date = data.get("date", "")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("日期必须为 YYYY-MM-DD")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("日期无效") from None
    category, type_ = data.get("category"), data.get("type")
    if not isinstance(category, str) or not category.strip() or len(category.strip()) > 30:
        raise ValueError("分类名称应为 1 至 30 个字符")
    if type_ not in ("收入", "支出"):
        raise ValueError("类型必须为收入或支出")
    try:
        amount = float(data.get("amount"))
    except (ValueError, TypeError, OverflowError):
        raise ValueError("金额格式无效") from None
    if isinstance(data.get("amount"), bool) or not math.isfinite(amount) or not 0 < amount <= 999999999.99:
        raise ValueError("金额必须大于 0 且不超过 999999999.99")
    if not math.isclose(amount, round(amount, 2), rel_tol=0, abs_tol=1e-8):
        raise ValueError("金额最多保留两位小数")
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > 250:
        raise ValueError("备注不得超过 250 个字符")
    return date, category.strip(), type_, round(amount, 2), description

ds_client = OpenAI(api_key=DS_API_KEY or "not-configured", base_url=DS_BASE_URL)

# ── DB helpers ─────────────────────────────────────────────
import sqlite3


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


DEFAULT_CATEGORIES = [
    {"name": "餐饮",   "type": "支出", "color": "#e11d48"},
    {"name": "交通",   "type": "支出", "color": "#d97706"},
    {"name": "购物",   "type": "支出", "color": "#7c3aed"},
    {"name": "娱乐",   "type": "支出", "color": "#0891b2"},
    {"name": "医疗",   "type": "支出", "color": "#059669"},
    {"name": "住房",   "type": "支出", "color": "#b45309"},
    {"name": "教育",   "type": "支出", "color": "#0369a1"},
    {"name": "通讯",   "type": "支出", "color": "#6d28d9"},
    {"name": "其他支出","type": "支出", "color": "#6b7280"},
    {"name": "工资",   "type": "收入", "color": "#15803d"},
    {"name": "兼职",   "type": "收入", "color": "#0f766e"},
    {"name": "投资收益","type": "收入", "color": "#1d4ed8"},
    {"name": "其他收入","type": "收入", "color": "#4f46e5"},
]


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            type        TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            description TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL UNIQUE,
            type  TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#4f46e5'
        )
    """
    )
    # 仅在空表时插入默认分类
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO categories (name, type, color) VALUES (?,?,?)",
            [(c["name"], c["type"], c["color"]) for c in DEFAULT_CATEGORIES],
        )
    conn.commit()
    conn.close()


# ── Routes: pages ─────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.get("/assets/<path:filename>")
def vue_assets(filename):
    return send_from_directory(FRONTEND_DIST / "assets", filename)


# ── Routes: CRUD ──────────────────────────────────────────
@app.route("/api/records", methods=["GET"])
def get_records():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM records ORDER BY date DESC, id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/records", methods=["POST"])
def add_record():
    data = json_object()
    try:
        record = validate_record(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO records (date, category, type, amount, description) VALUES (?,?,?,?,?)",
        record,
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/records/<int:record_id>", methods=["DELETE"])
def delete_record(record_id):
    conn = get_db()
    conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/records/random", methods=["POST"])
def generate_random():
    conn = get_db()
    cats = conn.execute("SELECT name, type FROM categories").fetchall()
    if not cats:
        conn.close()
        return jsonify({"error": "无分类数据"}), 400
    start = datetime.now() - timedelta(days=90)
    for _ in range(30):
        date = start + timedelta(days=random.randint(0, 90))
        cat = random.choice(cats)
        amount = round(
            random.uniform(1000, 5000) if cat["type"] == "收入" else random.uniform(10, 800),
            2,
        )
        conn.execute(
            "INSERT INTO records (date, category, type, amount, description) VALUES (?,?,?,?,?)",
            (date.strftime("%Y-%m-%d"), cat["name"], cat["type"], amount, f"{cat['name']}消费"),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "count": 30})


@app.route("/api/records/clear", methods=["POST"])
def clear_records():
    conn = get_db()
    conn.execute("DELETE FROM records")
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Routes: 分类管理 ──────────────────────────────────────
@app.route("/api/categories", methods=["GET"])
def get_categories():
    conn = get_db()
    rows = conn.execute("SELECT * FROM categories ORDER BY type, name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
def add_category():
    data = json_object()
    name, type_, color = data.get("name", ""), data.get("type"), data.get("color", "#4f46e5")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 30 or type_ not in ("收入", "支出"):
        return jsonify({"error": "名称应为 1 至 30 个字符，类型必须为收入或支出"}), 400
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return jsonify({"error": "颜色必须为六位十六进制色值"}), 400
    name = name.strip()
    conn = get_db()
    try:
        conn.execute("INSERT INTO categories (name, type, color) VALUES (?,?,?)", (name, type_, color))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "分类名称已存在"}), 409
    conn.close()
    return jsonify({"success": True})


@app.route("/api/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    conn = get_db()
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Routes: 种子测试数据 ──────────────────────────────────
SEED_DATA = [
    # 近 3 个月典型收支
    ("2026-03-05", "工资",   "收入", 12500.00, "3月工资"),
    ("2026-03-06", "餐饮",   "支出",   380.50, "同事聚餐"),
    ("2026-03-08", "交通",   "支出",    96.00, "滴滴打车"),
    ("2026-03-10", "购物",   "支出",   560.00, "网购衣物"),
    ("2026-03-12", "娱乐",   "支出",   210.00, "电影+KTV"),
    ("2026-03-15", "住房",   "支出",  2200.00, "3月房租"),
    ("2026-03-18", "医疗",   "支出",   145.00, "体检费用"),
    ("2026-03-20", "通讯",   "支出",    99.00, "手机话费"),
    ("2026-03-22", "投资收益","收入",   820.00, "基金分红"),
    ("2026-03-25", "餐饮",   "支出",   210.00, "外卖订餐"),
    ("2026-03-28", "教育",   "支出",   399.00, "在线课程"),
    ("2026-04-05", "工资",   "收入", 12500.00, "4月工资"),
    ("2026-04-06", "兼职",   "收入",  1800.00, "周末兼职"),
    ("2026-04-08", "餐饮",   "支出",   430.00, "家庭聚餐"),
    ("2026-04-10", "购物",   "支出",  1280.00, "电子产品"),
    ("2026-04-12", "交通",   "支出",   150.00, "高铁票"),
    ("2026-04-14", "娱乐",   "支出",   320.00, "健身月卡"),
    ("2026-04-15", "住房",   "支出",  2200.00, "4月房租"),
    ("2026-04-18", "餐饮",   "支出",   185.00, "咖啡+早餐"),
    ("2026-04-20", "通讯",   "支出",    99.00, "手机话费"),
    ("2026-04-22", "投资收益","收入",  1200.00, "股票收益"),
    ("2026-04-25", "教育",   "支出",   680.00, "英语培训"),
    ("2026-04-28", "医疗",   "支出",    58.00, "药品购买"),
    ("2026-05-05", "工资",   "收入", 13000.00, "5月工资(涨薪)"),
    ("2026-05-06", "兼职",   "收入",  2200.00, "设计外包"),
    ("2026-05-08", "餐饮",   "支出",   520.00, "生日聚餐"),
    ("2026-05-10", "购物",   "支出",   890.00, "618预购"),
    ("2026-05-12", "交通",   "支出",   260.00, "机票+出租"),
    ("2026-05-14", "娱乐",   "支出",   180.00, "演唱会门票"),
    ("2026-05-15", "住房",   "支出",  2200.00, "5月房租"),
    ("2026-05-18", "通讯",   "支出",    99.00, "手机话费"),
    ("2026-05-20", "医疗",   "支出",   320.00, "牙科检查"),
    ("2026-05-22", "其他支出","支出",   150.00, "快递费用"),
    ("2026-05-25", "投资收益","收入",   560.00, "定期存款利息"),
    ("2026-05-28", "教育",   "支出",   299.00, "书籍购买"),
    ("2026-05-30", "餐饮",   "支出",   340.00, "月末聚餐"),
]


@app.route("/api/records/seed", methods=["POST"])
def seed_records():
    conn = get_db()
    conn.executemany(
        "INSERT INTO records (date, category, type, amount, description) VALUES (?,?,?,?,?)",
        SEED_DATA,
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "count": len(SEED_DATA)})


# ── Routes: stats ─────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def get_stats():
    conn = get_db()
    rows = conn.execute("SELECT * FROM records").fetchall()
    conn.close()
    records = [dict(r) for r in rows]

    total_income = sum(r["amount"] for r in records if r["type"] == "收入")
    total_expense = sum(r["amount"] for r in records if r["type"] == "支出")

    cat_data: dict = {}
    for r in records:
        cat = r["category"]
        if cat not in cat_data:
            cat_data[cat] = {"income": 0.0, "expense": 0.0}
        if r["type"] == "收入":
            cat_data[cat]["income"] += r["amount"]
        else:
            cat_data[cat]["expense"] += r["amount"]

    daily: dict = {}
    for r in records:
        d = r["date"]
        if d not in daily:
            daily[d] = {"income": 0.0, "expense": 0.0}
        if r["type"] == "收入":
            daily[d]["income"] += r["amount"]
        else:
            daily[d]["expense"] += r["amount"]

    return jsonify(
        {
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
            "count": len(records),
            "categories": cat_data,
            "daily": dict(sorted(daily.items())),
        }
    )


# ── Routes: import / export ───────────────────────────────
@app.route("/api/import", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "未上传文件"}), 400
    try:
        content = file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content), strict=True)
        if not {"日期", "分类", "类型", "金额"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV 缺少必需列：日期、分类、类型、金额")
        records = []
        for row in reader:
            try:
                records.append(validate_record({"date": row.get("日期"), "category": row.get("分类"), "type": row.get("类型"), "amount": row.get("金额"), "description": row.get("描述", "")}))
            except ValueError as e:
                raise ValueError(f"CSV 第 {reader.line_num} 行：{e}") from None
        if not records:
            raise ValueError("CSV 没有可导入的记录")
    except (UnicodeDecodeError, csv.Error, ValueError) as e:
        return jsonify({"error": f"导入失败（文件需为 UTF-8）：{e}"}), 400
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany("INSERT INTO records (date, category, type, amount, description) VALUES (?,?,?,?,?)", records)
    return jsonify({"success": True, "count": len(records)})


@app.route("/api/export", methods=["GET"])
def export_csv():
    conn = get_db()
    rows = conn.execute(
        "SELECT date, category, type, amount, description FROM records ORDER BY date DESC"
    ).fetchall()
    conn.close()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["日期", "分类", "类型", "金额", "描述"])
    for r in rows:
        writer.writerow([r["date"], r["category"], r["type"], r["amount"], r["description"]])
    buf.seek(0)
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=finance_records.csv"},
    )


# ── DeepSeek helpers ──────────────────────────────────────
def build_financial_context() -> str:
    conn = get_db()
    rows = conn.execute("SELECT * FROM records ORDER BY date DESC").fetchall()
    conn.close()
    records = [dict(r) for r in rows]
    if not records:
        return "当前没有任何财务数据。"

    total_income = sum(r["amount"] for r in records if r["type"] == "收入")
    total_expense = sum(r["amount"] for r in records if r["type"] == "支出")
    balance = total_income - total_expense
    expense_rate = f"{total_expense / total_income * 100:.1f}%" if total_income else "不适用（收入为零）"

    cat_summary: dict = {}
    for r in records:
        key = f"{r['category']}({r['type']})"
        cat_summary[key] = cat_summary.get(key, 0.0) + r["amount"]

    ctx = (
        f"【用户财务数据摘要】\n"
        f"总记录数：{len(records)} 条\n"
        f"总收入：{total_income:.2f} 元\n"
        f"总支出：{total_expense:.2f} 元\n"
        f"净结余：{balance:.2f} 元\n"
        f"支出率：{expense_rate}\n\n"
        f"各分类金额：\n"
    )
    for cat, amt in sorted(cat_summary.items(), key=lambda x: -x[1]):
        ctx += f"  {cat}: {amt:.2f} 元\n"
    ctx += "\n最近 10 条记录：\n"
    for r in records[:10]:
        ctx += f"  {r['date']} | {r['category']} | {r['type']} | ¥{r['amount']:.2f} | {r['description']}\n"
    return ctx


# ── Routes: AI 两个接入点 ────────────────────────────────

# 接入点 1：AI 智能财务诊断
@app.route("/api/ai/advice", methods=["POST"])
def ai_advice():
    if not DS_API_KEY:
        return jsonify({"error": "请先在 backend/config.ini 中配置 DeepSeek API Key"}), 503
    ctx = build_financial_context()
    try:
        resp = ds_client.chat.completions.create(
            model=DS_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一位专业的个人理财顾问，擅长分析用户收支数据并给出具体可执行的建议。"
                        "请用中文回复，分条列点，简洁直接，重点突出风险和优化方向。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"请根据我的财务数据，给出详细的个性化理财分析与建议：\n\n{ctx}",
                },
            ],
            max_tokens=DS_MAX_ADVICE,
        )
        return jsonify({"advice": resp.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 接入点 2：AI 财务问答助手（带流式输出）
@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    if not DS_API_KEY:
        return jsonify({"error": "请先在 backend/config.ini 中配置 DeepSeek API Key"}), 503
    data = json_object()
    user_msg = data.get("message", "")
    history = data.get("history", [])
    if not isinstance(user_msg, str) or not user_msg.strip() or len(user_msg) > 4000:
        return jsonify({"error": "消息应为 1 至 4000 个字符"}), 400
    user_msg = user_msg.strip()
    if not isinstance(history, list) or any(not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str) or len(m["content"]) > 20000 for m in history):
        return jsonify({"error": "对话历史格式无效"}), 400

    ctx = build_financial_context()
    messages = [
        {
            "role": "system",
            "content": (
                f"你是一位专业的个人财务助手，用户的财务数据如下：\n\n{ctx}\n\n"
                "根据这些数据回答用户的问题，用中文简洁友好地回复，必要时给出数字依据。"
            ),
        }
    ]
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_msg})

    def generate():
        try:
            stream = ds_client.chat.completions.create(
                model=DS_MODEL,
                messages=messages,
                stream=True,
                max_tokens=DS_MAX_CHAT,
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=False, port=SRV_PORT)
