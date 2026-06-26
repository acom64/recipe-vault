from dataclasses import dataclass, field

@dataclass
class Ingredient:
  """represents a single ingredient within a recipe"""
  name: str
  quantity: float
  unit: str
  

@dataclass
class Recipe:
  """represents a single recipe will map to database eventually"""
  id: int | None = None
  title: str = ""
  description: str = ""
  ingredients: list[Ingredient] = field(default_factory=list)
  instructions: str = ""



  @staticmethod
  def get_all(): #returns all recipes, currently using sample data as database doesn't exist

      return [
        Recipe(
          id = 1,
          title="Chicken Alfredo",
          description="Creamy pasta with chicken and parmesean",
          ingredients=[
            Ingredient(
                name="Chicken Breast",
                quantity=2,
                unit="lbs",
            )
          ],
          instructions= "cook",
        )

      ]