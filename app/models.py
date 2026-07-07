from datetime import UTC, datetime
from fractions import Fraction

import sqlalchemy as sa
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now():
    return datetime.now(UTC)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    recipes = db.relationship("Recipe", backref="user", cascade="all, delete-orphan")
    planned_meals = db.relationship("PlannedMeal", backref="user", cascade="all, delete-orphan")
    shopping_item_states = db.relationship("ShoppingListItemState", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class Ingredient(db.Model):
    """Represents a single ingredient within a recipe."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(50))
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)


class Recipe(db.Model):
    """Represents a single recipe."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    food_category = db.Column(db.String(80))
    meal_type = db.Column(db.String(40))
    prep_time = db.Column(db.Integer)
    cook_time = db.Column(db.Integer)
    servings = db.Column(db.Integer)
    notes = db.Column(db.Text)
    is_favorite = db.Column(db.Boolean, nullable=False, default=False)
    photo_filename = db.Column(db.String(255))
    chef_photo_filename = db.Column(db.String(255))
    ingredients = db.relationship(
        "Ingredient",
        backref="recipe",
        cascade="all, delete-orphan",
    )
    instructions = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)


class PlannedMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)
    meal_type = db.Column(db.String(40), nullable=False, default="dinner")
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipe = db.relationship("Recipe")


class ShoppingListItemState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    item_key = db.Column(db.String(255), nullable=False)
    checked = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "item_key", name="uq_shopping_item_state_user_key"),
    )


def ensure_default_user():
    inspector = sa.inspect(db.engine)

    if not inspector.has_table("user"):
        db.create_all()

    user = User.query.first()

    if not user:
        user = User(username="admin")
        user.set_password("changeme123")
        db.session.add(user)
        db.session.commit()

    if inspector.has_table("recipe") and "user_id" not in {column["name"] for column in inspector.get_columns("recipe")}:
        with db.engine.begin() as connection:
            connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN user_id INTEGER"))

    if inspector.has_table("recipe"):
        recipe_columns = {column["name"] for column in inspector.get_columns("recipe")}
        with db.engine.begin() as connection:
            if "food_category" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN food_category VARCHAR(80)"))
            if "meal_type" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN meal_type VARCHAR(40)"))
            if "prep_time" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN prep_time INTEGER"))
            if "cook_time" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN cook_time INTEGER"))
            if "servings" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN servings INTEGER"))
            if "notes" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN notes TEXT"))
            if "is_favorite" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN is_favorite BOOLEAN DEFAULT 0"))
            if "photo_filename" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN photo_filename VARCHAR(255)"))
            if "chef_photo_filename" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN chef_photo_filename VARCHAR(255)"))
            if "created_at" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN created_at DATETIME"))
            if "updated_at" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN updated_at DATETIME"))

    if inspector.has_table("planned_meal"):
        planned_meal_columns = {column["name"] for column in inspector.get_columns("planned_meal")}
        with db.engine.begin() as connection:
            if "user_id" not in planned_meal_columns:
                connection.execute(sa.text("ALTER TABLE planned_meal ADD COLUMN user_id INTEGER"))
            if "meal_type" not in planned_meal_columns:
                connection.execute(sa.text("ALTER TABLE planned_meal ADD COLUMN meal_type VARCHAR(40)"))

    if inspector.has_table("recipe"):
        Recipe.query.filter(Recipe.user_id.is_(None)).update({"user_id": user.id})
        Recipe.query.filter(Recipe.is_favorite.is_(None)).update({"is_favorite": False})
        Recipe.query.filter(Recipe.created_at.is_(None)).update({"created_at": utc_now()})
        Recipe.query.filter(Recipe.updated_at.is_(None)).update({"updated_at": utc_now()})
    if inspector.has_table("planned_meal"):
        PlannedMeal.query.filter(PlannedMeal.user_id.is_(None)).update({"user_id": user.id})
        PlannedMeal.query.filter(PlannedMeal.meal_type.is_(None)).update({"meal_type": "dinner"})

    db.session.commit()


def parse_quantity_token(token):
    """Return a float quantity from beginner-friendly numeric text."""

    unicode_fractions = {
        "¼": 0.25,
        "½": 0.5,
        "¾": 0.75,
        "⅓": 1 / 3,
        "⅔": 2 / 3,
        "⅛": 0.125,
        "⅜": 0.375,
        "⅝": 0.625,
        "⅞": 0.875,
    }
    normalized = token.strip()

    if normalized in unicode_fractions:
        return unicode_fractions[normalized]

    if "-" in normalized and "/" in normalized:
        whole, fraction = normalized.split("-", 1)
        return float(whole) + float(Fraction(fraction))

    if "/" in normalized:
        return float(Fraction(normalized))

    return float(normalized)


def read_quantity(parts):
    if not parts:
        return None, 0

    try:
        quantity = parse_quantity_token(parts[0])
    except (ValueError, ZeroDivisionError):
        return None, 0

    consumed = 1

    if len(parts) > 1:
        try:
            fraction = parse_quantity_token(parts[1])
            if 0 < fraction < 1:
                quantity += fraction
                consumed = 2
        except (ValueError, ZeroDivisionError):
            pass

    return quantity, consumed


def parse_ingredients(ingredient_text):
    """Convert ingredient text into Ingredient objects."""

    lines = ingredient_text.splitlines()
    ingredients = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        parts = line.split()
        quantity, consumed = read_quantity(parts)

        if consumed and len(parts) > consumed:
            if len(parts) - consumed >= 2:
                unit = parts[consumed]
                name = " ".join(parts[consumed + 1:])
            else:
                unit = ""
                name = parts[consumed]
        else:
            quantity = None
            unit = ""
            name = line

        ingredient = Ingredient(
            name=name,
            quantity=quantity,
            unit=unit,
        )

        ingredients.append(ingredient)

    return ingredients


def format_quantity(quantity):
    if quantity is None:
        return ""

    if float(quantity).is_integer():
        return str(int(quantity))

    return f"{quantity:.2f}".rstrip("0").rstrip(".")


def format_ingredients(ingredients):
    lines = []

    for ingredient in ingredients:
        line = ""

        if ingredient.quantity is not None:
            line += format_quantity(ingredient.quantity)

            if ingredient.unit:
                line += f" {ingredient.unit}"

            line += " "

        line += ingredient.name

        lines.append(line)

    return "\n".join(lines)
