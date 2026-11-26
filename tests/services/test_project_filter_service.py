from types import SimpleNamespace

from app.schemas.project_filters import (
    ProjectFilter,
    ProjectFilterResult,
)

from app.services.project_filter_service import (
    ProjectFilterService,
)


def make_project(**attributes):

    return SimpleNamespace(
        attributes=attributes,
    )


PROJECTS = [

    make_project(**{
        "ProjectName": "SHAHRUKHZ BY DANUBE",
        "Total_Units__c": 1200,
        "Total_Saleable_Area__c": 2500000000,
        "Construction_Status__c": "Off Plan",
        "Starting_Price_Mob__c": "900,220.00",
        "Completion_Date_Mob__c ": "Q4-2028",
        "EOIActive ": False,
        "UOM__c": "Square Feet",
        "currency_symbol": "AED",
    }),

    make_project(**{
        "ProjectName": "SHAHRUKHZ RESIDENCES",
        "Total_Units__c": 800,
        "Total_Saleable_Area__c": 1000000000,
        "Construction_Status__c": "Off Plan",
        "Starting_Price_Mob__c": "1,500,000",
        "Completion_Date_Mob__c ": "Q2-2028",
        "EOIActive ": True,
        "UOM__c": "Square Feet",
        "currency_symbol": "AED",
    }),

    make_project(**{
        "ProjectName": "GREENZ BY DANUBE",
        "Total_Units__c": 1500,
        "Total_Saleable_Area__c": 3000000000,
        "Construction_Status__c": "Completed",
        "Starting_Price_Mob__c": None,
        "Completion_Date_Mob__c ": "Q4-2027",
        "EOIActive ": False,
        "UOM__c": "Square Feet",
        "currency_symbol": "AED",
    }),
]


def run_filter(*conditions, logic="and"):

    extracted = ProjectFilterResult(
        filters=list(conditions),
        logic=logic,
    )

    return ProjectFilterService().filter_projects(
        PROJECTS,
        extracted,
    )


def test_project_family():

    result = run_filter(
        ProjectFilter(
            field="ProjectName",
            operator="contains",
            value="shahrukhz",
        )
    )

    assert len(result) == 2


def test_total_units():

    result = run_filter(
        ProjectFilter(
            field="Total_Units__c",
            operator="gt",
            value=1000,
        )
    )

    assert len(result) == 2


def test_saleable_area():

    result = run_filter(
        ProjectFilter(
            field="Total_Saleable_Area__c",
            operator="gt",
            value=2000000000,
        )
    )

    assert len(result) == 2


def test_multiple_and_filters():

    result = run_filter(

        ProjectFilter(
            field="Total_Units__c",
            operator="gt",
            value=1000,
        ),

        ProjectFilter(
            field="Construction_Status__c",
            operator="eq",
            value="Off Plan",
        ),
    )

    assert len(result) == 1


def test_multiple_or_filters():

    result = run_filter(

        ProjectFilter(
            field="Total_Units__c",
            operator="gt",
            value=1000,
        ),

        ProjectFilter(
            field="EOIActive",
            operator="eq",
            value=True,
        ),

        logic="or",
    )

    assert len(result) == 3


def test_starting_price():

    result = run_filter(
        ProjectFilter(
            field="Starting_Price_Mob__c",
            operator="lt",
            value=1000000,
        )
    )

    assert len(result) == 1


def test_completion_year():

    result = run_filter(
        ProjectFilter(
            field="Completion_Date_Mob__c",
            operator="eq",
            value=2028,
        )
    )

    assert len(result) == 2


def test_boolean_with_trailing_space():

    result = run_filter(
        ProjectFilter(
            field="EOIActive",
            operator="eq",
            value=False,
        )
    )

    assert len(result) == 2


def test_null_value():

    result = run_filter(
        ProjectFilter(
            field="Starting_Price_Mob__c",
            operator="is_null",
        )
    )

    assert len(result) == 1


def test_between():

    result = run_filter(
        ProjectFilter(
            field="Total_Units__c",
            operator="between",
            value=800,
            second_value=1200,
        )
    )

    assert len(result) == 2


def test_strict_boundary():

    result = run_filter(
        ProjectFilter(
            field="Total_Units__c",
            operator="gt",
            value=1200,
        )
    )

    assert len(result) == 1


def test_no_matching_projects():

    result = run_filter(
        ProjectFilter(
            field="Total_Units__c",
            operator="gt",
            value=1000000,
        )
    )

    assert len(result) == 0