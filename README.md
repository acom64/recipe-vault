# Recipe Vault

A private Flask web application for saving recipes, planning meals, and generating mobile-friendly shopping lists.

## Features

- User registration, login, logout, hashed passwords, and private user-owned data
- Dashboard with recipe totals, weekly plan status, shopping progress, quick actions, and recent recipes
- Recipe library with search, automatic filters, sorting, category and meal badges, favorites, duplicate, import, text export, and ZIP backups with photos
- Recipe editor with ingredients, instructions, notes, photos, prep time, cook time, servings, and beginner-friendly ingredient parsing
- Weekly meal planner for Monday through Sunday with breakfast, lunch, and dinner support
- Autosaved meal-plan drafts and add-to-plan actions from the recipe library
- Shopping list generated from the saved meal plan with merged duplicate ingredients, groups, checkboxes, progress, copy, Notes-friendly export text, print, and shopping mode
- Responsive Bootstrap 5 interface optimized for desktop and phones

## Requirements

- Python 3.12 or newer
- pip
- A virtual environment

Dependencies are listed in `requirements.txt`.

## Installation

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Database Setup

The app uses SQLite by default and stores the local database at `instance/recipes.db`.

Initialize or update the database:

```bash
python init_db.py
```

The application also creates missing tables and additive columns on startup. Existing older databases are upgraded with the current startup helper.

## Run Locally

```bash
python run.py
```

Open:

```text
http://127.0.0.1:5000
```

Default local configuration:

- `SECRET_KEY=dev-secret-key`
- `DATABASE_URL=sqlite:///recipes.db`
- Uploaded images are stored in `app/static/uploads/`

For production, set a strong `SECRET_KEY` and configure `DATABASE_URL`.

## Tests

```bash
python -m unittest discover -s tests
```

## Development Workflow

1. Create a feature branch.
2. Activate the virtual environment.
3. Install dependencies from `requirements.txt`.
4. Run `python run.py` while developing.
5. Run `python -m unittest discover -s tests` before committing.

## Data Notes

Recipe Vault now stores recipe metadata such as prep time, cook time, servings, notes, favorite state, and created/updated timestamps. Shopping-list checked state is stored per user and keyed to the generated ingredient item.

If you want a clean local database during development, stop the server, remove `instance/recipes.db`, then run:

```bash
python init_db.py
```
