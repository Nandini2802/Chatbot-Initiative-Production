from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def display(value):
    if value is None:
        return "--"

    if isinstance(value, str):
        value = value.strip()
        return value if value else "--"

    return str(value)


def format_price(value):
    if value is None or str(value).strip() == "":
        return "--"

    try:
        amount = Decimal(str(value).replace(",", ""))
        if not amount.is_finite():
            return "--"
        return f"{amount:,.2f}"
    except (InvalidOperation, ValueError):
        return "--"


def format_area(value):
    if value is None or str(value).strip() == "":
        return "--"

    try:
        amount = Decimal(str(value).replace(",", ""))
        if not amount.is_finite():
            return "--"
        number = f"{amount:,.2f}".rstrip("0").rstrip(".")
        return f"{number} SQFT"
    except (InvalidOperation, ValueError):
        return "--"


def format_date(value):
    if not value:
        return "--"

    try:
        parsed = date.fromisoformat(str(value)[:10])
        return parsed.strftime("%B %Y")
    except (ValueError, TypeError):
        return "--"


def map_comparison(project, unit):
    raw_plans = (
        (project.get("Payment_Plans__r") or {})
        .get("records") or []
    )

    payment_plans = []

    for plan in raw_plans:
        if not isinstance(plan, dict):
            continue

        payment_plans.append({
            "name": display(plan.get("Name")),
            "installment_count": display(
                plan.get("Number_of_Installments__c")
            ),
        })

    return {
        "unit": {
            "unit_name": display(unit.get("Name")),
            "currency": display(unit.get("CurrencyIsoCode")),
            "price": format_price(unit.get("SellingPrice__c")),
            "project_name": display(project.get("Name")),
            "project_location": display(
                project.get("Location_Name_Mob__c")
            ),
            "category": display(unit.get("Category__c")),
            "unit_type": display(unit.get("Unit_Type1__c")),
            "bathrooms": display(
                unit.get("NumberOfBathrooms__c")
            ),
            "parking": display(unit.get("Parking__c")),
            "total_area": format_area(unit.get("TotalArea__c")),
            "internal_area": format_area(
                unit.get("Internal_Saleable_Area__c")
            ),
            "plot_area": format_area(unit.get("PlotArea__c")),
            "status": display(unit.get("Status__c")),
            "completion_date": format_date(
                unit.get("CompletionDate__c")
            ),
        },
        "payment_plans": payment_plans,
    }