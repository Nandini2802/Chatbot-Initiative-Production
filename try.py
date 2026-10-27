
import os
import requests
import webbrowser
from urllib.parse import urlencode

# Set GOOGLE_MAPS_API_KEY in your environment or .env
from dotenv import load_dotenv
load_dotenv()

API_KEY = "AIzaSyD84QYanwRUNM3Qw8jiamj_p3PIGSajF4w"

# Coordinates from Danube OSF Portfolio API
LATITUDE = 25.057597887203908
LONGITUDE = 55.23928235101428


def get_google_maps_link(latitude, longitude):
    if not API_KEY:
        raise ValueError("GOOGLE_MAPS_API_KEY is missing")

    # Step 1: Call Google's paid Geocoding API
    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"

    response = requests.get(
        endpoint,
        params={
            "latlng": f"{latitude},{longitude}",
            "key": API_KEY,
        },
        timeout=15,
    )

    response.raise_for_status()
    data = response.json()

    print("API STATUS:", data.get("status"))

    if data.get("status") != "OK":
        raise RuntimeError(
            f"Google API error: {data.get('error_message', data.get('status'))}"
        )

    results = data.get("results", [])

    if not results:
        raise RuntimeError("No location found")

    # Step 2: Retrieve Google's formatted address
    location = results[0]

    address = location.get("formatted_address")
    place_id = location.get("place_id")

    print("GOOGLE ADDRESS:", address)
    print("GOOGLE PLACE ID:", place_id)

    # Step 3: Generate map URL using original coordinates
    query = urlencode({
        "api": 1,
        "query": f"{latitude},{longitude}",
    })

    map_url = f"https://www.google.com/maps/search/?{query}"

    return map_url


if __name__ == "__main__":
    url = get_google_maps_link(LATITUDE, LONGITUDE)

    print("\nGENERATED GOOGLE MAPS URL:")
    print(url)

    webbrowser.open(url)
