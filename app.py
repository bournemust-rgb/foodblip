from flask import Flask, render_template, request, jsonify
import requests
import os

app = Flask(__name__)

GOOGLE_API_KEY = "AIzaSyCLeD0v0ZKH6PHHQUJ4uQIR-ETu9K_21Z8"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search")
def search():
    query = request.args.get("query", "")
    location = request.args.get("location", "Cape Town")

    if not query:
        return jsonify({"error": "Please enter a restaurant name"}), 400

    # Step 1: Geocode the location
    geo_url = "https://maps.googleapis.com/maps/api/geocode/json"
    geo_params = {"address": location, "key": GOOGLE_API_KEY}
    geo_response = requests.get(geo_url, params=geo_params).json()

    if not geo_response.get("results"):
        return jsonify({"error": "Could not find that location"}), 400

    lat = geo_response["results"][0]["geometry"]["location"]["lat"]
    lng = geo_response["results"][0]["geometry"]["location"]["lng"]

    # Step 2: Search for places
    places_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    places_params = {
        "query": f"{query} restaurant",
        "location": f"{lat},{lng}",
        "radius": 10000,
        "key": GOOGLE_API_KEY
    }
    places_response = requests.get(places_url, params=places_params).json()
    results = places_response.get("results", [])

    if not results:
        return jsonify({"error": "No restaurants found. Did you mean something else?"}), 404

    output = []
    for place in results[:4]:
        place_id = place.get("place_id")

        # Step 3: Get place details
        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        details_params = {
            "place_id": place_id,
            "fields": "name,rating,user_ratings_total,formatted_address,opening_hours,current_opening_hours,price_level,types,geometry,photos",
            "key": GOOGLE_API_KEY
        }
        details = requests.get(details_url, params=details_params).json().get("result", {})

        # Step 4: Distance
        dist_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        dist_params = {
            "origins": f"{lat},{lng}",
            "destinations": f"place_id:{place_id}",
            "key": GOOGLE_API_KEY
        }
        dist_response = requests.get(dist_url, params=dist_params).json()
        try:
            distance = dist_response["rows"][0]["elements"][0]["distance"]["text"]
            duration = dist_response["rows"][0]["elements"][0]["duration"]["text"]
        except:
            distance = "N/A"
            duration = "N/A"

        # Step 5: Halaal check
        name = details.get("name", "")
        halaal_keywords = ["halaal", "halal", "muslim", "nandos", "steers", "burger king", "kfc", "mcdonalds"]
        is_halaal = any(k in name.lower() for k in halaal_keywords)
        halaal_label = "likely" if is_halaal else "unknown"

        # Step 6: Open now
        open_now = False
        try:
            open_now = details.get("current_opening_hours", {}).get("open_now", False)
        except:
            open_now = details.get("opening_hours", {}).get("open_now", False)

        # Step 7: Busy estimate based on time of day
        from datetime import datetime
        hour = datetime.now().hour
        day = datetime.now().weekday()  # 0=Monday, 6=Sunday
        if day >= 5:  # Weekend
            if 11 <= hour <= 14: busy = 90
            elif 18 <= hour <= 21: busy = 85
            elif 9 <= hour <= 11: busy = 60
            elif 14 <= hour <= 18: busy = 70
            else: busy = 20
        else:  # Weekday
            if 12 <= hour <= 14: busy = 80
            elif 18 <= hour <= 20: busy = 75
            elif 9 <= hour <= 12: busy = 40
            elif 14 <= hour <= 18: busy = 50
            else: busy = 15

        if busy >= 75: busy_label = "Very Busy"
        elif busy >= 50: busy_label = "Fairly Busy"
        elif busy >= 30: busy_label = "Moderate"
        else: busy_label = "Quiet"

        # Step 8: Photo
        photo_url = None
        photos = details.get("photos", [])
        if photos:
            photo_ref = photos[0].get("photo_reference")
            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_ref}&key={GOOGLE_API_KEY}"

        # Step 9: Destination coordinates for routing
        dest_lat = details.get("geometry", {}).get("location", {}).get("lat", "")
        dest_lng = details.get("geometry", {}).get("location", {}).get("lng", "")

        output.append({
            "name": name,
            "place_id": place_id,
            "address": details.get("formatted_address", ""),
            "rating": details.get("rating", "N/A"),
            "reviews": details.get("user_ratings_total", 0),
            "distance": distance,
            "drive_time": duration,
            "halaal": halaal_label,
            "open_now": open_now,
            "photo_url": photo_url,
            "busy": busy,
            "busy_label": busy_label,
            "maps_link": f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            "dest_lat": dest_lat,
            "dest_lng": dest_lng
        })

    return jsonify(output)


if __name__ == "__main__":
    app.run(debug=True)
