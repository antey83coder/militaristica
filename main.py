from fastapi import FastAPI, Form, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse
from datetime import datetime, timedelta
import os
import shutil
import json
from typing import List
import databases
import sqlalchemy
import uuid
import urllib.request
import urllib.parse
import hashlib
import jwt
import base64
import asyncio
import calendar
from contextlib import asynccontextmanager

# ================= НАЛАШТУВАННЯ ================= #
IMGBB_API_KEY = "0622c07513943192add7076ce8eb167e"
MONO_TOKEN = os.getenv("MONO_TOKEN", "ТУТ_ВСТАВТЕ_ВАШ_MONOBANK_TOKEN")

for folder in ["uploads", "goods_types", "sn_logos", "forses_logos"]:
    os.makedirs(folder, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./militaristica.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# --- КРИПТОГРАФІЯ ---
SECRET_KEY = "militaristica_secret_ua_2026"
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000).hex()
    return f"{salt}${pwd_hash}"

def verify_password(stored_password: str, provided_password: str) -> bool:
    try:
        salt, pwd_hash = stored_password.split('$')
        check_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), bytes.fromhex(salt), 100000).hex()
        return pwd_hash == check_hash
    except Exception:
        return False

def create_access_token(user_id: int):
    expire = datetime.utcnow() + timedelta(days=7)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Не авторизовано (відсутній токен)")
    token = auth.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Токен недійсний або прострочений")

# --- АВТОМАТИЧНИЙ РОЗРАХУНОК ПРОГНОЗУ ВІЙНИ ---
def update_war_forecast_file():
    now = datetime.now()
    current_year = now.year
    
    total_days = 366 if calendar.isleap(current_year) else 365
    day_of_year = now.timetuple().tm_yday
    days_remaining = max(1, total_days - day_of_year)
    time_factor = days_remaining / total_days

    forecasts = {}
    
    for i in range(3):
        y = str(current_year + i)
        if i == 0:
            r_max = max(1.0, 14.0 * time_factor)
            r_part = max(2.0, 24.0 * time_factor)
            frozen = max(5.0, 52.0 * time_factor)
            borders = max(0.5, 10.0 * time_factor)
        elif i == 1:
            r_max = 16.50
            r_part = 28.50
            frozen = 45.00
            borders = 10.00
        else:
            r_max = 12.00
            r_part = 21.00
            frozen = 54.00
            borders = 13.00
            
        total = r_max + r_part + frozen + borders
        forecasts[y] = {
            "russia_max": round((r_max / total) * 100, 2),
            "russia_partial": round((r_part / total) * 100, 2),
            "frozen": round((frozen / total) * 100, 2),
            "borders_1991": round((borders / total) * 100, 2)
        }

    data = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        "forecasts": forecasts
    }
    
    try:
        with open("war_forecast_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Помилка запису war_forecast_data.json:", e)

# --- НАДІЙНА ФУНКЦІЯ ЗАВАНТАЖЕННЯ НА IMGBB (Асинхронна) ---
async def upload_to_imgbb(file: UploadFile) -> str:
    try:
        file_content = await file.read()
        if not file_content:
            return ""
        
        base64_image = base64.b64encode(file_content).decode('utf-8')
        payload = urllib.parse.urlencode({
            "key": IMGBB_API_KEY,
            "image": base64_image
        }).encode('utf-8')
        
        req = urllib.request.Request(
            "https://api.imgbb.com/1/upload", 
            data=payload, 
            headers={"Content-Type": "application/x-www-form-urlencoded"}, 
            method="POST"
        )
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, urllib.request.urlopen, req)
        
        result = json.loads(response.read().decode('utf-8'))
        return result.get("data", {}).get("url", "")
            
    except Exception as e:
        print(f"Помилка завантаження на ImgBB: {e}")
        return ""

# ================= ТАБЛИЦІ БАЗИ ДАНИХ ================= #

ranks = sqlalchemy.Table(
    "ranks", metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("name", sqlalchemy.String(50), unique=True, nullable=False),
    sqlalchemy.Column("min_activity", sqlalchemy.Numeric(12, 2), nullable=False),
    sqlalchemy.Column("max_activity", sqlalchemy.Numeric(12, 2), nullable=False),
    sqlalchemy.Column("commission_rate", sqlalchemy.Numeric(5, 4), nullable=False),
)

products = sqlalchemy.Table(
    "products", metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("title", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("categories", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("price", sqlalchemy.Numeric(10, 2), nullable=False),
    sqlalchemy.Column("stock", sqlalchemy.Integer, default=1),
    sqlalchemy.Column("sku", sqlalchemy.String, unique=True, nullable=False),
    sqlalchemy.Column("description", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("image_urls", sqlalchemy.Text, default=""),
    sqlalchemy.Column("owner_id", sqlalchemy.Integer, default=0),
    sqlalchemy.Column("characteristics", sqlalchemy.Text, default="[]"),
    sqlalchemy.Column("keywords", sqlalchemy.String, default=""),
    sqlalchemy.Column("phone", sqlalchemy.String, default=""),
    sqlalchemy.Column("city", sqlalchemy.String, default=""),
    sqlalchemy.Column("condition", sqlalchemy.String, default="Нове"),
    sqlalchemy.Column("seller_name", sqlalchemy.String, default=""),
    sqlalchemy.Column("delivery_mode", sqlalchemy.String, default="самовивіз"),
    sqlalchemy.Column("delivery_details", sqlalchemy.String, default=""),
)

orders = sqlalchemy.Table(
    "orders", metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("customer_name", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("phone", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("delivery_info", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("items_json", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("total_price", sqlalchemy.Numeric(10, 2), nullable=False),
    sqlalchemy.Column("status", sqlalchemy.String, default="Нове"),
    sqlalchemy.Column("payment_status", sqlalchemy.String, default="Очікує оплати"),
    sqlalchemy.Column("created_at", sqlalchemy.String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M")),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, default=0),
    sqlalchemy.Column("commission", sqlalchemy.Numeric(10, 2), default=0.00),
    sqlalchemy.Column("seller_payout", sqlalchemy.Numeric(10, 2), default=0.00),
)

users = sqlalchemy.Table(
    "users", metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("email", sqlalchemy.String, unique=True, nullable=False),
    sqlalchemy.Column("password", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("rank", sqlalchemy.String, default="Рекрут"),
    sqlalchemy.Column("total_activity", sqlalchemy.Numeric(12, 2), default=0.00),
    sqlalchemy.Column("discount", sqlalchemy.Integer, default=0),
    sqlalchemy.Column("role", sqlalchemy.String, default="user"),
    sqlalchemy.Column("avatar_url", sqlalchemy.String, default=""),
    sqlalchemy.Column("created_at", sqlalchemy.String, default=lambda: datetime.now().strftime("%Y-%m-%d")),
    sqlalchemy.Column("admin_password", sqlalchemy.String, default=""),
    sqlalchemy.Column("verify_token", sqlalchemy.String, default=""),
    sqlalchemy.Column("telegram_chat_id", sqlalchemy.String, default=""),
)

media = sqlalchemy.Table(
    "media", metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("file_url", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("media_type", sqlalchemy.String, default="photostrip"),
    sqlalchemy.Column("media_format", sqlalchemy.String, default="image"),
    sqlalchemy.Column("product_id", sqlalchemy.Integer, default=0),
)

if "sqlite" in DATABASE_URL:
    engine = sqlalchemy.create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = sqlalchemy.create_engine(DATABASE_URL)

metadata.create_all(engine)

# --- ЖИТТЄВИЙ ЦИКЛ FastAPI ТА ІНІЦІАЛІЗАЦІЯ ЗВАНЬ ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    try:
        update_war_forecast_file()
    except Exception as e:
        print("Помилка автооновлення прогнозу при старті:", e)

    try: 
        await database.execute("ALTER TABLE users ADD COLUMN telegram_chat_id TEXT DEFAULT ''")
    except Exception: 
        pass
    try: 
        await database.execute("ALTER TABLE users ADD COLUMN total_activity NUMERIC(12,2) DEFAULT 0.00")
    except Exception: 
        pass
    try: 
        await database.execute("ALTER TABLE orders ADD COLUMN commission NUMERIC(10,2) DEFAULT 0.00")
        await database.execute("ALTER TABLE orders ADD COLUMN seller_payout NUMERIC(10,2) DEFAULT 0.00")
    except Exception: 
        pass

    # Заповнюємо початкові звання ЗСУ та комісії, якщо таблиця порожня
    existing_rank = await database.fetch_one(ranks.select())
    if not existing_rank:
        default_ranks = [
            ("Рекрут", 0, 5000, 0.0500),
            ("Солдат", 5001, 10000, 0.0450),
            ("Сержант", 10001, 20000, 0.0400),
            ("Лейтенант", 20001, 35000, 0.0350),
            ("Капітан", 35001, 50000, 0.0300),
            ("Майор", 50001, 75000, 0.0250),
            ("Полковник", 75001, 100000, 0.0200),
            ("Генерал", 100001, 300000, 0.0100),
            ("Маршал", 300001, 1000000, 0.0010),
        ]
        for name, min_a, max_a, rate in default_ranks:
            await database.execute(ranks.insert().values(
                name=name, min_activity=min_a, max_activity=max_a, commission_rate=rate
            ))

    yield
    await database.disconnect()

app = FastAPI(title="Militaristica API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

CATEGORY_PREFIXES = {
    "mil_goods": "MIL", "sport_goods": "SPT", "tour_goods": "TUR",
    "work_goods": "WRK", "trans_goods": "TRS", "drone_goods": "DRN",
    "com_goods": "COM", "2hetd_goods": "SEC"
}

# Ручне оновлення прогнозу за запитом
@app.get("/api/update-forecast-manual")
async def manual_update_forecast():
    update_war_forecast_file()
    return {"status": "success", "message": "Прогноз успішно перераховано та оновлено!"}

# --- ЛОГІКА ОНОВЛЕННЯ АКТИВНОСТІ ТА ЗВАННЯ ---
async def process_user_activity(user_id: int, amount: float):
    user = await database.fetch_one(users.select().where(users.c.id == user_id))
    if not user:
        return
    
    current_act = float(user["total_activity"] or 0)
    new_activity = current_act + amount
    
    all_ranks = await database.fetch_all(ranks.select())
    matched_rank_name = "Рекрут"
    commission_rate = 0.0500
    
    for r in all_ranks:
        if float(r["min_activity"]) <= new_activity <= float(r["max_activity"]):
            matched_rank_name = r["name"]
            commission_rate = float(r["commission_rate"])
            break
            
    if new_activity > 1000000:
        matched_rank_name = "Маршал"
        commission_rate = 0.0010

    await database.execute(
        users.update().where(users.c.id == user_id).values(
            total_activity=new_activity, rank=matched_rank_name
        )
    )
    return matched_rank_name, commission_rate

# ================= АВТОРИЗАЦІЯ ТА КОРИСТУВАЧІ ================= #
@app.post("/api/auth/register")
async def register_user(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if await database.fetch_one(users.select().where(users.c.email == email)):
        raise HTTPException(status_code=400, detail="Email вже існує!")
    
    hashed_pwd = hash_password(password)
    user_id = await database.execute(users.insert().values(
        name=name, email=email, password=hashed_pwd, rank="Рекрут", total_activity=0.00, discount=0, role="user", avatar_url=""
    ))
    return {"status": "success", "id": user_id, "user_id": user_id, "name": name, "telegram_chat_id": ""}

@app.post("/api/auth/login")
async def login_user(email: str = Form(...), password: str = Form(...)):
    user = await database.fetch_one(users.select().where(users.c.email == email))
    if not user: raise HTTPException(status_code=400, detail="Невірний Email або пароль!")
    
    user_dict = dict(user)
    if not verify_password(user_dict["password"], password):
        raise HTTPException(status_code=400, detail="Невірний Email або пароль!")

    access_token = create_access_token(user_dict["id"])

    return {
        "status": "success", "id": user_dict["id"], "user_id": user_dict["id"], "name": user_dict["name"], 
        "role": user_dict["role"], "avatar_url": user_dict["avatar_url"], "telegram_chat_id": user_dict.get("telegram_chat_id", ""),
        "access_token": access_token
    }

@app.post("/api/auth/admin_login")
async def admin_login(email: str = Form(...), admin_password: str = Form(...)):
    user = await database.fetch_one(users.select().where(users.c.email == email).where(users.c.admin_password == admin_password))
    if not user: raise HTTPException(status_code=400, detail="Невірний Email або пароль адмінки!")
    user_dict = dict(user)
    if user_dict["role"] not in ["admin", "seller"]: raise HTTPException(status_code=403, detail="Немає доступу!")
    
    access_token = create_access_token(user_dict["id"])
    return {
        "status": "success", "id": user_dict["id"], "user_id": user_dict["id"], "name": user_dict["name"], 
        "role": user_dict["role"], "avatar_url": user_dict["avatar_url"], "telegram_chat_id": user_dict.get("telegram_chat_id", ""),
        "access_token": access_token
    }

@app.post("/api/users/change-password")
async def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    current_user_id: int = Depends(verify_token)
):
    user = await database.fetch_one(users.select().where(users.c.id == current_user_id))
    if not user: raise HTTPException(status_code=404, detail="Користувача не знайдено.")

    user_dict = dict(user)
    if not verify_password(user_dict["password"], old_password):
        raise HTTPException(status_code=400, detail="Старий пароль введено невірно!")

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Новий пароль має бути не менше 6 символів!")

    new_hash = hash_password(new_password)
    await database.execute(users.update().where(users.c.id == current_user_id).values(password=new_hash))
    return {"status": "success", "message": "Пароль успішно змінено!"}

@app.post("/api/auth/forgot-password")
async def forgot_password(email: str = Form(...)):
    user = await database.fetch_one(users.select().where(users.c.email == email))
    if not user:
        return {"status": "success", "message": "Якщо такий email існує, інструкції відправлено."}

    user_dict = dict(user)
    reset_token = str(uuid.uuid4())
    await database.execute(users.update().where(users.c.id == user_dict["id"]).values(verify_token=reset_token))

    reset_link = f"https://militaristica.onrender.com/reset_password.html?token={reset_token}"
    GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwFKRRRJQtpdXDpBGiilLEA1nd84wjXMAlaPNYI_aw3HD3oR7jDevm7O2fzgjBsVPjJxw/exec"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; background: #1a1e18; color: #ffffff; padding: 20px; border-radius: 8px;">
        <h2 style="color: #4CAF50;">Скидання пароля — Militaristica</h2>
        <p>Привіт, {user_dict['name']}!</p>
        <p>Ми отримали запит на відновлення пароля для вашого облікового запису.</p>
        <br>
        <a href="{reset_link}" style="background-color: #a33333; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Встановити новий пароль</a>
        <br><br>
        <p style="color: #888; font-size: 13px;">Якщо ви не робили цього запиту, просто проігноруйте цей лист.</p>
    </div>
    """
    data = {"to": user_dict["email"], "subject": "Відновлення пароля на сайті Militaristica", "htmlContent": html_content}

    try:
        req = urllib.request.Request(GOOGLE_SCRIPT_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req)
    except Exception as e:
        print("Помилка відправки Email:", e)

    return {"status": "success", "message": "Лист для відновлення надіслано на вашу пошту!"}

@app.post("/api/auth/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    if not token or len(token) < 10: raise HTTPException(status_code=400, detail="Недійсний токен.")
    user = await database.fetch_one(users.select().where(users.c.verify_token == token))
    if not user: raise HTTPException(status_code=400, detail="Посилання недійсне або прострочене.")
    if len(new_password) < 6: raise HTTPException(status_code=400, detail="Пароль має містити щонайменше 6 символів.")
    
    new_hash = hash_password(new_password)
    await database.execute(users.update().where(users.c.id == user["id"]).values(password=new_hash, verify_token=""))
    return {"status": "success", "message": "Пароль успішно змінено. Тепер ви можете увійти!"}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, current_user_id: int = Depends(verify_token)):
    admin = await database.fetch_one(users.select().where(users.c.id == current_user_id))
    if not admin or admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Тільки адміністратор може видаляти користувачів.")
    
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Ви не можете видалити власний акаунт.")

    await database.execute(users.delete().where(users.c.id == user_id))
    return {"status": "success"}

@app.get("/api/users")
async def get_all_users():
    all_users = await database.fetch_all(users.select().order_by(users.c.id.desc()))
    return [dict(u) for u in all_users]

@app.post("/api/users/update/{user_id}")
async def update_user_rank(user_id: int, rank: str = Form(...), discount: int = Form(...), role: str = Form(...)):
    await database.execute(users.update().where(users.c.id == user_id).values(rank=rank, discount=discount, role=role))
    return {"status": "success"}

@app.post("/api/users/profile/{user_id}")
async def update_my_profile(
    user_id: int, name: str = Form(...), email: str = Form(...), 
    avatar_url: str = Form(""), telegram_chat_id: str = Form(""),
    current_user_id: int = Depends(verify_token)
):
    if user_id != current_user_id: raise HTTPException(status_code=403, detail="Доступ заборонено!")
    await database.execute(users.update().where(users.c.id == user_id).values(
        name=name, email=email, avatar_url=avatar_url, telegram_chat_id=telegram_chat_id
    ))
    return {"status": "success"}

@app.post("/api/users/become-seller/{user_id}")
async def become_seller(user_id: int):
    user = await database.fetch_one(users.select().where(users.c.id == user_id))
    if not user: raise HTTPException(status_code=404, detail="Користувача не знайдено.")
    
    token = str(uuid.uuid4())
    await database.execute(users.update().where(users.c.id == user_id).values(verify_token=token))
    
    verify_link = f"https://militaristica.onrender.com/api/users/confirm-seller/{token}"
    GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwFKRRRJQtpdXDpBGiilLEA1nd84wjXMAlaPNYI_aw3HD3oR7jDevm7O2fzgjBsVPjJxw/exec"
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
        <h2 style="color: #4CAF50;">Вітаємо, {user['name']}!</h2>
        <p>Щоб активувати панель продавця на <b>Militaristica</b>, підтвердіть свою пошту.</p>
        <br>
        <a href="{verify_link}" style="background-color: #a33333; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">Підтвердити статус продавця</a>
        <br><br><br>
        <p>Слава Україні!</p>
    </div>
    """
    data = {"to": user["email"], "subject": "Підтвердження статусу продавця — Militaristica", "htmlContent": html_content}
    
    try:
        req = urllib.request.Request(GOOGLE_SCRIPT_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req)
    except Exception as e: 
        print("Помилка Google API:", e)
        
    return {"status": "email_sent"}

@app.get("/api/users/confirm-seller/{token}", response_class=HTMLResponse)
async def confirm_seller(token: str):
    user = await database.fetch_one(users.select().where(users.c.verify_token == token))
    if not user: return "<h1>Помилка</h1><p>Недійсне посилання.</p>"
    await database.execute(users.update().where(users.c.id == user["id"]).values(role="seller", verify_token=""))
    return """
    <html><head><meta charset="utf-8"><title>Успіх!</title><style>body{background:#1a1e18; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;}</style></head>
    <body><h1 style="color:#98c379;">✅ Пошту успішно підтверджено!</h1>
    <a href="/admin_dashboard.html" style="background:#a33333; color:#fff; padding:15px 30px; text-decoration:none; border-radius:6px; font-weight:bold;">Перейти в Панель</a>
    <script>let u = JSON.parse(localStorage.getItem('militaristica_user')); if(u){u.role = 'seller'; localStorage.setItem('militaristica_user', JSON.stringify(u));}</script></body></html>
    """

# ================= ТОВАРИ ================= #
@app.post("/api/products/add")
async def add_product(
    title: str = Form("Без назви"), categories: str = Form(""), price: float = Form(0.0), stock: int = Form(1),
    description: str = Form(""), characteristics: str = Form("[]"), keywords: str = Form(""),
    owner_id: int = Form(0), phone: str = Form(""), city: str = Form(""), condition: str = Form("Нове"),
    seller_name: str = Form(""), delivery_mode: str = Form("самовивіз"), delivery_details: str = Form(""),
    files: List[UploadFile] = File(default=[]), current_user_id: int = Depends(verify_token)
):
    if owner_id != current_user_id: raise HTTPException(status_code=403, detail="Токен не збігається з ID власника.")
    user = await database.fetch_one(users.select().where(users.c.id == owner_id))
    user_role = str(user["role"]).strip().lower() if user and user["role"] else ""
    if not user or user_role not in ["admin", "seller"]: raise HTTPException(status_code=403, detail="Недостатньо прав.")

    selected_cats = [c.strip() for c in categories.split(",") if c.strip()]
    main_prefix = CATEGORY_PREFIXES.get(selected_cats[0], "GEN") if selected_cats else "GEN"
    current_count = await database.fetch_val(sqlalchemy.select(sqlalchemy.func.count()).select_from(products).where(products.c.sku.like(f"{main_prefix}-%"))) or 0
    auto_sku = f"{main_prefix}-{current_count + 1:04d}"

    saved_images = []
    for f in files:
        if f.filename:
            url = await upload_to_imgbb(f)
            if url: 
                saved_images.append(url)

    await database.execute(products.insert().values(
        title=title, categories=",".join(selected_cats), price=price, stock=stock, sku=auto_sku,
        description=description, characteristics=characteristics, image_urls=",".join(saved_images),
        keywords=keywords, owner_id=owner_id, phone=phone, city=city, condition=condition, 
        seller_name=seller_name, delivery_mode=delivery_mode, delivery_details=delivery_details
    ))
    return {"status": "success"}

@app.post("/api/products/update/{product_id}")
async def update_product(
    product_id: int, requester_id: int = Form(0), title: str = Form("Без назви"), categories: str = Form(""), 
    price: float = Form(0.0), stock: int = Form(1), description: str = Form(""), characteristics: str = Form("[]"), 
    keywords: str = Form(""), phone: str = Form(""), city: str = Form(""), condition: str = Form("Нове"), 
    seller_name: str = Form(""), delivery_mode: str = Form("самовивіз"), delivery_details: str = Form(""),
    existing_images: str = Form(""), files: List[UploadFile] = File(default=[]) 
):
    prod = await database.fetch_one(products.select().where(products.c.id == product_id))
    if not prod: raise HTTPException(status_code=404, detail="Товар не знайдено.")
    user = await database.fetch_one(users.select().where(users.c.id == requester_id))
    if not user or (user["role"] != "admin" and prod["owner_id"] != requester_id): raise HTTPException(status_code=403, detail="Ви можете редагувати лише власні товари.")

    final_images = [img.strip() for img in existing_images.split(",") if img.strip()]
    if files and len(files) > 0 and files[0].filename:
        for f in files:
            if f.filename:
                url = await upload_to_imgbb(f)
                if url: final_images.append(url)

    await database.execute(products.update().where(products.c.id == product_id).values(
        title=title, categories=",".join([c.strip() for c in categories.split(",") if c.strip()]),
        price=price, stock=stock, description=description, characteristics=characteristics,
        image_urls=",".join(final_images), keywords=keywords, phone=phone, city=city, 
        condition=condition, seller_name=seller_name, delivery_mode=delivery_mode, delivery_details=delivery_details
    ))
    return {"status": "success"}

@app.delete("/api/products/{product_id}")
async def delete_product(product_id: int, requester_id: int, current_user_id: int = Depends(verify_token)):
    if requester_id != current_user_id: raise HTTPException(status_code=403, detail="Невірний токен.")
    prod = await database.fetch_one(products.select().where(products.c.id == product_id))
    user = await database.fetch_one(users.select().where(users.c.id == requester_id))
    if not user or (user["role"] != "admin" and prod["owner_id"] != requester_id): raise HTTPException(status_code=403, detail="Немає прав.")
    await database.execute(products.delete().where(products.c.id == product_id))
    return {"status": "success"}

@app.get("/api/products")
async def get_products(): 
    all_prods = await database.fetch_all(products.select().order_by(products.c.id.desc()))
    return [dict(p) for p in all_prods]

@app.get("/api/products/seller/{owner_id}")
async def get_seller_products(owner_id: int):
    seller_prods = await database.fetch_all(products.select().where(products.c.owner_id == owner_id).order_by(products.c.id.desc()))
    return [dict(p) for p in seller_prods]

@app.get("/api/products/{product_id}")
async def get_product(product_id: int): 
    prod = await database.fetch_one(products.select().where(products.c.id == product_id))
    return dict(prod) if prod else None

# ================= ЗАМОВЛЕННЯ ТА MONOBANK ================= #
@app.post("/api/orders/add")
async def create_order(
    customer_name: str = Form(...), phone: str = Form(...), delivery_info: str = Form(...),
    items_json: str = Form(...), total_price: float = Form(...), user_id: int = Form(0)
):
    try: items = json.loads(items_json)
    except Exception: raise HTTPException(status_code=400, detail="Помилка кошика.")

    for item in items:
        if item.get("id"):
            prod = await database.fetch_one(products.select().where(products.c.id == int(item["id"])))
            if not prod or prod["stock"] < int(item.get("quantity", 1)):
                raise HTTPException(status_code=400, detail="Недостатньо товару на складі.")

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    order_id = await database.execute(orders.insert().values(
        customer_name=customer_name, phone=phone, delivery_info=delivery_info,
        items_json=items_json, total_price=total_price, user_id=user_id, created_at=current_time,
        payment_status="Очікує оплати"
    ))
    
    seller_notifications = {}
    for item in items:
        if item.get("id"):
            prod = await database.fetch_one(products.select().where(products.c.id == int(item["id"])))
            if prod:
                qty = int(item.get("quantity", 1))
                await database.execute(products.update().where(products.c.id == prod["id"]).values(stock=prod["stock"] - qty))
                owner_id = prod["owner_id"]
                if owner_id not in seller_notifications: seller_notifications[owner_id] = []
                seller_notifications[owner_id].append({"title": prod["title"], "sku": prod["sku"], "qty": qty, "price": float(prod["price"])})

    GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwFKRRRJQtpdXDpBGiilLEA1nd84wjXMAlaPNYI_aw3HD3oR7jDevm7O2fzgjBsVPjJxw/exec"
    BOT_TOKEN = "8864557863:AAHohPKpi4Utypaepej0vtmOdenoYq0b1NE"
    
    for owner_id, prods in seller_notifications.items():
        if owner_id == 0: continue
        seller = await database.fetch_one(users.select().where(users.c.id == owner_id))
        if not seller: continue
        
        seller_dict = dict(seller)
        total_sum = sum([p['price'] * p['qty'] for p in prods])
        
        if seller_dict["email"]:
            try:
                items_html = "".join([f"<li>[{p['sku']}] <b>{p['title']}</b> (x{p['qty']}) — {p['price'] * p['qty']} ₴</li>" for p in prods])
                mail_html = f"<h3>Вітаємо, {seller_dict['name']}!</h3><p>У вас нове замовлення <b>№{order_id}</b>!</p><p><b>Покупець:</b> {customer_name}<br><b>Телефон:</b> {phone}<br><b>Доставка:</b> {delivery_info}</p><h4>Товари:</h4><ul>{items_html}</ul><p><b style='color:red;'>До оплати: {total_sum} ₴</b></p>"
                
                data = {"to": seller_dict["email"], "subject": f"Нове замовлення №{order_id}", "htmlContent": mail_html}
                req = urllib.request.Request(GOOGLE_SCRIPT_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req)
            except Exception as e: 
                print("Помилка Google API Email:", e)
        
        if seller_dict.get("telegram_chat_id"):
            try:
                items_text_tg = "\n".join([f"🔹 {p['title']} (x{p['qty']}) — {p['price'] * p['qty']} ₴" for p in prods])
                tg_text = f"🚨 *НОВЕ ЗАМОВЛЕННЯ №{order_id}* 🚨\n\n👤 *Покупець:* {customer_name}\n📞 *Телефон:* {phone}\n📍 *Доставка:* {delivery_info}\n\n📦 *Товари:*\n{items_text_tg}\n\n💰 *До оплати:* {total_sum} ₴"
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                data = urllib.parse.urlencode({"chat_id": seller_dict["telegram_chat_id"], "text": tg_text, "parse_mode": "Markdown"}).encode('utf-8')
                urllib.request.urlopen(urllib.request.Request(url, data=data))
            except Exception as e: 
                print("Помилка Telegram:", e)

    return {"status": "success", "order_id": order_id}

@app.post("/api/orders/{order_id}/create-invoice")
async def create_monobank_invoice(order_id: int):
    order = await database.fetch_one(orders.select().where(orders.c.id == order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Замовлення не знайдено.")
        
    amount = float(order["total_price"])
    amount_in_kopecks = int(amount * 100)
    
    payload = {
        "amount": amount_in_kopecks,
        "ccy": 980,
        "merchantPaymInfo": {
            "reference": str(order_id),
            "destination": f"Order #{order_id} payment on Militaristica"
        },
        "webHookUrl": "https://militaristica.onrender.com/api/webhook/monobank"
    }
    
    safe_token = MONO_TOKEN.strip().encode("ascii", "ignore").decode("ascii")
    
    headers = {
        "X-Token": safe_token,
        "Content-Type": "application/json; charset=utf-8"
    }
    
    json_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    
    req = urllib.request.Request(
        "https://api.monobank.ua/api/merchant/invoice/create",
        data=json_data,
        headers=headers,
        method="POST"
    )
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req))
        res_data = json.loads(response.read().decode("utf-8"))
        return {"status": "success", "invoiceId": res_data.get("invoiceId"), "pageUrl": res_data.get("pageUrl")}
    except Exception as e:
        print("Помилка створення інвойсу Monobank:", e)
        raise HTTPException(status_code=400, detail=f"Не вдалося створити платіж: {str(e)}")

@app.post("/api/webhook/monobank")
async def monobank_webhook(request: Request):
    try:
        data = await request.json()
        if data.get("status") == "success":
            reference = data.get("merchantPaymInfo", {}).get("reference")
            paid_amount = float(data.get("amount", 0)) / 100.0
            
            if reference:
                order = await database.fetch_one(orders.select().where(orders.c.id == int(reference)))
                if order and order["payment_status"] != "Оплачено":
                    await database.execute(
                        orders.update().where(orders.c.id == int(reference)).values(
                            payment_status="Оплачено", status="Підтверджено"
                        )
                    )
                    
                    buyer_id = order["user_id"]
                    if buyer_id:
                        await process_user_activity(buyer_id, paid_amount)
                        
                    try:
                        items = json.loads(order["items_json"])
                        for item in items:
                            prod_id = item.get("id")
                            if prod_id:
                                prod = await database.fetch_one(products.select().where(products.c.id == int(prod_id)))
                                if prod and prod["owner_id"]:
                                    seller_id = prod["owner_id"]
                                    item_sum = float(prod["price"]) * int(item.get("quantity", 1))
                                    await process_user_activity(seller_id, item_sum)
                    except Exception as ex:
                        print("Помилка нарахування активності продавцям:", ex)
                        
    except Exception as e:
        print("Помилка Monobank webhook:", e)
        
    return {"status": "ok"}

@app.get("/api/orders")
async def get_orders(): 
    all_orders = await database.fetch_all(orders.select().order_by(orders.c.id.desc()))
    return [dict(o) for o in all_orders]

@app.get("/api/orders/user/{user_id}")
async def get_user_purchases(user_id: int):
    buyer_orders = await database.fetch_all(orders.select().where(orders.c.user_id == user_id).order_by(orders.c.id.desc()))
    return [dict(o) for o in buyer_orders]

@app.get("/api/orders/seller/{owner_id}")
async def get_seller_orders(owner_id: int):
    seller_prods = await database.fetch_all(products.select().where(products.c.owner_id == owner_id))
    seller_prod_ids = [p["id"] for p in seller_prods]
    all_orders = await database.fetch_all(orders.select().order_by(orders.c.id.desc()))
    filtered_orders = []
    for o in all_orders:
        try:
            items = json.loads(o["items_json"]) 
            if any(int(item.get("id", 0)) in seller_prod_ids for item in items): filtered_orders.append(dict(o)) 
        except Exception: pass
    return filtered_orders

@app.post("/api/orders/status/{order_id}")
async def update_order_status(order_id: int, status: str = Form(...), current_user_id: int = Depends(verify_token)):
    await database.execute(orders.update().where(orders.c.id == order_id).values(status=status))
    return {"status": "success"}

@app.post("/api/orders/payment-status/{order_id}")
async def update_payment_status(order_id: int, payment_status: str = Form(...), current_user_id: int = Depends(verify_token)):
    await database.execute(orders.update().where(orders.c.id == order_id).values(payment_status=payment_status))
    return {"status": "success"}

# ================= МЕДІА ================= #
@app.get("/api/media")
async def get_media(): 
    all_media = await database.fetch_all(media.select().order_by(media.c.id.desc()))
    return [dict(m) for m in all_media]

@app.post("/api/media/upload")
async def upload_media(requester_id: int = Form(...), product_id: int = Form(0), files: List[UploadFile] = File(...)):
    user = await database.fetch_one(users.select().where(users.c.id == requester_id))
    if not user or user["role"] != "admin": raise HTTPException(status_code=403, detail="Лише адміністратор.")
    for f in files:
        if f.filename:
            url = await upload_to_imgbb(f)
            if url: await database.execute(media.insert().values(file_url=url, media_type="photostrip", media_format="image", product_id=product_id))
    return {"status": "success"}

@app.delete("/api/media/{media_id}")
async def delete_media(media_id: int, requester_id: int):
    user = await database.fetch_one(users.select().where(users.c.id == requester_id))
    if not user or user["role"] != "admin": raise HTTPException(status_code=403, detail="Лише адміністратор.")
    await database.execute(media.delete().where(media.c.id == media_id))
    return {"status": "success"}

# ================= OPEN GRAPH ТА СТАТИКА ================= #
@app.get("/robots.txt", response_class=PlainTextResponse)
async def get_robots():
    return "User-agent: *\nAllow: /\nUser-agent: facebookexternalhit\nAllow: /\nUser-agent: Facebot\nAllow: /"

@app.get("/product.html", response_class=HTMLResponse)
async def serve_product_page_with_og(id: int = 0):
    try:
        with open("product.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        return HTMLResponse("Помилка: файл product.html не знайдено", status_code=404)

    if not id: return HTMLResponse(content=html_content)

    prod = await database.fetch_one(products.select().where(products.c.id == id))
    if not prod: return HTMLResponse(content=html_content)

    prod_dict = dict(prod)
    image_urls = prod_dict.get("image_urls", "")
    first_image = image_urls.split(",")[0] if image_urls else "logo.png"
    BASE_URL = "https://militaristica.onrender.com"
    
    if not first_image.startswith("http"):
        clean_img = first_image.lstrip("/")
        full_image_url = f"{BASE_URL}/{clean_img}"
    else:
        full_image_url = first_image

    title = f"{prod_dict['title']} — Militaristica"
    price = f"{prod_dict['price']} грн"
    desc_raw = prod_dict.get('description', '')
    description = f"Ціна: {price}. {desc_raw[:150]}..."
    
    safe_title = title.replace('"', '&quot;').replace("'", '&#39;')
    safe_desc = description.replace('"', '&quot;').replace("'", '&#39;')
    canonical_url = f"{BASE_URL}/product.html?id={id}"

    og_tags = f"""
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="product" />
    <meta property="og:site_name" content="Militaristica" />
    <meta property="og:title" content="{safe_title}" />
    <meta property="og:description" content="{safe_desc}" />
    <meta property="og:image" content="{full_image_url}" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:url" content="{canonical_url}" />
    """

    if "<!-- OG_META_TAGS -->" in html_content:
        rendered_html = html_content.replace("<!-- OG_META_TAGS -->", og_tags)
    elif "</head>" in html_content:
        rendered_html = html_content.replace("</head>", f"{og_tags}\n</head>")
    else:
        rendered_html = html_content

    return HTMLResponse(content=rendered_html)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/goods_types", StaticFiles(directory="goods_types"), name="goods_types")
app.mount("/sn_logos", StaticFiles(directory="sn_logos"), name="sn_logos")
app.mount("/forses_logos", StaticFiles(directory="forses_logos"), name="forses_logos")
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)