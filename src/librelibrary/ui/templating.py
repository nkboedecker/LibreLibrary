"""The Jinja2 environment for the web interface."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from librelibrary.ui.support import (
    KIND_CHOICES,
    PRIVACY_CHOICES,
    kind_label,
    money,
    privacy_label,
)

UI_DIRECTORY = Path(__file__).parent

# Autoescaping is on for .html templates, which is every template here.
templates = Jinja2Templates(directory=UI_DIRECTORY / "templates")
templates.env.filters["privacy_label"] = privacy_label
templates.env.filters["money"] = money
templates.env.filters["kind_label"] = kind_label
templates.env.globals["KIND_CHOICES"] = KIND_CHOICES
templates.env.globals["PRIVACY_CHOICES"] = PRIVACY_CHOICES
