
from app.services.project_resolution_service import (
    resolve_comparison_project,
    extract_comparison_projects,
)

# Test fixture only. Production uses the live API.
projects = [
    "ELITZ BY DANUBE",
    "ELITZ 2 BY DANUBE",
    "ELITZ 3 BY DANUBE",
    "GREENZ BY DANUBE",
    "OCEANZ 1 BY DANUBE",
    "OCEANZ 2 BY DANUBE",
    "OCEANZ 3 BY DANUBE",
    "SHAHRUKHZ BY DANUBE",
    "SHAHRUKHZ RESIDENCES BY DANUBE",
]

assert resolve_comparison_project(
    "elite", projects
).name == "ELITZ BY DANUBE"

assert resolve_comparison_project(
    "elitz 3", projects
).name == "ELITZ 3 BY DANUBE"

assert resolve_comparison_project(
    "oceanz", projects
).name == "OCEANZ 1 BY DANUBE"

assert resolve_comparison_project(
    "shahrukhz", projects
).name == "SHAHRUKHZ BY DANUBE"

assert extract_comparison_projects(
    "compare elite and greenz",
    projects,
) == [
    "ELITZ BY DANUBE",
    "GREENZ BY DANUBE",
]

without_base = [
    name for name in projects
    if name != "ELITZ BY DANUBE"
]

assert resolve_comparison_project(
    "elitz", without_base
).name == "ELITZ 2 BY DANUBE"

assert resolve_comparison_project(
    "elitz 4", projects
).status == "not_found"

print("All project comparison tests passed.")
