import requests
import time
import json
import os
from datetime import datetime
from geopy.geocoders import Nominatim   
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client["tolo_delivery"]
deliveries_collection = db["deliveries"]
feedback_collection = db["feedback"]

BOT_TOKEN = os.getenv("BOT_TOKEN")
username = os.getenv("AT_USERNAME")
api_key = os.getenv("AT_API_KEY")

AFRO_TOKEN = os.getenv("AFRO_TOKEN")
AFRO_SENDER_ID = os.getenv("AFRO_SENDER_ID")

API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'
JSON_FILE = 'messages.json'
STATE_FILE = 'user_states.json'

url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"


geolocator = Nominatim(user_agent="ssas-bot")


# Create files if not exist


for file in [JSON_FILE, STATE_FILE]:
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump({}, f) if file == STATE_FILE else json.dump([], f)



Commands = [
    {"command": "/start", "description": "Start the bot / ቦትን ጀምር"},
    {"command": "/about", "description": "About this bot / ስለምን ይህ ቦት"},
    {"command": "/contact", "description": "Contact us / እኛን ያግኙ"},
    {"command": "/cancel", "description": "Cancel current operation / አሁን ያቋርጡ"},
    {"command": "/feedback", "description": "Send feedback / እቅድ ያስተውሉ"},
    {"command": "/price", "description": "Get price list / ዋጋ "},
]

# Fields expected in the delivery form
Data_Message = [
    {"field": "pickup", "label": "Enter pickup location: / መነሻ ቦታን ያስገቡ:"},
    {"field": "sender_phone", "label": "Enter sender's phone number: / የላኪውን ስልክ ቁጥር ያስገቡ:"},
    {"field": "dropoff", "label": "Enter drop-off location: / መድረሻ ቦታን ያስገቡ:"},
    {"field": "receiver_phone", "label": "Enter receiver's phone number: / የተቀባዩን ስልክ ቁጥር ያስገቡ:"},
    {"field": "location_marker", "label": "📍 Please share your location: / እባክዎ አካባቢዎን ያካፍሉ:"},
    {"field": "payment_from_sender_or_receiver", "label": "Who will pay for the delivery? / ክፍያው በማን ነው?"},
    {"field": "item_description", "label": "Enter item description: / የእቃውን አይነት ያስገቡ:"},
    {"field": "Quantity", "label": "Enter quantity: / ብዛትን ያስገቡ:"},
]



def get_updates(offset=None):
    return requests.get(f'{API_URL}/getUpdates', params={'timeout': 100, 'offset': offset}).json()


def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f'{API_URL}/sendMessage', data=payload)


def request_location(chat_id):
    keyboard = {
        "keyboard": [[{"text": "📍 Share Location", "request_location": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    send_message(chat_id, "📍 Please share your location: / እባክዎ አካባቢዎን ያጋሩ: ", reply_markup=keyboard)

def request_payment_option(chat_id):
    keyboard = {
        "keyboard": [
            [{"text": "Sender / ላኪ"}],
            [{"text": "Receiver / ተቀባይ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    send_message(chat_id, "Who will pay for the delivery? / ከፋዩ ማን ነው?", reply_markup=keyboard)


def get_address_from_coordinates(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {'lat': lat, 'lon': lon, 'format': 'json', 'addressdetails': 1}
        headers = {'User-Agent': 'ToloDeliveryBot/1.0'}
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        address = data.get("address", {})
        return {
            "full_address": data.get("display_name", "Unknown location"),
            "city": address.get("city", address.get("town", "")),
            "postcode": address.get("postcode", ""),
            "country": address.get("country", "")
        }
    except Exception as e:
        print("Geocoding failed:", e)
        return {}


def remove_keyboard(chat_id):
    keyboard = {"remove_keyboard": True}
    send_message(chat_id, "✅Confirmed ", reply_markup=keyboard)  



def save_delivery(data):
   
    try:
        deliveries_collection.insert_one(data)
        print("✅ Delivery saved to MongoDB.")
    except Exception as e:
        print("❌ Failed to save to MongoDB:", e)


def send_sms(phone_number, message):
    session = requests.Session()
    # base url
    base_url = 'https://api.afromessage.com/api/send'
    # api token
    token = AFRO_TOKEN
        # header
    headers = {'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'}
        # request body
    body = {'callback': 'YOUR_CALLBACK',
                'from':AFRO_SENDER_ID,
                'sender':'AfroMessage',
                'to': phone_number,
                'message': message}
        # make request
    result = session.post(base_url, json=body, headers=headers)
        # check result
    if result.status_code == 200:
        json_resp = result.json()
        print("🔍 Full JSON Response:", json_resp)  # ← ADD THIS LINE

        if json_resp.get('acknowledge') == 'success':
            print('✅ SMS sent successfully!')
        else:
            print('❌ API responded with error:', json_resp)

    else:
            # anything other than 200 goes here.
        print ('http error ... code: %d , msg: %s ' % (result.status_code, result.content))


def save_feedback(data):
    try:
        feedback_collection.insert_one(data)
        print("✅ Feedback saved to MongoDB.")
    except Exception as e:
        print("❌ Failed to save feedback:", e)



def load_states():
    with open(STATE_FILE, 'r') as f:
        return json.load(f)


def save_states(states):
    with open(STATE_FILE, 'w') as f:
        json.dump(states, f)


def main():
    last_update_id = None
    print("🚀 Bot is running...")

    while True:
        updates = get_updates(offset=last_update_id)
        states = load_states()

        for result in updates.get("result", []):
            update_id = result["update_id"]
            message = result.get("message")
            if not message:
                continue

            chat_id = str(message["chat"]["id"])

            if "location" in message and chat_id in states:
                lat = message["location"]["latitude"]
                lon = message["location"]["longitude"]
                states[chat_id]["data"].update({"latitude": lat, "longitude": lon})
                states[chat_id]["data"].update(get_address_from_coordinates(lat, lon))
                states[chat_id]["step"] += 1
                save_states(states)
            
                request_payment_option(chat_id)
                continue  # ✅ No update to last_update_id here

            if "text" not in message:
                continue

            text = message["text"].strip()
            if text.lower() == "/feedback":
                states[chat_id] = {"step": "feedback"}  # special mode
                save_states(states)
                send_message(chat_id, "📝 Please type your feedback below. / እባክዎ እቅድዎን እዚህ ያስገቡ:")
                continue

            # If user is in feedback mode
            if chat_id in states and states[chat_id].get("step") == "feedback":
                user = message["from"]
                full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                feedback_data = {
                    "user_name": full_name,
                    "chat_id": chat_id,
                    "feedback": text,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_feedback(feedback_data)
                send_message(chat_id, "✅ Thank you for your feedback! / እናመሰግናለን ለእቅድዎ!")
                del states[chat_id]
                save_states(states)
                continue
            elif text.lower() == "/about":
                send_message(chat_id,
                    "📦 *About Tolo Delivery*\n\n"
                    "Tolo Delivery is a fast and reliable delivery service helping you send packages across Addis Ababa.\n"
                    "We are committed to making your delivery experience quick and seamless.\n\n"
                    "ቶሎ ዴሊቨሪ በአዲስ አበባ ውስጥ ጥቅሎችን ለመላክ የሚረዳ ፈጣን እና አስተማማኝ የአቅርቦት አገልግሎት ነው. \n"
                    "የአቅርቦት ተሞክሮዎ ፈጣን እና እንከን የለሽ ለማድረግ ተግተን እንሰራለን"
                )

            elif text.lower() == "/contact":
                send_message(chat_id,
                    "📞 *Contact Us*\n\n"
                    "Phone: +251921296933\n"
                    "     : +251900041277\n"
                    "Email: info@tolo9558.com\n"
                    "ለአገልግሎታችን ከሆነ ጥያቄ ወይም መረጃ ለማግኘት:\n"
                    "ስልክ: +251921296933\n"
                    "     +251900041277\n"
                    "ኢሜይል: info@tolo9558.com"
                )
            elif text.lower() == "/price":
                send_message(chat_id,
                    "💰 *Delivery Price*: \n\n"
                    "1 - 5 km: 100 birr\n"
                    "6 - 10 km: 200 birr\n"
                    "11 - 20 km: 300 birr\n"
                    "የዋጋ ዝርዝር: \n"
                    "1 - 5 ኪ.ሜ: 100 ብር\n"
                    "6 - 10 ኪ.ሜ: 200 ብር\n"
                    "11 - 20 ኪ.ሜ: 300 ብር\n"
                )
            if text.lower() == "/start":
                states[chat_id] = {"step": 0, "data": {}}
                save_states(states)
                send_message(chat_id, "👋 Selam! Welcome to Tolo Delivery.\nሰላም! ወደ ቶሎ ዴሊቨሪ እንኳን በደህና መጡ።\nLet's begin / እንጀምር።")
                send_message(chat_id, Data_Message[0]['label'])
            
            elif text.lower() == "/cancel":
                if chat_id in states:
                    del states[chat_id]
                    save_states(states)
                    send_message(chat_id, "❌ Operation cancelled. / እቅዱ ተሰርዟል።")
                else:
                    send_message(chat_id, "No operation to cancel. / ምንም እቅድ የለም።")

            elif chat_id in states:
                state = states[chat_id]
                step = state["step"]
                field_info = Data_Message[step]
                field = field_info["field"]

                if field in ["sender_phone", "receiver_phone"]:
                    if not ((text.startswith("09") and len(text) == 10 and text.isdigit()) or
                            (text.startswith("+2519") and len(text) == 13 and text[1:].isdigit())):
                        send_message(chat_id, "⚠️ Invalid Ethiopian phone number. Example: 0912345678 or +251912345678 / እባክዎ ትክክል የኢትዮጵያ ስልክ ቁጥር ያስገቡ።")
                        continue

                if field == "Quantity":
                    if not text.isdigit() or int(text) <= 0:
                        send_message(chat_id, "⚠️ Please enter a valid quantity (positive number). / እባክዎ ትክክል ቁጥር ያስገቡ።")
                        continue

                valid_inputs = ["Sender / ላኪ", "Receiver / ተቀባይ"]
                if field == "payment_from_sender_or_receiver":
                    if text not in valid_inputs:
                        request_payment_option(chat_id)
                        continue
                    else:
                        remove_keyboard(chat_id)  # ✅ User selected valid input → now remove keyboard

             
                
                state["data"][field] = text

                if step == 0:
                    user = message["from"]
                    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    state["data"]["user_name"] = full_name

                if step + 1 < len(Data_Message):
                    next_field_info = Data_Message[step + 1]
                    state["step"] += 1
                    save_states(states)

                    if next_field_info["field"] == "location_marker":
                        request_location(chat_id)
                    elif next_field_info["field"] == "payment_from_sender_or_receiver":
                        request_payment_option(chat_id)
                      
                    else:
                        send_message(chat_id, next_field_info["label"])
                else:
                    state["data"]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_delivery(state["data"])
                    del states[chat_id]
                    save_states(states)
                    send_message(chat_id, "✅ Your order has been accepted! We Will Notify via sms When Driver Is Assigned Thank you for using Tolo Delivery.\n ትዕዛዝዎ ተቀባይነት አግኝቷል! ሾፌሩ ሲመደብ በSMS አማካኝነት እናሳውቆታለን። ቶሎ ዴሊቨሪ በመጠቀምዎ እናመሰግናለን")
                
                response = requests.post(url, json={"commands": Commands})
                    
            else:
                send_message(chat_id, "Type /start to begin. / እባክዎ /start ይጻፉ ለመጀመር።")
            
        # ✅ Update offset here ONLY ONCE after all processing
        if updates.get("result"):
            last_update_id = updates["result"][-1]["update_id"] + 1

        time.sleep(1)
        
if __name__ == '__main__':
    main()
