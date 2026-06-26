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

  return app