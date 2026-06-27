from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db
from .models import PlannedMeal, Recipe, User, format_ingredients, parse_ingredients


def register_routes(app):

    def build_shopping_list(user):
        planned_meals = PlannedMeal.query.filter_by(user_id=user.id).all()
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

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("recipes"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            if not username or not password:
                flash("Please enter both a username and password.", "danger")
                return render_template("register.html")

            if len(password) < 6:
                flash("Password must be at least 6 characters long.", "danger")
                return render_template("register.html")

            if User.query.filter_by(username=username).first():
                flash("That username is already taken.", "danger")
                return render_template("register.html")

            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("recipes"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            if not username or not password:
                flash("Please enter both a username and password.", "danger")
                return render_template("login.html")

            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                flash(f"Welcome back, {user.username}!", "success")
                return redirect(request.args.get("next") or url_for("recipes"))

            flash("Invalid username or password.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/recipes")
    @login_required
    def recipes():
        recipe_list = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.title.asc()).all()
        return render_template("recipes.html", recipes=recipe_list)

    @app.route("/recipes/<int:recipe_id>")
    @login_required
    def recipe_detail(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first_or_404()
        return render_template("recipe_details.html", recipe=recipe)

    @app.route("/recipes/new", methods=["GET", "POST"])
    @login_required
    def new_recipe():
        if request.method == "GET":
            return render_template("recipe_form.html", recipe=None, ingredients_text="")

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        ingredients_text = request.form.get("ingredients", "")
        instructions = request.form.get("instructions", "").strip()

        if not title or not ingredients_text.strip():
            flash("Please add a title and at least one ingredient.", "danger")
            return render_template("recipe_form.html", recipe=None, ingredients_text=ingredients_text)

        recipe = Recipe(
            title=title,
            description=description,
            instructions=instructions,
            user_id=current_user.id,
        )
        recipe.ingredients = parse_ingredients(ingredients_text)

        db.session.add(recipe)
        db.session.commit()
        flash("Recipe saved.", "success")

        return redirect(url_for("recipe_detail", recipe_id=recipe.id))

    @app.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_recipe(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first_or_404()

        if request.method == "GET":
            ingredients_text = format_ingredients(recipe.ingredients)

            return render_template(
                "recipe_form.html",
                recipe=recipe,
                ingredients_text=ingredients_text,
            )

        recipe.title = request.form.get("title", "").strip()
        recipe.description = request.form.get("description", "").strip()
        recipe.instructions = request.form.get("instructions", "").strip()

        recipe.ingredients.clear()

        for ingredient in parse_ingredients(request.form.get("ingredients", "")):
            recipe.ingredients.append(ingredient)

        db.session.commit()
        flash("Recipe updated.", "success")

        return redirect(url_for("recipe_detail", recipe_id=recipe.id))

    @app.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
    @login_required
    def delete_recipe(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first_or_404()

        db.session.delete(recipe)
        db.session.commit()
        flash("Recipe deleted.", "success")

        return redirect(url_for("recipes"))

    @app.route("/meal-plan", methods=["GET", "POST"])
    @login_required
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

        recipes = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.title.asc()).all()

        if not recipes:
            flash("Add a recipe before creating a meal plan.", "warning")

        if request.method == "POST":
            PlannedMeal.query.filter_by(user_id=current_user.id).delete()

            for day in days:
                recipe_id = request.form.get(day.lower(), "")

                if not recipe_id:
                    continue

                planned_meal = PlannedMeal(
                    day=day,
                    recipe_id=recipe_id,
                    user_id=current_user.id,
                )

                db.session.add(planned_meal)

            db.session.commit()
            flash("Meal plan saved.", "success")
            return redirect(url_for("meal_plan"))

        planned_meals = PlannedMeal.query.filter_by(user_id=current_user.id).all()
        planned_ingredients = build_shopping_list(current_user)

        return render_template(
            "meal_plan.html",
            recipes=recipes,
            days=days,
            planned_meals=planned_meals,
            planned_ingredients=planned_ingredients,
        )

    @app.route("/shopping-list")
    @login_required
    def shopping_list():
        planned_ingredients = build_shopping_list(current_user)

        return render_template(
            "shopping_list.html",
            planned_ingredients=planned_ingredients,
        )

    return app
