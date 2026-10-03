from flask import Blueprint, render_template, request, jsonify
import os
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
from google import genai


# =========================================================
# SETUP
# =========================================================

load_dotenv()

myai = Blueprint("myai", __name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print("MyAI API key loaded:", bool(GEMINI_API_KEY))


SEARXNG_URL = os.environ.get(
    "SEARXNG_URL",
    "http://localhost:8080"
)


# Open-Meteo does not require an API key for normal
# non-commercial API usage.
OPEN_METEO_GEOCODING_URL = (
    "https://geocoding-api.open-meteo.com/v1/search"
)

OPEN_METEO_WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
)


if GEMINI_API_KEY:

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

else:

    gemini_client = None


# =========================================================
# GEMINI MODELS
# =========================================================

AI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash"
]


# =========================================================
# WEATHER HELPERS
# =========================================================

STATE_ABBREVIATIONS = {

    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",

    "DC": "District of Columbia"
}


# For a whole-state request, use the state capital as a
# representative weather location.
STATE_CAPITALS = {

    "Alabama": "Montgomery, Alabama",
    "Alaska": "Juneau, Alaska",
    "Arizona": "Phoenix, Arizona",
    "Arkansas": "Little Rock, Arkansas",
    "California": "Sacramento, California",
    "Colorado": "Denver, Colorado",
    "Connecticut": "Hartford, Connecticut",
    "Delaware": "Dover, Delaware",
    "Florida": "Tallahassee, Florida",
    "Georgia": "Atlanta, Georgia",
    "Hawaii": "Honolulu, Hawaii",
    "Idaho": "Boise, Idaho",
    "Illinois": "Springfield, Illinois",
    "Indiana": "Indianapolis, Indiana",
    "Iowa": "Des Moines, Iowa",
    "Kansas": "Topeka, Kansas",
    "Kentucky": "Frankfort, Kentucky",
    "Louisiana": "Baton Rouge, Louisiana",
    "Maine": "Augusta, Maine",
    "Maryland": "Annapolis, Maryland",
    "Massachusetts": "Boston, Massachusetts",
    "Michigan": "Lansing, Michigan",
    "Minnesota": "Saint Paul, Minnesota",
    "Mississippi": "Jackson, Mississippi",
    "Missouri": "Jefferson City, Missouri",
    "Montana": "Helena, Montana",
    "Nebraska": "Lincoln, Nebraska",
    "Nevada": "Carson City, Nevada",
    "New Hampshire": "Concord, New Hampshire",
    "New Jersey": "Trenton, New Jersey",
    "New Mexico": "Santa Fe, New Mexico",
    "New York": "Albany, New York",
    "North Carolina": "Raleigh, North Carolina",
    "North Dakota": "Bismarck, North Dakota",
    "Ohio": "Columbus, Ohio",
    "Oklahoma": "Oklahoma City, Oklahoma",
    "Oregon": "Salem, Oregon",
    "Pennsylvania": "Harrisburg, Pennsylvania",
    "Rhode Island": "Providence, Rhode Island",
    "South Carolina": "Columbia, South Carolina",
    "South Dakota": "Pierre, South Dakota",
    "Tennessee": "Nashville, Tennessee",
    "Texas": "Austin, Texas",
    "Utah": "Salt Lake City, Utah",
    "Vermont": "Montpelier, Vermont",
    "Virginia": "Richmond, Virginia",
    "Washington": "Olympia, Washington",
    "West Virginia": "Charleston, West Virginia",
    "Wisconsin": "Madison, Wisconsin",
    "Wyoming": "Cheyenne, Wyoming"
}


WEATHER_WORDS = [
    "weather",
    "wether",
    "weater",
    "weahter",
    "forecast",
    "temperature",
    "temp",
]

def looks_like_weather_question(message):

    text = message.lower().strip()

    return any(
        word in text
        for word in WEATHER_WORDS
    )

def clean_weather_location(message):
    text = message.strip()

    # Normalize common weather typos.
    text = re.sub(r"\bwether\b", "weather", text, flags=re.IGNORECASE)
    text = re.sub(r"\bweater\b", "weather", text, flags=re.IGNORECASE)
    text = re.sub(r"\bweahter\b", "weather", text, flags=re.IGNORECASE)

    # Extract everything after "in", "for", or "at".
    match = re.search(
        r"\b(?:in|for|at)\s+(.+?)(?:\?|$)",
        text,
        flags=re.IGNORECASE
    )

    if match:
        text = match.group(1).strip()
    else:
        # No location was provided.
        return ""

    # Remove common trailing words.
    text = re.sub(
        r"\s+(?:right\s+now|currently|today|tonight)$",
        "",
        text,
        flags=re.IGNORECASE
    ).strip()

    # Remove punctuation.
    text = text.strip(" .,?!")

    # Fix common city-name typos.
    city_typos = {
        "decader": "Decatur",
        "decater": "Decatur",
        "decatur": "Decatur",
        "huntsvill": "Huntsville",
        "huntsville": "Huntsville",
        "montgomry": "Montgomery",
        "montgomery": "Montgomery",
    }

    words_lower = text.lower().split()

    # Handle phrases such as "north al decader".
    if "decader" in words_lower or "decater" in words_lower:
        return "Decatur, Alabama"

    # State abbreviations.
    state_abbreviations = {
        "AL": "Alabama",
        "AK": "Alaska",
        "AZ": "Arizona",
        "AR": "Arkansas",
        "CA": "California",
        "CO": "Colorado",
        "CT": "Connecticut",
        "DE": "Delaware",
        "FL": "Florida",
        "GA": "Georgia",
        "HI": "Hawaii",
        "ID": "Idaho",
        "IL": "Illinois",
        "IN": "Indiana",
        "IA": "Iowa",
        "KS": "Kansas",
        "KY": "Kentucky",
        "LA": "Louisiana",
        "ME": "Maine",
        "MD": "Maryland",
        "MA": "Massachusetts",
        "MI": "Michigan",
        "MN": "Minnesota",
        "MS": "Mississippi",
        "MO": "Missouri",
        "MT": "Montana",
        "NE": "Nebraska",
        "NV": "Nevada",
        "NH": "New Hampshire",
        "NJ": "New Jersey",
        "NM": "New Mexico",
        "NY": "New York",
        "NC": "North Carolina",
        "ND": "North Dakota",
        "OH": "Ohio",
        "OK": "Oklahoma",
        "OR": "Oregon",
        "PA": "Pennsylvania",
        "RI": "Rhode Island",
        "SC": "South Carolina",
        "SD": "South Dakota",
        "TN": "Tennessee",
        "TX": "Texas",
        "UT": "Utah",
        "VT": "Vermont",
        "VA": "Virginia",
        "WA": "Washington",
        "WV": "West Virginia",
        "WI": "Wisconsin",
        "WY": "Wyoming"
    }

    # Regional Alabama locations.
    regional_states = {
        "north al": "Huntsville, Alabama",
        "north ala": "Huntsville, Alabama",
        "north alabama": "Huntsville, Alabama",
        "south al": "Mobile, Alabama",
        "south ala": "Mobile, Alabama",
        "south alabama": "Mobile, Alabama",
        "central al": "Montgomery, Alabama",
        "central ala": "Montgomery, Alabama",
        "central alabama": "Montgomery, Alabama"
    }

    normalized = re.sub(
        r"\s+",
        " ",
        text
    ).strip().lower()

    if normalized in regional_states:
        return regional_states[normalized]

    # State-only weather requests.
    state_weather_cities = {
        "alabama": "Montgomery, Alabama",
        "alaska": "Anchorage, Alaska",
        "arizona": "Phoenix, Arizona",
        "arkansas": "Little Rock, Arkansas",
        "california": "Los Angeles, California",
        "colorado": "Denver, Colorado",
        "connecticut": "Hartford, Connecticut",
        "delaware": "Dover, Delaware",
        "florida": "Tallahassee, Florida",
        "georgia": "Atlanta, Georgia",
        "hawaii": "Honolulu, Hawaii",
        "idaho": "Boise, Idaho",
        "illinois": "Springfield, Illinois",
        "indiana": "Indianapolis, Indiana",
        "iowa": "Des Moines, Iowa",
        "kansas": "Topeka, Kansas",
        "kentucky": "Frankfort, Kentucky",
        "louisiana": "Baton Rouge, Louisiana",
        "maine": "Augusta, Maine",
        "maryland": "Annapolis, Maryland",
        "massachusetts": "Boston, Massachusetts",
        "michigan": "Lansing, Michigan",
        "minnesota": "Saint Paul, Minnesota",
        "mississippi": "Jackson, Mississippi",
        "missouri": "Jefferson City, Missouri",
        "montana": "Helena, Montana",
        "nebraska": "Lincoln, Nebraska",
        "nevada": "Carson City, Nevada",
        "new hampshire": "Concord, New Hampshire",
        "new jersey": "Trenton, New Jersey",
        "new mexico": "Santa Fe, New Mexico",
        "new york": "Albany, New York",
        "north carolina": "Raleigh, North Carolina",
        "north dakota": "Bismarck, North Dakota",
        "ohio": "Columbus, Ohio",
        "oklahoma": "Oklahoma City, Oklahoma",
        "oregon": "Salem, Oregon",
        "pennsylvania": "Harrisburg, Pennsylvania",
        "rhode island": "Providence, Rhode Island",
        "south carolina": "Columbia, South Carolina",
        "south dakota": "Pierre, South Dakota",
        "tennessee": "Nashville, Tennessee",
        "texas": "Austin, Texas",
        "utah": "Salt Lake City, Utah",
        "vermont": "Montpelier, Vermont",
        "virginia": "Richmond, Virginia",
        "washington": "Olympia, Washington",
        "west virginia": "Charleston, West Virginia",
        "wisconsin": "Madison, Wisconsin",
        "wyoming": "Cheyenne, Wyoming"
    }

    lower_text = text.lower()

    if lower_text in state_weather_cities:
        return state_weather_cities[lower_text]

    # A location ending in a full state name.
    for state_name in state_abbreviations.values():
        if lower_text.endswith(" " + state_name.lower()):
            city = text[
                :len(text) - len(state_name)
            ].strip(" ,")

            if city:
                return f"{city}, {state_name}"

    # A city followed by a state abbreviation.
    words = text.split()

    if len(words) >= 2:
        possible_state = words[-1].upper()

        if possible_state in state_abbreviations:
            city = " ".join(words[:-1]).strip()

            if city:
                return f"{city}, {state_abbreviations[possible_state]}"

    # A state abbreviation by itself.
    if text.upper() in state_abbreviations:
        return state_weather_cities.get(
            state_abbreviations[text.upper()].lower(),
            state_abbreviations[text.upper()]
        )

    return text

def geocode_weather_location(location):
    """Convert a city/state name into latitude and longitude using Open-Meteo."""

    if not location:
        return None

    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": location,
                "count": 5,
                "language": "en",
                "format": "json"
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        if not results:
            return None

        # Prefer a U.S. result when available.
        for result in results:
            if result.get("country_code") == "US":
                return {
                    "name": result.get("name", location),
                    "latitude": result.get("latitude"),
                    "longitude": result.get("longitude"),
                    "country": result.get("country", "United States"),
                    "state": result.get("admin1", "")
                }

        result = results[0]

        return {
            "name": result.get("name", location),
            "latitude": result.get("latitude"),
            "longitude": result.get("longitude"),
            "country": result.get("country", ""),
            "state": result.get("admin1", "")
        }

    except Exception as e:
        print("Weather geocoding error:", e)
        return None

def weather_code_description(code):
    """Convert Open-Meteo weather codes into readable descriptions."""

    descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }

    return descriptions.get(code, "Unknown weather")

def get_weather(location):

    original_location = location

    # Whole-state weather request.
    if location in STATE_CAPITALS:

        location = STATE_CAPITALS[location]

        state_summary = (
            f"This is a representative weather reading "
            f"for {location}; weather can vary across "
            f"the state."
        )

    else:

        state_summary = ""

    place = geocode_weather_location(
        location
    )

    if not place:

        return {
            "success": False,
            "error": (
                f"I couldn't find weather information "
                f"for {original_location}."
            )
        }

    latitude = place.get(
        "latitude"
    )

    longitude = place.get(
        "longitude"
    )

    if latitude is None or longitude is None:

        return {
            "success": False,
            "error": (
                f"I couldn't determine the location "
                f"for {original_location}."
            )
        }

    try:

        response = requests.get(
            OPEN_METEO_WEATHER_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,

                "current": (
                    "temperature_2m,"
                    "relative_humidity_2m,"
                    "apparent_temperature,"
                    "precipitation,"
                    "rain,"
                    "showers,"
                    "snowfall,"
                    "weather_code,"
                    "cloud_cover,"
                    "wind_speed_10m,"
                    "wind_direction_10m"
                ),

                "daily": (
                    "weather_code,"
                    "temperature_2m_max,"
                    "temperature_2m_min,"
                    "precipitation_probability_max,"
                    "precipitation_sum"
                ),

                "temperature_unit": "fahrenheit",

                "wind_speed_unit": "mph",

                "precipitation_unit": "inch",

                "timezone": "auto",

                "forecast_days": 3
            },

            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        current = data.get(
            "current",
            {}
        )

        daily = data.get(
            "daily",
            {}
        )

        weather_code = current.get(
            "weather_code"
        )

        description = weather_code_description(
            weather_code
        )

        current_time = current.get(
            "time",
            ""
        )

        result = {

            "success": True,

            "requested_location":
                original_location,

            "location_name":
                place.get(
                    "name",
                    original_location
                ),

            "state":
                place.get(
                    "admin1",
                    ""
                ),

            "country":
                place.get(
                    "country",
                    ""
                ),

            "latitude":
                latitude,

            "longitude":
                longitude,

            "timezone":
                data.get(
                    "timezone",
                    ""
                ),

            "time":
                current_time,

            "description":
                description,

            "temperature":
                current.get(
                    "temperature_2m"
                ),

            "apparent_temperature":
                current.get(
                    "apparent_temperature"
                ),

            "humidity":
                current.get(
                    "relative_humidity_2m"
                ),

            "precipitation":
                current.get(
                    "precipitation"
                ),

            "rain":
                current.get(
                    "rain"
                ),

            "showers":
                current.get(
                    "showers"
                ),

            "snowfall":
                current.get(
                    "snowfall"
                ),

            "cloud_cover":
                current.get(
                    "cloud_cover"
                ),

            "wind_speed":
                current.get(
                    "wind_speed_10m"
                ),

            "wind_direction":
                current.get(
                    "wind_direction_10m"
                ),

            "daily":
                daily,

            "state_summary":
                state_summary
        }

        return result

    except Exception as e:

        print(
            "MyAI weather API error:",
            e
        )

        return {
            "success": False,
            "error": (
                "The weather service could not "
                "be reached right now."
            )
        }


def format_weather_context(weather):

    if not weather.get("success"):

        return ""

    daily = weather.get(
        "daily",
        {}
    )

    dates = daily.get(
        "time",
        []
    )

    max_temps = daily.get(
        "temperature_2m_max",
        []
    )

    min_temps = daily.get(
        "temperature_2m_min",
        []
    )

    rain_probability = daily.get(
        "precipitation_probability_max",
        []
    )

    precipitation = daily.get(
        "precipitation_sum",
        []
    )

    forecast_lines = []

    for index, date in enumerate(
        dates[:3]
    ):

        maximum = (
            max_temps[index]
            if index < len(max_temps)
            else None
        )

        minimum = (
            min_temps[index]
            if index < len(min_temps)
            else None
        )

        probability = (
            rain_probability[index]
            if index < len(rain_probability)
            else None
        )

        rain_amount = (
            precipitation[index]
            if index < len(precipitation)
            else None
        )

        # Convert the API date into the correct weekday.
        try:
            forecast_date = datetime.strptime(
                date,
                "%Y-%m-%d"
            )

            if index == 0:
                day_name = "Today"
            elif index == 1:
                day_name = "Tomorrow"
            else:
                day_name = forecast_date.strftime("%A")

            display_date = forecast_date.strftime("%b %-d")
        except Exception:
            day_name = date
            display_date = date

        forecast_lines.append(
            f"{day_name} ({display_date}): "
            f"low={minimum}°F, "
            f"high={maximum}°F, "
            f"precipitation chance={probability}%, "
            f"precipitation={rain_amount} in"
        )

    forecast_text = "\n".join(
        forecast_lines
    )

    return f"""
LIVE WEATHER DATA

Location:
{weather["location_name"]}, {weather["state"]}

Timezone:
{weather["timezone"]}

Current observation time:
{weather["time"]}

Current conditions:
{weather["description"]}

Temperature:
{weather["temperature"]}°F

Feels like:
{weather["apparent_temperature"]}°F

Humidity:
{weather["humidity"]}%

Wind:
{weather["wind_speed"]} mph

Wind direction:
{weather["wind_direction"]}°

Cloud cover:
{weather["cloud_cover"]}%

Rain:
{weather["rain"]} in

Showers:
{weather["showers"]} in

Snow:
{weather["snowfall"]} in

{weather["state_summary"]}

3-DAY FORECAST:
{forecast_text}

Weather data source:
Open-Meteo
"""


# =========================================================
# SEARXNG WEB SEARCH
# =========================================================

def ai_web_search(query):

    try:

        response = requests.get(
            f"{SEARXNG_URL}/search",

            params={
                "q": query,
                "format": "json",
                "categories": "general"
            },

            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for result in data.get(
            "results",
            []
        )[:8]:

            title = result.get(
                "title",
                ""
            )

            content = result.get(
                "content",
                ""
            )

            url = result.get(
                "url",
                ""
            )

            if title and url:

                results.append({

                    "title":
                        title,

                    "content":
                        content,

                    "url":
                        url
                })

        return results

    except Exception as e:

        print(
            "MyAI search error:",
            e
        )

        return []


# =========================================================
# AI PAGE
# =========================================================

@myai.route("/ai")
def ai_page():

    return render_template(
        "ai.html"
    )


# =========================================================
# AI CHAT
# =========================================================

@myai.route(
    "/api/ai",
    methods=["POST"]
)
def ai_chat():

    if not gemini_client:

        return jsonify({

            "error":
                "MyAI is not configured. "
                "Add GEMINI_API_KEY."

        }), 500


    data = request.get_json(
        silent=True
    ) or {}


    message = data.get(
        "message",
        ""
    ).strip()


    if not message:

        return jsonify({

            "error":
                "Please enter a message."

        }), 400


    conversation = data.get(
        "conversation",
        ""
    )


    # =====================================================
    # WEATHER
    # =====================================================

    weather = None

    if looks_like_weather_question(
        message
    ):

        weather_location = (
            clean_weather_location(
                message
            )
        )

        if not weather_location:
            return jsonify({
                "answer": "Sure! What city or location would you like the weather for?",
                "model": "weather",
                "sources": []
            })

        # Handle "AL" and other states.
        state_name = None

        if weather_location:

            if weather_location in STATE_CAPITALS:

                state_name = (
                    weather_location
                )

        if state_name:

            weather = get_weather(
                state_name
            )

        else:

            weather = get_weather(
                weather_location
            )


    # =====================================================
    # NORMAL WEB SEARCH
    # =====================================================

    results = []

    # Weather questions use the weather API instead
    # of wasting the search query on normal web search.
    if not weather:

        results = ai_web_search(
            message
        )


    # =====================================================
    # SEARCH CONTEXT
    # =====================================================

    search_context_parts = []

    for result in results:

        search_context_parts.append(

            f"Title: {result['title']}\n"
            f"Content: {result['content']}\n"
            f"URL: {result['url']}"

        )


    search_context = "\n\n".join(
        search_context_parts
    )


    # =====================================================
    # WEATHER CONTEXT
    # =====================================================

    weather_context = ""

    if weather:

        if weather.get("success"):

            weather_context = (
                format_weather_context(
                    weather
                )
            )

        else:

            weather_context = (
                "WEATHER ERROR:\n"
                + weather.get(
                    "error",
                    "Unknown weather error."
                )
            )


    # =====================================================
    # PROMPT
    # =====================================================

    prompt = f"""
You are MyAI, the AI assistant built into MySpace.

You are helpful, honest, clear, and friendly.

SAFETY RULES:

- Do not help steal passwords, accounts, money, or personal information.
- Do not provide malware, ransomware, spyware, or credential-stealing code.
- Do not help bypass security systems without authorization.
- For cybersecurity questions, focus on defensive and authorized security.
- Do not provide instructions for seriously harming someone.
- If a request is unsafe, briefly explain that you cannot help with it.

IMPORTANT WEATHER RULE:

If LIVE WEATHER DATA is provided below, use that data for weather questions.

Do not replace the live weather data with random search results.

If the user asks about "AL", "Alabama", or another state,
explain that the weather shown for a whole state is a representative
location and that conditions can vary across the state.

LIVE WEATHER DATA:

{weather_context}

INTERNET SEARCH RESULTS:

{search_context}

CONVERSATION:

{conversation}

CURRENT USER MESSAGE:

{message}

ANSWER RULES:

- Answer the user clearly and directly.
- Use LIVE WEATHER DATA for weather questions.
- Use internet search results when they are relevant.
- Do not invent facts.
- Do not invent URLs.
- If a weather question has live weather data, give the current
  temperature, conditions, feels-like temperature, humidity,
  wind, and useful forecast information when appropriate.
- Use Fahrenheit for temperatures.
- Keep weather answers easy to read.
- If the user asks about a whole state, mention the representative
  city being used.
- When giving the user a website, article, page, video, or other
  online resource, make it a clickable Markdown link.
- Use this exact format:

  [Website Name](URL)

- Always use the actual URL from the search results.
- Never make up a URL.
- If the user specifically asks for a link, provide the relevant
  clickable link.
- If multiple useful sources are available, you may provide multiple
  clickable links.
"""


    # =====================================================
    # GEMINI MODEL FALLBACK
    # =====================================================

    last_error = None


    for model in AI_MODELS:

        print(
            f"MyAI trying model: {model}"
        )


        try:

            response = (
                gemini_client
                .models
                .generate_content(
                    model=model,
                    contents=prompt
                )
            )


            answer = response.text


            print(
                f"MyAI succeeded with model: {model}"
            )


            return jsonify({

                "answer":
                    answer,

                "sources":
                    results,

                "model":
                    model

            })


        except Exception as e:

            error_text = str(e)


            print(
                f"MyAI model {model} failed: "
                f"{error_text}"
            )


            last_error = e


            if (
                "429" in error_text
                or
                "RESOURCE_EXHAUSTED"
                in error_text
            ):

                print(
                    f"MyAI quota reached for "
                    f"{model}. Trying next model."
                )

                continue


            if (
                "503" in error_text
                or
                "UNAVAILABLE"
                in error_text
            ):

                print(
                    f"MyAI temporary overload "
                    f"on {model}. Trying next model."
                )

                continue


            if (
                "404" in error_text
                or
                "NOT_FOUND"
                in error_text
            ):

                print(
                    f"MyAI model {model} "
                    f"unavailable. Trying next model."
                )

                continue


            print(
                f"MyAI error on {model}. "
                f"Trying next model."
            )

            continue


    # =====================================================
    # ALL MODELS FAILED
    # =====================================================

    return jsonify({

        "error": (
            "MyAI could not get a response "
            "from any available Gemini model. "
            f"Last error: {last_error}"
        )

    }), 503
