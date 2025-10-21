"""
Simple LiveKit Token Server
============================
A Flask server that generates LiveKit access tokens for your webapp frontend.

This server has one job: securely generate a LiveKit access token when your 
webapp asks for one.

Usage:
    python token_server.py

The server will run on http://localhost:8080
Your frontend can POST to http://localhost:8080/get-token to get credentials.
"""

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from livekit.api import AccessToken, VideoGrants
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

LIVEKIT_URL = os.environ.get("LIVEKIT_URL")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET")


@app.route("/get-token", methods=["POST"])
def get_livekit_token():
    """
    Generate a LiveKit access token.
    
    Expects a JSON body with 'identity' and 'roomName'.
    """
    data = request.get_json()
    identity = data.get("identity")
    room_name = data.get("roomName")

    if not identity or not room_name:
        return jsonify({"error": "identity and roomName are required"}), 400

    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        return jsonify({"error": "LiveKit server environment variables not set"}), 500

    # Create an AccessToken using the builder pattern
    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
    )

    return jsonify({
        "token": token.to_jwt(),
        "url": LIVEKIT_URL
    })


@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        print("⚠️  Warning: LiveKit environment variables are missing or incomplete.")
        print("   Please set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in your .env file")
    else:
        print(f"✓ LiveKit credentials loaded for URL: {LIVEKIT_URL}")
    
    print("\n🚀 Starting token server on http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)

