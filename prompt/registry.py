import os
from pathlib import Path
from typing import Dict, Optional


class PromptRegistry:
    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize Prompt Templates

        Args:
            template_dir: path to prompt template directory

        """
        if template_dir is None:
            template_dir = Path(__file__).parent / "templates"

        self.template_dir = Path(template_dir)
        self._template: Dict[str, str] = {}

        if self.template_dir.exists():
            self._load_templates()

    def _load_templates(self):
        """Load all prompt templates from the templates directory."""
        prompt_list = os.listdir(self.template_dir)
        for prompt in prompt_list:
            prompt_name = prompt.split(".")[0]
            with open(self.template_dir / prompt, "r", encoding="utf-8") as file:
                self._template[prompt_name] = file.read()

    def get(self, template_name: str) -> str:
        """Get a prompt template by name.

            Args:
                template_name: Name of the template (without .md extension)

            Returns:
                Template content or None if not found
        """
        return self._template.get(template_name)

    def registry(self, template_name: str, template_content: str):
        """Register a new prompt template.

            Args:
                template_name: Name for the template
                template_content: Content of the template
        """
        self._template[template_name] = template_content

    def list_templates(self):
        """List all available template names."""
        return list(self._templates.keys())
