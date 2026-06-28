from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

from app import create_app
from app.extensions import db
from app.models import PlannedMeal, Recipe


class AuthAndOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.uploads = TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SECRET_KEY": "test-secret",
                "UPLOAD_FOLDER": self.uploads.name,
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        self.uploads.cleanup()

    def register_and_login(self, username="alice"):
        self.client.post(
            "/register",
            data={"username": username, "password": "secret123"},
            follow_redirects=True,
        )
        self.client.post(
            "/login",
            data={"username": username, "password": "secret123"},
            follow_redirects=True,
        )

    def test_private_recipes_and_login_flow(self):
        register_response = self.client.post(
            "/register",
            data={"username": "alice", "password": "secret123"},
            follow_redirects=True,
        )
        self.assertIn(b"Account created", register_response.data)

        login_response = self.client.post(
            "/login",
            data={"username": "alice", "password": "secret123"},
            follow_redirects=True,
        )
        self.assertIn(b"Recipes", login_response.data)

        recipe_response = self.client.post(
            "/recipes/new",
            data={
                "title": "Pizza",
                "description": "A tasty pizza",
                "ingredients": "2 cups flour\n1 egg",
                "instructions": "Mix and bake",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Pizza", recipe_response.data)

        self.client.get("/logout", follow_redirects=True)

        self.client.post(
            "/register",
            data={"username": "bob", "password": "secret123"},
            follow_redirects=True,
        )
        self.client.post(
            "/login",
            data={"username": "bob", "password": "secret123"},
            follow_redirects=True,
        )

        recipes_response = self.client.get("/recipes")
        self.assertNotIn(b"Pizza", recipes_response.data)

    def test_recipe_and_chef_photos_are_saved_and_rendered(self):
        self.register_and_login()

        recipe_response = self.client.post(
            "/recipes/new",
            data={
                "title": "Soup",
                "description": "Cozy",
                "ingredients": "1 cup broth",
                "instructions": "Simmer",
                "photo": (BytesIO(b"recipe image"), "soup.jpg"),
                "chef_photo": (BytesIO(b"chef image"), "chef.png"),
            },
            follow_redirects=True,
        )

        recipe = Recipe.query.filter_by(title="Soup").first()

        self.assertIsNotNone(recipe)
        self.assertTrue(recipe.photo_filename.endswith("_soup.jpg"))
        self.assertTrue(recipe.chef_photo_filename.endswith("_chef.png"))
        self.assertIn(f"uploads/{recipe.photo_filename}".encode(), recipe_response.data)
        self.assertIn(f"uploads/{recipe.chef_photo_filename}".encode(), recipe_response.data)
        self.assertIn(b"Chef Photo", recipe_response.data)

    def test_recipes_can_be_exported_and_imported(self):
        self.register_and_login("dana")
        self.client.post(
            "/recipes/new",
            data={
                "title": "Pancakes",
                "description": "Weekend breakfast",
                "food_category": "Bowls",
                "meal_type": "breakfast",
                "ingredients": "1 cup flour\n2 eggs",
                "instructions": "Mix\nCook on a skillet",
            },
            follow_redirects=True,
        )

        export_response = self.client.get("/recipes/export")

        self.assertEqual(export_response.status_code, 200)
        self.assertIn("attachment", export_response.headers["Content-Disposition"])
        self.assertIn(b"Recipe Vault Export", export_response.data)
        self.assertIn(b"Pancakes", export_response.data)
        self.assertIn(b"Food Category:", export_response.data)
        self.assertIn(b"Meal Type:", export_response.data)

        self.client.get("/logout", follow_redirects=True)
        self.register_and_login("erin")

        import_response = self.client.post(
            "/recipes/import",
            data={
                "recipe_export": (
                    BytesIO(export_response.data),
                    "recipe-vault-export.txt",
                ),
            },
            follow_redirects=True,
        )
        imported_recipe = Recipe.query.filter_by(title="Pancakes").filter(Recipe.user.has(username="erin")).one()

        self.assertIn(b"Imported 1 recipes.", import_response.data)
        self.assertEqual(imported_recipe.user.username, "erin")
        self.assertEqual(imported_recipe.description, "Weekend breakfast")
        self.assertEqual(imported_recipe.food_category, "Bowls")
        self.assertEqual(imported_recipe.meal_type, "breakfast")
        self.assertEqual(imported_recipe.instructions, "Mix\nCook on a skillet")
        self.assertEqual(len(imported_recipe.ingredients), 2)

    def test_recipes_can_be_labeled_and_filtered_by_category(self):
        self.register_and_login("gina")
        self.client.post(
            "/recipes/new",
            data={
                "title": "Tomato Soup",
                "description": "Warm",
                "food_category": "Soups",
                "meal_type": "lunch",
                "ingredients": "2 cups tomatoes",
                "instructions": "Simmer",
            },
            follow_redirects=True,
        )
        self.client.post(
            "/recipes/new",
            data={
                "title": "Egg Bowl",
                "description": "Fast",
                "food_category": "Bowls",
                "meal_type": "breakfast",
                "ingredients": "2 eggs",
                "instructions": "Cook",
            },
            follow_redirects=True,
        )

        recipes_response = self.client.get("/recipes?food_category=Soups&meal_type=lunch&sort=food_category")

        self.assertIn(b"Tomato Soup", recipes_response.data)
        self.assertIn(b"Soups", recipes_response.data)
        self.assertIn(b"Lunch", recipes_response.data)
        self.assertNotIn(b"Egg Bowl", recipes_response.data)

    def test_recipe_instructions_render_markdown_safely(self):
        self.register_and_login("ivy")

        response = self.client.post(
            "/recipes/new",
            data={
                "title": "Toast",
                "description": "",
                "ingredients": "1 slice bread",
                "instructions": "# Prep\n\n- **Toast** bread\n- Add `butter`\n\n::: center\nServe warm\n:::\n\n<script>alert('x')</script>",
            },
            follow_redirects=True,
        )

        self.assertIn(b"<h2>Prep</h2>", response.data)
        self.assertIn(b"<li><strong>Toast</strong> bread</li>", response.data)
        self.assertIn(b"<code>butter</code>", response.data)
        self.assertIn(b'<div class="text-center">', response.data)
        self.assertIn(b"<p>Serve warm</p>", response.data)
        self.assertIn(b"&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;", response.data)
        self.assertNotIn(b"<script>alert('x')</script>", response.data)

    def test_numbered_instruction_steps_keep_their_numbers(self):
        self.register_and_login("jordan")

        response = self.client.post(
            "/recipes/new",
            data={
                "title": "Tea",
                "description": "",
                "ingredients": "1 cup water",
                "instructions": "1. Boil water\n\n2. Steep tea\n\n3. Serve",
            },
            follow_redirects=True,
        )

        self.assertIn(b"<ol>", response.data)
        self.assertIn(b'<ol start="2">', response.data)
        self.assertIn(b'<ol start="3">', response.data)

    def test_recipe_form_has_instruction_formatting_toolbar(self):
        self.register_and_login("jules")

        response = self.client.get("/recipes/new")

        self.assertIn(b"class=\"markdown-toolbar\"", response.data)
        self.assertIn(b"data-format=\"bullet\"", response.data)
        self.assertIn(b"data-format=\"number\"", response.data)
        self.assertIn(b"data-format=\"center\"", response.data)

    def test_recipe_form_has_polished_photo_upload_controls(self):
        self.register_and_login("kai")

        response = self.client.get("/recipes/new")
        html = response.data.decode()
        form_end = html.index("</form>")

        self.assertIn('class="photo-upload-picker"', html)
        self.assertIn('class="visually-hidden photo-upload-input"', html)
        self.assertLess(html.index('name="photo"'), form_end)
        self.assertLess(html.index('name="chef_photo"'), form_end)

    def test_import_rejects_text_without_valid_recipes(self):
        self.register_and_login("fran")

        response = self.client.post(
            "/recipes/import",
            data={
                "recipe_export": (
                    BytesIO(b"this is not a recipe export"),
                    "notes.txt",
                ),
            },
            follow_redirects=True,
        )

        self.assertIn(b"No valid recipes were found in that file.", response.data)
        self.assertEqual(Recipe.query.count(), 0)

    def test_meal_plan_requires_recipes(self):
        self.client.post(
            "/register",
            data={"username": "carol", "password": "secret123"},
            follow_redirects=True,
        )
        self.client.post(
            "/login",
            data={"username": "carol", "password": "secret123"},
            follow_redirects=True,
        )

        response = self.client.get("/meal-plan", follow_redirects=True)
        self.assertIn(b"Add a recipe before creating a meal plan.", response.data)

    def test_meal_plan_can_schedule_breakfast_lunch_and_dinner(self):
        self.register_and_login("harper")
        recipe_ids = {}

        for title, meal_type in [
            ("Oats", "breakfast"),
            ("Salad", "lunch"),
            ("Soup", "dinner"),
        ]:
            self.client.post(
                "/recipes/new",
                data={
                    "title": title,
                    "description": "",
                    "food_category": "Bowls",
                    "meal_type": meal_type,
                    "ingredients": "1 cup water",
                    "instructions": "",
                },
                follow_redirects=True,
            )
            recipe_ids[meal_type] = Recipe.query.filter_by(title=title).one().id

        initial_response = self.client.get("/meal-plan")
        self.assertIn(b"meal-slot-breakfast\" hidden", initial_response.data)
        self.assertIn(b"meal-slot-lunch\" hidden", initial_response.data)

        response = self.client.post(
            "/meal-plan",
            data={
                "include_breakfast": "1",
                "include_lunch": "1",
                "breakfast_monday": str(recipe_ids["breakfast"]),
                "lunch_monday": str(recipe_ids["lunch"]),
                "dinner_monday": str(recipe_ids["dinner"]),
            },
            follow_redirects=True,
        )

        planned_meals = PlannedMeal.query.filter_by(user_id=Recipe.query.first().user_id, day="Monday").all()
        planned_types = {planned_meal.meal_type for planned_meal in planned_meals}

        self.assertEqual(planned_types, {"breakfast", "lunch", "dinner"})
        self.assertIn(b"Breakfast:", response.data)
        self.assertIn(b"Lunch:", response.data)
        self.assertIn(b"Dinner:", response.data)


if __name__ == "__main__":
    unittest.main()
