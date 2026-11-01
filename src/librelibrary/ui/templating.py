"""The Jinja2 environment for the web interface."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

UI_DIRECTORY = Path(__file__).parent

# Autoescaping is on for .html templates, which is every template here.
templates = Jinja2Templates(directory=UI_DIRECTORY / "templates")
