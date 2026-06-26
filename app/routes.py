from flask import render_template
from .models import Recipe

def register_routes(app):

  @app.route("/")
  def home():
      return render_template("index.html")
  
  @app.route("/recipes") 
  def recipes():
    recipeList=Recipe.get_all()
    return render_template("recipes.html", recipes=recipeList)
  
  @app.route("/recipes/<int:recipe_id>")
  def recipe_detail(recipe_id):
     recipe=Recipe.get_by_id(recipe_id)
     return render_template("recipe_details.html", recipe=recipe)
  
  @app.route("/recipes/new")
  def new_recipe():
     return render_template("new_recipe.html")


  return app