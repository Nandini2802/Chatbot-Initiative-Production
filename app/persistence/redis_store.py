"""
Redis cache keys used across the Danube Chatbot.
"""


class RedisCacheKeys:

    MARKETING_CATALOG = "danube:api:marketing:v1"
    CURRENCY_RATES = "danube:api:currency-rates:v1"
    HOW_TO_VIDEOS = "danube:api:how-to-videos:v1"


    @staticmethod
    def api_cache(api_name: str) -> str:
        return (
            f"danube:api:{api_name}:v1"
        )
