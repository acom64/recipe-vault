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
  lines = ingredient_text.splitlines()
  ingredients = []
  for line in lines:
    if not line.strip():
      continue
    parts = line.split()
    quantity = float(parts[0])
    unit = parts[1]
    name = " ".join(parts[2:])
    ingredient = Ingredient(
      name = name,
      unit = unit,
      quantity = quantity 
    )
    ingredients.append(ingredient)
  return ingredients