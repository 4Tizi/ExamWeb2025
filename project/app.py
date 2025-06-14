import os
import hashlib
import random
import requests, hashlib
from functools import wraps
import click
from faker import Faker
from flask import (
    Flask, redirect, url_for, flash, request,
    render_template, send_from_directory
)
from flask_login import current_user, login_user, logout_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
                     

from config import Config
from extensions import db, login_manager
from models import (
    Role, User, Genre, Cover,
    Book, Review, ReviewStatus
)
from forms import LoginForm, BookForm, ReviewForm


# ────────────────────────────────────────────────────────────────
fake = Faker("ru_RU")            # единый экземпляр Faker


def create_app() -> Flask:
    """Application-factory: создаёт и настраивает Flask-приложение."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── init extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    # ── seed (roles, statuses, demo-users, genres, fake books)
    def seed() -> None:
        # ---- роли
        roles = {
            "administrator": "Полный доступ",
            "moderator":     "Модерация рецензий",
            "user":          "Обычный пользователь"
        }
        for name, desc in roles.items():
            if not Role.query.filter_by(name=name).first():
                db.session.add(Role(name=name, description=desc))

        # ---- статусы
        statuses = {
            "pending":  "На рассмотрении",
            "approved": "Одобрена",
            "rejected": "Отклонена"
        }
        for name, desc in statuses.items():
            if not ReviewStatus.query.filter_by(name=name).first():
                db.session.add(ReviewStatus(name=name, description=desc))

        db.session.commit()        # нужны id ролей

        # ---- demo-users
        demo = [
            ("admin", "adminpass", "Admin",      "Super", "administrator"),
            ("mod",   "modpass",   "Moderator",  "Mighty", "moderator"),
            ("user",  "userpass",  "User",       "Usual", "user")
        ]
        for uname, pwd, last, first, r in demo:
            if not User.query.filter_by(username=uname).first():
                role = Role.query.filter_by(name=r).first()
                db.session.add(
                    User(
                        username=uname,
                        password_hash=generate_password_hash(pwd),
                        last_name=last,
                        first_name=first,
                        role=role
                    )
                )

        # ---- жанры
        base_genres = [
            "Фэнтези", "Научная фантастика", "Детектив", "История",
            "Бизнес", "Саморазвитие", "Приключения", "Поэзия"
        ]
        for g in base_genres:
            if not Genre.query.filter_by(name=g).first():
                db.session.add(Genre(name=g))
        db.session.commit()

        # ---- книги: генерируем, только если их пока нет
        if not Book.query.first():
            all_genres = Genre.query.all()
            for _ in range(40):                       # ~40 книг
                g_sample = random.sample(all_genres, k=random.randint(1, 3))
                year = random.randint(1950, 2024)
                book = Book(
                    title=fake.sentence(nb_words=4).rstrip("."),
                    description=fake.paragraph(nb_sentences=8),
                    year=year,
                    publisher=fake.company(),
                    author=fake.name(),
                    pages=random.randint(120, 700),
                    genres=g_sample
                )
                db.session.add(book)
            print("✅ Faker: сгенерировано 40 книг.")
        else:
            print("ℹ️  Faker: книги уже существуют, генерация пропущена.")

        db.session.commit()
        print("✅ seed(): готово")

    # ── create tables & seed
    with app.app_context():
        db.create_all()
        seed()

    # ────────────────── STATIC (covers)
    @app.route("/uploads/<path:filename>")
    def uploads(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    # ────────────────── AUTH
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user and user.verify_password(form.password.data):
                login_user(user, remember=form.remember.data)
                flash("Вы вошли в систему", "success")
                return redirect(request.args.get("next") or url_for("index"))
            flash("Неверный логин или пароль", "danger")

        return render_template("login.html", form=form)

    @app.route("/logout")
    def logout():
        logout_user()
        flash("Вы вышли", "info")
        return redirect(request.referrer or url_for("index"))

    # ────────────────── ROLE DECORATOR
    def role_required(*roles):
        def decorator(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not current_user.is_authenticated:
                    flash("Для выполнения данного действия необходимо пройти процедуру аутентификации",
                          "warning")
                    return redirect(url_for("login", next=request.full_path))
                if current_user.role.name not in roles:
                    flash("У вас недостаточно прав для выполнения данного действия",
                          "danger")
                    return redirect(url_for("index"))
                return fn(*args, **kwargs)
            return wrapped
        return decorator

    # ────────────────── ГЛАВНАЯ
    @app.route("/")
    def index():
        page = request.args.get("page", 1, type=int)
        books = Book.query.order_by(Book.year.desc()).paginate(page=page, per_page=10)
        return render_template("index.html", books=books)

    # ────────────────── ПРОСМОТР КНИГИ
    @app.route("/books/<int:book_id>")
    def view_book(book_id):
        book = Book.query.get_or_404(book_id)
        approved = ReviewStatus.query.filter_by(name="approved").first()
        reviews = (
            Review.query.filter_by(book_id=book.id, status=approved)
            .order_by(Review.created_at.desc())
            .all()
        )
        user_review = (
            Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
            if current_user.is_authenticated else None
        )
        return render_template("book_detail.html", book=book,
                               reviews=reviews, user_review=user_review)

    # ────────────────── ДОБАВЛЕНИЕ КНИГИ
    @app.route("/books/add", methods=["GET", "POST"])
    @role_required("administrator", "moderator")
    def add_book():
        form = BookForm()
        form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name)]
        if form.validate_on_submit():
            book = Book(
                title=form.title.data,
                description=form.description.data,
                year=form.year.data,
                publisher=form.publisher.data,
                author=form.author.data,
                pages=form.pages.data
            )
            book.genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
            db.session.add(book)
            db.session.flush()  # нужен id

            if form.cover.data:
                f = form.cover.data
                md5 = hashlib.md5(f.read()).hexdigest()
                f.seek(0)
                existing = Cover.query.filter_by(md5_hash=md5).first()
                if existing:
                    book.cover = existing
                else:
                    filename = f"{md5}{os.path.splitext(secure_filename(f.filename))[1]}"
                    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                    f.save(path)
                    db.session.add(Cover(
                        filename=filename,
                        mimetype=f.mimetype,
                        md5_hash=md5,
                        book=book
                    ))
            db.session.commit()
            flash("Книга добавлена", "success")
            return redirect(url_for("view_book", book_id=book.id))
        return render_template("book_form.html", form=form, title="Добавить книгу")

    # ─────────── РЕДАКТИРОВАНИЕ КНИГИ (исправлено)
    @app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
    @role_required("administrator", "moderator")
    def edit_book(book_id):
        book = Book.query.get_or_404(book_id)
        form = BookForm(obj=book)

        # обложку не трогаем
        form.cover.render_kw = {"disabled": True}
        form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name)]

        # заполняем мультиселект при первом открытии
        if request.method == "GET":
            form.genres.data = [g.id for g in book.genres]

        # ─── ЭТОТ блок должен быть ОТДЕЛЬНО ───
        if form.validate_on_submit():
            book.title       = form.title.data
            book.description = form.description.data
            book.year        = form.year.data
            book.publisher   = form.publisher.data
            book.author      = form.author.data
            book.pages       = form.pages.data
            book.genres      = Genre.query.filter(
                Genre.id.in_(form.genres.data)
            ).all()

            db.session.commit()
            flash("Книга обновлена", "success")
            return redirect(url_for("view_book", book_id=book.id))

        # рендер формы (GET или невалидный POST)
        return render_template("book_form.html",
                            form=form,
                            title="Редактировать книгу")




    # ────────────────── УДАЛЕНИЕ КНИГИ
    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    @role_required("administrator")
    def delete_book(book_id):
        book = Book.query.get_or_404(book_id)
        if book.cover:
            path = os.path.join(app.config["UPLOAD_FOLDER"], book.cover.filename)
            if os.path.exists(path):
                os.remove(path)
        db.session.delete(book)
        db.session.commit()
        flash("Книга удалена", "info")
        return redirect(url_for("index"))

    # ────────────────── ДОБАВЛЕНИЕ РЕЦЕНЗИИ
    @app.route("/reviews/new/<int:book_id>", methods=["GET", "POST"])
    @role_required("user", "moderator", "administrator")
    def new_review(book_id):
        book = Book.query.get_or_404(book_id)
        if Review.query.filter_by(book_id=book.id, user_id=current_user.id).first():
            flash("Вы уже оставили рецензию", "warning")
            return redirect(url_for("view_book", book_id=book.id))

        form = ReviewForm()
        if form.validate_on_submit():
            pending = ReviewStatus.query.filter_by(name="pending").first()
            review = Review(
                book=book,
                user=current_user,
                rating=form.rating.data,
                text_md=form.text.data,
                status=pending
            )
            db.session.add(review)
            db.session.commit()
            flash("Рецензия отправлена на модерацию", "info")
            return redirect(url_for("view_book", book_id=book.id))
        return render_template("review_form.html", form=form, book=book)

    # ────────────────── МОИ РЕЦЕНЗИИ
    @app.route("/my_reviews")
    @role_required("user", "moderator", "administrator")
    def my_reviews():
        page = request.args.get("page", 1, type=int)
        reviews = (
            Review.query.filter_by(user_id=current_user.id)
            .order_by(Review.created_at.desc())
            .paginate(page=page, per_page=10)
        )
        return render_template("my_reviews.html", reviews=reviews)

    # ────────────────── СПИСОК НА МОДЕРАЦИИ
    @app.route("/moderation")
    @role_required("administrator", "moderator")
    def moderation():
        page = request.args.get("page", 1, type=int)
        pending = ReviewStatus.query.filter_by(name="pending").first()
        reviews = (
            Review.query.filter_by(status=pending)
            .order_by(Review.created_at)
            .paginate(page=page, per_page=10)
        )
        return render_template("moderate_list.html", reviews=reviews)

    # ────────────────── ПРОСМОТР РЕЦЕНЗИИ
    @app.route("/moderation/<int:review_id>")
    @role_required("administrator", "moderator")
    def moderation_view(review_id):
        review = Review.query.get_or_404(review_id)
        return render_template("moderate_view.html", review=review)

    # ─── смена статуса
    def change_status(review_id, status_name):
        review = Review.query.get_or_404(review_id)
        review.status = ReviewStatus.query.filter_by(name=status_name).first()
        db.session.commit()
        flash(f"Статус изменён на «{review.status.description}»", "success")
        return redirect(url_for("moderation"))

    @app.route("/moderation/<int:review_id>/approve", methods=["POST"])
    @role_required("administrator", "moderator")
    def approve(review_id):
        return change_status(review_id, "approved")

    @app.route("/moderation/<int:review_id>/reject", methods=["POST"])
    @role_required("administrator", "moderator")
    def reject(review_id):
        return change_status(review_id, "rejected")
    # ────────────────── УДАЛЕНИЕ РЕЦЕНЗИИ ─────────────────────────
    @app.route("/reviews/<int:review_id>/delete", methods=["POST"])
    @role_required("administrator", "moderator", "user")
    def delete_review(review_id):
        review = Review.query.get_or_404(review_id)

        # обычный пользователь может удалить только СВОЮ рецензию
        if (current_user.role.name == "user"
                and review.user_id != current_user.id):
            flash("Нельзя удалить чужую рецензию", "danger")
            return redirect(request.referrer or url_for("index"))

        db.session.delete(review)
        db.session.commit()
        flash("Рецензия удалена", "info")

        # вернуться туда, откуда пришли (книга или «Мои рецензии»)
        return redirect(request.referrer or url_for("my_reviews"))
    @app.cli.command("fake-books")
    @click.option("--count", default=40, help="Сколько книг добавить")
    def fake_books(count):
        """Генерирует <count> случайных книг через Faker."""
        import requests, hashlib

        fake = Faker("ru_RU")
        all_genres = Genre.query.all()
        upload_dir = app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)

        for _ in range(count):
            book = Book(
                title=fake.sentence(nb_words=4).rstrip("."),
                description=fake.paragraph(nb_sentences=8),
                year=random.randint(1950, 2024),
                publisher=fake.company(),
                author=fake.name(),
                pages=random.randint(120, 700),
                genres=random.sample(all_genres, k=random.randint(1, 3))
            )
            db.session.add(book)
            db.session.flush()      # нужен book.id для обложки

            # загружаем обложку с Unsplash
            url  = f"https://source.unsplash.com/featured/300x450/?book&sig={book.id}"
            resp = requests.get(url, timeout=10)
            if resp.ok:
                md5 = hashlib.md5(resp.content).hexdigest()
                existing = Cover.query.filter_by(md5_hash=md5).first()
                if existing:
                    book.cover = existing
                else:
                    filename = f"{md5}.jpg"
                    with open(os.path.join(upload_dir, filename), "wb") as f:
                        f.write(resp.content)
                    db.session.add(Cover(
                        filename=filename,
                        mimetype="image/jpeg",
                        md5_hash=md5,
                        book=book
                    ))

        db.session.commit()
        print(f"✅ Добавлено книг: {count}")
        
    @app.cli.command("fill-covers")
    def fill_covers():
        """Создаёт/привязывает обложки всем книгам, у которых их нет."""
        import requests, hashlib, os, uuid
        upload_dir = app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)

        books = Book.query.filter(Book.cover == None).all()
        added, linked = 0, 0

        for bk in books:
            # 👉 уменьшаем шанс одинаковых байтов:
            url = f"https://picsum.photos/seed/{uuid.uuid4()}/300/450"
            resp = requests.get(url, timeout=10)
            if not resp.ok:
                continue

            img = resp.content
            md5 = hashlib.md5(img).hexdigest()
            cover = Cover.query.filter_by(md5_hash=md5).first()

            if cover:                         # такое изображение уже есть
                bk.cover = cover              # просто привязываем
                linked += 1
                continue

            # пишем файл
            fname = f"{md5}.jpg"
            with open(os.path.join(upload_dir, fname), "wb") as f:
                f.write(img)

            cover = Cover(filename=fname,
                        mimetype="image/jpeg",
                        md5_hash=md5,
                        book=bk)
            db.session.add(cover)
            added += 1

        db.session.commit()
        print(f"✅ новых={added}, привязано к существующим={linked}")


    return app


# ────────────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
