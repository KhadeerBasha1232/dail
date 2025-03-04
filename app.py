import os, json
from flask import Flask, request
from flask_socketio import SocketIO, join_room, leave_room, send, disconnect
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()  # Load environment variables

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Supabase Configuration (Secure)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

rooms = {}  # Dictionary to track receivers in each room

@app.route("/")
def home():
    return "Chat App is Running with Supabase!"

@socketio.on("join")
def handle_join(data):
    name = data["name"]
    room = data["room"]
    help_type = data["helpType"]

    if room not in rooms:
        rooms[room] = {"receiver_present": False, "users": {}}

    if help_type == "help_receive":
        if rooms[room]["receiver_present"]:
            send({"name": "Server", "msg": "Receiver already exists in this room."}, to=request.sid)
            disconnect(request.sid)
            return
        rooms[room]["receiver_present"] = True

    role = "Receiver" if help_type == "help_receive" else "Sender"
    rooms[room]["users"][request.sid] = {"name": name, "role": role}

    join_room(room)
    send({"name": "Server", "msg": f"{name} has joined as {role}."}, to=room)

    # Fetch previous messages from Supabase
    response = supabase.table("messages").select("*").eq("room", room).order("timestamp").execute()

    if "error" in response:
        print("DB Fetch Error:", response["error"])

    messages = response.data if response.data else []

    for msg in messages:
        send({"name": msg["name"], "msg": msg["message"]}, to=request.sid)

@socketio.on("message")
def handle_message(data):
    name = data["name"]
    msg = data["msg"]
    room = data["room"]

    # Save message to Supabase
    response = supabase.table("messages").insert({"room": room, "name": name, "message": msg}).execute()

    if "error" in response:
        print("DB Insert Error:", response["error"])

    send({"name": name, "msg": msg}, to=room)

@socketio.on("leave")
def handle_leave(data):
    room = data["room"]

    if room in rooms and request.sid in rooms[room]["users"]:
        user = rooms[room]["users"].pop(request.sid)
        leave_room(room)
        send({"name": "Server", "msg": f"{user['name']} ({user['role']}) has left the room."}, to=room)

        if user["role"] == "Receiver":
            rooms[room]["receiver_present"] = False  

        if not rooms[room]["users"]:
            del rooms[room]

@socketio.on("disconnect")
def handle_disconnect():
    for room, data in rooms.items():
        if request.sid in data["users"]:
            user = data["users"].pop(request.sid)
            send({"name": "Server", "msg": f"{user['name']} ({user['role']}) has been disconnected."}, to=room)

            if user["role"] == "Receiver":
                data["receiver_present"] = False  

            if not data["users"]:
                del rooms[room]
            break  

@socketio.on("screen-data")
def handle_screen_data(data):
    try:
        data = json.loads(data)
        room = data.get("room")
        image = data.get("image")

        if not image.startswith("data:image"):  # If no MIME type, add one
            print("Invalid image format received:", image[:50])
            image = f"data:image/png;base64,{image}"  # Ensure correct format

        print(f"Sending image to room {room}")

        socketio.emit("screen-data", {"room": room, "image": image}, room=room, include_self=True)

    except json.JSONDecodeError as e:
        print(f"Invalid JSON received: {e}")




if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
