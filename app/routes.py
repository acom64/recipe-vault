from flask import render_template, request, redirect, url_for
from .models import Recipe, parse_ingredients, format_ingredients, PlannedMeal
from .extensions import db


def register_routes(app):

    def build_shopping_list():
        planned_meals = PlannedMeal.query.all()
        grouped_ingredients = {}

        for planned_meal in planned_meals:
            for ingredient in planned_meal.recipe.ingredients:
                unit = ingredient.unit or ""
                key = (ingredient.name.lower(), unit.lower())

                if key in grouped_ingredients:
                    existing_ingredient = grouped_ingredients[key]

                    if (
                        existing_ingredient["quantity"] is not None
                        and ingredient.quantity is not None
                    ):
                        existing_ingredient["quantity"] += ingredient.quantity
                else:
                    grouped_ingredients[key] = {
                        "name": ingredient.name,
                        "quantity": ingredient.quantity,
                        "unit": unit,
                    }

        return grouped_ingredients.values()

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/recipes")
    def recipes():
        recipe_list = Recipe.query.all()
        return render_template("recipes.html", recipes=recipe_list)

    @app.route("/recipes/<int:recipe_id>")
    def recipe_detail(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id).first()
        return render_template("recipe_details.html", recipe=recipe)

    @app.route("/recipes/new", methods=["GET", "POST"])
    def new_recipe():
        if request.method == "GET":
            return render_template(
                "recipe_form.html",
                recipe=None,
                ingredients_text=""
            )

        title = request.form["title"].strip()
        description = request.form["description"].strip()
        ingredients = parse_ingredients(request.form["ingredients"])
        instructions = request.form["instructions"].strip()

        recipe = Recipe(
            title=title,
            description=description,
            instructions=instructions,
        )

        recipe.ingredients = ingredients

        db.session.add(recipe)
        db.session.commit()

        return redirect(url_for("recipe_detail", recipe_id=recipe.id))

    @app.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
    def edit_recipe(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id).first()

        if request.method == "GET":
            ingredients_text = format_ingredients(recipe.ingredients)

            return render_template(
                "recipe_form.html",
                recipe=recipe,
                ingredients_text=ingredients_text
            )

        recipe.title = request.form["title"].strip()
        recipe.description = request.form["description"].strip()
        recipe.instructions = request.form["instructions"].strip()

        recipe.ingredients.clear()

        for ingredient in parse_ingredients(request.form["ingredients"]):
            recipe.ingredients.append(ingredient)

        db.session.commit()

        return redirect(url_for("recipe_detail", recipe_id=recipe.id))

    @app.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
    def delete_recipe(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id).first()

        db.session.delete(recipe)
        db.session.commit()

        return redirect(url_for("recipes"))

    @app.route("/meal-plan", methods=["GET", "POST"])
    def meal_plan():
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        recipes = Recipe.query.all()

        if request.method == "POST":
            PlannedMeal.query.delete()

            for day in days:
                recipe_id = request.form.get(day.lower(), "")

                if not recipe_id:
                    continue

                planned_meal = PlannedMeal(
                    day=day,
                    recipe_id=recipe_id,
                )

                db.session.add(planned_meal)

            db.session.commit()

            return redirect(url_for("meal_plan"))

        planned_meals = PlannedMeal.query.all()
        planned_ingredients = build_shopping_list()

        return render_template(
            "meal_plan.html",
            recipes=recipes,
            days=days,
            planned_meals=planned_meals,
            planned_ingredients=planned_ingredients,
        )

    @app.route("/shopping-list")
    def shopping_list():
        planned_ingredients = build_shopping_list()

        return render_template(
            "shopping_list.html",
            planned_ingredients=planned_ingredients,
        )

    return app
