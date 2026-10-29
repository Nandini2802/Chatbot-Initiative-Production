from sqlalchemy.ext.asyncio import AsyncSession


async def get_sales_offer_db():
    """
    Yield an AsyncSession from the existing
    application session factory.
    """
    raise NotImplementedError(
        "Connect the existing SQLAlchemy session factory"
    )


async def get_sales_offer_authenticated_user() -> str:
    """
    Validate the request's Salesforce authentication
    and return the verified user ID.

    Never trust a user_id supplied in the URL
    or request body as proof of ownership.
    """
    raise NotImplementedError(
        "Connect the existing Salesforce authentication"
    )