from dataclasses import dataclass, field
from .extensions import db


class Ingredient(db.Model):
  """Represents a single ingredient within a recipe"""
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(50), nullable=False)
  quantity = db.Column(db.Float)
  unit = db.Column(db.String(50))
  recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False)
  


class Recipe(db.Model):
  """Represents a single recipe"""
  id = db.Column(db.Integer, primary_key=True)
  title = db.Column(db.String(100), nullable=False)
  description = db.Column(db.String(500))
  ingredients = db.relationship(
    "Ingredient", 
     backref="recipe", 
     cascade="all, delete-orphan")
  instructions = db.Column(db.Text)




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

    