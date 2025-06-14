# forms.py
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    TextAreaField, IntegerField, SelectField, SelectMultipleField, FileField
)
from wtforms.validators import DataRequired, Length, NumberRange


# ──────────────── ЛОГИН ─────────────────────────────────────────
class LoginForm(FlaskForm):
    username   = StringField('Логин', validators=[DataRequired(), Length(max=64)])
    password   = PasswordField('Пароль', validators=[DataRequired()])
    remember   = BooleanField('Запомнить меня')
    submit     = SubmitField('Войти')


# ──────────────── КНИГИ ─────────────────────────────────────────
class _BaseBookForm(FlaskForm):
    title       = StringField('Название', validators=[DataRequired(), Length(max=256)])
    description = TextAreaField('Описание (Markdown)', validators=[DataRequired()])
    year        = IntegerField('Год', validators=[DataRequired(), NumberRange(min=1000, max=2100)])
    publisher   = StringField('Издательство', validators=[DataRequired(), Length(max=128)])
    author      = StringField('Автор', validators=[DataRequired(), Length(max=128)])
    pages       = IntegerField('Страниц', validators=[DataRequired(), NumberRange(min=1)])
    genres      = SelectMultipleField('Жанры', coerce=int, validators=[DataRequired()])
    submit      = SubmitField('Сохранить')

class CreateBookForm(_BaseBookForm):
    cover       = FileField('Обложка (JPEG/PNG)', validators=[DataRequired()])

class EditBookForm(_BaseBookForm):
    """Без поля cover — так требует ТЗ."""
    pass

# alias (чтобы старый код, если был, не сломался)
BookForm = CreateBookForm


# ──────────────── РЕЦЕНЗИИ ──────────────────────────────────────
class ReviewForm(FlaskForm):
    rating = SelectField(
        'Оценка',
        coerce=int,
        choices=[
            (5, '5 — отлично'), (4, '4 — хорошо'), (3, '3 — удовлетворительно'),
            (2, '2 — неудовлетворительно'), (1, '1 — плохо'), (0, '0 — ужасно')
        ],
        default=5,
        validators=[DataRequired()],
    )
    text   = TextAreaField('Текст рецензии (Markdown)', validators=[DataRequired()])
    submit = SubmitField('Сохранить')
