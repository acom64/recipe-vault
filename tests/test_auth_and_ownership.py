from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

from app import create_app
from app.extensions import db
from app.models import Recipe


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
        self.assertEqual(imported_recipe.instructions, "Mix\nCook on a skillet")
        self.assertEqual(len(imported_recipe.ingredients), 2)

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


if __name__ == "__main__":
    unittest.main()
