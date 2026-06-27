import sqlalchemy as sa
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    recipes = db.relationship("Recipe", backref="user", cascade="all, delete-orphan")
    planned_meals = db.relationship("PlannedMeal", backref="user", cascade="all, delete-orphan")

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
    photo_filename = db.Column(db.String(255))
    chef_photo_filename = db.Column(db.String(255))
    ingredients = db.relationship(
        "Ingredient",
        backref="recipe",
        cascade="all, delete-orphan",
    )
    instructions = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class PlannedMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipe = db.relationship("Recipe")


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
            if "photo_filename" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN photo_filename VARCHAR(255)"))
            if "chef_photo_filename" not in recipe_columns:
                connection.execute(sa.text("ALTER TABLE recipe ADD COLUMN chef_photo_filename VARCHAR(255)"))

    if inspector.has_table("planned_meal") and "user_id" not in {column["name"] for column in inspector.get_columns("planned_meal")}:
        with db.engine.begin() as connection:
            connection.execute(sa.text("ALTER TABLE planned_meal ADD COLUMN user_id INTEGER"))

    if inspector.has_table("recipe"):
        Recipe.query.filter(Recipe.user_id.is_(None)).update({"user_id": user.id})
    if inspector.has_table("planned_meal"):
        PlannedMeal.query.filter(PlannedMeal.user_id.is_(None)).update({"user_id": user.id})

    db.session.commit()


def parse_ingredients(ingredient_text):
    """Convert ingredient text into Ingredient objects."""

    lines = ingredient_text.splitlines()
    ingredients = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        parts = line.split()

        try:
            quantity = float(parts[0])
            has_quantity = True
        except ValueError:
            quantity = None
            has_quantity = False

        if has_quantity:
            if len(parts) >= 3:
                unit = parts[1]
                name = " ".join(parts[2:])
            else:
                unit = ""
                name = parts[1]
        else:
            unit = ""
            name = line

        ingredient = Ingredient(
            name=name,
            quantity=quantity,
            unit=unit,
        )

        ingredients.append(ingredient)

    return ingredients


def format_ingredients(ingredients):
    lines = []

    for ingredient in ingredients:
        line = ""

        if ingredient.quantity is not None:
            line += str(ingredient.quantity)

            if ingredient.unit:
                line += f" {ingredient.unit}"

            line += " "

        line += ingredient.name

        lines.append(line)

    return "\n".join(lines)
