# Recipe Database

A simple web application for storing, viewing, and editing recipes. Built with Flask and SQLite.

## Features

- Browse a gallery of recipes with images
- View detailed recipe information (ingredients, instructions, notes, tags)
- Edit existing recipes
- Upload images for each recipe
- Filter recipes by tags
- AI chat assistant for recipe help

## Getting Started

1. Clone the repository
2. Install dependencies:  
   ```
   pip install -r requirements.txt
   ```
3. Run the app:  
   ```
   python app.py
   ```
4. Open your browser at [http://localhost:5000](http://localhost:5000)

## Folder Structure

- `app.py` - Main Flask application
- `create_db.py` - Script to create the SQLite database
- `templates/` - HTML templates
- `static/uploads/` - Uploaded recipe images

## Future Features

- Website
- User authentication (login/register)
- Possible to rate recipes
- Personal cookbooks that can be divided into sections and filtered with tags
- Price estimation based on ingredients
- Shopping list generator
- Mobile-friendly design