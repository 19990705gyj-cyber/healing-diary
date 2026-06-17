from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='member')  # 'admin' | 'member'
    avatar_color = db.Column(db.String(20), default='#FFB5A7')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    reviews = db.relationship('Review', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'avatar_color': self.avatar_color,
            'created_at': self.created_at.isoformat()
        }


class FormField(db.Model):
    __tablename__ = 'form_fields'
    id = db.Column(db.Integer, primary_key=True)
    field_key = db.Column(db.String(50), nullable=False, unique=True)
    label = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(20), nullable=False)
    # text | textarea | rating | single_choice | multi_choice | slider | mood_picker
    options = db.Column(db.Text)  # JSON string for choices
    placeholder = db.Column(db.String(200))
    is_required = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def get_options(self):
        if self.options:
            return json.loads(self.options)
        return []

    def set_options(self, options_list):
        self.options = json.dumps(options_list, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'field_key': self.field_key,
            'label': self.label,
            'field_type': self.field_type,
            'options': self.get_options(),
            'placeholder': self.placeholder,
            'is_required': self.is_required,
            'sort_order': self.sort_order,
            'is_active': self.is_active
        }


class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    review_date = db.Column(db.Date, nullable=False)
    content = db.Column(db.Text, nullable=False)  # JSON: {field_key: value}
    share_token = db.Column(db.String(64), unique=True)
    is_shared = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'review_date', name='uq_user_date'),
    )

    def get_content(self):
        if self.content:
            return json.loads(self.content)
        return {}

    def set_content(self, content_dict):
        self.content = json.dumps(content_dict, ensure_ascii=False)

    def to_dict(self, include_user=False):
        d = {
            'id': self.id,
            'user_id': self.user_id,
            'review_date': self.review_date.isoformat(),
            'content': self.get_content(),
            'share_token': self.share_token,
            'is_shared': self.is_shared,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        if include_user:
            d['username'] = self.user.username
            d['avatar_color'] = self.user.avatar_color
        d['fish_images'] = [fi.to_dict() for fi in self.fish_images]
        return d


class FishImage(db.Model):
    """摸鱼环节上传的图片"""
    __tablename__ = 'fish_images'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.Text)  # 可选文字说明
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    review = db.relationship('Review', backref='fish_images', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'review_id': self.review_id,
            'filename': self.filename,
            'caption': self.caption,
            'created_at': self.created_at.isoformat()
        }
