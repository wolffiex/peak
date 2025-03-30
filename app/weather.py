# Weather data scraper and database integration
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import psycopg2
from psycopg2 import sql
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse

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
                    item_value = value_element["value"].strip()  # Extract the value attribute
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
                "dbname": "monitoring",
                "user": "adam",
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
                "dbname": "monitoring",
                "user": "adam",
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
            hourly_data.append({
                "hour": row[0].isoformat(),
                "avg_temp": float(row[1]) if row[1] else None,
                "min_temp": float(row[2]) if row[2] else None,
                "max_temp": float(row[3]) if row[3] else None,
                "avg_humidity": float(row[4]) if row[4] else None,
                "avg_pressure": float(row[5]) if row[5] else None,
                "avg_wind": float(row[6]) if row[6] else None,
            })
        
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
                "dbname": "monitoring",
                "user": "adam",
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
            daily_data.append({
                "day": row[0].isoformat().split('T')[0],
                "min_temp": float(row[1]) if row[1] else None,
                "max_temp": float(row[2]) if row[2] else None,
                "avg_temp": float(row[3]) if row[3] else None,
                "avg_humidity": float(row[4]) if row[4] else None,
            })
        
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
            barometer_data.append({
                "period": row[0].isoformat(),
                "avg_pressure": float(row[1]) if row[1] else None,
            })
        
        # Calculate barometer trend (rising, falling, steady)
        barometer_trend = "steady"
        if len(barometer_data) >= 2:
            first = barometer_data[0]["avg_pressure"] if barometer_data[0]["avg_pressure"] else 0
            last = barometer_data[-1]["avg_pressure"] if barometer_data[-1]["avg_pressure"] else 0
            if last - first > 0.02:  # More than 0.02 inHg change
                barometer_trend = "rising"
            elif first - last > 0.02:
                barometer_trend = "falling"
        
        # UV index high in last 24 hours
        query = """
        SELECT max(uvi) as max_uvi
        FROM weather 
        WHERE time > NOW() - INTERVAL '24 hours';
        """
        
        cur.execute(query)
        row = cur.fetchone()
        max_uvi = float(row[0]) if row and row[0] else None
        
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
            wind_data.append({
                "hour": row[0].isoformat(),
                "avg_wind": float(row[1]) if row[1] else None,
                "max_wind": float(row[2]) if row[2] else None,
            })
        
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
            "max_uvi": max_uvi,
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

@router.get("/weather", response_class=HTMLResponse)
async def weather_page(request: Request):
    """HTML page for displaying the weather report with server-rendered data"""
    report = get_weather_report()
    
    return _templates.TemplateResponse(
        "weather.html", 
        {
            "request": request,
            "weather_data": report if report else {},
            "current": report.get("current", {}) if report else {},
            "daily_data": report.get("daily_data", []) if report else [],
            "barometer_data": report.get("barometer_data", []) if report else [],
            "barometer_trend": report.get("barometer_trend", "steady") if report else "steady",
            "max_uvi": report.get("max_uvi", None) if report else None,
            "wind_data": report.get("wind_data", []) if report else []
        }
    )

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
        return JSONResponse({"status": "error", "message": "Failed to update weather data"}, status_code=500)

def install_routes(app, templates):
    """Install routes to the FastAPI app"""
    global _templates
    _templates = templates
    app.include_router(router)