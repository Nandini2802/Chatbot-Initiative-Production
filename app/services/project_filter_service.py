import re
import calendar

from datetime import date
from decimal import Decimal, InvalidOperation

from app.schemas.project_filters import (
    ProjectFilter,
    ProjectFilterResult,
)


NUMERIC_FIELDS = {
    "Service_Charge__c",
    "ProjectSequence",
    "Starting_Price_Mob__c",
    "Total_Units__c",
    "Total_Sold_Unit__c",
    "Total_Selling_Price__c",
    "Total_Saleable_Area__c",
    "Total_Residential_Units__c",
    "Total_Other_Unit__c",
    "Total_New_Unit__c",
    "Total_Floor__c",
    "Total_Commercial_Units__c",
    "Total_Building__c",
    "Total_Booked_Unit__c",
    "Total_BUA_sq_feet__c",
    "Total_Available_Unit__c",
    "Total_Available_Residential_Units__c",
    "Total_Available_Commercial_Units__c",
    "Plot_Size_Sq_Ft__c",
}


BOOLEAN_FIELDS = {
    "EOIActive",
    "is_show_villa",
    "is_visit",
}


DATE_FIELDS = {
    "Anticipated_Handover_Date__c",
    "Completion_Date_Mob__c",
}


AREA_FIELDS = {
    "Total_Saleable_Area__c",
    "Total_BUA_sq_feet__c",
    "Plot_Size_Sq_Ft__c",
}


PRICE_FIELDS = {
    "Starting_Price_Mob__c",
    "Total_Selling_Price__c",
    "Service_Charge__c",
}


NULL_OPERATORS = {
    "is_null",
    "is_not_null",
}


COMPARISON_OPERATORS = {
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
}


TEXT_OPERATORS = {
    "eq",
    "ne",
    "contains",
    "not_contains",
    "starts_with",
}


def normalize_text(value):

    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        value = " ".join(
            str(item) for item in value
        )

    return " ".join(
        str(value).casefold().strip().split()
    )


def is_empty(value):

    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, dict, tuple, set)):
        return not value

    return False


def to_number(value):

    if value is None or isinstance(value, bool):
        return None

    try:

        cleaned = str(value).strip().casefold()

        cleaned = cleaned.replace(",", "")
        cleaned = cleaned.replace("aed", "").strip()

        number = Decimal(cleaned)

        if not number.is_finite():
            return None

        return number

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None


def to_boolean(value):

    if isinstance(value, bool):
        return value

    text = normalize_text(value)

    if text in {"true", "yes", "1"}:
        return True

    if text in {"false", "no", "0"}:
        return False

    return None


def to_date_range(value):

    if value is None:
        return None

    text = str(value).strip().upper()

    # Exact year: 2028
    if re.fullmatch(r"\d{4}", text):

        year = int(text)

        try:
            return (
                date(year, 1, 1),
                date(year, 12, 31),
            )
        except ValueError:
            return None

    # Quarter: Q4-2028
    quarter_match = re.fullmatch(
        r"Q([1-4])[\s/-]*(\d{4})",
        text,
    )

    if quarter_match:

        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2))

        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2

        try:

            end_day = calendar.monthrange(
                year,
                end_month,
            )[1]

            return (
                date(year, start_month, 1),
                date(year, end_month, end_day),
            )

        except ValueError:
            return None

    # Exact date: 2028-12-31
    try:

        parsed = date.fromisoformat(text)

        return parsed, parsed

    except ValueError:
        return None


def compare_values(
    actual,
    expected,
    operator,
    second_value=None,
):

    if actual is None or expected is None:
        return False

    if operator == "eq":
        return actual == expected

    if operator == "ne":
        return actual != expected

    if operator == "gt":
        return actual > expected

    if operator == "gte":
        return actual >= expected

    if operator == "lt":
        return actual < expected

    if operator == "lte":
        return actual <= expected

    if operator == "between":

        if second_value is None:
            return False

        return expected <= actual <= second_value

    return False


def compare_dates(
    actual,
    expected,
    operator,
    second_value=None,
):

    actual_range = to_date_range(actual)
    expected_range = to_date_range(expected)

    if actual_range is None or expected_range is None:
        return False

    actual_start, actual_end = actual_range
    expected_start, expected_end = expected_range

    if operator == "eq":

        return (
            actual_start >= expected_start
            and actual_end <= expected_end
        )

    if operator == "ne":

        return (
            actual_end < expected_start
            or actual_start > expected_end
        )

    if operator == "gt":
        return actual_start > expected_end

    if operator == "gte":
        return actual_start >= expected_start

    if operator == "lt":
        return actual_end < expected_start

    if operator == "lte":
        return actual_end <= expected_end

    if operator == "between":

        second_range = to_date_range(second_value)

        if second_range is None:
            return False

        return (
            actual_start >= expected_start
            and actual_end <= second_range[1]
        )

    return False


def get_project_attributes(project):

    raw = getattr(
        project,
        "attributes",
        {},
    ) or {}

    # Remove trailing spaces from API field names.
    return {
        str(key).strip(): value
        for key, value in raw.items()
    }


def validate_condition(condition: ProjectFilter):

    field = condition.field
    operator = condition.operator

    if operator in NULL_OPERATORS:
        return

    if field in NUMERIC_FIELDS:

        if operator not in COMPARISON_OPERATORS:
            raise ValueError(
                f"Unsupported numeric operator: {operator}"
            )

        first = to_number(condition.value)

        if first is None:
            raise ValueError(
                f"Invalid numeric value for {field}"
            )

        if operator == "between":

            second = to_number(
                condition.second_value
            )

            if second is None or first > second:
                raise ValueError(
                    f"Invalid numeric range for {field}"
                )

    elif field in BOOLEAN_FIELDS:

        if operator not in {"eq", "ne"}:
            raise ValueError(
                f"Invalid Boolean operator for {field}"
            )

        if to_boolean(condition.value) is None:
            raise ValueError(
                f"Invalid Boolean value for {field}"
            )

    elif field in DATE_FIELDS:

        if operator not in COMPARISON_OPERATORS:
            raise ValueError(
                f"Invalid date operator for {field}"
            )

        first = to_date_range(condition.value)

        if first is None:
            raise ValueError(
                f"Invalid date value for {field}"
            )

        if operator == "between":

            second = to_date_range(
                condition.second_value
            )

            if second is None or first[0] > second[1]:
                raise ValueError(
                    f"Invalid date range for {field}"
                )

    elif operator not in TEXT_OPERATORS:

        raise ValueError(
            f"Unsupported text operator for {field}"
        )


def matches_condition(
    attributes: dict,
    condition: ProjectFilter,
):

    field = condition.field
    operator = condition.operator

    actual = attributes.get(field)

    if operator == "is_null":
        return is_empty(actual)

    if operator == "is_not_null":
        return not is_empty(actual)

    # Missing data must never be treated as zero,
    # false, or a valid negative match.
    if is_empty(actual):
        return False

    if field in NUMERIC_FIELDS:

        actual_number = to_number(actual)

        # Area filters are expressed in square feet.
        if field in AREA_FIELDS:

            uom = normalize_text(
                attributes.get("UOM__c")
            )

            if uom in {
                "square meter",
                "square meters",
                "square metre",
                "square metres",
                "sqm",
                "m2",
                "m²",
            }:

                if actual_number is not None:
                    actual_number *= Decimal(
                        "10.7639104167"
                    )

            elif uom not in {
                "square feet",
                "square foot",
                "sq ft",
                "sqft",
                "ft2",
                "ft²",
            }:
                return False

        # Do not compare prices in different currencies.
        if field in PRICE_FIELDS:

            currency = normalize_text(
                attributes.get("currency_symbol")
            )

            if currency != "aed":
                return False

        return compare_values(
            actual=actual_number,
            expected=to_number(condition.value),
            operator=operator,
            second_value=to_number(
                condition.second_value
            ),
        )

    if field in BOOLEAN_FIELDS:

        return compare_values(
            actual=to_boolean(actual),
            expected=to_boolean(condition.value),
            operator=operator,
        )

    if field in DATE_FIELDS:

        return compare_dates(
            actual=actual,
            expected=condition.value,
            operator=operator,
            second_value=condition.second_value,
        )

    actual_text = normalize_text(actual)

    expected_text = normalize_text(
        condition.value
    )

    if not expected_text:
        return False

    if operator == "contains":
        return expected_text in actual_text

    if operator == "not_contains":
        return expected_text not in actual_text

    if operator == "starts_with":
        return actual_text.startswith(expected_text)

    return compare_values(
        actual=actual_text,
        expected=expected_text,
        operator=operator,
    )


class ProjectFilterService:

    def filter_projects(
        self,
        projects,
        extracted: ProjectFilterResult,
    ):

        if extracted.requires_clarification:
            raise ValueError(
                "Project filters require clarification."
            )

        if not extracted.filters:
            raise ValueError(
                "Project filters cannot be empty."
            )

        for condition in extracted.filters:
            validate_condition(condition)

        results = []

        for project in projects:

            attributes = get_project_attributes(
                project
            )

            matches = [
                matches_condition(
                    attributes,
                    condition,
                )
                for condition in extracted.filters
            ]

            if extracted.logic == "or":
                matched = any(matches)
            else:
                matched = all(matches)

            if matched:
                results.append(project)

        # Preserve API ordering.
        # Apply limit only after filtering.
        return results