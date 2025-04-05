# Weather data scraper and database integration
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import psycopg2
from psycopg2 import sql
from fastapi import APIRouter
from .utils import (
    LOCAL_TIMEZONE as LOCAL_TZ,
    DATABASE_NAME,
    DATABASE_USER,
    localize_time,
    get_sunrise_sunset,
)
from .http_client import fetch
from .api import stream_anthropic_api, call_anthropic_api
from .prompts import get_standard_system_prompt
from .cache import cached

router = APIRouter()


def scrape_weather_data():
    """Scrape weather data from AmbientWeather and return processed data"""
    url = "http://10.1.1.150/livedata.htm"

    # Send an HTTP GET request to the URL
    try:
        # Increase timeout for slow responding device (over 10s observed)
        with httpx.Client(timeout=20) as client:
            response = client.get(url)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
    except httpx.HTTPError as e:
        print(f"Error fetching weather data: {e}")
        return None

    # Parse the HTML content of the page with BeautifulSoup
    soup = BeautifulSoup(response.content, "html.parser")

    # Initialize an empty dictionary to store results
    data = {}

    SCRAPED_FIELDS = {
        "Receiver Time": "time",
        "Indoor Temperature": "indoor_temp",
        "Relative Pressure": "pressure",
        "Outdoor Temperature": "outdoor_temp",
        "Humidity": "humidity",
        "Wind Speed": "wind_speed",
        "Solar Radiation": "solar_radiation",
        "UVI": "uvi",
        "Hourly Rain Rate": "rain_rate",
    }

    # Find all 'tr' elements
    for row in soup.find_all("tr"):
        # Find 'div' for the name and 'input' for the value within each 'tr'
        item_name_element = row.find("div", class_="item_1")
        value_element = row.find("input", class_="item_2")

        # If both elements are found, extract the text and value
        if item_name_element and value_element:
            item_name = item_name_element.text.strip()
            for sub_str, field_name in SCRAPED_FIELDS.items():
                if sub_str in item_name:
                    item_value = value_element[
                        "value"
                    ].strip()  # Extract the value attribute
                    data[field_name] = item_value
                    break

    if "time" not in data:
        print("No time data found in scrape")
        return None

    # Process the time
    time_format = "%H:%M %m/%d/%Y"
    try:
        naive_dt = datetime.strptime(data.pop("time"), time_format)
        eastern = pytz.timezone("US/Eastern")
        aware_dt = eastern.localize(naive_dt)
        data["time"] = aware_dt
    except ValueError as e:
        print(f"Error parsing time: {e}")
        return None

    return data


def save_to_db(data):
    """Save scraped weather data to the database"""
    if not data:
        return False

    # Establish a connection to the database
    try:
        conn = psycopg2.connect(
            **{
                "dbname": DATABASE_NAME,
                "user": DATABASE_USER,
            }
        )
        cur = conn.cursor()

        column_names = data.keys()
        column_values = data.values()
        weather_insert = sql.SQL("INSERT INTO weather ({}) VALUES ({})").format(
            sql.SQL(",").join(map(sql.Identifier, column_names)),
            sql.SQL(",").join(sql.Placeholder() * len(column_values)),
        )

        cur.execute(weather_insert, list(column_values))
        conn.commit()
        success = True
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
        success = False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return success


def get_recent_weather_stats(hours=24):
    """Get recent weather statistics from the database"""
    try:
        conn = psycopg2.connect(
            **{
                "dbname": DATABASE_NAME,
                "user": DATABASE_USER,
            }
        )
        cur = conn.cursor()

        # Query for hourly averages in the last 24 hours
        query = """
        SELECT time_bucket('1 hour', time) as hour, 
               avg(outdoor_temp) as avg_temp,
               min(outdoor_temp) as min_temp,
               max(outdoor_temp) as max_temp,
               avg(humidity) as avg_humidity,
               avg(pressure) as avg_pressure,
               avg(wind_speed) as avg_wind
        FROM weather 
        WHERE time > NOW() - INTERVAL '%s hours'
        GROUP BY hour 
        ORDER BY hour DESC;
        """

        cur.execute(query, (hours,))
        hourly_data = []
        for row in cur.fetchall():
            hourly_data.append(
                {
                    "hour": row[0].isoformat(),
                    "avg_temp": float(row[1]) if row[1] else None,
                    "min_temp": float(row[2]) if row[2] else None,
                    "max_temp": float(row[3]) if row[3] else None,
                    "avg_humidity": float(row[4]) if row[4] else None,
                    "avg_pressure": float(row[5]) if row[5] else None,
                    "avg_wind": float(row[6]) if row[6] else None,
                }
            )

        # Query for overall stats
        query = """
        SELECT 
            avg(outdoor_temp) as avg_temp,
            min(outdoor_temp) as min_temp,
            max(outdoor_temp) as max_temp,
            avg(humidity) as avg_humidity,
            avg(pressure) as avg_pressure,
            avg(wind_speed) as avg_wind,
            max(time) as last_update
        FROM weather 
        WHERE time > NOW() - INTERVAL '%s hours';
        """

        cur.execute(query, (hours,))
        row = cur.fetchone()
        overall_stats = {
            "avg_temp": float(row[0]) if row[0] else None,
            "min_temp": float(row[1]) if row[1] else None,
            "max_temp": float(row[2]) if row[2] else None,
            "avg_humidity": float(row[3]) if row[3] else None,
            "avg_pressure": float(row[4]) if row[4] else None,
            "avg_wind": float(row[5]) if row[5] else None,
            "last_update": row[6].isoformat() if row[6] else None,
        }

        return {
            "hourly_data": hourly_data,
            "overall_stats": overall_stats,
        }

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_yesterday_summary():
    """Get a summary of yesterday's weather including:
    - High temperature and time it occurred
    - UV index from sunrise to sunset
    - Total rainfall
    """
    # Get yesterday's date with timezone
    yesterday = datetime.now(LOCAL_TZ) - timedelta(days=1)
    yesterday_start = LOCAL_TZ.localize(
        datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
    )
    yesterday_end = LOCAL_TZ.localize(
        datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
    )

    # Calculate sunrise and sunset for yesterday using utility function
    sunrise_time, sunset_time = get_sunrise_sunset(yesterday)

    # Query database for yesterday's weather data
    try:
        conn = psycopg2.connect(
            **{
                "dbname": DATABASE_NAME,
                "user": DATABASE_USER,
            }
        )
        cur = conn.cursor()

        # Find the high temperature and when it occurred
        high_temp_query = """
        SELECT outdoor_temp, time
        FROM weather
        WHERE time >= %s AND time <= %s
        ORDER BY outdoor_temp DESC
        LIMIT 1;
        """

        cur.execute(high_temp_query, (yesterday_start, yesterday_end))
        high_temp_row = cur.fetchone()

        high_temp = None
        high_temp_time = None

        if high_temp_row:
            high_temp = float(high_temp_row[0]) if high_temp_row[0] else None
            high_temp_time = high_temp_row[1] if high_temp_row[1] else None

        # Get UV index data during daylight hours
        uv_query = """
        SELECT 
            AVG(uvi) as avg_uvi,
            MAX(uvi) as max_uvi,
            MIN(uvi) as min_uvi
        FROM weather
        WHERE time >= %s AND time <= %s;
        """

        daylight_start = sunrise_time if sunrise_time else yesterday_start
        daylight_end = sunset_time if sunset_time else yesterday_end

        cur.execute(uv_query, (daylight_start, daylight_end))
        uv_row = cur.fetchone()

        avg_uvi = float(uv_row[0]) if uv_row and uv_row[0] else None
        max_uvi = float(uv_row[1]) if uv_row and uv_row[1] else None
        min_uvi = float(uv_row[2]) if uv_row and uv_row[2] else None

        # Calculate total rainfall for yesterday
        rain_query = """
        SELECT 
            SUM(rain_rate) / 4 as total_rain  -- Divide by 4 because readings are hourly rates taken every 15 minutes
        FROM weather
        WHERE time >= %s AND time <= %s AND rain_rate > 0;
        """

        cur.execute(rain_query, (yesterday_start, yesterday_end))
        rain_row = cur.fetchone()

        total_rain = float(rain_row[0]) if rain_row and rain_row[0] else 0.0

        # Get UV index data for every two hours during daylight
        hourly_uv = []
        if sunrise_time and sunset_time:
            # Create two-hour intervals between sunrise and sunset
            intervals = []
            current_time = sunrise_time

            while current_time < sunset_time:
                interval_end = min(current_time + timedelta(hours=2), sunset_time)
                intervals.append((current_time, interval_end))
                current_time = interval_end

            # Query UV data for each interval
            for start, end in intervals:
                interval_query = """
                SELECT 
                    time_bucket('5 minutes', time) as bucket,
                    AVG(uvi) as avg_uvi
                FROM weather
                WHERE time >= %s AND time <= %s
                GROUP BY bucket
                ORDER BY bucket;
                """

                cur.execute(interval_query, (start, end))

                # Calculate average UV for this interval
                readings = []
                for row in cur.fetchall():
                    if row[1] is not None:  # Check if UVI reading exists
                        readings.append(float(row[1]))

                # Add to hourly data if we have readings
                if readings:
                    avg_uvi_interval = (
                        sum(readings) / len(readings) if readings else None
                    )
                    max_uvi_interval = max(readings) if readings else None

                    # Convert to local time for display
                    start_local = localize_time(start)
                    end_local = localize_time(end)

                    hourly_uv.append(
                        {
                            "start_time": start_local,
                            "end_time": end_local,
                            "avg_uvi": avg_uvi_interval,
                            "max_uvi": max_uvi_interval,
                        }
                    )

        return {
            "date": yesterday.strftime("%Y-%m-%d"),
            "high_temp": high_temp,
            "high_temp_time": high_temp_time,
            "sunrise": sunrise_time,
            "sunset": sunset_time,
            "daylight_hours": (sunset_time - sunrise_time).total_seconds() / 3600
            if sunrise_time and sunset_time
            else None,
            "avg_uvi": avg_uvi,
            "max_uvi": max_uvi,
            "min_uvi": min_uvi,
            "hourly_uv": hourly_uv,
            "total_rain": total_rain,
        }

    except psycopg2.Error as e:
        print(f"Database error in yesterday summary: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_weather_report():
    """Get a comprehensive weather report including:
    - High/low for the last seven days
    - 12-hour barometer trend
    - UV index high in last 24 hours
    - Average wind for each of the last three hours
    """
    try:
        conn = psycopg2.connect(
            **{
                "dbname": DATABASE_NAME,
                "user": DATABASE_USER,
            }
        )
        cur = conn.cursor()

        # Daily high/low for the last 7 days
        query = """
        SELECT 
            time_bucket('1 day', time) as day,
            min(outdoor_temp) as min_temp,
            max(outdoor_temp) as max_temp,
            avg(outdoor_temp) as avg_temp,
            avg(humidity) as avg_humidity
        FROM weather 
        WHERE time > NOW() - INTERVAL '7 days'
        GROUP BY day
        ORDER BY day DESC;
        """

        cur.execute(query)
        daily_data = []
        for row in cur.fetchall():
            daily_data.append(
                {
                    "day": row[0].isoformat().split("T")[0],
                    "min_temp": float(row[1]) if row[1] else None,
                    "max_temp": float(row[2]) if row[2] else None,
                    "avg_temp": float(row[3]) if row[3] else None,
                    "avg_humidity": float(row[4]) if row[4] else None,
                }
            )

        # 12-hour barometer trend
        query = """
        SELECT 
            time_bucket('3 hour', time) as period,
            avg(pressure) as avg_pressure
        FROM weather 
        WHERE time > NOW() - INTERVAL '12 hours'
        GROUP BY period
        ORDER BY period;
        """

        cur.execute(query)
        barometer_data = []
        for row in cur.fetchall():
            barometer_data.append(
                {
                    "period": row[0].isoformat(),
                    "avg_pressure": float(row[1]) if row[1] else None,
                }
            )

        # Calculate barometer trend (rising, falling, steady)
        barometer_trend = "steady"
        if len(barometer_data) >= 2:
            first = (
                barometer_data[0]["avg_pressure"]
                if barometer_data[0]["avg_pressure"]
                else 0
            )
            last = (
                barometer_data[-1]["avg_pressure"]
                if barometer_data[-1]["avg_pressure"]
                else 0
            )
            if last - first > 0.02:  # More than 0.02 inHg change
                barometer_trend = "rising"
            elif first - last > 0.02:
                barometer_trend = "falling"

        # Wind for each of the last 3 hours
        query = """
        SELECT 
            time_bucket('1 hour', time) as hour,
            avg(wind_speed) as avg_wind,
            max(wind_speed) as max_wind
        FROM weather 
        WHERE time > NOW() - INTERVAL '3 hours'
        GROUP BY hour
        ORDER BY hour DESC;
        """

        cur.execute(query)
        wind_data = []
        for row in cur.fetchall():
            wind_data.append(
                {
                    "hour": row[0].isoformat(),
                    "avg_wind": float(row[1]) if row[1] else None,
                    "max_wind": float(row[2]) if row[2] else None,
                }
            )

        # Current conditions (most recent reading)
        query = """
        SELECT 
            time,
            outdoor_temp,
            humidity,
            pressure,
            wind_speed,
            uvi,
            rain_rate
        FROM weather 
        ORDER BY time DESC
        LIMIT 1;
        """

        cur.execute(query)
        row = cur.fetchone()
        current = None
        if row:
            current = {
                "time": row[0].isoformat(),
                "outdoor_temp": float(row[1]) if row[1] else None,
                "humidity": float(row[2]) if row[2] else None,
                "pressure": float(row[3]) if row[3] else None,
                "wind_speed": float(row[4]) if row[4] else None,
                "uvi": float(row[5]) if row[5] else None,
                "rain_rate": float(row[6]) if row[6] else None,
            }

        return {
            "daily_data": daily_data,
            "barometer_data": barometer_data,
            "barometer_trend": barometer_trend,
            "wind_data": wind_data,
            "current": current,
        }

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# Global variable for templates that will be set in install_routes
_templates = None


# Endpoint removed to focus on stdout functionality


@router.get("/api/weather/scrape")
@router.post("/api/weather/scrape")
async def scrape_weather_cron():
    """Endpoint for cron to trigger weather data scraping"""
    data = scrape_weather_data()
    if data and save_to_db(data):
        from fastapi.responses import JSONResponse

        return JSONResponse({"status": "success", "message": "Weather data updated"})
    else:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"status": "error", "message": "Failed to update weather data"},
            status_code=500,
        )


def install_routes(app, templates):
    """Install routes to the FastAPI app"""
    global _templates
    _templates = templates
    app.include_router(router)

    import markdown
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    import traceback

    @app.get("/weather")
    async def get_weather_html(request: Request):
        """Get weather info as HTML"""
        try:
            # Get the weather report
            report = get_report()

            # Get the summary as markdown
            weather_md = await get_weather_summary(report)

            # Convert markdown to HTML
            weather_html = markdown.markdown(weather_md, extensions=["extra"])

            # Return the HTML directly
            return HTMLResponse(weather_html)
        except Exception as e:
            print(f"Error generating weather HTML: {e}")
            traceback.print_exc()
            return HTMLResponse(f"<p>Error loading weather data: {str(e)}</p>")


def get_report():
    """Get a formatted weather summary as a string."""
    report = get_weather_report()
    yesterday = get_yesterday_summary()

    if not report:
        return "Failed to retrieve weather report"

    lines = []

    # Format current conditions
    current = report.get("current", {})
    if current:
        from datetime import datetime

        time_str = current.get("time")
        time_obj = datetime.fromisoformat(time_str) if time_str else None

        # Convert to local time zone (Pacific Time)
        time_obj = localize_time(time_obj)
        time_formatted = (
            time_obj.strftime("%A, %B %d at %I:%M %p") if time_obj else "Unknown"
        )

        lines.append("\n=== CURRENT WEATHER CONDITIONS ===")
        lines.append(f"Last Updated: {time_formatted}")
        lines.append(f"Temperature: {current.get('outdoor_temp', 'N/A'):.1f}°F")
        lines.append(f"Humidity: {current.get('humidity', 'N/A'):.0f}%")
        lines.append(
            f"Barometric Pressure: {current.get('pressure', 'N/A'):.2f} inHg ({report.get('barometer_trend', 'steady')})"
        )
        lines.append(f"Wind Speed: {current.get('wind_speed', 'N/A') or 'Calm'}")
        lines.append(f"UV Index: {current.get('uvi', 'N/A')}")
        lines.append(f"Rain Rate: {current.get('rain_rate', 'N/A') or 'None'}")

    # Yesterday's summary
    if yesterday:
        from datetime import datetime

        lines.append("\n=== YESTERDAY'S SUMMARY ===")
        lines.append(f"Date: {yesterday.get('date')}")

        # Format high temperature and time
        high_temp = yesterday.get("high_temp")
        high_temp_time = yesterday.get("high_temp_time")
        if high_temp is not None and high_temp_time is not None:
            time_formatted = (
                high_temp_time.strftime("%I:%M %p") if high_temp_time else "Unknown"
            )
            lines.append(f"High Temperature: {high_temp:.1f}°F at {time_formatted}")
        else:
            lines.append("High Temperature: No data available")

        # Format sunrise/sunset times
        sunrise = yesterday.get("sunrise")
        sunset = yesterday.get("sunset")
        daylight_hours = yesterday.get("daylight_hours")

        if sunrise and sunset:
            sunrise_local = localize_time(sunrise)
            sunset_local = localize_time(sunset)

            sunrise_fmt = sunrise_local.strftime("%I:%M %p")
            sunset_fmt = sunset_local.strftime("%I:%M %p")

            lines.append(f"Sunrise: {sunrise_fmt}")
            lines.append(f"Sunset: {sunset_fmt}")

            if daylight_hours:
                hours = int(daylight_hours)
                minutes = int((daylight_hours - hours) * 60)
                lines.append(f"Daylight: {hours} hours, {minutes} minutes")
        else:
            lines.append("Sunrise/Sunset: No data available")

        # Format UV index during daylight
        avg_uvi = yesterday.get("avg_uvi")
        max_uvi = yesterday.get("max_uvi")

        if avg_uvi is not None and max_uvi is not None:
            uvi_level = (
                "Low"
                if max_uvi < 3
                else "Moderate"
                if max_uvi < 6
                else "High"
                if max_uvi < 8
                else "Very High"
                if max_uvi < 11
                else "Extreme"
            )
            lines.append(
                f"UV Index during daylight: Avg {avg_uvi:.1f}, Max {max_uvi:.1f} ({uvi_level})"
            )

        # Display total rainfall for yesterday
        total_rain = yesterday.get("total_rain", 0.0)
        if total_rain > 0:
            lines.append(f"Total Rainfall: {total_rain:.2f} inches")
        else:
            lines.append("Total Rainfall: None")

        # Print UV index for every two hours from sunrise to sunset
        hourly_uv = yesterday.get("hourly_uv", [])
        if hourly_uv:
            lines.append("\n=== UV INDEX BY TIME PERIOD (YESTERDAY) ===")
            lines.append("Time Period           Average UV    Level")
            lines.append("--------------------------------------------")
            for period in hourly_uv:
                start_time = period.get("start_time")
                end_time = period.get("end_time")
                avg_uvi = period.get("avg_uvi")

                # Format times
                start_str = start_time.strftime("%I:%M %p")
                end_str = end_time.strftime("%I:%M %p")
                time_period = f"{start_str} - {end_str}"

                # Determine UV level
                if avg_uvi is not None:
                    uvi_level = (
                        "Low"
                        if avg_uvi < 3
                        else "Moderate"
                        if avg_uvi < 6
                        else "High"
                        if avg_uvi < 8
                        else "Very High"
                        if avg_uvi < 11
                        else "Extreme"
                    )
                    uvi_str = f"{avg_uvi:.1f}"
                else:
                    uvi_str = "N/A"
                    uvi_level = "N/A"

                lines.append(f"{time_period.ljust(22)} {uvi_str.ljust(12)} {uvi_level}")
        else:
            lines.append("UV Index: No data available")

    # Format daily high/low temperatures
    daily_data = report.get("daily_data", [])
    if daily_data:
        lines.append("\n=== 7-DAY TEMPERATURE HISTORY ===")
        lines.append("Date            Min    Max    Avg    Humidity")
        lines.append("--------------------------------------------")
        for day in daily_data:
            date_str = day.get("day", "N/A")
            min_temp = day.get("min_temp", "N/A")
            max_temp = day.get("max_temp", "N/A")
            avg_temp = day.get("avg_temp", "N/A")
            humidity = day.get("avg_humidity", "N/A")

            min_temp_str = (
                f"{min_temp:.1f}°F" if isinstance(min_temp, (int, float)) else "N/A"
            )
            max_temp_str = (
                f"{max_temp:.1f}°F" if isinstance(max_temp, (int, float)) else "N/A"
            )
            avg_temp_str = (
                f"{avg_temp:.1f}°F" if isinstance(avg_temp, (int, float)) else "N/A"
            )
            humidity_str = (
                f"{humidity:.0f}%" if isinstance(humidity, (int, float)) else "N/A"
            )

            lines.append(
                f"{date_str}    {min_temp_str.ljust(6)} {max_temp_str.ljust(6)} {avg_temp_str.ljust(6)} {humidity_str}"
            )

    # Format barometer trend
    lines.append("\n=== BAROMETER TREND (12 HOURS) ===")
    lines.append(f"Current Trend: {report.get('barometer_trend', 'steady').title()}")

    barometer_data = report.get("barometer_data", [])
    if barometer_data:
        first_pressure = (
            barometer_data[0].get("avg_pressure")
            if barometer_data[0].get("avg_pressure")
            else 0
        )
        last_pressure = (
            barometer_data[-1].get("avg_pressure")
            if barometer_data[-1].get("avg_pressure")
            else 0
        )
        change = last_pressure - first_pressure
        lines.append(f"Pressure Change: {change:.3f} inHg")

    # Format wind data
    wind_data = report.get("wind_data", [])
    if wind_data:
        lines.append("\n=== RECENT WIND CONDITIONS ===")
        lines.append("Time              Average    Maximum")
        lines.append("-------------------------------------")
        for hour in wind_data:
            from datetime import datetime

            time_str = hour.get("hour")
            time_obj = datetime.fromisoformat(time_str) if time_str else None

            # Convert to local time zone (Pacific Time)
            time_obj = localize_time(time_obj)

            time_formatted = time_obj.strftime("%I:%M %p") if time_obj else "Unknown"

            avg_wind = hour.get("avg_wind")
            max_wind = hour.get("max_wind")

            avg_wind_str = (
                f"{avg_wind:.1f} mph" if isinstance(avg_wind, (int, float)) else "Calm"
            )
            max_wind_str = (
                f"{max_wind:.1f} mph" if isinstance(max_wind, (int, float)) else "Calm"
            )

            lines.append(
                f"{time_formatted.ljust(16)} {avg_wind_str.ljust(10)} {max_wind_str}"
            )

    lines.append("")

    # Join all lines into a single string
    return "\n".join(lines)


# Weather context prompts
WEATHER_PROMPT = f"""
Give a casual, friendly description of the weather right here in Meyers.
Start with a conversational mention of the current temperature and conditions - like you're chatting with a neighbor.
For example: 'It's a chilly 38° here in Meyers right now with clear skies. Yesterday was a warm with highs in the 60s.'
Blend in the following weather station data naturally without listing statistics.
Remember that rain rate may actually be snowmelt; this is not a fancy weather station. When in doubt, refer to moisture, not rain.
{{report}}
After a summary of the weather yesterday and the current conditions, tell us what to expect today/tomorrow and through the week.
Be enthusiastic about any exciting weather patterns coming - especially snow!
During winter and spring, suggest skiing and snowshowing as an outdoor activity when appropriate.
During summer and fall, suggest hiking and mountain biking.
End with a casual recommendation for outdoor activities given the forecast.
Use markdown to format your response.
"""


async def get_meyers_weather_forecast():
    # Fetch the NOAA forecast data
    noaa_url = "https://forecast.weather.gov/MapClick.php?lat=38.8569&lon=-120.0126"
    return await fetch(noaa_url)


@cached(600)  # Cache for 10 minutes
async def get_weather_summary(report):
    """
    Generate a weather forecast summary that can be cached
    """
    # Fetch the NOAA forecast data
    forecast_data = await get_meyers_weather_forecast()

    # Call the API to generate the summary
    messages = [
        {
            "role": "user",
            "content": "Here's the current weather forecast for Meyers, near South Lake Tahoe:",
        },
        {"role": "user", "content": forecast_data},
        {"role": "user", "content": WEATHER_PROMPT.format(report=report)},
    ]

    response = await call_anthropic_api(
        model="claude-3-7-sonnet-latest",
        system=get_standard_system_prompt(),
        messages=messages,
        max_tokens=800,
        temperature=0.2,
    )

    # Extract and return the content as a string
    return response.content[0].text


async def main():
    """Run the weather report and print results when script is run directly."""
    report = get_report()
    print(report)
    print()
    weather_summary = await get_weather_summary(report)
    print(weather_summary)
    print()


if __name__ == "__main__":
    # Run the main function when script is executed directly
    import asyncio

    asyncio.run(main())
