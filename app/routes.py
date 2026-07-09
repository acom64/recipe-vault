import os
import re
import zipfile
from collections import OrderedDict
from io import BytesIO
from uuid import uuid4

from flask import Response, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

from .extensions import db
from .models import (
    Ingredient,
    PlannedMeal,
    Recipe,
    ShoppingListItemState,
    User,
    format_ingredients,
    format_quantity,
    parse_ingredients,
)


def register_routes(app):
    app.jinja_env.filters["quantity"] = format_quantity

    allowed_image_extensions = {"jpg", "jpeg", "png", "gif", "webp"}
    food_categories = [
        "Breakfast",
        "Sandwiches",
        "Salads",
        "Bowls",
        "Soups",
        "Pastas",
        "Tacos",
        "Stir-fries",
        "Sheet Pan",
        "Slow Cooker",
        "Baking",
        "Drinks",
        "Desserts",
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
        "Prep Time:": "prep_time",
        "Cook Time:": "cook_time",
        "Servings:": "servings",
        "Notes:": "notes",
        "Favorite:": "is_favorite",
        "Recipe Photo:": "photo_filename",
        "Chef Photo:": "chef_photo_filename",
        "Ingredients:": "ingredients",
        "Instructions:": "instructions",
    }
    shopping_group_order = OrderedDict(
        [
            ("Produce", ("onion", "tomato", "pepper", "lettuce", "spinach", "garlic", "carrot", "celery", "potato", "herb", "cilantro", "parsley", "lemon", "lime", "apple", "banana", "berry", "mushroom", "avocado")),
            ("Protein", ("chicken", "beef", "pork", "turkey", "fish", "salmon", "shrimp", "tofu", "egg", "sausage", "bacon", "beans")),
            ("Dairy", ("milk", "cream", "cheese", "yogurt", "butter", "parmesan", "mozzarella", "cheddar")),
            ("Bakery", ("bread", "bun", "roll", "tortilla", "pita", "bagel")),
            ("Pantry", ("flour", "sugar", "rice", "pasta", "noodle", "oil", "vinegar", "broth", "stock", "can", "sauce", "honey", "oats", "quinoa")),
            ("Spices", ("salt", "pepper", "paprika", "cumin", "oregano", "basil", "cinnamon", "chili", "spice", "seasoning")),
            ("Frozen", ("frozen", "ice")),
            ("Beverages", ("juice", "soda", "coffee", "tea", "wine", "beer")),
        ]
    )

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
            recipe.total_time = (recipe.prep_time or 0) + (recipe.cook_time or 0)

        return recipe_list

    def recipe_form_values(recipe=None, overrides=None):
        values = {
            "title": "",
            "description": "",
            "food_category": "",
            "prep_time": "",
            "cook_time": "",
            "servings": "",
            "notes": "",
            "instructions": "",
            "is_favorite": False,
        }

        if recipe:
            values.update(
                {
                    "title": recipe.title or "",
                    "description": recipe.description or "",
                    "food_category": recipe.food_category or "",
                    "prep_time": recipe.prep_time or "",
                    "cook_time": recipe.cook_time or "",
                    "servings": recipe.servings or "",
                    "notes": recipe.notes or "",
                    "instructions": recipe.instructions or "",
                    "is_favorite": bool(recipe.is_favorite),
                }
            )

        if overrides:
            values.update(overrides)

        return values

    def get_recipe_form_values():
        return {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "food_category": request.form.get("food_category", "").strip(),
            "prep_time": request.form.get("prep_time", "").strip(),
            "cook_time": request.form.get("cook_time", "").strip(),
            "servings": request.form.get("servings", "").strip(),
            "notes": request.form.get("notes", "").strip(),
            "instructions": request.form.get("instructions", "").strip(),
            "is_favorite": bool(request.form.get("is_favorite")),
        }

    def parse_optional_positive_int(field_name, label, allow_zero=True):
        raw_value = request.form.get(field_name, "").strip()

        if not raw_value:
            return None, None

        try:
            value = int(raw_value)
        except ValueError:
            return None, f"{label} must be a whole number."

        if value < 0 or (value == 0 and not allow_zero):
            return None, f"{label} must be {'zero or greater' if allow_zero else 'at least 1'}."

        return value, None

    def parse_recipe_numbers():
        prep_time, prep_error = parse_optional_positive_int("prep_time", "Prep time")
        cook_time, cook_error = parse_optional_positive_int("cook_time", "Cook time")
        servings, servings_error = parse_optional_positive_int("servings", "Servings", allow_zero=False)
        errors = [error for error in (prep_error, cook_error, servings_error) if error]

        return prep_time, cook_time, servings, errors

    def get_all_food_categories():
        if not current_user.is_authenticated:
            return food_categories

        user_food_categories = [
            category
            for (category,) in db.session.query(Recipe.food_category)
            .filter(Recipe.user_id == current_user.id, Recipe.food_category.isnot(None), Recipe.food_category != "")
            .distinct()
            .order_by(Recipe.food_category.asc())
            .all()
        ]

        return sorted(set(food_categories + user_food_categories))

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

    def uploaded_image_path(filename):
        if not filename:
            return None

        safe_filename = secure_filename(filename)

        if safe_filename != filename:
            return None

        image_path = os.path.join(current_app.config["UPLOAD_FOLDER"], safe_filename)

        if not os.path.isfile(image_path):
            return None

        return image_path

    def zip_image_member(filename):
        safe_filename = secure_filename(filename or "")

        if not safe_filename:
            return None

        return f"uploads/{safe_filename}"

    def save_image_from_backup(zip_file, filename):
        member_name = zip_image_member(filename)

        if not member_name or member_name not in zip_file.namelist():
            return None

        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in allowed_image_extensions:
            return None

        saved_filename = f"{uuid4().hex}_{secure_filename(filename)}"
        destination_path = os.path.join(current_app.config["UPLOAD_FOLDER"], saved_filename)

        with zip_file.open(member_name) as source, open(destination_path, "wb") as destination:
            destination.write(source.read())

        return saved_filename

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
                    "Prep Time:",
                    str(recipe.prep_time or ""),
                    "Cook Time:",
                    str(recipe.cook_time or ""),
                    "Servings:",
                    str(recipe.servings or ""),
                    "Notes:",
                    recipe.notes or "",
                    "Favorite:",
                    "yes" if recipe.is_favorite else "no",
                    "Recipe Photo:",
                    recipe.photo_filename or "",
                    "Chef Photo:",
                    recipe.chef_photo_filename or "",
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
                    "prep_time": [],
                    "cook_time": [],
                    "servings": [],
                    "notes": [],
                    "is_favorite": [],
                    "photo_filename": [],
                    "chef_photo_filename": [],
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

    def parse_export_int(value):
        value = (value or "").strip()

        if not value:
            return None

        try:
            parsed_value = int(value)
        except ValueError:
            return None

        return parsed_value if parsed_value > 0 else None

    def parse_export_bool(value):
        return (value or "").strip().lower() in {"1", "true", "yes", "y", "favorite"}

    def ingredient_group(name):
        normalized_name = (name or "").lower()

        for group, keywords in shopping_group_order.items():
            if any(keyword in normalized_name for keyword in keywords):
                return group

        return "Other"

    def shopping_item_key(name, unit):
        return f"{(name or '').strip().lower()}|{(unit or '').strip().lower()}"

    def ingredient_line(ingredient):
        parts = []

        if ingredient.get("quantity") is not None:
            parts.append(format_quantity(ingredient["quantity"]))

        if ingredient.get("unit"):
            parts.append(ingredient["unit"])

        parts.append(ingredient["name"])

        return " ".join(part for part in parts if part).strip()

    def shopping_text_from_items(items):
        if not items:
            return "Recipe Vault Shopping List\n\nNo shopping items yet."

        lines = ["Recipe Vault Shopping List", ""]
        current_group = None

        for item in items:
            if item["group"] != current_group:
                current_group = item["group"]
                lines.extend([current_group, "-" * len(current_group)])

            lines.append(ingredient_line(item))

        return "\n".join(lines)

    def build_shopping_list(user, include_state=True):
        planned_meals = PlannedMeal.query.filter_by(user_id=user.id).all()
        grouped_ingredients = {}

        for planned_meal in planned_meals:
            if not planned_meal.recipe:
                continue

            for ingredient in planned_meal.recipe.ingredients:
                unit = ingredient.unit or ""
                key = shopping_item_key(ingredient.name, unit)

                if key in grouped_ingredients:
                    existing_ingredient = grouped_ingredients[key]

                    if (
                        existing_ingredient["quantity"] is not None
                        and ingredient.quantity is not None
                    ):
                        existing_ingredient["quantity"] += ingredient.quantity
                else:
                    grouped_ingredients[key] = {
                        "key": key,
                        "name": ingredient.name,
                        "quantity": ingredient.quantity,
                        "unit": unit,
                        "group": ingredient_group(ingredient.name),
                        "checked": False,
                    }

        items = sorted(
            grouped_ingredients.values(),
            key=lambda item: (
                list(shopping_group_order.keys()).index(item["group"])
                if item["group"] in shopping_group_order
                else len(shopping_group_order),
                item["name"].lower(),
                item["unit"].lower(),
            ),
        )

        if include_state and items:
            states = {
                state.item_key: state.checked
                for state in ShoppingListItemState.query.filter_by(user_id=user.id).all()
            }

            for item in items:
                item["checked"] = bool(states.get(item["key"]))

        return items

    def shopping_progress(items):
        total = len(items)
        checked = sum(1 for item in items if item.get("checked"))
        percent = round((checked / total) * 100) if total else 0

        return {"total": total, "checked": checked, "percent": percent}

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        return render_template("index.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        recipes_query = Recipe.query.filter_by(user_id=current_user.id)
        recipe_count = recipes_query.count()
        favorite_count = recipes_query.filter_by(is_favorite=True).count()
        planned_meals = PlannedMeal.query.filter_by(user_id=current_user.id).all()
        planned_by_day = {day: [] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}

        for planned_meal in planned_meals:
            if planned_meal.day in planned_by_day:
                planned_by_day[planned_meal.day].append(planned_meal)

        recent_recipes = attach_recipe_display_data(
            recipes_query.order_by(Recipe.created_at.desc(), Recipe.id.desc()).limit(5).all()
        )
        shopping_items = build_shopping_list(current_user)
        progress = shopping_progress(shopping_items)

        return render_template(
            "dashboard.html",
            recipe_count=recipe_count,
            favorite_count=favorite_count,
            planned_meals=planned_meals,
            planned_by_day=planned_by_day,
            recent_recipes=recent_recipes,
            shopping_items=shopping_items[:6],
            shopping_progress=progress,
            meal_type_label=meal_type_label,
        )

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

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
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            remember = request.form.get("remember") == "1"

            if not username or not password:
                flash("Please enter both a username and password.", "danger")
                return render_template("login.html", username=username, remember=remember)

            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user, remember=remember)
                flash(f"Welcome back, {user.username}!", "success")
                return redirect(request.args.get("next") or url_for("dashboard"))

            flash("Invalid username or password.", "danger")
            return render_template("login.html", username=username, remember=remember)

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
        selected_favorite = request.args.get("favorite") == "1"
        query = Recipe.query.filter_by(user_id=current_user.id)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    Recipe.title.ilike(search_pattern),
                    Recipe.description.ilike(search_pattern),
                    Recipe.notes.ilike(search_pattern),
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

        if selected_favorite:
            query = query.filter_by(is_favorite=True)

        sort_options = {
            "title": Recipe.title.asc(),
            "food_category": Recipe.food_category.asc(),
            "meal_type": Recipe.meal_type.asc(),
            "newest": Recipe.created_at.desc(),
            "favorites": Recipe.is_favorite.desc(),
            "quickest": (db.func.coalesce(Recipe.prep_time, 0) + db.func.coalesce(Recipe.cook_time, 0)).asc(),
        }
        recipe_list = attach_recipe_display_data(
            query.order_by(sort_options.get(selected_sort, Recipe.title.asc()), Recipe.title.asc()).all()
        )

        return render_template(
            "recipes.html",
            recipes=recipe_list,
            food_categories=get_all_food_categories(),
            meal_types=meal_types,
            meal_plan_slots=meal_plan_slots,
            days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            search_query=search_query,
            selected_food_category=selected_food_category,
            selected_meal_type=selected_meal_type,
            selected_sort=selected_sort,
            selected_favorite=selected_favorite,
            recipe_count=Recipe.query.filter_by(user_id=current_user.id).count(),
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

    @app.route("/recipes/export/backup")
    @login_required
    def export_recipe_backup():
        recipe_list = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.title.asc()).all()
        export_text = build_recipe_export(recipe_list)
        archive_buffer = BytesIO()
        added_images = set()

        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as backup_zip:
            backup_zip.writestr("recipe-vault-export.txt", export_text)

            for recipe in recipe_list:
                for filename in (recipe.photo_filename, recipe.chef_photo_filename):
                    image_path = uploaded_image_path(filename)

                    if not image_path or filename in added_images:
                        continue

                    backup_zip.write(image_path, zip_image_member(filename))
                    added_images.add(filename)

        archive_buffer.seek(0)

        return send_file(
            archive_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name="recipe-vault-backup.zip",
        )

    @app.route("/recipes/import", methods=["POST"])
    @login_required
    def import_recipes():
        export_file = request.files.get("recipe_export")

        if not export_file or not export_file.filename:
            flash("Please choose a recipe export text or backup ZIP file to import.", "danger")
            return redirect(url_for("recipes"))

        backup_zip = None

        if export_file.filename.lower().endswith(".zip"):
            try:
                backup_zip = zipfile.ZipFile(BytesIO(export_file.read()))
                export_text = backup_zip.read("recipe-vault-export.txt").decode("utf-8-sig", errors="replace")
            except (KeyError, zipfile.BadZipFile):
                flash("That backup ZIP does not contain a valid Recipe Vault export.", "danger")
                return redirect(url_for("recipes"))
        else:
            export_text = export_file.read().decode("utf-8-sig", errors="replace")

        imported_recipe_data = parse_recipe_export(export_text)
        imported_recipes = []

        for recipe_data in imported_recipe_data:
            if not recipe_data["title"] or not recipe_data["ingredients"]:
                continue

            photo_filename = None
            chef_photo_filename = None

            if backup_zip:
                photo_filename = save_image_from_backup(backup_zip, recipe_data.get("photo_filename", ""))
                chef_photo_filename = save_image_from_backup(backup_zip, recipe_data.get("chef_photo_filename", ""))

            recipe = Recipe(
                title=recipe_data["title"],
                description=recipe_data["description"],
                food_category=recipe_data.get("food_category", ""),
                meal_type=serialize_meal_types(parse_meal_types(recipe_data.get("meal_type", ""))),
                prep_time=parse_export_int(recipe_data.get("prep_time", "")),
                cook_time=parse_export_int(recipe_data.get("cook_time", "")),
                servings=parse_export_int(recipe_data.get("servings", "")),
                notes=recipe_data.get("notes", ""),
                is_favorite=parse_export_bool(recipe_data.get("is_favorite", "")),
                photo_filename=photo_filename,
                chef_photo_filename=chef_photo_filename,
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
                form_values=recipe_form_values(),
                ingredients_text="",
                food_categories=get_all_food_categories(),
                meal_types=meal_types,
                selected_meal_types=[],
            )

        form_values = get_recipe_form_values()
        title = form_values["title"]
        description = form_values["description"]
        food_category = form_values["food_category"]
        meal_type = get_selected_meal_types()
        ingredients_text = request.form.get("ingredients", "")
        instructions = form_values["instructions"]
        prep_time, cook_time, servings, number_errors = parse_recipe_numbers()

        if not title or not ingredients_text.strip():
            flash("Please add a title and at least one ingredient.", "danger")
            return render_template(
                "recipe_form.html",
                recipe=None,
                form_values=form_values,
                ingredients_text=ingredients_text,
                food_categories=get_all_food_categories(),
                meal_types=meal_types,
                selected_meal_types=parse_meal_types(meal_type),
            )

        if number_errors:
            for error in number_errors:
                flash(error, "danger")

            return render_template(
                "recipe_form.html",
                recipe=None,
                form_values=form_values,
                ingredients_text=ingredients_text,
                food_categories=get_all_food_categories(),
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
                form_values=form_values,
                ingredients_text=ingredients_text,
                food_categories=get_all_food_categories(),
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
            prep_time=prep_time,
            cook_time=cook_time,
            servings=servings,
            notes=form_values["notes"],
            is_favorite=form_values["is_favorite"],
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
                form_values=recipe_form_values(recipe),
                ingredients_text=ingredients_text,
                food_categories=get_all_food_categories(),
                meal_types=meal_types,
                selected_meal_types=selected_meal_types,
            )

        form_values = get_recipe_form_values()
        prep_time, cook_time, servings, number_errors = parse_recipe_numbers()

        if not form_values["title"] or not request.form.get("ingredients", "").strip():
            flash("Please add a title and at least one ingredient.", "danger")
            return render_template(
                "recipe_form.html",
                recipe=recipe,
                form_values=form_values,
                ingredients_text=request.form.get("ingredients", ""),
                food_categories=get_all_food_categories(),
                meal_types=meal_types,
                selected_meal_types=parse_meal_types(get_selected_meal_types()),
            )

        if number_errors:
            for error in number_errors:
                flash(error, "danger")

            return render_template(
                "recipe_form.html",
                recipe=recipe,
                form_values=form_values,
                ingredients_text=request.form.get("ingredients", ""),
                food_categories=get_all_food_categories(),
                meal_types=meal_types,
                selected_meal_types=parse_meal_types(get_selected_meal_types()),
            )

        recipe.title = form_values["title"]
        recipe.description = form_values["description"]
        recipe.food_category = form_values["food_category"]
        recipe.meal_type = get_selected_meal_types()
        recipe.prep_time = prep_time
        recipe.cook_time = cook_time
        recipe.servings = servings
        recipe.notes = form_values["notes"]
        recipe.is_favorite = form_values["is_favorite"]
        recipe.instructions = form_values["instructions"]
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
                form_values=form_values,
                ingredients_text=request.form.get("ingredients", ""),
                food_categories=get_all_food_categories(),
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

        PlannedMeal.query.filter_by(recipe_id=recipe.id, user_id=current_user.id).delete()
        db.session.delete(recipe)
        db.session.commit()
        flash("Recipe deleted.", "success")

        return redirect(url_for("recipes"))

    @app.route("/recipes/<int:recipe_id>/duplicate", methods=["POST"])
    @login_required
    def duplicate_recipe(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first_or_404()
        duplicate = Recipe(
            title=f"Copy of {recipe.title}",
            description=recipe.description,
            food_category=recipe.food_category,
            meal_type=recipe.meal_type,
            prep_time=recipe.prep_time,
            cook_time=recipe.cook_time,
            servings=recipe.servings,
            notes=recipe.notes,
            is_favorite=recipe.is_favorite,
            instructions=recipe.instructions,
            photo_filename=recipe.photo_filename,
            chef_photo_filename=recipe.chef_photo_filename,
            user_id=current_user.id,
        )
        duplicate.ingredients = [
            Ingredient(name=ingredient.name, quantity=ingredient.quantity, unit=ingredient.unit)
            for ingredient in recipe.ingredients
        ]

        db.session.add(duplicate)
        db.session.commit()
        flash(f"Duplicated {recipe.title}.", "success")

        return redirect(url_for("edit_recipe", recipe_id=duplicate.id))

    @app.route("/recipes/<int:recipe_id>/favorite", methods=["POST"])
    @login_required
    def toggle_favorite_recipe(recipe_id):
        recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first_or_404()
        recipe.is_favorite = not recipe.is_favorite
        db.session.commit()

        message = f"{recipe.title} {'added to' if recipe.is_favorite else 'removed from'} favorites."

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                {
                    "status": "saved",
                    "is_favorite": recipe.is_favorite,
                    "message": message,
                    "button_label": "Favorited" if recipe.is_favorite else "Favorite",
                    "aria_label": "Remove favorite" if recipe.is_favorite else "Favorite",
                }
            )

        flash(
            message,
            "success",
        )

        return redirect(request.form.get("next") or url_for("recipe_detail", recipe_id=recipe.id))

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
        day_order = {day: index for index, day in enumerate(days)}
        slot_order = {slot: index for index, (slot, _label) in enumerate(meal_plan_slots)}
        planned_meals.sort(
            key=lambda planned_meal: (
                day_order.get(planned_meal.day, 99),
                slot_order.get(planned_meal.meal_type, 99),
            )
        )
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
        progress = shopping_progress(planned_ingredients)

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
            shopping_progress=progress,
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
        progress = shopping_progress(planned_ingredients)

        return render_template(
            "shopping_list.html",
            planned_ingredients=planned_ingredients,
            shopping_progress=progress,
            shopping_text=shopping_text_from_items(planned_ingredients),
        )

    @app.route("/shopping-list/item", methods=["POST"])
    @login_required
    def update_shopping_item():
        data = request.get_json(silent=True) or request.form
        item_key = (data.get("item_key") or "").strip()
        checked = str(data.get("checked", "")).lower() in {"1", "true", "on", "yes"}
        current_items = build_shopping_list(current_user, include_state=False)
        valid_keys = {item["key"] for item in current_items}

        if item_key not in valid_keys:
            return jsonify({"status": "error", "message": "Shopping item was not found."}), 400

        state = ShoppingListItemState.query.filter_by(user_id=current_user.id, item_key=item_key).first()

        if not state:
            state = ShoppingListItemState(user_id=current_user.id, item_key=item_key)
            db.session.add(state)

        state.checked = checked
        db.session.commit()

        updated_items = build_shopping_list(current_user)

        return jsonify({"status": "saved", "progress": shopping_progress(updated_items)})

    @app.route("/shopping-list/reset", methods=["POST"])
    @login_required
    def reset_shopping_list():
        ShoppingListItemState.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash("Shopping list progress reset.", "success")

        return redirect(url_for("shopping_list"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            action = request.form.get("action")

            if action == "profile":
                username = request.form.get("username", "").strip()

                if not username:
                    flash("Username cannot be blank.", "danger")
                elif User.query.filter(User.username == username, User.id != current_user.id).first():
                    flash("That username is already taken.", "danger")
                else:
                    current_user.username = username
                    db.session.commit()
                    flash("Profile updated.", "success")

                return redirect(url_for("settings"))

            if action == "password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")

                if not current_user.check_password(current_password):
                    flash("Current password is incorrect.", "danger")
                elif len(new_password.strip()) < 6:
                    flash("New password must be at least 6 characters long.", "danger")
                else:
                    current_user.set_password(new_password.strip())
                    db.session.commit()
                    flash("Password updated.", "success")

                return redirect(url_for("settings"))

            flash("Choose a valid settings action.", "danger")
            return redirect(url_for("settings"))

        return render_template("settings.html")

    return app
