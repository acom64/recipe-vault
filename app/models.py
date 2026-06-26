from dataclasses import dataclass, field

@dataclass
class Ingredient:
  """Represents a single ingredient within a recipe"""
  name: str
  quantity: float
  unit: str
  

@dataclass
class Recipe:
  """Represents a single recipe will map to database eventually"""
  id: int | None = None
  title: str = ""
  description: str = ""
  ingredients: list[Ingredient] = field(default_factory=list)
  instructions: str = ""

  @staticmethod
  def get_all(): 
    """Returns all recipes, currently using sample data as database doesn't exist"""
    return RECIPES
    
  @staticmethod
  def get_by_id(recipe_id):
      """Returns recipe associated with provided id"""
      recipe_list=Recipe.get_all()
      for recipe in recipe_list:
        if recipe.id == recipe_id:
          return recipe
      return None
  
  @staticmethod
  def add(recipe):
      """Assigns an ID to a recipe and stores it in memory."""
      new_id = len(RECIPES) + 1
      recipe.id = new_id
      RECIPES.append(recipe)



RECIPES = [
   Recipe(
          id = 1,
          title="Chicken Alfredo",
          description="Creamy pasta with chicken and parmesean",
          ingredients = [
            Ingredient(
                name = "Chicken Breast",
                quantity = 2,
                unit = "lbs",
            ),
            Ingredient(
                name = "Parmesean",
                quantity = 4,
                unit = "oz",
            )
          ],
          instructions= "cook",
        ),

        Recipe(
          id = 2,
          title="Steak",
          description = "Nice Steak",
          ingredients = [
            Ingredient(
                name = "Ribeye",
                quantity = 2,
                unit = "lbs",
            )
            
          ],
          instructions = "cook",
        )
]

def parse_ingredients(ingredient_text):
  lines = ingredient_text.splitlines()
  ingredients = []
  for line in lines:
    if not line.strip():
      continue
    parts = line.split()
    quantity = float(parts[0])
    unit = parts[1]
    name = " ".join(parts[2:])
    ingredient = Ingredient(
      name = name,
      unit = unit,
      quantity = quantity 
    )
    ingredients.append(ingredient)
  return ingredients