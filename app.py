from flask import Flask, render_template, request, jsonify
import requests
import os
import json

app = Flask(__name__, static_folder='static', static_url_path='/static')

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyCLeD0v0ZKH6PHHQUJ4uQIR-ETu9K_21Z8")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

# ── Static files ──────────────────────────────────────────
@app.route("/static/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/static/icon-192.png")
def icon192():
    return app.send_static_file("icon-192.png")

@app.route("/static/icon-512.png")
def icon512():
    return app.send_static_file("icon-512.png")

# ── Home ─────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ── AI Mood Picker (Groq) ─────────────────────────────────
@app.route("/mood", methods=["POST"])
def mood():
    data      = request.get_json(silent=True) or {}
    mood_text = data.get("mood", "").strip()

    if not mood_text:
        return jsonify({"error": "Please describe what you feel like eating."}), 400

    if not GROQ_API_KEY:
        return jsonify({"error": "AI mood picker is not configured yet."}), 503

    system_prompt = (
        "You are a food recommendation assistant for a South African restaurant finder app called Food Blip. "
        "The user will describe their mood, craving, or what they feel like eating. "
        "Your job is to respond with ONLY a valid JSON object — no extra text, no markdown. "
        "The JSON must have exactly these keys:\n"
        "  search_term: a short 1-3 word search term to use (e.g. 'pizza', 'spicy chicken', 'sushi')\n"
        "  reason: one short friendly sentence explaining why you picked this (max 12 words)\n"
        "  emoji: one relevant food emoji\n"
        "Example: {\"search_term\": \"spicy chicken\", \"reason\": \"Sounds like you need something bold and satisfying!\", \"emoji\": \"🌶️\"}"
    )

    try:
        groq_response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens":  120,
                "temperature": 0.7,
                "messages": [
                    {"role": "system",  "content": system_prompt},
                    {"role": "user",    "content": mood_text}
                ]
            },
            timeout=10
        )
        result  = groq_response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Strip any markdown fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        parsed = json.loads(content)
        return jsonify({
            "search_term": parsed.get("search_term", "restaurant"),
            "reason":      parsed.get("reason", "Here's a great option for you!"),
            "emoji":       parsed.get("emoji", "🍽️")
        })

    except Exception as e:
        return jsonify({"error": "AI is thinking too hard. Try again in a second!"}), 500


# ── Main search ───────────────────────────────────────────
@app.route("/search")
def search():
    query    = request.args.get("query", "")
    location = request.args.get("location", "Cape Town")

    if not query:
        return jsonify({"error": "Please enter a restaurant name"}), 400

    # Step 1: Geocode
    geo_response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": location, "key": GOOGLE_API_KEY}
    ).json()

    if not geo_response.get("results"):
        return jsonify({"error": "Could not find that location"}), 400

    lat = geo_response["results"][0]["geometry"]["location"]["lat"]
    lng = geo_response["results"][0]["geometry"]["location"]["lng"]

    # Step 2: Text search
    places_response = requests.get(
        "https://maps.googleapis.com/maps/api/place/textsearch/json",
        params={
            "query":    f"{query} restaurant",
            "location": f"{lat},{lng}",
            "radius":   10000,
            "key":      GOOGLE_API_KEY
        }
    ).json()

    results = places_response.get("results", [])
    if not results:
        return jsonify({"error": "No restaurants found. Did you mean something else?"}), 404

    output = []
    for place in results[:4]:
        place_id = place.get("place_id")

        # Step 3: Place details
        details = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields":   "name,rating,user_ratings_total,formatted_address,opening_hours,current_opening_hours,price_level,types,geometry,photos",
                "key":      GOOGLE_API_KEY
            }
        ).json().get("result", {})

        # Step 4: Distance
        try:
            dist_response = requests.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins":      f"{lat},{lng}",
                    "destinations": f"place_id:{place_id}",
                    "key":          GOOGLE_API_KEY
                }
            ).json()
            distance = dist_response["rows"][0]["elements"][0]["distance"]["text"]
            duration = dist_response["rows"][0]["elements"][0]["duration"]["text"]
        except:
            distance = "N/A"
            duration = "N/A"

        # Step 5: Halaal check
        name = details.get("name", "")
        halaal_keywords = ["halaal", "halal", "muslim", "nandos", "steers", "burger king", "kfc", "mcdonalds"]
        halaal_label = "likely" if any(k in name.lower() for k in halaal_keywords) else "unknown"

        # Step 6: Open now
        try:
            open_now = details.get("current_opening_hours", {}).get("open_now", False)
        except:
            open_now = details.get("opening_hours", {}).get("open_now", False)

        # Step 7: Busy estimate
        from datetime import datetime
        hour = datetime.now().hour
        day  = datetime.now().weekday()

        if day >= 5:
            if   11 <= hour <= 14: busy = 90
            elif 18 <= hour <= 21: busy = 85
            elif  9 <= hour <= 11: busy = 60
            elif 14 <= hour <= 18: busy = 70
            else:                  busy = 20
        else:
            if   12 <= hour <= 14: busy = 80
            elif 18 <= hour <= 20: busy = 75
            elif  9 <= hour <= 12: busy = 40
            elif 14 <= hour <= 18: busy = 50
            else:                  busy = 15

        if   busy >= 75: busy_label = "Very Busy"
        elif busy >= 50: busy_label = "Fairly Busy"
        elif busy >= 30: busy_label = "Moderate"
        else:            busy_label = "Quiet"

        # Step 8: Peak hours array
        peak_hours = []
        for h in range(24):
            if day >= 5:
                if   11 <= h <= 14: b = 90
                elif 18 <= h <= 21: b = 85
                elif  9 <= h <= 11: b = 60
                elif 14 <= h <= 18: b = 70
                else:               b = 20
            else:
                if   12 <= h <= 14: b = 80
                elif 18 <= h <= 20: b = 75
                elif  9 <= h <= 12: b = 40
                elif 14 <= h <= 18: b = 50
                else:               b = 15
            peak_hours.append(b)

        # Step 9: Photo
        photo_url = None
        photos = details.get("photos", [])
        if photos:
            photo_ref = photos[0].get("photo_reference")
            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_ref}&key={GOOGLE_API_KEY}"

        # Step 10: Coords for routing
        dest_lat = details.get("geometry", {}).get("location", {}).get("lat", "")
        dest_lng = details.get("geometry", {}).get("location", {}).get("lng", "")

        output.append({
            "name":       name,
            "place_id":   place_id,
            "address":    details.get("formatted_address", ""),
            "rating":     details.get("rating", "N/A"),
            "reviews":    details.get("user_ratings_total", 0),
            "distance":   distance,
            "drive_time": duration,
            "halaal":     halaal_label,
            "open_now":   open_now,
            "photo_url":  photo_url,
            "busy":       busy,
            "busy_label": busy_label,
            "maps_link":  f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(name)}&query_place_id={place_id}",
            "dest_lat":   dest_lat,
            "dest_lng":   dest_lng,
            "peak_hours": peak_hours
        })

    return jsonify(output)


if __name__ == "__main__":
    app.run(debug=True)
