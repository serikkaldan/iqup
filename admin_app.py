import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

admin_app = Flask(__name__)
admin_app.secret_key = os.getenv("SECRET_KEY", "iqup_admin_secret_2026")
admin_app.wsgi_app = ProxyFix(admin_app.wsgi_app, x_proto=1, x_host=1)

PRIMARY_DB_URL = os.getenv("PRIMARY_DB_URL")
STANDBY_DB_URL = os.getenv("STANDBY_DB_URL")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "iqup2026admin")


def query(sql, params=(), read=False, one=False, commit=False):
    dsn = STANDBY_DB_URL if (read and STANDBY_DB_URL) else PRIMARY_DB_URL
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            res = None
            if cur.description:
                res = cur.fetchone() if one else cur.fetchall()
            if commit:
                conn.commit()
            return res
    finally:
        conn.close()


@admin_app.get("/health")
def health():
    primary = query("SELECT pg_is_in_recovery() AS recovery", one=True)
    standby = query("SELECT pg_is_in_recovery() AS recovery", read=True, one=True)
    return jsonify({
        "status": "ok",
        "service": "admin_server",
        "primary_recovery": primary["recovery"],
        "standby_recovery": standby["recovery"],
    })


@admin_app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Админ панеліне сәтті кірдіңіз!", "success")
            return redirect(url_for("dashboard"))
        flash("Логин немесе құпиясөз қате!", "danger")
    return render_template("admin.html", login_mode=True)


@admin_app.get("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("login"))


@admin_app.get("/")
def dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    questions = query("SELECT * FROM questions ORDER BY stage, id", read=True)
    users = query("SELECT id, full_name, email, created_at FROM users ORDER BY created_at DESC", read=True)
    results = query("""
        SELECT r.id, u.full_name, u.email, r.stage, r.score, r.total, r.created_at
        FROM results r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC
    """, read=True)
    suggestions = query("""
        SELECT s.id, u.full_name, u.email, s.topic, s.message, s.created_at
        FROM suggestions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
    """, read=True)

    return render_template(
        "admin.html",
        login_mode=False,
        questions=questions,
        users=users,
        results=results,
        suggestions=suggestions
    )


@admin_app.post("/questions/add")
def add_question():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    stage = request.form.get("stage", type=int)
    stage_names = {
        1: "1-кезең: Жеңіл (Тест)",
        2: "2-кезең: Сынақ (Логика)",
        3: "3-кезең: Аралас",
        4: "4-кезең: Рас (Блиц)",
        5: "5-кезең: Қорытынды"
    }
    stage_name = stage_names.get(stage, f"{stage}-кезең")
    question_text = request.form.get("question_text", "").strip()
    option_a = request.form.get("option_a", "").strip()
    option_b = request.form.get("option_b", "").strip()
    option_c = request.form.get("option_c", "").strip()
    correct_answer = request.form.get("correct_answer", "").strip()
    hint = request.form.get("hint", "").strip()

    query("""
        INSERT INTO questions (stage, stage_name, question_text, option_a, option_b, option_c, correct_answer, hint)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (stage, stage_name, question_text, option_a, option_b, option_c, correct_answer, hint), commit=True)

    flash("Жаңа сұрақ сәтті қосылды!", "success")
    return redirect(url_for("dashboard"))


@admin_app.post("/questions/edit/<int:qid>")
def edit_question(qid):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    question_text = request.form.get("question_text", "").strip()
    option_a = request.form.get("option_a", "").strip()
    option_b = request.form.get("option_b", "").strip()
    option_c = request.form.get("option_c", "").strip()
    correct_answer = request.form.get("correct_answer", "").strip()
    hint = request.form.get("hint", "").strip()

    query("""
        UPDATE questions
        SET question_text=%s, option_a=%s, option_b=%s, option_c=%s, correct_answer=%s, hint=%s
        WHERE id=%s
    """, (question_text, option_a, option_b, option_c, correct_answer, hint, qid), commit=True)

    flash(f"#{qid} сұрақ сәтті жаңартылды!", "info")
    return redirect(url_for("dashboard"))


@admin_app.post("/questions/delete/<int:qid>")
def delete_question(qid):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    query("DELETE FROM questions WHERE id=%s", (qid,), commit=True)
    flash(f"#{qid} сұрақ өшірілді.", "warning")
    return redirect(url_for("dashboard"))