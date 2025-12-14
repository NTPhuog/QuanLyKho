from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional
import os
import tempfile

app = FastAPI(
    title="Hệ thống quản lý kho thông minh",
    description="Hệ thống quản lý kho hàng với đầy đủ tính năng",
    version="2.0"
)

# ===== CONFIGURATION =====
try:
    os.makedirs('static', exist_ok=True)
except OSError:
    pass # Bỏ qua lỗi nếu chạy trên môi trường read-only (Vercel)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ===== DATABASE CONFIG =====
# Trên Vercel, chúng ta không thể ghi vào thư mục gốc, phải dùng thư mục tạm
if os.environ.get("VERCEL"):
    # Nếu đang chạy trên Vercel, luôn dùng thư mục tạm
    DB_PATH = os.path.join(tempfile.gettempdir(), 'database.db')
else:
    try:
        os.makedirs('data', exist_ok=True)
        DB_PATH = 'data/database.db'
    except OSError:
        DB_PATH = os.path.join(tempfile.gettempdir(), 'database.db')

# ===== DATABASE SETUP =====
def init_db():
    # Không cần os.makedirs('data') ở đây nữa vì đã xử lý ở trên
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Xóa bảng cũ nếu tồn tại và tạo mới
    # cursor.execute('DROP TABLE IF EXISTS transactions')
    # cursor.execute('DROP TABLE IF EXISTS products')
    # cursor.execute('DROP TABLE IF EXISTS users')
    
    # Users table - ĐẦY ĐỦ CÁC CỘT
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            avatar TEXT,
            phone TEXT,
            address TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Products table - ĐẦY ĐỦ CÁC CỘT
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            sku TEXT UNIQUE,
            stock INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 5,
            price DECIMAL(10,2),
            supplier TEXT,
            supplier_country TEXT,
            manufacturer TEXT,
            distributor TEXT,
            location TEXT,
            description TEXT,
            image_url TEXT,
            status TEXT DEFAULT 'pending', -- pending/approved/rejected
            added_by INTEGER,
            approved_by INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users (id),
            FOREIGN KEY (approved_by) REFERENCES users (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            user_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Đã tạo database mới với đầy đủ cột")

init_db()

# ===== HELPER FUNCTIONS =====
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(email: str, password: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hashed_pw = hash_password(password)
    
    cursor.execute('''
        SELECT id, email, full_name, role, avatar, phone, address, status 
        FROM users 
        WHERE email = ? AND password = ? AND status = 'active'
    ''', (email, hashed_pw))
    
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            "id": user[0],
            "email": user[1],
            "full_name": user[2],
            "role": user[3],
            "avatar": user[4],
            "phone": user[5],
            "address": user[6],
            "status": user[7]
        }
    return None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_current_user(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return dict(user)
    return None

# ===== INITIAL DATA =====
def create_initial_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO users (email, password, full_name, role, avatar, phone, address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            "admin@warehouse.com",
            hash_password("admin123"),
            "Nguyễn Văn Admin",
            "admin",
            "/static/image/phuong.jpg",
            "0912345678",
            "Hà Nội, Việt Nam"
        ))
        
        cursor.execute('''
            INSERT INTO users (email, password, full_name, role, avatar, phone, address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            "staff@warehouse.com",
            hash_password("staff123"),
            "Trần Văn Nhân viên",
            "staff",
            "/static/image/Thanh.png",
            "0987654321",
            "TP.HCM, Việt Nam"
        ))
        print("✅ Đã tạo tài khoản mẫu")
    else:
        # Cập nhật avatar admin nếu tài khoản đã tồn tại
        cursor.execute("UPDATE users SET avatar = ? WHERE email = ?", ("/static/image/phuong.jpg", "admin@warehouse.com"))
    
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ("Laptop Dell XPS 13", "Điện tử", "SKU-001", 15, 5, 25000000, "Dell Việt Nam", "USA", "Dell Inc.", "Công ty TNHH Dell VN", "Kệ A1", "Laptop cao cấp", "/static/img/products/laptop.png", "approved", 1, 1),
            ("Chuột không dây Logitech", "Phụ kiện", "SKU-002", 45, 20, 850000, "Logitech", "Switzerland", "Logitech International", "Công ty Logitech", "Kệ B2", "Chuột không dây", "/static/img/products/mouse.png", "approved", 2, 1),
            ("Màn hình Samsung 27inch", "Điện tử", "SKU-003", 8, 10, 7500000, "Samsung", "South Korea", "Samsung Electronics", "Công ty Samsung VN", "Kệ C3", "Màn hình 4K", "/static/img/products/monitor.png", "pending", 2, None),
        ]
        
        for product in sample_products:
            cursor.execute('''
                INSERT INTO products (name, category, sku, stock, min_stock, price, supplier, supplier_country, 
                                     manufacturer, distributor, location, description, image_url, status, added_by, approved_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', product)
        print("✅ Đã tạo sản phẩm mẫu")
    
    conn.commit()
    conn.close()

create_initial_data()

# ===== ROUTES =====
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Thống kê khác nhau cho Admin và Staff
    if user["role"] == "admin":
        # Admin: sản phẩm chờ duyệt, đã duyệt
        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'pending'")
        pending_products = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'approved'")
        approved_products = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'staff'")
        total_staff = cursor.fetchone()[0]
        
        my_products = 0
        my_pending = 0
    else:
        # Staff: sản phẩm của mình
        cursor.execute("SELECT COUNT(*) FROM products WHERE added_by = ?", (user["id"],))
        my_products = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM products WHERE added_by = ? AND status = 'pending'", (user["id"],))
        my_pending = cursor.fetchone()[0]
        
        pending_products = 0
        approved_products = 0
        total_staff = 0
    
    # Lấy số giao dịch hôm nay
    today_str = datetime.now().strftime('%Y-%m-%d')
    if user["role"] == "admin":
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE date(created_at) = ?", (today_str,))
    else:
        cursor.execute('''
            SELECT COUNT(*) FROM transactions t 
            JOIN products p ON t.product_id = p.id 
            WHERE date(t.created_at) = ? AND p.added_by = ?
        ''', (today_str, user["id"]))
    transactions_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM products WHERE stock <= min_stock")
    low_stock = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(stock * COALESCE(price, 0)) FROM products WHERE status = 'approved'")
    total_value = cursor.fetchone()[0] or 0
    
    # Lấy tổng số sản phẩm
    if user["role"] == "admin":
        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'approved'")
        total_products = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT COUNT(*) FROM products WHERE added_by = ? AND status = 'approved'", (user["id"],))
        total_products = cursor.fetchone()[0]
    
    # Lấy danh sách categories cho biểu đồ
    if user["role"] == "admin":
        cursor.execute("SELECT category, COUNT(*) as count FROM products WHERE status = 'approved' GROUP BY category")
    else:
        cursor.execute("SELECT category, COUNT(*) as count FROM products WHERE added_by = ? AND status = 'approved' GROUP BY category", (user["id"],))
    
    categories = [dict(row) for row in cursor.fetchall()]
    
    # Lấy giao dịch gần đây
    if user["role"] == "admin":
        cursor.execute('''
            SELECT t.*, p.name as product_name, u.full_name 
            FROM transactions t 
            LEFT JOIN products p ON t.product_id = p.id 
            LEFT JOIN users u ON t.user_id = u.id 
            ORDER BY t.created_at DESC 
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT t.*, p.name as product_name, u.full_name 
            FROM transactions t 
            LEFT JOIN products p ON t.product_id = p.id 
            LEFT JOIN users u ON t.user_id = u.id 
            WHERE p.added_by = ? 
            ORDER BY t.created_at DESC 
            LIMIT 10
        ''', (user["id"],))
    
    recent_transactions = [dict(row) for row in cursor.fetchall()]
    
    # Lấy sản phẩm sắp hết
    if user["role"] == "admin":
        cursor.execute('''
            SELECT name, stock, min_stock, supplier 
            FROM products 
            WHERE stock <= min_stock AND status = 'approved'
            ORDER BY stock ASC 
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT name, stock, min_stock, supplier 
            FROM products 
            WHERE stock <= min_stock AND status = 'approved' AND added_by = ?
            ORDER BY stock ASC 
            LIMIT 10
        ''', (user["id"],))
    
    low_stock_items = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Bảng điều khiển",
            "user": user,
            "pending_products": pending_products,
            "approved_products": approved_products,
            "total_staff": total_staff,
            "my_products": my_products,
            "my_pending": my_pending,
            "transactions_today": transactions_today,
            "low_stock": low_stock,
            "total_value": total_value,
            "total_products": total_products,
            "categories": categories,
            "recent_transactions": recent_transactions,
            "low_stock_items": low_stock_items,
            "now": datetime.now
        }
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "title": "Đăng nhập hệ thống"
        }
    )

@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: Optional[str] = Form(None)
):
    user = verify_user(email, password)
    
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "title": "Đăng nhập",
                "error": "Email hoặc mật khẩu không đúng!"
            }
        )
    
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(
        key="user_id",
        value=str(user["id"]),
        max_age=86400 if remember else 3600,
        httponly=True,
        secure=False
    )
    
    return response

# ===== NHÂN VIÊN: QUẢN LÝ SẢN PHẨM =====
@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    search = request.query_params.get('search', '')
    category = request.query_params.get('category', '')
    min_stock_filter = request.query_params.get('min_stock', '')
    
    if user["role"] == "staff":
        # Nhân viên thấy: Sản phẩm đã duyệt (toàn bộ) HOẶC Sản phẩm do mình thêm (kể cả chưa duyệt)
        query = '''
            SELECT p.*, u.full_name as added_by_name, u2.full_name as approved_by_name 
            FROM products p 
            LEFT JOIN users u ON p.added_by = u.id 
            LEFT JOIN users u2 ON p.approved_by = u2.id
            WHERE p.status = 'approved' OR p.added_by = ?
        '''
        params = [user["id"]]
    else:
        # Admin thấy tất cả sản phẩm
        query = '''
            SELECT p.*, u.full_name as added_by_name, u2.full_name as approved_by_name 
            FROM products p 
            LEFT JOIN users u ON p.added_by = u.id 
            LEFT JOIN users u2 ON p.approved_by = u2.id 
            WHERE 1=1
        '''
        params = []
    
    if search:
        query += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ? OR p.supplier LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    
    if category:
        query += " AND p.category = ?"
        params.append(category)
    
    if min_stock_filter:
        if min_stock_filter == '5':
            query += " AND p.stock <= 5"
        elif min_stock_filter == '10':
            query += " AND p.stock <= 10"
    
    query += " ORDER BY p.last_updated DESC"
    
    cursor.execute(query, params)
    products = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = [{"category": row[0]} for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "title": "Quản lý sản phẩm",
            "user": user,
            "products": products,
            "categories": categories,
            "search": search,
            "selected_category": category,
            "min_stock": min_stock_filter
        }
    )

@app.post("/products/add")
async def add_product(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    sku: str = Form(...),
    stock: int = Form(...),
    min_stock: int = Form(...),
    price: float = Form(None),
    supplier: str = Form(None),
    supplier_country: str = Form(None),
    manufacturer: str = Form(None),
    distributor: str = Form(None),
    location: str = Form(None),
    description: str = Form(None),
    image_url: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO products 
            (name, category, sku, stock, min_stock, price, supplier, supplier_country, 
             manufacturer, distributor, location, description, image_url, added_by, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (name, category, sku, stock, min_stock, price, supplier, supplier_country, 
              manufacturer, distributor, location, description, image_url, user["id"]))
        
        product_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO transactions (product_id, type, quantity, user_id, notes)
            VALUES (?, 'in', ?, ?, ?)
        ''', (product_id, stock, user["id"], f"Thêm sản phẩm mới: {name}"))
        
        conn.commit()
    except sqlite3.IntegrityError:
        return JSONResponse(
            status_code=400,
            content={"error": "SKU đã tồn tại!"}
        )
    finally:
        conn.close()
    
    return RedirectResponse("/products", status_code=302)

@app.post("/products/{product_id}/update")
async def update_product(
    request: Request,
    product_id: int,
    stock_change: int = Form(...),
    type: str = Form(...),
    notes: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Kiểm tra quyền: chỉ cập nhật sản phẩm đã approved hoặc của chính mình
    cursor.execute("SELECT added_by, status FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return RedirectResponse("/products", status_code=302)
    
    # Nếu là nhân viên, chỉ được cập nhật sản phẩm của mình và đã approved
    if user["role"] == "staff" and product[0] != user["id"]:
        conn.close()
        return RedirectResponse("/products?error=Không có quyền cập nhật sản phẩm này", status_code=302)
    
    # Chỉ cập nhật tồn kho cho sản phẩm đã approved
    if product[1] != "approved":
        conn.close()
        return RedirectResponse("/products?error=Chỉ được cập nhật tồn kho sản phẩm đã duyệt", status_code=302)
    
    if type == 'in':
        cursor.execute('''
            UPDATE products 
            SET stock = stock + ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (stock_change, product_id))
    else:
        # Kiểm tra không xuất quá số lượng tồn
        cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
        current_stock = cursor.fetchone()[0]
        if stock_change > current_stock:
            conn.close()
            return RedirectResponse(f"/products?error=Không thể xuất {stock_change} khi chỉ còn {current_stock}", status_code=302)
        
        cursor.execute('''
            UPDATE products 
            SET stock = stock - ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (stock_change, product_id))
    
    cursor.execute('''
        INSERT INTO transactions (product_id, type, quantity, user_id, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (product_id, type, stock_change, user["id"], notes))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse("/products", status_code=302)

@app.post("/products/{product_id}/edit")
async def edit_product_info(
    request: Request,
    product_id: int,
    name: str = Form(...),
    category: str = Form(...),
    price: float = Form(None),
    image_url: str = Form(None),
    description: str = Form(None),
    supplier: str = Form(None),
    location: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT added_by, status FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return RedirectResponse("/products", status_code=302)
    
    # Kiểm tra quyền: Admin hoặc người tạo ra sản phẩm mới được sửa
    if user["role"] != "admin" and product[0] != user["id"]:
        conn.close()
        return RedirectResponse("/products?error=Không có quyền sửa sản phẩm này", status_code=302)

    cursor.execute('''
        UPDATE products 
        SET name = ?, category = ?, price = ?, image_url = ?, description = ?, supplier = ?, location = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (name, category, price, image_url, description, supplier, location, product_id))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse("/products", status_code=302)

@app.get("/products/{product_id}/delete")
async def delete_product(request: Request, product_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT added_by, status FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return RedirectResponse("/products", status_code=302)
    
    # Nhân viên chỉ xóa được sản phẩm của mình và ở trạng thái pending
    if user["role"] == "staff":
        if product[0] != user["id"] or product[1] != "pending":
            conn.close()
            return RedirectResponse("/products?error=Không có quyền xóa sản phẩm này", status_code=302)
    
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    cursor.execute("DELETE FROM transactions WHERE product_id = ?", (product_id,))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse("/products", status_code=302)

# ===== THÔNG TIN CHI TIẾT SẢN PHẨM =====
@app.get("/products/{product_id}/detail")
async def product_detail(request: Request, product_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, u.full_name as added_by_name, u2.full_name as approved_by_name 
        FROM products p 
        LEFT JOIN users u ON p.added_by = u.id 
        LEFT JOIN users u2 ON p.approved_by = u2.id 
        WHERE p.id = ?
    ''', (product_id,))
    
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return RedirectResponse("/products", status_code=302)
        
    # Lấy lịch sử giao dịch
    cursor.execute('''
        SELECT t.*, u.full_name as user_name 
        FROM transactions t 
        LEFT JOIN users u ON t.user_id = u.id 
        WHERE t.product_id = ? 
        ORDER BY t.created_at DESC 
        LIMIT 20
    ''', (product_id,))
    
    transactions = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        "product_detail.html",
        {
            "request": request,
            "title": f"Chi tiết: {product['name']}",
            "user": user,
            "product": dict(product),
            "transactions": transactions
        }
    )

# ===== ADMIN: DUYỆT SẢN PHẨM =====
@app.get("/admin/approve-products", response_class=HTMLResponse)
async def admin_approve_products(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, u.full_name as added_by_name, u.phone, u.email
        FROM products p 
        LEFT JOIN users u ON p.added_by = u.id
        WHERE p.status = 'pending'
        ORDER BY p.last_updated DESC
    ''')
    pending_products = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    response = templates.TemplateResponse(
        "admin_approve.html",
        {
            "request": request,
            "title": "Duyệt sản phẩm",
            "user": user,
            "pending_products": pending_products
        }
    )
    # Thêm header để ngăn trình duyệt lưu cache trang duyệt sản phẩm
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.post("/admin/products/{product_id}/approve")
async def approve_product(request: Request, product_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE products 
        SET status = 'approved', approved_by = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (user["id"], product_id))
    
    conn.commit()
    conn.close()
    print(f"✅ Đã duyệt sản phẩm {product_id}")
    
    # Sử dụng 303 See Other để trình duyệt hiểu rõ cần tải lại trang mới bằng GET
    return RedirectResponse("/admin/approve-products", status_code=303)

@app.post("/admin/products/{product_id}/reject")
async def reject_product(request: Request, product_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE products 
        SET status = 'rejected', approved_by = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (user["id"], product_id))
    
    conn.commit()
    conn.close()
    print(f"❌ Đã từ chối sản phẩm {product_id}")
    
    return RedirectResponse("/admin/approve-products", status_code=303)

# ===== ADMIN: QUẢN LÝ NGƯỜI DÙNG =====
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "title": "Quản lý người dùng",
            "user": user,
            "users": users
        }
    )

@app.post("/admin/users/add")
async def admin_add_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    role: str = Form(...)
):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (email, password, full_name, phone, address, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, hash_password(password), full_name, phone, address, role))
        
        conn.commit()
    except sqlite3.IntegrityError:
        return JSONResponse(
            status_code=400,
            content={"error": "Email đã tồn tại!"}
        )
    finally:
        conn.close()
    
    return RedirectResponse("/admin/users", status_code=302)

@app.get("/admin/users/{user_id}/toggle-status")
async def admin_toggle_user_status(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    # Không cho khóa chính mình
    if str(user["id"]) == str(user_id):
        return RedirectResponse("/admin/users?error=Không thể khóa tài khoản của chính mình", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM users WHERE id = ?", (user_id,))
    current_status = cursor.fetchone()[0]
    
    new_status = "inactive" if current_status == "active" else "active"
    
    cursor.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse("/admin/users", status_code=302)

@app.get("/admin/users/{user_id}/delete")
async def admin_delete_user(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)
    
    # Không cho xóa chính mình
    if str(user["id"]) == str(user_id):
        return RedirectResponse("/admin/users?error=Không thể xóa tài khoản của chính mình", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Cập nhật các bản ghi liên quan thành NULL trước khi xóa user để tránh lỗi và giữ lịch sử
    cursor.execute("UPDATE products SET added_by = NULL WHERE added_by = ?", (user_id,))
    cursor.execute("UPDATE products SET approved_by = NULL WHERE approved_by = ?", (user_id,))
    cursor.execute("UPDATE transactions SET user_id = NULL WHERE user_id = ?", (user_id,))
    
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse("/admin/users?success=Đã xóa tài khoản thành công", status_code=302)

# ===== THÔNG TIN CÁ NHÂN =====
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admin_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'staff'")
    staff_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'pending'")
    pending_products = cursor.fetchone()[0]
    
    conn.close()
    
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "title": "Thông tin cá nhân",
            "user": user,
            "stats": {
                "total_users": total_users,
                "admin_count": admin_count,
                "staff_count": staff_count,
                "pending_products": pending_products
            }
        }
    )

@app.post("/profile/update")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    current_password: str = Form(None),
    new_password: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Cập nhật thông tin cơ bản
    cursor.execute('''
        UPDATE users 
        SET full_name = ?, phone = ?, address = ?
        WHERE id = ?
    ''', (full_name, phone, address, user["id"]))
    
    # Cập nhật mật khẩu nếu có
    if new_password and current_password:
        cursor.execute('SELECT password FROM users WHERE id = ?', (user["id"],))
        db_password = cursor.fetchone()[0]
        
        if hash_password(current_password) == db_password:
            cursor.execute('''
                UPDATE users 
                SET password = ?
                WHERE id = ?
            ''', (hash_password(new_password), user["id"]))
        else:
            conn.close()
            return RedirectResponse("/profile?error=Mật khẩu hiện tại không đúng", status_code=302)
    
    conn.commit()
    conn.close()
    
    return RedirectResponse("/profile?success=1", status_code=302)

# ===== BÁO CÁO =====
@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    report_type = request.query_params.get('type', 'daily')
    
    if report_type == 'daily':
        cursor.execute('''
            SELECT DATE(created_at) as date, 
                   COUNT(*) as transactions,
                   SUM(CASE WHEN type='in' THEN quantity ELSE 0 END) as stock_in,
                   SUM(CASE WHEN type='out' THEN quantity ELSE 0 END) as stock_out
            FROM transactions
            WHERE DATE(created_at) >= DATE('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        ''')
    elif report_type == 'products':
        cursor.execute('''
            SELECT p.category, 
                   COUNT(*) as product_count,
                   SUM(p.stock) as total_stock,
                   SUM(p.stock * COALESCE(p.price, 0)) as total_value
            FROM products p
            WHERE p.status = 'approved'
            GROUP BY p.category
            ORDER BY total_value DESC
        ''')
    elif report_type == 'suppliers':
        cursor.execute('''
            SELECT supplier, supplier_country,
                   COUNT(*) as product_count,
                   SUM(stock) as total_stock,
                   SUM(stock * COALESCE(price, 0)) as total_value
            FROM products
            WHERE status = 'approved'
            GROUP BY supplier, supplier_country
            ORDER BY product_count DESC
        ''')
    elif report_type == 'staff' and user["role"] == "admin":
        cursor.execute('''
            SELECT u.full_name, u.email,
                   COUNT(p.id) as product_count,
                   SUM(CASE WHEN p.status='approved' THEN 1 ELSE 0 END) as approved_count,
                   SUM(CASE WHEN p.status='pending' THEN 1 ELSE 0 END) as pending_count
            FROM users u
            LEFT JOIN products p ON u.id = p.added_by
            WHERE u.role = 'staff'
            GROUP BY u.id
            ORDER BY product_count DESC
        ''')
    else:
        cursor.execute('''
            SELECT DATE(created_at) as date, 
                   COUNT(*) as transactions
            FROM transactions
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 10
        ''')
    
    report_data = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "title": "Báo cáo & Thống kê",
            "user": user,
            "report_type": report_type,
            "report_data": report_data,
            "now": datetime.now
        }
    )

# ===== API ENDPOINTS =====
@app.get("/api/stats")
async def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT strftime('%Y-%m', created_at) as month,
               SUM(CASE WHEN type='in' THEN quantity ELSE 0 END) as in_qty,
               SUM(CASE WHEN type='out' THEN quantity ELSE 0 END) as out_qty
        FROM transactions
        WHERE created_at >= DATE('now', '-6 months')
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY month
    ''')
    
    monthly_data = cursor.fetchall()
    
    conn.close()
    
    return {
        "months": [row[0] for row in monthly_data],
        "in_qty": [row[1] or 0 for row in monthly_data],
        "out_qty": [row[2] or 0 for row in monthly_data]
    }

@app.get("/api/pending-count")
async def get_pending_count(request: Request):
    user = get_current_user(request)
    if not user:
        return {"admin_pending": 0, "staff_pending": 0}
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'pending'")
    admin_pending = cursor.fetchone()[0]
    
    if user["role"] == "staff":
        cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'pending' AND added_by = ?", (user["id"],))
        staff_pending = cursor.fetchone()[0]
    else:
        staff_pending = 0
    
    conn.close()
    
    return {
        "admin_pending": admin_pending,
        "staff_pending": staff_pending
    }

@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("user_id")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )