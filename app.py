import os
import json
import secrets
import shutil
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, FormField, Review, FishImage

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'healing-community-secret-key-2024')
# Render Disk 持久化路径优先；本地开发回退到 /tmp
DATA_DIR = os.environ.get('DATA_DIR', '/tmp')
DB_PATH = os.path.join(DATA_DIR, 'data.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大上传 16MB
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

# ─────────────────────────────────────────
# 默认复盘字段（种子数据）
# ─────────────────────────────────────────
DEFAULT_FIELDS = [
    {
        'field_key': 'daily_mood',
        'label': '今日心情',
        'field_type': 'mood_picker',
        'options': ['😊 开心', '😌 平静', '😔 有点低落', '😰 焦虑', '😍 很棒', '🥺 感动'],
        'placeholder': None,
        'is_required': True,
        'sort_order': 1,
    },
    {
        'field_key': 'energy_level',
        'label': '今日能量指数',
        'field_type': 'rating',
        'options': [],
        'placeholder': '1-10分，你今天的能量如何？',
        'is_required': True,
        'sort_order': 2,
    },
    {
        'field_key': 'fish_mode',
        'label': '摸鱼环节',
        'field_type': 'single_choice',
        'options': ['🎣 今天摸了，上点图看看', '📝 今天没摸，正常复盘'],
        'placeholder': None,
        'is_required': False,
        'sort_order': 3,
    },
    {
        'field_key': 'today_gratitude',
        'label': '今日感恩',
        'field_type': 'textarea',
        'options': [],
        'placeholder': '今天有哪些值得感恩的小事？（可以是一件小事、一个微笑、一杯好茶）',
        'is_required': False,
        'sort_order': 4,
    },
    {
        'field_key': 'today_insight',
        'label': '今日洞见',
        'field_type': 'textarea',
        'options': [],
        'placeholder': '今天有什么新的领悟或成长？',
        'is_required': False,
        'sort_order': 5,
    },
    {
        'field_key': 'difficulty_faced',
        'label': '遇到的困难',
        'field_type': 'textarea',
        'options': [],
        'placeholder': '今天遇到了什么挑战？你是怎么面对的？',
        'is_required': False,
        'sort_order': 6,
    },
    {
        'field_key': 'tomorrow_intention',
        'label': '明日意图',
        'field_type': 'text',
        'options': [],
        'placeholder': '明天我想要……',
        'is_required': False,
        'sort_order': 7,
    },
]


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def init_db():
    """初始化数据库并写入种子数据"""
    db.create_all()
    # 创建默认管理员
    if not User.query.filter_by(role='admin').first():
        admin = User(
            username='admin',
            email='admin@healing.com',
            role='admin',
            avatar_color='#C3B1E1'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush()

        # 写入默认字段
        for f in DEFAULT_FIELDS:
            field = FormField(
                field_key=f['field_key'],
                label=f['label'],
                field_type=f['field_type'],
                placeholder=f.get('placeholder'),
                is_required=f['is_required'],
                sort_order=f['sort_order'],
                is_active=True,
                created_by=admin.id
            )
            field.set_options(f.get('options', []))
            db.session.add(field)

        db.session.commit()


# ─────────────────────────────────────────
# 页面路由
# ─────────────────────────────────────────
@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/history')
@login_required
def history_page():
    return render_template('history.html')


@app.route('/weekly')
@login_required
def weekly_page():
    return render_template('weekly.html')


@app.route('/share/<token>')
def share_page(token):
    review = Review.query.filter_by(share_token=token, is_shared=True).first_or_404()
    return render_template('share.html', token=token)


@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        abort(403)
    return render_template('admin/dashboard.html')


@app.route('/admin/fields')
@login_required
def admin_fields():
    if current_user.role != 'admin':
        abort(403)
    return render_template('admin/fields.html')


# ─────────────────────────────────────────
# API：认证
# ─────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    # 邮箱不再必填，用用户名生成唯一标识
    email = f"{username}@healing.diary" if username else ''

    if not username or not password:
        return jsonify({'error': '请填写用户名和密码'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码不能少于6位'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '用户名已存在'}), 400

    colors = ['#FFB5A7', '#B7E1CD', '#C3B1E1', '#FFD9A0', '#A8D8EA', '#F7C5D0']
    color = colors[User.query.count() % len(colors)]

    user = User(username=username, email=email, avatar_color=color)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/auth/check-username', methods=['GET'])
def api_check_username():
    """检查用户名是否已存在"""
    username = request.args.get('username', '').strip()
    if not username or len(username) < 2:
        return jsonify({'exists': False, 'error': '用户名至少2个字符'})
    exists = User.query.filter_by(username=username).first() is not None
    return jsonify({'exists': exists})


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    remember = data.get('remember', False)

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password):
        return jsonify({'error': '用户名或密码错误'}), 401
    if not user.is_active:
        return jsonify({'error': '账号已被禁用'}), 403

    login_user(user, remember=remember)
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({'success': True})


@app.route('/api/auth/me')
@login_required
def api_me():
    return jsonify(current_user.to_dict())


# ─────────────────────────────────────────
# API：表单字段
# ─────────────────────────────────────────
@app.route('/api/fields')
@login_required
def api_get_fields():
    fields = FormField.query.filter_by(is_active=True).order_by(FormField.sort_order).all()
    return jsonify([f.to_dict() for f in fields])


@app.route('/api/admin/fields')
@login_required
def api_admin_get_fields():
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    fields = FormField.query.order_by(FormField.sort_order).all()
    return jsonify([f.to_dict() for f in fields])


@app.route('/api/admin/fields', methods=['POST'])
@login_required
def api_admin_create_field():
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    data = request.get_json()

    if not data.get('field_key') or not data.get('label') or not data.get('field_type'):
        return jsonify({'error': '请填写完整字段信息'}), 400
    if FormField.query.filter_by(field_key=data['field_key']).first():
        return jsonify({'error': '字段Key已存在'}), 400

    max_order = db.session.query(db.func.max(FormField.sort_order)).scalar() or 0
    field = FormField(
        field_key=data['field_key'],
        label=data['label'],
        field_type=data['field_type'],
        placeholder=data.get('placeholder'),
        is_required=data.get('is_required', False),
        sort_order=max_order + 1,
        is_active=True,
        created_by=current_user.id
    )
    field.set_options(data.get('options', []))
    db.session.add(field)
    db.session.commit()
    return jsonify(field.to_dict()), 201


@app.route('/api/admin/fields/<int:fid>', methods=['PUT'])
@login_required
def api_admin_update_field(fid):
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    field = FormField.query.get_or_404(fid)
    data = request.get_json()

    if 'label' in data:
        field.label = data['label']
    if 'field_type' in data:
        field.field_type = data['field_type']
    if 'options' in data:
        field.set_options(data['options'])
    if 'placeholder' in data:
        field.placeholder = data['placeholder']
    if 'is_required' in data:
        field.is_required = data['is_required']
    if 'is_active' in data:
        field.is_active = data['is_active']
    if 'sort_order' in data:
        field.sort_order = data['sort_order']

    db.session.commit()
    return jsonify(field.to_dict())


@app.route('/api/admin/fields/<int:fid>', methods=['DELETE'])
@login_required
def api_admin_delete_field(fid):
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    field = FormField.query.get_or_404(fid)
    db.session.delete(field)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/fields/reorder', methods=['PUT'])
@login_required
def api_admin_reorder_fields():
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    data = request.get_json()  # [{id: 1, sort_order: 1}, ...]
    for item in data:
        field = FormField.query.get(item['id'])
        if field:
            field.sort_order = item['sort_order']
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────
# API：复盘记录
# ─────────────────────────────────────────
@app.route('/api/reviews/today')
@login_required
def api_get_today_review():
    today = date.today()
    review = Review.query.filter_by(user_id=current_user.id, review_date=today).first()
    if review:
        return jsonify(review.to_dict())
    return jsonify(None)


@app.route('/api/reviews/today', methods=['POST'])
@login_required
def api_save_today_review():
    data = request.get_json()
    content = data.get('content', {})
    today = date.today()

    review = Review.query.filter_by(user_id=current_user.id, review_date=today).first()
    if review:
        review.set_content(content)
        review.updated_at = datetime.utcnow()
    else:
        review = Review(user_id=current_user.id, review_date=today)
        review.set_content(content)
        db.session.add(review)

    db.session.commit()
    return jsonify(review.to_dict())


# ── 按日期获取/保存复盘（支持编辑历史日期）──
@app.route('/api/reviews/<string:date_str>', methods=['GET'])
@login_required
def api_get_review_by_date(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    # 不能查看未来日期
    if d > date.today():
        return jsonify({'error': '不能查看未来日期'}), 400
    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first()
    if review:
        return jsonify(review.to_dict())
    return jsonify(None)


@app.route('/api/reviews/<string:date_str>', methods=['POST'])
@login_required
def api_save_review_by_date(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    if d > date.today():
        return jsonify({'error': '不能保存未来日期'}), 400

    data = request.get_json()
    content = data.get('content', {})

    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first()
    if review:
        review.set_content(content)
        review.updated_at = datetime.utcnow()
    else:
        review = Review(user_id=current_user.id, review_date=d)
        review.set_content(content)
        db.session.add(review)

    db.session.commit()
    return jsonify(review.to_dict())


@app.route('/api/reviews/history')
@login_required
def api_get_history():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = Review.query.filter_by(user_id=current_user.id).order_by(Review.review_date.desc())
    if year and month:
        from sqlalchemy import extract
        query = query.filter(
            extract('year', Review.review_date) == year,
            extract('month', Review.review_date) == month
        )

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'items': [r.to_dict() for r in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'page': page
    })


@app.route('/api/reviews/weekly-stats')
@login_required
def api_weekly_stats():
    # 获取本周（周一到周日）
    today = date.today()
    week_offset = int(request.args.get('offset', 0))  # 0=本周, -1=上周
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    reviews = Review.query.filter(
        Review.user_id == current_user.id,
        Review.review_date >= week_start,
        Review.review_date <= week_end
    ).order_by(Review.review_date).all()

    # 建立日期到记录的映射
    review_map = {r.review_date.isoformat(): r for r in reviews}

    # 获取所有字段
    fields = FormField.query.filter_by(is_active=True).order_by(FormField.sort_order).all()
    mood_field = next((f for f in fields if f.field_type == 'mood_picker'), None)
    rating_field = next((f for f in fields if f.field_type == 'rating'), None)

    days_data = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        d_str = d.isoformat()
        r = review_map.get(d_str)
        content = r.get_content() if r else {}

        mood_value = None
        energy_value = None
        if r:
            if mood_field:
                mv = content.get(mood_field.field_key)
                # 将情绪选项转换为数值（0-5对应6种情绪）
                if mv:
                    options = mood_field.get_options()
                    if mv in options:
                        mood_value = options.index(mv)
            if rating_field:
                ev = content.get(rating_field.field_key)
                if ev is not None:
                    try:
                        energy_value = float(ev)
                    except (ValueError, TypeError):
                        pass

        days_data.append({
            'date': d_str,
            'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][i],
            'has_review': r is not None,
            'mood': mood_value,
            'energy': energy_value,
            'review': r.to_dict() if r else None
        })

    # 连续打卡天数（从今天往前算）
    streak = 0
    check_date = today
    while True:
        r = Review.query.filter_by(user_id=current_user.id, review_date=check_date).first()
        if r:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    return jsonify({
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'days': days_data,
        'checkin_count': sum(1 for d in days_data if d['has_review']),
        'streak': streak,
        'mood_field': mood_field.to_dict() if mood_field else None,
        'rating_field': rating_field.to_dict() if rating_field else None
    })


# ─────────────────────────────────────────
# API：分享
# ─────────────────────────────────────────
@app.route('/api/reviews/<string:date_str>/share', methods=['POST'])
@login_required
def api_create_share(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first_or_404()
    if not review.share_token:
        review.share_token = secrets.token_urlsafe(32)
    review.is_shared = True
    db.session.commit()
    share_url = f"/share/{review.share_token}"
    return jsonify({'share_token': review.share_token, 'share_url': share_url})


@app.route('/api/reviews/<string:date_str>/share', methods=['DELETE'])
@login_required
def api_cancel_share(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first_or_404()
    review.is_shared = False
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/share/<token>')
def api_get_share(token):
    review = Review.query.filter_by(share_token=token, is_shared=True).first_or_404()
    fields = FormField.query.filter_by(is_active=True).order_by(FormField.sort_order).all()
    fish_images = FishImage.query.filter_by(review_id=review.id).order_by(FishImage.created_at).all()
    return jsonify({
        'review': review.to_dict(include_user=True),
        'fields': [f.to_dict() for f in fields],
        'fish_images': [img.to_dict() for img in fish_images]
    })


# ─────────────────────────────────────────
# API：管理员统计
# ─────────────────────────────────────────
@app.route('/api/admin/stats')
@login_required
def api_admin_stats():
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403

    total_users = User.query.filter_by(role='member').count()
    total_reviews = Review.query.count()
    today = date.today()
    today_reviews = Review.query.filter_by(review_date=today).count()
    week_start = today - timedelta(days=today.weekday())
    week_reviews = Review.query.filter(Review.review_date >= week_start).count()

    # 最近7天每日打卡人数
    daily_stats = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = Review.query.filter_by(review_date=d).count()
        daily_stats.append({'date': d.isoformat(), 'count': count})

    # 最近活跃用户
    recent_users = db.session.query(User, db.func.max(Review.review_date).label('last_review'))\
        .outerjoin(Review, User.id == Review.user_id)\
        .filter(User.role == 'member')\
        .group_by(User.id)\
        .order_by(db.desc('last_review'))\
        .limit(10).all()

    return jsonify({
        'total_users': total_users,
        'total_reviews': total_reviews,
        'today_reviews': today_reviews,
        'week_reviews': week_reviews,
        'daily_stats': daily_stats,
        'recent_users': [
            {**u.to_dict(), 'last_review': str(lr) if lr else None}
            for u, lr in recent_users
        ],
        'disk': get_disk_usage()
    })


@app.route('/api/admin/users')
@login_required
def api_admin_users():
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    users = User.query.order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        d = u.to_dict()
        d['review_count'] = Review.query.filter_by(user_id=u.id).count()
        result.append(d)
    return jsonify(result)


@app.route('/api/admin/users/<int:uid>/toggle', methods=['POST'])
@login_required
def api_admin_toggle_user(uid):
    if current_user.role != 'admin':
        return jsonify({'error': '无权访问'}), 403
    user = User.query.get_or_404(uid)
    if user.role == 'admin':
        return jsonify({'error': '不能禁用管理员账号'}), 400
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': user.is_active})


# 确保数据库初始化（在生产环境中通过 before_first_request 或直接调用）
with app.app_context():
    init_db()

# ─────────────────────────────────────────
# API：摸鱼环节图片上传
# ─────────────────────────────────────────
@app.route('/api/reviews/today/fish-images', methods=['POST'])
@login_required
def api_upload_fish_images():
    today = date.today()
    review = Review.query.filter_by(user_id=current_user.id, review_date=today).first()
    # 如果还没有复盘记录，先创建一个空的
    if not review:
        review = Review(user_id=current_user.id, review_date=today)
        review.set_content({})
        db.session.add(review)
        db.session.flush()

    caption = request.form.get('caption', '').strip()

    if 'image' not in request.files:
        return jsonify({'error': '请上传图片'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '请选择图片'}), 400

    # 允许的图片格式
    allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        return jsonify({'error': f'不支持的图片格式: .{ext}，支持: {", ".join(allowed_ext)}'}), 400

    # 生成唯一文件名
    import uuid
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(save_path)

    fish_img = FishImage(
        review_id=review.id,
        filename=safe_name,
        caption=caption if caption else None
    )
    db.session.add(fish_img)
    db.session.commit()

    return jsonify(fish_img.to_dict()), 201


@app.route('/api/reviews/today/fish-images', methods=['GET'])
@login_required
def api_get_fish_images():
    today = date.today()
    review = Review.query.filter_by(user_id=current_user.id, review_date=today).first()
    if not review:
        return jsonify([])
    images = FishImage.query.filter_by(review_id=review.id).order_by(FishImage.created_at).all()
    return jsonify([img.to_dict() for img in images])


@app.route('/api/reviews/<string:date_str>/fish-images', methods=['POST'])
@login_required
def api_upload_fish_images_by_date(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    if d > date.today():
        return jsonify({'error': '不能为未来日期上传图片'}), 400

    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first()
    if not review:
        review = Review(user_id=current_user.id, review_date=d)
        review.set_content({})
        db.session.add(review)
        db.session.flush()

    caption = request.form.get('caption', '').strip()
    if 'image' not in request.files:
        return jsonify({'error': '请上传图片'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '请选择图片'}), 400

    allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        return jsonify({'error': f'不支持的图片格式: .{ext}'}), 400

    import uuid
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(save_path)

    fish_img = FishImage(review_id=review.id, filename=safe_name, caption=caption if caption else None)
    db.session.add(fish_img)
    db.session.commit()
    return jsonify(fish_img.to_dict()), 201


@app.route('/api/reviews/<string:date_str>/fish-images/<int:img_id>', methods=['DELETE'])
@login_required
def api_delete_fish_image_by_date(date_str, img_id):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first()
    if not review:
        return jsonify({'error': '无该日复盘'}), 400
    img = FishImage.query.filter_by(id=img_id, review_id=review.id).first_or_404()
    path = os.path.join(UPLOAD_FOLDER, img.filename)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(img)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/reviews/<string:date_str>/fish-images', methods=['GET'])
@login_required
def api_get_fish_images_by_date(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400
    review = Review.query.filter_by(user_id=current_user.id, review_date=d).first()
    if not review:
        return jsonify([])
    images = FishImage.query.filter_by(review_id=review.id).order_by(FishImage.created_at).all()
    return jsonify([img.to_dict() for img in images])


@app.route('/api/fish-images/<string:filename>')
def api_serve_fish_image(filename):
    """提供图片访问（需要安全校验文件名）"""
    safe_name = os.path.basename(filename)
    path = os.path.join(UPLOAD_FOLDER, safe_name)
    if not os.path.exists(path):
        abort(404)
    from flask import send_file
    return send_file(path)


@app.route('/api/reviews/today/fish-images/<int:img_id>', methods=['DELETE'])
@login_required
def api_delete_fish_image(img_id):
    today = date.today()
    review = Review.query.filter_by(user_id=current_user.id, review_date=today).first()
    if not review:
        return jsonify({'error': '无今日复盘'}), 400
    img = FishImage.query.filter_by(id=img_id, review_id=review.id).first_or_404()
    # 删除文件
    path = os.path.join(UPLOAD_FOLDER, img.filename)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(img)
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────
# 磁盘使用统计工具函数
# ─────────────────────────────────────────
def get_disk_usage():
    """获取磁盘使用情况（用于管理员后台展示 Render Disk 1GB 限额）"""
    data_dir = os.environ.get('DATA_DIR', '/tmp')
    total_limit = 1 * 1024 * 1024 * 1024  # 1GB (Render 免费 Disk 限额)

    # 统计数据目录实际使用量
    used_bytes = 0
    db_size = 0
    uploads_size = 0
    uploads_count = 0

    # 数据库文件大小
    db_path = os.path.join(data_dir, 'data.db')
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path)
        used_bytes += db_size

    # 上传文件大小
    uploads_dir = os.path.join(data_dir, 'uploads')
    if os.path.exists(uploads_dir):
        for dirpath, dirnames, filenames in os.walk(uploads_dir):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    uploads_size += os.path.getsize(fp)
                    uploads_count += 1
                except OSError:
                    pass
    used_bytes += uploads_size

    # 系统级磁盘信息（尝试获取挂载点信息）
    try:
        stat = shutil.disk_usage(data_dir)
        disk_total = stat.total
        disk_free = stat.free
        disk_used = stat.used
    except Exception:
        disk_total = total_limit
        disk_free = max(0, total_limit - used_bytes)
        disk_used = used_bytes

    def fmt(size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    return {
        'used_bytes': used_bytes,
        'used_display': fmt(used_bytes),
        'db_size': db_size,
        'db_display': fmt(db_size),
        'uploads_size': uploads_size,
        'uploads_display': fmt(uploads_size),
        'uploads_count': uploads_count,
        'total_limit': total_limit,
        'total_limit_display': '1 GB',
        'free_bytes': disk_free,
        'free_display': fmt(disk_free),
        'usage_percent': round(used_bytes / total_limit * 100, 1),
        'disk_total': disk_total,
        'disk_total_display': fmt(disk_total),
    }


if __name__ == '__main__':
    print("🌿 疗愈社群复盘系统已启动")
    print("📍 访问地址: http://localhost:5000")
    print("🔑 默认管理员: admin / admin123")
    app.run(debug=False, host='0.0.0.0', port=5000)
