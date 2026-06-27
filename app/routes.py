import os
from uuid import uuid4

from flask import Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from .extensions import db
from .models import PlannedMeal, Recipe, User, format_ingredients, parse_ingredients


def register_routes(app):
    allowed_image_extensions = {"jpg", "jpeg", "png", "gif", "webp"}
    export_header = "Recipe Vault Export"
    recipe_start_marker = "--- Recipe ---"
    recipe_end_marker = "--- End Recipe ---"
    export_fields = {
        "Title:": "title",
        "Description:": "description",
        "Ingredients:": "ingredients",
        "Instructions:": "instructions",
    }

    def get_uploaded_image(field_name):
        image = request.files.get(field_name)

        if not image or not image.filename:
            return None

        return image

    def validate_uploaded_image(image):
        if not image:
            return None

        extension = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
        if extension not in allowed_image_extensions:
            return "Please upload images as JPG, PNG, GIF, or WebP files."

        return None

    def save_uploaded_image(image):
        if not image:
            return None

        original_filename = secure_filename(image.filename)
        filename = f"{uuid4().hex}_{original_filename}"
        image.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

        return filename

    def build_recipe_export(recipe_list):
        lines = [export_header, ""]

        for recipe in recipe_list:
            lines.extend(
                [
                    recipe_start_marker,
                    "Title:",
                    recipe.title or "",
                    "Description:",
                    recipe.description or "",
                    "Ingredients:",
                    format_ingredients(recipe.ingredients),
                    "Instructions:",
                    recipe.instructions or "",
                    recipe_end_marker,
                    "",
                ]
            )

        return "\n".join(lines)

    def parse_recipe_export(export_text):
        recipes_to_import = []
        current_recipe = None
        current_field = None

        for raw_line in export_text.splitlines():
            line = raw_line.rstrip()

            if line == recipe_start_marker:
                current_recipe = {
                    "title": [],
                    "description": [],
                    "ingredients": [],
                    "instructions": [],
                }
                current_field = None
                continue

            if line == recipe_end_marker:
                if current_recipe is not None:
                    recipes_to_import.append(
                        {
                            key: "\n".join(value).strip()
                            for key, value in current_recipe.items()
                        }
                    )
                current_recipe = None
                current_field = None
                continue

            if current_recipe is None:
                continue

            if line in export_fields:
                current_field = export_fields[line]
                continue

            if current_field:
                current_recipe[current_field].append(line)

        if current_recipe is not None:
            recipes_to_import.append(
                {
                    key: "\n".join(value).strip()
                    for key, value in current_recipe.items()
                }
            )

        return recipes_to_import

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

    @app.route("/recipes/export")
    @login_required
    def export_recipes():
        recipe_list = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.title.asc()).all()
        export_text = build_recipe_export(recipe_list)

        return Response(
            export_text,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=recipe-vault-export.txt"},
        )

    @app.route("/recipes/import", methods=["POST"])
    @login_required
    def import_recipes():
        export_file = request.files.get("recipe_export")

        if not export_file or not export_file.filename:
            flash("Please choose a recipe export text file to import.", "danger")
            return redirect(url_for("recipes"))

        export_text = export_file.read().decode("utf-8-sig", errors="replace")
        imported_recipe_data = parse_recipe_export(export_text)
        imported_recipes = []

        for recipe_data in imported_recipe_data:
            if not recipe_data["title"] or not recipe_data["ingredients"]:
                continue

            recipe = Recipe(
                title=recipe_data["title"],
                description=recipe_data["description"],
                instructions=recipe_data["instructions"],
                user_id=current_user.id,
            )
            recipe.ingredients = parse_ingredients(recipe_data["ingredients"])
            imported_recipes.append(recipe)

        if not imported_recipes:
            flash("No valid recipes were found in that file.", "danger")
            return redirect(url_for("recipes"))

        db.session.add_all(imported_recipes)
        db.session.commit()
        flash(f"Imported {len(imported_recipes)} recipes.", "success")

        return redirect(url_for("recipes"))

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

        photo = get_uploaded_image("photo")
        chef_photo = get_uploaded_image("chef_photo")
        photo_error = validate_uploaded_image(photo)
        chef_photo_error = validate_uploaded_image(chef_photo)
        upload_error = photo_error or chef_photo_error

        if upload_error:
            flash(upload_error, "danger")
            return render_template("recipe_form.html", recipe=None, ingredients_text=ingredients_text)

        photo_filename = save_uploaded_image(photo)
        chef_photo_filename = save_uploaded_image(chef_photo)

        recipe = Recipe(
            title=title,
            description=description,
            instructions=instructions,
            photo_filename=photo_filename,
            chef_photo_filename=chef_photo_filename,
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
        photo = get_uploaded_image("photo")
        chef_photo = get_uploaded_image("chef_photo")
        photo_error = validate_uploaded_image(photo)
        chef_photo_error = validate_uploaded_image(chef_photo)
        upload_error = photo_error or chef_photo_error

        if upload_error:
            flash(upload_error, "danger")
            return render_template(
                "recipe_form.html",
                recipe=recipe,
                ingredients_text=request.form.get("ingredients", ""),
            )

        photo_filename = save_uploaded_image(photo)
        chef_photo_filename = save_uploaded_image(chef_photo)

        if photo_filename:
            recipe.photo_filename = photo_filename

        if chef_photo_filename:
            recipe.chef_photo_filename = chef_photo_filename

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
