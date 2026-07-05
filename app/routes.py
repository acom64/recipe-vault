import os
import re
from uuid import uuid4

from flask import Response, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Ingredient, PlannedMeal, Recipe, User, format_ingredients, parse_ingredients


def register_routes(app):
    allowed_image_extensions = {"jpg", "jpeg", "png", "gif", "webp"}
    food_categories = [
        "Sandwiches",
        "Salads",
        "Bowls",
        "Soups",
        "Pastas",
        "Tacos",
        "Stir-fries",
        "Drinks",
    ]
    meal_types = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("cocktails", "Cocktails"),
        ("snacks", "Snacks"),
        ("appetizers", "Appetizers"),
        ("sides", "Sides"),
        ("desserts", "Desserts")
    ]
    meal_plan_slots = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
    ]
    export_header = "Recipe Vault Export"
    recipe_start_marker = "--- Recipe ---"
    recipe_end_marker = "--- End Recipe ---"
    export_fields = {
        "Title:": "title",
        "Description:": "description",
        "Food Category:": "food_category",
        "Meal Type:": "meal_type",
        "Ingredients:": "ingredients",
        "Instructions:": "instructions",
    }

    def meal_type_label(meal_type):
        return dict(meal_types).get(meal_type, meal_type.title() if meal_type else "")

    def parse_meal_types(meal_type_text):
        if not meal_type_text:
            return []

        return [meal_type.strip() for meal_type in meal_type_text.split(",") if meal_type.strip()]

    def serialize_meal_types(selected_meal_types):
        valid_meal_types = {value for value, _label in meal_types}
        unique_meal_types = []

        for meal_type in selected_meal_types:
            if meal_type in valid_meal_types and meal_type not in unique_meal_types:
                unique_meal_types.append(meal_type)

        return ",".join(unique_meal_types)

    def get_selected_meal_types():
        return serialize_meal_types(request.form.getlist("meal_type"))

    def meal_type_labels(meal_type_text):
        return [meal_type_label(meal_type) for meal_type in parse_meal_types(meal_type_text)]

    def attach_recipe_display_data(recipe_list):
        for recipe in recipe_list:
            recipe.meal_type_values = parse_meal_types(recipe.meal_type)
            recipe.meal_type_labels = meal_type_labels(recipe.meal_type)

        return recipe_list

    def meal_plan_draft_key():
        return f"meal_plan_draft_{current_user.id}"

    def empty_meal_plan_draft():
        return {
            "include_breakfast": False,
            "include_lunch": False,
            "meals": {},
        }

    def get_meal_plan_draft():
        draft = session.get(meal_plan_draft_key())

        if not isinstance(draft, dict):
            return None

        meals = draft.get("meals", {})

        if not isinstance(meals, dict):
            meals = {}

        return {
            "include_breakfast": bool(draft.get("include_breakfast")),
            "include_lunch": bool(draft.get("include_lunch")),
            "meals": {
                key: str(value)
                for key, value in meals.items()
                if isinstance(key, str) and str(value).isdigit()
            },
        }

    def save_meal_plan_draft(draft):
        session[meal_plan_draft_key()] = draft
        session.modified = True

    def clear_meal_plan_draft():
        session.pop(meal_plan_draft_key(), None)
        session.modified = True

    def build_meal_plan_draft_from_form(days):
        draft = {
            "include_breakfast": bool(request.form.get("include_breakfast")),
            "include_lunch": bool(request.form.get("include_lunch")),
            "meals": {},
        }
        valid_slots = {slot for slot, _label in meal_plan_slots}
        valid_days = {day.lower() for day in days}

        for field_name, recipe_id in request.form.items():
            if not recipe_id or not recipe_id.isdigit() or "_" not in field_name:
                continue

            slot, day_key = field_name.split("_", 1)

            if slot in valid_slots and day_key in valid_days:
                draft["meals"][field_name] = recipe_id

        return draft

    def build_planned_lookup_from_draft(draft, recipe_ids):
        planned_lookup = {}

        if not draft:
            return planned_lookup

        for field_name, recipe_id in draft["meals"].items():
            if "_" not in field_name:
                continue

            slot, day_key = field_name.split("_", 1)

            if int(recipe_id) not in recipe_ids:
                continue

            planned_lookup[(day_key.title(), slot)] = int(recipe_id)

        return planned_lookup

    def render_inline_markdown(text):
        rendered = str(escape(text))
        rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
        rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
        rendered = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", rendered)
        rendered = re.sub(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
            r'<a href="\2" rel="noopener noreferrer">\1</a>',
            rendered,
        )

        return rendered

    def render_markdown(text):
        if not text:
            return Markup("")

        html = []
        paragraph = []
        list_type = None
        alignment_class = None
        alignment_classes = {
            "left": "text-start",
            "center": "text-center",
            "right": "text-end",
        }

        def close_paragraph():
            if paragraph:
                html.append(f"<p>{render_inline_markdown(' '.join(paragraph))}</p>")
                paragraph.clear()

        def close_list():
            nonlocal list_type
            if list_type:
                html.append(f"</{list_type}>")
                list_type = None

        def close_alignment():
            nonlocal alignment_class
            if alignment_class:
                html.append("</div>")
                alignment_class = None

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                close_paragraph()
                close_list()
                continue

            alignment_start = re.match(r"^:::\s*(left|center|right)$", line)
            if alignment_start:
                close_paragraph()
                close_list()
                close_alignment()
                alignment_class = alignment_classes[alignment_start.group(1)]
                html.append(f'<div class="{alignment_class}">')
                continue

            if line == ":::":
                close_paragraph()
                close_list()
                close_alignment()
                continue

            heading = re.match(r"^(#{1,4})\s+(.+)$", line)
            unordered_item = re.match(r"^[-*]\s+(.+)$", line)
            ordered_item = re.match(r"^(\d+)[.)]\s+(.+)$", line)

            if heading:
                close_paragraph()
                close_list()
                level = len(heading.group(1)) + 1
                html.append(f"<h{level}>{render_inline_markdown(heading.group(2))}</h{level}>")
                continue

            if unordered_item or ordered_item:
                close_paragraph()
                next_list_type = "ul" if unordered_item else "ol"
                item_text = unordered_item.group(1) if unordered_item else ordered_item.group(2)

                if list_type != next_list_type:
                    close_list()
                    if ordered_item:
                        start = ordered_item.group(1)
                        start_attr = f' start="{start}"' if start != "1" else ""
                        html.append(f"<{next_list_type}{start_attr}>")
                    else:
                        html.append(f"<{next_list_type}>")
                    list_type = next_list_type

                html.append(f"<li>{render_inline_markdown(item_text)}</li>")
                continue

            close_list()
            paragraph.append(line)

        close_paragraph()
        close_list()
        close_alignment()

        return Markup("\n".join(html))

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
                    "Food Category:",
                    recipe.food_category or "",
                    "Meal Type:",
                    recipe.meal_type or "",
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
                    "food_category": [],
                    "meal_type": [],
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
        search_query = request.args.get("q", "").strip()
        selected_food_category = request.args.get("food_category", "").strip()
        selected_meal_type = request.args.get("meal_type", "").strip()
        selected_sort = request.args.get("sort", "title")
        query = Recipe.query.filter_by(user_id=current_user.id)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    Recipe.title.ilike(search_pattern),
                    Recipe.description.ilike(search_pattern),
                    Recipe.instructions.ilike(search_pattern),
                    Recipe.ingredients.any(Ingredient.name.ilike(search_pattern)),
                )
            )

        if selected_food_category:
            query = query.filter(Recipe.food_category == selected_food_category)

        if selected_meal_type:
            query = query.filter(
                db.or_(
                    Recipe.meal_type == selected_meal_type,
                    Recipe.meal_type.like(f"{selected_meal_type},%"),
                    Recipe.meal_type.like(f"%,{selected_meal_type}"),
                    Recipe.meal_type.like(f"%,{selected_meal_type},%"),
                )
            )

        sort_options = {
            "title": Recipe.title.asc(),
            "food_category": Recipe.food_category.asc(),
            "meal_type": Recipe.meal_type.asc(),
        }
        recipe_list = attach_recipe_display_data(
            query.order_by(sort_options.get(selected_sort, Recipe.title.asc()), Recipe.title.asc()).all()
        )
        user_food_categories = [
            category
            for (category,) in db.session.query(Recipe.food_category)
            .filter(Recipe.user_id == current_user.id, Recipe.food_category.isnot(None), Recipe.food_category != "")
            .distinct()
            .order_by(Recipe.food_category.asc())
            .all()
        ]
        all_food_categories = sorted(set(food_categories + user_food_categories))

        return render_template(
            "recipes.html",
            recipes=recipe_list,
            food_categories=all_food_categories,
            meal_types=meal_types,
            meal_plan_slots=meal_plan_slots,
            days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            search_query=search_query,
            selected_food_category=selected_food_category,
            selected_meal_type=selected_meal_type,
            selected_sort=selected_sort,
        )

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
                food_category=recipe_data.get("food_category", ""),
                meal_type=serialize_meal_types(parse_meal_types(recipe_data.get("meal_type", ""))),
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
        attach_recipe_display_data([recipe])
        return render_template(
            "recipe_details.html",
            recipe=recipe,
            rendered_instructions=render_markdown(recipe.instructions),
        )

    @app.route("/recipes/new", methods=["GET", "POST"])
    @login_required
    def new_recipe():
        if request.method == "GET":
            return render_template(
                "recipe_form.html",
                recipe=None,
                ingredients_text="",
                food_categories=food_categories,
                meal_types=meal_types,
                selected_meal_types=[],
            )

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        food_category = request.form.get("food_category", "").strip()
        meal_type = get_selected_meal_types()
        ingredients_text = request.form.get("ingredients", "")
        instructions = request.form.get("instructions", "").strip()

        if not title or not ingredients_text.strip():
            flash("Please add a title and at least one ingredient.", "danger")
            return render_template(
                "recipe_form.html",
                recipe=None,
                ingredients_text=ingredients_text,
                food_categories=food_categories,
                meal_types=meal_types,
                selected_meal_types=parse_meal_types(meal_type),
            )

        photo = get_uploaded_image("photo")
        chef_photo = get_uploaded_image("chef_photo")
        photo_error = validate_uploaded_image(photo)
        chef_photo_error = validate_uploaded_image(chef_photo)
        upload_error = photo_error or chef_photo_error

        if upload_error:
            flash(upload_error, "danger")
            return render_template(
                "recipe_form.html",
                recipe=None,
                ingredients_text=ingredients_text,
                food_categories=food_categories,
                meal_types=meal_types,
                selected_meal_types=parse_meal_types(meal_type),
            )

        photo_filename = save_uploaded_image(photo)
        chef_photo_filename = save_uploaded_image(chef_photo)

        recipe = Recipe(
            title=title,
            description=description,
            food_category=food_category,
            meal_type=meal_type,
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
            selected_meal_types = parse_meal_types(recipe.meal_type)

            return render_template(
                "recipe_form.html",
                recipe=recipe,
                ingredients_text=ingredients_text,
                food_categories=food_categories,
                meal_types=meal_types,
                selected_meal_types=selected_meal_types,
            )

        recipe.title = request.form.get("title", "").strip()
        recipe.description = request.form.get("description", "").strip()
        recipe.food_category = request.form.get("food_category", "").strip()
        recipe.meal_type = get_selected_meal_types()
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
                food_categories=food_categories,
                meal_types=meal_types,
                selected_meal_types=parse_meal_types(recipe.meal_type),
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
            valid_recipe_ids = {
                recipe_id
                for (recipe_id,) in Recipe.query.filter_by(user_id=current_user.id).with_entities(Recipe.id).all()
            }
            selected_slots = ["dinner"]

            if request.form.get("include_breakfast"):
                selected_slots.insert(0, "breakfast")

            if request.form.get("include_lunch"):
                selected_slots.insert(-1, "lunch")

            for day in days:
                for meal_type in selected_slots:
                    recipe_id = request.form.get(f"{meal_type}_{day.lower()}", "")

                    if not recipe_id or not recipe_id.isdigit() or int(recipe_id) not in valid_recipe_ids:
                        continue

                    planned_meal = PlannedMeal(
                        day=day,
                        meal_type=meal_type,
                        recipe_id=int(recipe_id),
                        user_id=current_user.id,
                    )

                    db.session.add(planned_meal)

            db.session.commit()
            clear_meal_plan_draft()
            flash("Meal plan saved.", "success")
            return redirect(url_for("meal_plan"))

        planned_meals = PlannedMeal.query.filter_by(user_id=current_user.id).all()
        planned_lookup = {(planned_meal.day, planned_meal.meal_type): planned_meal.recipe_id for planned_meal in planned_meals}
        draft = get_meal_plan_draft()
        recipe_ids = {recipe.id for recipe in recipes}
        has_draft = draft is not None

        if draft:
            planned_lookup = build_planned_lookup_from_draft(draft, recipe_ids)

        show_breakfast = (
            draft["include_breakfast"] if draft else any(planned_meal.meal_type == "breakfast" for planned_meal in planned_meals)
        )
        show_lunch = (
            draft["include_lunch"] if draft else any(planned_meal.meal_type == "lunch" for planned_meal in planned_meals)
        )
        planned_ingredients = build_shopping_list(current_user)

        return render_template(
            "meal_plan.html",
            recipes=recipes,
            days=days,
            planned_meals=planned_meals,
            planned_lookup=planned_lookup,
            meal_plan_slots=meal_plan_slots,
            meal_type_label=meal_type_label,
            show_breakfast=show_breakfast,
            show_lunch=show_lunch,
            has_draft=has_draft,
            planned_ingredients=planned_ingredients,
        )

    @app.route("/meal-plan/draft", methods=["POST"])
    @login_required
    def save_meal_plan_draft_route():
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        draft = build_meal_plan_draft_from_form(days)
        valid_recipe_ids = {
            str(recipe_id)
            for (recipe_id,) in Recipe.query.filter_by(user_id=current_user.id).with_entities(Recipe.id).all()
        }
        draft["meals"] = {
            field_name: recipe_id
            for field_name, recipe_id in draft["meals"].items()
            if recipe_id in valid_recipe_ids
        }
        save_meal_plan_draft(draft)

        return jsonify({"status": "saved"})

    @app.route("/meal-plan/draft/add", methods=["POST"])
    @login_required
    def add_recipe_to_meal_plan_draft():
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        valid_day_keys = {day.lower() for day in days}
        valid_slots = {slot for slot, _label in meal_plan_slots}
        recipe_id = request.form.get("recipe_id", "")
        day_key = request.form.get("day", "").strip().lower()
        meal_type = request.form.get("meal_type", "").strip()

        recipe = None

        if recipe_id.isdigit():
            recipe = Recipe.query.filter_by(id=int(recipe_id), user_id=current_user.id).first()

        if not recipe or day_key not in valid_day_keys or meal_type not in valid_slots:
            flash("Choose a valid day and meal for that recipe.", "danger")
            return redirect(request.form.get("next") or url_for("recipes"))

        draft = get_meal_plan_draft()

        if draft is None:
            planned_meals = PlannedMeal.query.filter_by(user_id=current_user.id).all()
            draft = empty_meal_plan_draft()
            draft["include_breakfast"] = any(planned_meal.meal_type == "breakfast" for planned_meal in planned_meals)
            draft["include_lunch"] = any(planned_meal.meal_type == "lunch" for planned_meal in planned_meals)
            draft["meals"] = {
                f"{planned_meal.meal_type}_{planned_meal.day.lower()}": str(planned_meal.recipe_id)
                for planned_meal in planned_meals
            }

        if meal_type == "breakfast":
            draft["include_breakfast"] = True

        if meal_type == "lunch":
            draft["include_lunch"] = True

        draft["meals"][f"{meal_type}_{day_key}"] = str(recipe.id)
        save_meal_plan_draft(draft)
        flash(f"Added {recipe.title} to your meal plan draft.", "success")

        return redirect(request.form.get("next") or url_for("recipes"))

    @app.route("/shopping-list")
    @login_required
    def shopping_list():
        planned_ingredients = build_shopping_list(current_user)

        return render_template(
            "shopping_list.html",
            planned_ingredients=planned_ingredients,
        )

    return app
