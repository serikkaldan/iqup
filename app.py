import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "iqup_secret_2026")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

PRIMARY_DB_URL = os.getenv("PRIMARY_DB_URL")
STANDBY_DB_URL = os.getenv("STANDBY_DB_URL")


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


def init_db():
    # Кестелерді құру (Primary базада)
    query("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(120) NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """, commit=True)

    query("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            stage INTEGER NOT NULL,
            stage_name VARCHAR(100) NOT NULL,
            question_text TEXT NOT NULL,
            option_a VARCHAR(255),
            option_b VARCHAR(255),
            option_c VARCHAR(255),
            correct_answer VARCHAR(255) NOT NULL,
            hint TEXT
        );
    """, commit=True)

    query("""
        CREATE TABLE IF NOT EXISTS results (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            stage INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """, commit=True)

    query("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            topic VARCHAR(150) NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """, commit=True)

    # Егер сұрақтар базасы бос болса, IQUP 22.01.pdf файлындағы сұрақтарды енгізу
    count_row = query("SELECT COUNT(*) AS cnt FROM questions", one=True)
    if count_row and count_row["cnt"] == 0:
        initial_questions = [
            # 1-КЕЗЕҢ: ЖЕҢІЛ
            (1, "1-кезең: Жеңіл (Тест)", "Тарихта қазақ балаларына арналған алғашқы мектепті кім ашты?", "Ыбырай Алтынсарин", "Жәңгір хан", "Ахмет Байтұрсынұлы", "Жәңгір хан", "1841 жылы Бөкей ордасында ашылған"),
            (1, "1-кезең: Жеңіл (Тест)", "Есімі 23 сөзден тұратын танымал суретші кім?", "Пабло Пикассо", "Микеланджело", "Сальвадор Дали", "Пабло Пикассо", "Толық есімі Пабло Диего Хосе..."),
            (1, "1-кезең: Жеңіл (Тест)", "Қазақстандағы ең биік нысан қайсы?", "Көктөбе телемұнарасы", "Екібастұз МАЭС-2 түтін мұржасы", "Абу Даби Плаза", "Екібастұз МАЭС-2 түтін мұржасы", "Биіктігі 419.7 метр"),
            (1, "1-кезең: Жеңіл (Тест)", "Тарихта ең ұзақ билік құрған империя:", "Моңғол империясы", "Наполеон империясы", "Осман империясы", "Осман империясы", "600 жылдан астам өмір сүрген"),
            (1, "1-кезең: Жеңіл (Тест)", "Моббинг дегеніміз не?", "Жұмыстан шығару мақсатында қызметкерге психологиялық қысым көрсету", "Адамның бойында үрейден арылғысы келуі", "Тырнақтың өсу процесінің ғылыми атауы", "Жұмыстан шығару мақсатында қызметкерге психологиялық қысым көрсету", "Ұжымдық психологиялық қысым"),
            (1, "1-кезең: Жеңіл (Тест)", "Боршын дегеніміз не?", "Аяқ киім", "Құс", "Мата атауы", "Құс", "Қазақтың көне құс атауы"),
            # 2-КЕЗЕҢ: СЫНАҚ (ИКС / БҮЙТІП)
            (2, "2-кезең: Сынақ (Логика)", "1886 жылы ИКС дәрілік сусын ретінде нарыққа шықты. Бүгінде ең танымал сусындардың бірі. ИКС-ті табыңыз:", "", "", "", "Кока-кола", "Бас ауруын басуға арналған сусын ретінде шыққан"),
            (2, "2-кезең: Сынақ (Логика)", "Рим императоры Калигула өзінің ИКС-і Инцитатусты сенатор етіп тағайындаған. ИКС деген не?", "", "", "", "Жылқысы", "Тұлпарға сарай мен қызметшілер берген"),
            (2, "2-кезең: Сынақ (Логика)", "1518 жылы Страсбург қаласында эпидемия басталып, адамдар күндер бойы тоқтамай БҮЙТТІ. Не істеді?", "", "", "", "Биледі", "Тарихта «Би эпидемиясы» деп аталады"),
            (2, "2-кезең: Сынақ (Логика)", "1932 жылы австралиялықтар бұл соғыста ИКС-терден жеңіліс тапты. Қай құстар?", "", "", "", "Эму", "Эму соғысы"),
            (2, "2-кезең: Сынақ (Логика)", "Еліміздің оңтүстігінде дауыл кезінде студент «Универдің аты затына сай боп тұр» деп әзілдеген. Қай университет?", "", "", "", "Қорқыт ата", "Қызылорда қаласындағы университет"),
            # 3-КЕЗЕҢ: АРАЛАС
            (3, "3-кезең: Аралас", "Жасырылған сөзді табыңыз: «Арым, міне, сүттей аппақ алдыма кеп жылап тұр, Жаутаңдаған жанарында жалғыз ғана ?????»", "", "", "", "Сұрақ тұр", "Мұқағали Мақатаев өлеңі"),
            (3, "3-кезең: Аралас", "«Абайдың қара сөздері» (соңғы 3 әріп алынады) + «Саз» ребусының жауабы (жалқы есім):", "", "", "", "Қарасаз", "Мұқағали Мақатаевтың туған ауылы"),
            (3, "3-кезең: Аралас", "Қазақ бүркіттің бес жасар кезін қалай атайды? (2018 ж. анимациялық фильм атауы)", "", "", "", "Мұзбалақ", "Тұрдыбек Майдан мен Тілек Төлеуғазы фильмі"),
            (3, "3-кезең: Аралас", "«Шәмші қайда? Шәмшіге айт, тағы да бір таңдандырсын...» өлең жолдары кімге арналған?", "", "", "", "Шәмілге", "Мұқағалидың досы Шәмілге жазған хаты"),
            # 4-КЕЗЕҢ: РАС (БӘС)
            (4, "4-кезең: Рас (Блиц)", "Қазақша білмейтін хатшы қыз бастыққа «Бір облыс орталығының шенеунігі келді» деп хабарлаған жазушы кім?", "", "", "", "Әкім Тарази", "Әкім + Тараз"),
            (4, "4-кезең: Рас (Блиц)", "Әмір Темір Үндістанға жорығы кезінде пілді әскерлерге қарсы нені пайдаланды?", "", "", "", "Өртке оранған түйелерді", "Түйелердің үстіне шөп артып өртеп жіберген"),
            (4, "4-кезең: Рас (Блиц)", "Қазақ тіліндегі «қолмен немесе таяқпен ұрып жіберу, соғу» етістігімен бірдей аталатын мемлекет:", "", "", "", "Перу", "Оңтүстік Америка мемлекеті"),
            (4, "4-кезең: Рас (Блиц)", "Олжалы аңшыдан кездескенде сұралатын дәстүрлі кәделі жол әрі ырым қалай аталады?", "", "", "", "Сыралғы", "Қазақтың аңшылық дәстүрі"),
        ]
        for q in initial_questions:
            query("""
                INSERT INTO questions (stage, stage_name, question_text, option_a, option_b, option_c, correct_answer, hint)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, q, commit=True)


with app.app_context():
    try:
        init_db()
    except Exception as e:
        print("DB init waiting:", e)


@app.get("/health")
def health():
    primary = query("SELECT pg_is_in_recovery() AS recovery", one=True)
    standby = query("SELECT pg_is_in_recovery() AS recovery", read=True, one=True)
    return jsonify({
        "status": "ok",
        "instance": os.getenv("HOSTNAME", "unknown"),
        "primary_recovery": primary["recovery"],
        "standby_recovery": standby["recovery"],
    })


@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        action = request.form.get("action")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if action == "register":
            full_name = request.form.get("full_name", "").strip()
            if not full_name or not email or not password:
                flash("Барлық өрістерді толтырыңыз!", "danger")
                return redirect(url_for("auth"))
            existing = query("SELECT id FROM users WHERE email = %s", (email,), read=True, one=True)
            if existing:
                flash("Бұл пошта бұрын тіркелген. Кіру бөлімін қолданыңыз.", "warning")
                return redirect(url_for("auth"))

            pw_hash = generate_password_hash(password)
            user = query(
                "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id, full_name, email",
                (full_name, email, pw_hash),
                one=True,
                commit=True
            )
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            flash("Тіркелу сәтті аяқталды! IQUP платформасына қош келдіңіз!", "success")
            return redirect(url_for("index"))

        elif action == "login":
            user = query("SELECT * FROM users WHERE email = %s", (email,), read=True, one=True)
            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                flash(f"Қош келдіңіз, {user['full_name']}!", "success")
                return redirect(url_for("index"))
            else:
                flash("Пошта немесе құпиясөз қате!", "danger")
                return redirect(url_for("auth"))

    return render_template("auth.html")


@app.get("/logout")
def logout():
    session.clear()
    flash("Сіз аккаунттан шықтыңыз.", "info")
    return redirect(url_for("auth"))


@app.get("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("auth"))

    selected_stage = request.args.get("stage", default=1, type=int)
    stages = query("SELECT DISTINCT stage, stage_name FROM questions ORDER BY stage", read=True)
    questions = query("SELECT * FROM questions WHERE stage = %s ORDER BY id", (selected_stage,), read=True)
    user_results = query("""
        SELECT r.*, COALESCE(q.stage_name, 'Кезең ' || r.stage) AS stage_name
        FROM results r
        LEFT JOIN (SELECT DISTINCT stage, stage_name FROM questions) q ON r.stage = q.stage
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """, (session["user_id"],), read=True)

    total_points = sum(r["score"] for r in user_results) if user_results else 0
    if total_points >= 15:
        rank = "Алаш зиялысы (Жоғары деңгей)"
    elif total_points >= 7:
        rank = "Алғыр зерттеуші (Орта деңгей)"
    else:
        rank = "Жас талапкер (Бастапқы деңгей)"

    return render_template(
        "index.html",
        stages=stages,
        questions=questions,
        selected_stage=selected_stage,
        user_results=user_results,
        total_points=total_points,
        rank=rank,
        instance=os.getenv("HOSTNAME", "web-node")
    )


@app.post("/submit-quiz")
def submit_quiz():
    if "user_id" not in session:
        return redirect(url_for("auth"))

    stage = request.form.get("stage", type=int)
    questions = query("SELECT * FROM questions WHERE stage = %s ORDER BY id", (stage,), read=True)
    score = 0
    total = len(questions)

    for q in questions:
        user_ans = request.form.get(f"q_{q['id']}", "").strip().lower()
        correct_ans = q["correct_answer"].strip().lower()
        if user_ans and (user_ans == correct_ans or correct_ans in user_ans):
            score += 1

    query(
        "INSERT INTO results (user_id, stage, score, total) VALUES (%s, %s, %s, %s)",
        (session["user_id"], stage, score, total),
        commit=True
    )
    flash(f"{stage}-кезең аяқталды! Сіздің нәтижеңіз: {score} / {total} ұпай.", "success")
    return redirect(url_for("index", stage=stage))


@app.post("/suggest")
def suggest():
    if "user_id" not in session:
        return redirect(url_for("auth"))

    topic = request.form.get("topic", "").strip()
    message = request.form.get("message", "").strip()
    if topic and message:
        query(
            "INSERT INTO suggestions (user_id, topic, message) VALUES (%s, %s, %s)",
            (session["user_id"], topic, message),
            commit=True
        )
        flash("Сұрақ авторларына ұсынысыңыз сәтті жіберілді! Рақмет!", "success")
    else:
        flash("Тақырып пен ұсыныс мәтінін толық жазыңыз.", "warning")
    return redirect(url_for("index"))