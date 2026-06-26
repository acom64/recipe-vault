from flask import render_template, request, redirect, url_for
from .models import Recipe, parse_ingredients, format_ingredients
from.extensions import db

def register_routes(app):

  @app.route("/")
  def home():
      return render_template("index.html")
  
  @app.route("/recipes") 
  def recipes():
    recipeList=Recipe.query.all()
    return render_template("recipes.html", recipes=recipeList)
  
  @app.route("/recipes/<int:recipe_id>")
  def recipe_detail(recipe_id):
     recipe=Recipe.query.filter_by(id=recipe_id).first()
     return render_template("recipe_details.html", recipe=recipe)
  
  @app.route("/recipes/new",methods=["GET","POST"])
  def new_recipe():
    if request.method == "GET":
     return render_template("recipe_form.html", recipe=None)
    else:
      title = request.form["title"]
      description = request.form["description"].strip()
      ingredients = parse_ingredients(request.form["ingredients"])
      instructions = request.form["instructions"].strip()
      recipe = Recipe(
        title = title,
        description = description,
        instructions = instructions
      )

      recipe.ingredients = ingredients

      db.session.add(recipe)
      db.session.commit()
      return redirect(url_for("recipe_detail",recipe_id=recipe.id))
    
  @app.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
  def edit_recipe(recipe_id):
    recipe = Recipe.query.filter_by(id=recipe_id).first()
    ingredients_text = format_ingredients(recipe.ingredients)
    if request.method == "GET":
      return render_template("recipe_form.html", recipe=recipe, ingredients_text=ingredients_text)
    
    recipe.title = request.form["title"].strip()
    recipe.description = request.form["description"].strip()
    recipe.instructions = request.form["instructions"].strip()

    recipe.ingredients.clear()
    recipe.ingredients = parse_ingredients(request.form["ingredients"])
   
    db.session.commit()
  
    return redirect(url_for("recipe_detail", recipe_id=recipe.id))
  
  @app.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
  def delete_recipe(recipe_id):
    recipe = Recipe.query.filter_by(id=recipe_id).first()

    db.session.delete(recipe)
    db.session.commit()

    return redirect(url_for("recipes"))
      
  return app