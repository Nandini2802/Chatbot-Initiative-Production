
from pydantic import BaseModel, Field


class MarketingFile(BaseModel):
    name: str
    download_url: str

    # Size returned by Marketing API in bytes
    file_size_bytes: int | None = None

    # API field: uploaded_at
    updated_at: str | None = None

    language: str | None = None


class MarketingAsset(BaseModel):
    project: str
    asset_type: str

    files: list[MarketingFile] = Field(
        default_factory=list
    )

    zip_url: str | None = None
    total_files: int = 0

    # Combined size of original source files.
    # Not necessarily the compressed ZIP size.
    total_size_bytes: int | None = None

    # Latest uploaded_at among matching files
    updated_at: str | None = None
