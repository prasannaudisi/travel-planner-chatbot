from flask import Flask, render_template, request, jsonify,redirect,url_for
import json
import numpy as np
from tensorflow import keras
import pickle
import random
import json
from geopy.geocoders import Nominatim
from geopy.distance import distance
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import mysql.connector
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management
# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='Yaswanth@29',
        database='chatbot'
    )
# Load your model, tokenizer, and label encoder
model = keras.models.load_model('chat_model2.keras')
with open('tokenizer.pickle', 'rb') as handle:
    tokenizer = pickle.load(handle)
with open('label_encoder.pickle', 'rb') as enc:
    lbl_encoder = pickle.load(enc)
with open('city.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

def get_city_info(city):
    for intent in data['intents']:
        if intent['tag'] == 'city_info':
            city_data = intent['data'].get(city.lower())
            print(f"City Data for {city}: {city_data}")  # Log the data for debugging
            return city_data
    return None
def extract_city_name(user_input):
    normalized_input = user_input.lower().replace('_', ' ')
    cities = [
        "hyderabad", "chennai", "araku", "bangalore", "kerala",
        "pondicherry", "goa", "vizag", "mysore", "tirupati",
        "rajahmundry", "vijayawada", "bhimavaram", "kakinada",
        "manali", "nellore", "varanasi", "ladakh", "punjab"
    ]
    
    for city in cities:
        if city in normalized_input:
            return city
    return None
# Distance calculation functions
def driver_distance(loc1, loc2):
    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    
    geolocator = Nominatim(user_agent='distance_calculator')
    loc1 = geolocator.geocode(loc1)
    loc2 = geolocator.geocode(loc2)
    
    if loc1 and loc2:
        url = f'https://distancecalculator.globefeed.com/India_Distance_Result.asp?fromlat={loc1.latitude}&fromlng={loc1.longitude}&tolat={loc2.latitude}&tolng={loc2.longitude}'
        driver.get(url)
        try:
            # Wait for the result to be available, with retries
            for _ in range(10):  # Attempt up to 10 times
                distance_text = driver.find_element(By.XPATH, '//*[@id="drvDistance"]').text
                if distance_text != "Calculating...":
                    return float(distance_text.split()[0])  # Get the numeric value from the text
                time.sleep(1)  # Wait for 1 second before checking again

            print("Error: Distance calculation did not complete in time.")
            return None  # Return None if we didn't get a valid distance
        finally:
            driver.quit()
    return None

def calculate_budget(current_location, destination, mode):
    distance_km = driver_distance(current_location, destination)
    if distance_km is not None:
        cost_per_km = 10  # Default cost per kilometer
        if mode == 'bus':
            cost_per_km = 2  # Cost per km for bus
        elif mode == 'car':
            cost_per_km = 7  # Cost per km for car
        elif mode == 'bike':
            cost_per_km = 3   # Cost per km for bike
        
        total_cost = distance_km * cost_per_km
        return round(total_cost, 2), round(distance_km, 2)  # Return total cost and distance
    else:
        return None, None



# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['mail']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (mail, password) VALUES (%s, %s)", (username, password))
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for('login'))  # Redirect to the login page after registration

    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['mail']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE mail = %s and password= %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:  # user[1] is the password from the database
            return render_template('index.html')  # Redirect to the home page after successful login
        else:
            return "Invalid username or password!"

    return render_template('login.html')

# Home route
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    print(f"User Message: {user_message}")

    try:
        # Predict the intent
        max_len = 20
        padded_sequence = keras.preprocessing.sequence.pad_sequences(
            tokenizer.texts_to_sequences([user_message]),
            truncating='post', maxlen=max_len
        )
        result = model.predict(padded_sequence)
        tag = lbl_encoder.inverse_transform([np.argmax(result)])[0]
        response_data = []
# Check for budget-related inquiries
        if tag == 'budget':
            # Extract current location, destination, and mode from user_message
            import re
            match = re.search(r'from (\w+) to (\w+) by (\w+)', user_message)
            if match:
                current_location = match.group(1)
                destination = match.group(2)
                mode = match.group(3)
                
                total_cost, distance_km = calculate_budget(current_location, destination, mode)
                
                if total_cost is not None:
                    response_data.append({
                        "type": "text",
                        "text": f"The travel cost from {current_location} to {destination} by {mode} is ₹{total_cost} (Distance: {distance_km} km)."
                    })
                else:
                    response_data.append({"type": "error", "text": "I couldn't calculate the budget. Please check your input."})
            else:
                response_data.append({"type": "error", "text": "Could not extract locations and mode from your message. Please try a different format."})

        # Check for specific city-related inquiries
        elif tag == 'city_info':
            city = extract_city_name(user_message)
            city_data = get_city_info(city)

            if city_data:
                user_message_lower = user_message.lower()
# Handle accommodations inquiries
                if "stay" in user_message_lower or "accommodation" in user_message_lower or "hotel" in user_message_lower:
                    accommodations = city_data.get('accommodations', [])
                    if accommodations:
                        for accommodation in accommodations:
                            response_data.append({
                                'type': 'accommodation',
                                'name': accommodation['name'],
                                'description': accommodation['description'],
                                'price_range': accommodation['price_range'],
                                'image': accommodation.get('image')
                            })
                    else:
                        response_data.append({"type": "error", "text": "No accommodations found for this city."})

# Handle dining inquiries
                elif "dining" in user_message_lower or "eat" in user_message_lower or "restaurant" in user_message_lower:
                    dining_options = city_data.get('dining_options', [])
                    if dining_options:
                        for dining in dining_options:
                            response_data.append({
                                'type': 'dining',
                                'name': dining['name'],
                                'description': dining['description'],
                                'price_range': dining['price_range'],
                                'image': dining.get('image')
                            })
                    else:
                        response_data.append({"type": "error", "text": "No dining options found for this city."})
# Handle places to visit
                elif "visit" in user_message_lower or "places" in user_message_lower or "attractions" in user_message_lower:
                    places_to_visit = city_data.get('places_to_visit', [])
                    if places_to_visit:
                        for place in places_to_visit:
                            response_data.append({
                                'type': 'place',
                                'name': place['name'],
                                'description': place['description'],
                                'budget': place['budget'],
                                'image': place.get('image')
                            })
                    else:
                        response_data.append({"type": "error", "text": "No places to visit found for this city."})

                else:
                    response_data.append({"type": "error", "text": "Please specify if you're looking for accommodations, dining options, or places to visit."})
            else:
                response_data.append({"type": "error", "text": "Sorry, I couldn't find information for that city."})

        else:
            # Generic responses for other intents
            for intent in data['intents']:
                if intent['tag'] == tag:
                    response_data.append({
                        "type": "text",
                        "text": random.choice(intent['responses'])
                    })
                    break
            else:
                response_data.append({"type": "error", "text": "Sorry, I didn't understand that."})

        return jsonify(response_data)

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify([{"type": "error", "text": f"Oops! There was an error processing your request: {str(e)}"}])

if __name__ == '__main__':
    app.run(debug=True)
