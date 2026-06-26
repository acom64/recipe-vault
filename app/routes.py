from flask import render_template, request, redirect, url_for
from .models import Recipe, parse_ingredients

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
  
  @app.route("/recipes/new",methods=["GET","POST"])
  def new_recipe():
    if request.method == "GET":
     return render_template("new_recipe.html")
    else:
      title = request.form["title"]
      description = request.form["description"]
      ingredients = parse_ingredients(request.form["ingredients"])
      instructions = request.form["instructions"]
      recipe = Recipe(
        title = title,
        description = description,
        ingredients = ingredients,
        instructions = instructions
      )

      Recipe.add(recipe)
      return redirect(url_for("recipe_detail",recipe_id=recipe.id))

  return app