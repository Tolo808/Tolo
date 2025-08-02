import requests
import time
import json
import os
from datetime import datetime
from geopy.geocoders import Nominatim   
from dotenv import load_dotenv
from pymongo import MongoClient
import logging
from uuid import uuid4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_activity.log"),  
        logging.StreamHandler()                  
    ]
)




load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client["tolo_delivery"]
deliveries_collection = db["deliveries"]
feedback_collection = db["feedback"]
free_delivery_collection = db["free_delivery"]
last_info_collection = db["last_order_info"]
BOT_TOKEN = os.getenv("BOT_TOKEN")
username = os.getenv("AT_USERNAME")
api_key = os.getenv("AT_API_KEY")

AFRO_TOKEN = os.getenv("AFRO_TOKEN")
AFRO_SENDER_ID = os.getenv("AFRO_SENDER_ID")

API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'
JSON_FILE = 'messages.json'
STATE_FILE = 'user_states.json'



offset_collection = db["offset_tracking"]

def load_offset():
    record = offset_collection.find_one({"_id": "telegram_offset"})
    if record:
        return record.get("last_update_id")
    return None

def save_offset(offset):
    offset_collection.update_one(
        {"_id": "telegram_offset"},
        {"$set": {"last_update_id": offset}},
        upsert=True
    )


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
    {"command": "/level", "description": "Check your level / ደረጃዎን ያሳዩ"},
    {"command": "/mydeliveries", "description": "Your recent deliveries / ያስተላለፉት ትእዛዞች"},


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
    return requests.get(f'{API_URL}/getUpdates', params={'timeout': 100, 'offset': offset}, timeout=110).json()


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
        logging.info(f"Delivery saved: {data}")
    except Exception as e:
        print("❌ Failed to save to MongoDB:", e)
        logging.error(f"Error saving delivery: {e}")    


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
        logging.info(f"Feedback saved: {data}")
    except Exception as e:
        print("❌ Failed to save feedback:", e)
        error_message = f"Error saving feedback: {e}"



def load_states():
    with open(STATE_FILE, 'r') as f:
        return json.load(f)


def save_states(states):
    with open(STATE_FILE, 'w') as f:
        json.dump(states, f)

def get_user_level(delivery_count):
    if delivery_count < 10:
        return 1
    return (delivery_count // 10) + 1

def has_used_free_delivery(chat_id, level):
    return free_delivery_collection.find_one({"chat_id": chat_id, "level": level}) is not None

def mark_free_delivery_used(chat_id, level):
    free_delivery_collection.insert_one({"chat_id": chat_id, "level": level, "used": True})

def get_last_order_info(chat_id):
    doc = last_info_collection.find_one({"chat_id": chat_id})
    return doc.get("data", {}) if doc else {}

def save_last_order_info(chat_id, data):
    last_info_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"data": data}},
        upsert=True
    )


def main():
    last_update_id = load_offset()
    print("🚀 Bot is running...")
    logging.info("Bot started successfully.")
    response = requests.post(url, json={"commands": Commands})
    

    while True:
        updates = get_updates(offset=last_update_id)
        states = load_states()

        for result in updates.get("result", []):
            update_id = result["update_id"]
            if "callback_query" in result:
                callback = result["callback_query"]
                chat_id = str(callback["message"]["chat"]["id"])
                data = callback["data"]
                
                if data == "start_over":
                    states[chat_id] = {"step": 0, "data": {}}
                    save_states(states)
                    send_message(chat_id, "🔄 Starting over. Let's begin again.")
                    send_message(chat_id, Data_Message[0]['label'])
                elif data == "keep_going":
                    step = states[chat_id]["step"]
                    current_field = Data_Message[step]["label"]
                    send_message(chat_id, f"📍 Continuing your current session.\n\n{current_field}")
                elif data == "new_order":
                    states[chat_id] = {"step": 0, "data": {}}
                    previous = get_last_order_info(chat_id)
                    if previous:
                        payment_choice = states[chat_id]["data"].get("payment_from_sender_or_receiver")
                    send_message(chat_id, "📦 Great! Let's begin your new order.")
                    send_message(chat_id, Data_Message[0]["label"])

                elif data == "no_more_orders":
                    send_message(chat_id, "👍 Thank you for using Tolo Delivery!\nYou can type /start anytime to create a new delivery.")

            message = result.get("message")
            if not message:
                continue

            chat_id = str(message["chat"]["id"])
            logging.info(f"Processing message from chat_id {chat_id} with update_id {update_id}")

            if "location" in message and chat_id in states:
                lat = message["location"]["latitude"]
                lon = message["location"]["longitude"]
                states[chat_id]["data"].update({"latitude": lat, "longitude": lon})
                states[chat_id]["data"].update(get_address_from_coordinates(lat, lon))
                states[chat_id]["step"] += 1
                save_states(states)
                logging.info(f"Location received for chat_id {chat_id}: {lat}, {lon}")
                request_payment_option(chat_id)
                continue  # ✅ No update to last_update_id here

            if "text" not in message:
                continue

            text = message["text"].strip()
            logging.info(f"Received message: {text} from chat_id {chat_id}")

            if text.lower() in ["/about", "/contact", "/feedback", "/price"]:
                # Check if user is in an active delivery session (step is integer)
                if chat_id in states and isinstance(states[chat_id].get("step"), int):
                    send_message(chat_id, "⚠️ You have an active delivery session. Please finish or cancel it before using this command.")
                    logging.info(f"Blocked {text} command for active session user {chat_id}")
                    continue

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
            
       

            elif text.lower() == "/level":
                delivery_count = deliveries_collection.count_documents({"chat_id": chat_id})
                level = get_user_level(delivery_count)
                next_level = level + 1
                next_target = next_level * 10
                to_next = next_target - delivery_count

                used = has_used_free_delivery(chat_id, level)
                free_text = "✅ Used" if used else "🎁 Available"

                msg = (
                    f"🏅 *Your Level Info*\n\n"
                    f"Level: {level}\n"
                    f"Deliveries made: {delivery_count}\n"
                    f"Free delivery at this level: {free_text}\n\n"
                    f"📈 {to_next} more deliveries to reach Level {next_level}.\n"
                    f"Keep delivering with Tolo! 🚀"
                )
                send_message(chat_id, msg)
                continue
            
            elif text.lower() == "/mydeliveries":
                recent_deliveries = list(deliveries_collection.find(
                    {"chat_id": chat_id}
                ).sort("timestamp", -1).limit(5))

                if not recent_deliveries:
                    send_message(chat_id, "📭 You haven’t made any deliveries yet.")
                    continue

                message_lines = ["📦 *Your Last 5 Deliveries:*"]
                for d in recent_deliveries:
                    date_str = d.get("timestamp", "N/A")
                    level = d.get("user_level", "N/A")
                    free = "✅ Free" if d.get("is_free_delivery") else "💰 Paid"
                    destination = d.get("receiver_location", "Unknown")
                    message_lines.append(f"📍 {destination}\n🗓️ {date_str} | {level} | {free}\n")

                send_message(chat_id, "\n".join(message_lines))
                continue



            if text.lower() == "/start":
                if chat_id in states:
                    
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "✅ Yes, start over", "callback_data": "start_over"}],
                            [{"text": "❌ No, continue current", "callback_data": "keep_going"}]
                        ]
                    }
                    send_message(chat_id, "⚠️ You already have an active delivery. Do you want to cancel it and start over?", reply_markup=reply_markup)
                else:
                   
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
                        logging.warning(f"Invalid phone number input from chat_id {chat_id}: {text}")
                        continue

                if field == "Quantity":
                    if not text.isdigit() or int(text) <= 0:
                        send_message(chat_id, "⚠️ Please enter a valid quantity (positive number). / እባክዎ ትክክል ቁጥር ያስገቡ።")
                        logging.warning(f"Invalid quantity input from chat_id {chat_id}: {text}")
                        continue

                valid_inputs = ["Sender / ላኪ", "Receiver / ተቀባይ"]
                if field == "payment_from_sender_or_receiver":
                    valid_inputs = ["Sender / ላኪ", "Receiver / ተቀባይ"]
                    if text not in valid_inputs:
                        request_payment_option(chat_id)
                        continue
                    else:
                        remove_keyboard(chat_id)
                        if text == "Receiver / ተቀባይ":
                            state["skip_sender_info"] = True
                            previous = last_info_collection.get(chat_id, {})
                            state["data"]["pickup"] = previous.get("pickup")
                            state["data"]["sender_phone"] = previous.get("sender_phone")
                        else:
                            state["skip_sender_info"] = False
                            previous = get_last_order_info(chat_id)

                            state["data"]["dropoff"] = previous.get("dropoff")
                            state["data"]["receiver_phone"] = previous.get("receiver_phone")

                
                
                state["data"][field] = text
                logging.info(f"Step {step} completed for chat_id {chat_id}: {field} = {text}")

                if step == 0:
                    user = message["from"]
                    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    state["data"]["user_name"] = full_name

                 # Advance to next step, skipping if needed
                next_step = step + 1
                while next_step < len(Data_Message):
                    next_field = Data_Message[next_step]["field"]
                    if state.get("skip_sender_info") and next_field in ["pickup", "sender_phone"]:
                        next_step += 1
                        continue
                    if not state.get("skip_sender_info") and next_field in ["dropoff", "receiver_phone"]:
                        next_step += 1
                        continue
                    break

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
                    state["data"]["source"] = "bot" 
                    delivery_count = deliveries_collection.count_documents({"chat_id": chat_id})
                    level = get_user_level(delivery_count)
                    state["data"]["user_level"] = f"Level {level}"

                    if not has_used_free_delivery(chat_id, level):
                        state["data"]["is_free_delivery"] = True
                        mark_free_delivery_used(chat_id, level)
                    else:
                        state["data"]["is_free_delivery"] = False


                    order_id = str(uuid4())[:8]
                    state["data"]["order_id"] = order_id

                    save_delivery(state["data"])
                    save_last_order_info(chat_id, {
                        "pickup": state["data"].get("pickup"),
                        "sender_phone": state["data"].get("sender_phone"),
                        "dropoff": state["data"].get("dropoff"),
                        "receiver_phone": state["data"].get("receiver_phone")
                    })


                    del states[chat_id]
                    save_states(states)
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "➕ New Order", "callback_data": "new_order"}],
                            [{"text": "❌ Done", "callback_data": "no_more_orders"}]
                        ]
                    }

                    send_message(chat_id, "✅ Your order has been accepted! We Will Notify via sms When Driver Is Assigned Thank you for using Tolo Delivery..\nWould you like to place another order? \n ትዕዛዝዎ ተቀባይነት አግኝቷል! ሾፌሩ ሲመደብ በSMS አማካኝነት እናሳውቆታለን። ቶሎ ዴሊቨሪ በመጠቀምዎ እናመሰግናለን\n ሌላ ትእዛዝ መጨመር ይፍልጋሉ?", reply_markup=reply_markup)
                
               
                    
            else:
                send_message(chat_id, "Type /start to begin. / እባክዎ /start ይጻፉ ለመጀመር።")
                logging.info(f"Prompted chat_id={chat_id} to use /start")
                
            
        if updates.get("result"):
            last_update_id = updates["result"][-1]["update_id"] + 1
            save_offset(last_update_id)


        time.sleep(1)
        
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.critical(f"🚨 Bot crashed: {e}", exc_info=True)
