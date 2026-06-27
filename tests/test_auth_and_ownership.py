import unittest

from app import create_app
from app.extensions import db


class AuthAndOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SECRET_KEY": "test-secret",
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
