from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "cards"
)


class TemplateService:

    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(
                enabled_extensions=("html", "j2"),
                default_for_string=True,
            ),
        )

    def render(
        self,
        template_name: str,
        **context,
    ) -> str:

        template = self.env.get_template(template_name)

        return template.render(**context)

    def render_marketing_asset(self, asset) -> str:

        if asset.asset_type == "brochures":
            return self.render(
                "brochure.html.j2",
                project=asset.project,
                files=[
                    {
                        **item.model_dump(),
                        "size_label": self.format_file_size(
                            item.file_size_bytes
                        ),
                        "updated_at": self.format_uploaded_at(
                            item.updated_at
                        ),
                    }
                    for item in asset.files
                ],
                zip_url=None,
            )

        if asset.asset_type in {"videos", "walkthrough"}:
            return self.render(
                "video.html.j2",
                project=asset.project,
                files=[
                    {
                        **item.model_dump(),
                        "size_label": self.format_file_size(
                            item.file_size_bytes
                        ),
                        "updated_at": self.format_uploaded_at(
                            item.updated_at
                        ),
                    }
                    for item in asset.files
                ],
                zip_url=None,
            )

        if asset.asset_type == "floor-plans":
            return self.render(
                "floor_plan.html.j2",
                project=asset.project,
                total_images=asset.total_files,
                zip_url=asset.zip_url,
                size_label=self.format_file_size(
                    asset.total_size_bytes
                ),
                updated_at=self.format_uploaded_at(
                    asset.updated_at
                ),
            )

        labels = {
            "interiors": "Interior Images",
            "exteriors": "Exterior Images",
            "amenities": "Amenities",
            "social-media": "Social Media",
            "factsheet": "Factsheet",
            "other": "Other Materials",
            "all": "All Marketing Materials",
            "ppt": "Presentations",
            "renders": "Renders",
            "price-list": "Price List",
        }

        if asset.asset_type not in labels:
            raise ValueError(
                f"Unsupported marketing asset: {asset.asset_type}"
            )

        return self.render(
            "zip_download.html.j2",
            project=asset.project,
            label=labels[asset.asset_type],
            total_files=asset.total_files,
            zip_url=asset.zip_url,
            size_label=self.format_file_size(
                asset.total_size_bytes
            ),
            updated_at=self.format_uploaded_at(
                asset.updated_at
            ),
        )

    @staticmethod
    def format_uploaded_at(value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
            return (
                f"{parsed.day} "
                f"{parsed.strftime('%B %Y')}"
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    def format_file_size(size_bytes):
        if size_bytes is None:
            return None

        if size_bytes < 0:
            return None

        size = float(size_bytes)

        units = ["B", "KB", "MB", "GB", "TB"]

        for unit in units:
            if size < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} B"

                return f"{size:.2f} {unit}"

            size /= 1024

        if size_bytes is None:
            return None

        if size_bytes < 1024:
            return f"{size_bytes} B"

        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"

        return f"{size_bytes / (1024 * 1024):.2f} MB"