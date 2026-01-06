# app.py - Vercel deployment
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pyrogram import Client
from pyrogram.enums import ChatType, UserStatus
from pyrogram.errors import PeerIdInvalid, UsernameNotOccupied, ChannelInvalid
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import os
import asyncio
import threading

# Vercel environment variables
API_ID = int(os.getenv("API_ID", "24785831"))
API_HASH = os.getenv("API_HASH", "81b87c7c85bf0c4ca15ca94dcea3fb95")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8007668447:AAE9RK3SCTvYVAXB8ZTQFUClCoqCAbvF9jQ")

# Validate environment variables
if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError("Please set API_ID, API_HASH, and BOT_TOKEN environment variables")

app = FastAPI(title="Telegram Info API", description="Get Telegram user/chat information", version="2.0.0")

# CORS enable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pyrogram client setup
client = None
client_lock = threading.Lock()

def get_dc_locations():
    return {
        1: "MIA, Miami, USA, US",
        2: "AMS, Amsterdam, Netherlands, NL",
        3: "MBA, Mumbai, India, IN",
        4: "STO, Stockholm, Sweden, SE",
        5: "SIN, Singapore, SG",
        6: "LHR, London, United Kingdom, GB",
        7: "FRA, Frankfurt, Germany, DE",
        8: "JFK, New York, USA, US",
        9: "HKG, Hong Kong, HK",
        10: "TYO, Tokyo, Japan, JP",
        11: "SYD, Sydney, Australia, AU",
        12: "GRU, São Paulo, Brazil, BR",
        13: "DXB, Dubai, UAE, AE",
        14: "CDG, Paris, France, FR",
        15: "ICN, Seoul, South Korea, KR",
    }

def calculate_account_age(creation_date):
    today = datetime.now()
    delta = relativedelta(today, creation_date)
    years = delta.years
    months = delta.months
    days = delta.days
    return f"{years} years, {months} months, {days} days"

def estimate_account_creation_date(user_id):
    reference_points = [
        (100000000, datetime(2013, 8, 1)),
        (1273841502, datetime(2020, 8, 13)),
        (1500000000, datetime(2021, 5, 1)),
        (2000000000, datetime(2022, 12, 1)),
    ]
    closest_point = min(reference_points, key=lambda x: abs(x[0] - user_id))
    closest_user_id, closest_date = closest_point
    id_difference = user_id - closest_user_id
    days_difference = id_difference / 20000000
    creation_date = closest_date + timedelta(days=days_difference)
    return creation_date

def get_profile_photo_url(username, size=320):
    if username:
        username = username.strip('@')
        return f"https://t.me/i/userpic/{size}/{username}.jpg"
    return None

def format_usernames_list(usernames):
    if not usernames:
        return []
    formatted_usernames = []
    for username_obj in usernames:
        if hasattr(username_obj, 'username'):
            formatted_usernames.append(username_obj.username)
        else:
            formatted_usernames.append(str(username_obj))
    return formatted_usernames

def clean_username_or_id(input_str):
    """
    Clean and extract username/ID from various input formats
    Supports:
    - https://t.me/username
    - t.me/username  
    - @username
    - username
    - https://t.me/joinchat/xxxx (for private groups)
    - User IDs
    """
    if not input_str:
        return None
    
    # Remove leading/trailing whitespace
    cleaned = input_str.strip()
    
    # Case 1: https://t.me/username or t.me/username
    telegram_patterns = [
        r'https?://(?:www\.)?t\.me/([a-zA-Z0-9_]+)',
        r'https?://(?:www\.)?telegram\.me/([a-zA-Z0-9_]+)',
        r'https?://(?:www\.)?telegram\.dog/([a-zA-Z0-9_]+)',
        r't\.me/([a-zA-Z0-9_]+)',
        r'telegram\.me/([a-zA-Z0-9_]+)',
        r'telegram\.dog/([a-zA-Z0-9_]+)'
    ]
    
    for pattern in telegram_patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(1)
    
    # Case 2: Join chat links (private groups)
    joinchat_pattern = r'https?://(?:www\.)?t\.me/joinchat/([a-zA-Z0-9_-]+)'
    match = re.search(joinchat_pattern, cleaned)
    if match:
        return match.group(1)
    
    # Case 3: +joinchat links (another format)
    plus_joinchat_pattern = r'https?://(?:www\.)?t\.me/\+([a-zA-Z0-9_-]+)'
    match = re.search(plus_joinchat_pattern, cleaned)
    if match:
        return match.group(1)
    
    # Case 4: @username format
    if cleaned.startswith('@'):
        return cleaned[1:]
    
    # Case 5: Direct username or ID
    # Remove any remaining special characters
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', cleaned)
    
    return cleaned if cleaned else None

async def ensure_client():
    global client
    with client_lock:
        if client is None:
            try:
                client = Client(
                    "VercelTelegramAPI",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    bot_token=BOT_TOKEN,
                    in_memory=True  # Vercel serverless
                )
                await client.start()
                print("Pyrogram client started successfully")
                return True
            except Exception as e:
                print(f"Failed to start Pyrogram client: {str(e)}")
                client = None
                return False
        
        try:
            # Check if client is connected
            is_connected = getattr(client, 'is_connected', False)
            if callable(is_connected):
                connected = is_connected()
            else:
                connected = is_connected
            
            if not connected:
                await client.start()
                print("Pyrogram client reconnected successfully")
        except Exception as e:
            print(f"Failed to check/restart client: {str(e)}")
            try:
                client = Client(
                    "VercelTelegramAPI",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    bot_token=BOT_TOKEN,
                    in_memory=True
                )
                await client.start()
                print("Pyrogram client recreated successfully")
            except Exception as e2:
                print(f"Failed to recreate client: {str(e2)}")
                client = None
                return False
        
        return True

async def get_user_info(username_or_id):
    try:
        if not await ensure_client():
            return {"success": False, "error": "Client initialization failed"}
        
        DC_LOCATIONS = get_dc_locations()
        
        # Clean the input
        cleaned_input = clean_username_or_id(username_or_id)
        if not cleaned_input:
            return {"success": False, "error": "Invalid username or ID format"}
        
        print(f"Looking up user with cleaned input: {cleaned_input}")
        
        # Try to get user by username or ID
        try:
            # First try as user ID if it's numeric
            if cleaned_input.isdigit():
                user_id = int(cleaned_input)
                user = await client.get_users(user_id)
            else:
                # Try as username
                user = await client.get_users(cleaned_input)
        except Exception as e:
            print(f"Error getting user: {str(e)}")
            return {"success": False, "error": "User not found"}
        
        # Get full user info to retrieve bio
        try:
            full_user = await client.get_chat(user.id)
            bio = getattr(full_user, 'bio', None)
        except:
            bio = None
        
        premium_status = getattr(user, 'is_premium', False)
        dc_location = DC_LOCATIONS.get(user.dc_id, "Unknown")
        account_created = estimate_account_creation_date(user.id)
        account_created_str = account_created.strftime("%B %d, %Y")
        account_age = calculate_account_age(account_created)
        
        profile_photo_url = get_profile_photo_url(user.username) if user.username else None
        
        usernames_list = format_usernames_list(getattr(user, 'usernames', []))
        
        user_data = {
            "success": True,
            "type": "bot" if user.is_bot else "user",
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "usernames": usernames_list,
            "bio": bio,
            "dc_id": user.dc_id,
            "dc_location": dc_location,
            "is_premium": premium_status,
            "is_bot": user.is_bot,
            "account_created": account_created_str,
            "account_age": account_age,
            "profile_photo_url": profile_photo_url,
            "api_owner": "@nkka404",
            "api_updates": "t.me/premium_channel_404",
            "links": {
                "android": f"tg://openmessage?user_id={user.id}",
                "ios": f"tg://user?id={user.id}",
                "permanent": f"tg://user?id={user.id}"
            }
        }
        return user_data
    except (PeerIdInvalid, UsernameNotOccupied):
        return {"success": False, "error": "User not found"}
    except Exception as e:
        print(f"Error fetching user info: {str(e)}")
        return {"success": False, "error": f"Failed to fetch user information: {str(e)}"}

async def get_chat_info(username_or_id):
    try:
        if not await ensure_client():
            return {"success": False, "error": "Client initialization failed"}
        
        DC_LOCATIONS = get_dc_locations()
        
        # Clean the input
        cleaned_input = clean_username_or_id(username_or_id)
        if not cleaned_input:
            return {"success": False, "error": "Invalid username or ID format"}
        
        print(f"Looking up chat with cleaned input: {cleaned_input}")
        
        # Try to get chat by username or ID
        try:
            # First try as chat ID if it's numeric
            if cleaned_input.isdigit():
                chat_id = int(cleaned_input)
                # For group/channel IDs, they usually start with -100
                if chat_id > 0:
                    chat = await client.get_chat(chat_id)
                else:
                    chat = await client.get_chat(chat_id)
            else:
                # Try as username
                chat = await client.get_chat(cleaned_input)
        except Exception as e:
            print(f"Error getting chat: {str(e)}")
            return {"success": False, "error": "Chat not found"}
        
        chat_type_map = {
            ChatType.SUPERGROUP: "supergroup",
            ChatType.GROUP: "group",
            ChatType.CHANNEL: "channel"
        }
        chat_type = chat_type_map.get(chat.type, "unknown")
        dc_location = DC_LOCATIONS.get(getattr(chat, 'dc_id', None), "Unknown")
        
        profile_photo_url = get_profile_photo_url(chat.username) if chat.username else None
        
        usernames_list = format_usernames_list(getattr(chat, 'usernames', []))
        
        if chat.username:
            join_link = f"t.me/{chat.username}"
            permanent_link = f"t.me/{chat.username}"
        elif chat.id < 0:
            chat_id_str = str(chat.id).replace('-100', '')
            join_link = f"t.me/c/{chat_id_str}/1"
            permanent_link = f"t.me/c/{chat_id_str}/1"
        else:
            join_link = f"tg://resolve?domain={chat.id}"
            permanent_link = f"tg://resolve?domain={chat.id}"
        
        chat_data = {
            "success": True,
            "type": chat_type,
            "id": chat.id,
            "title": chat.title,
            "username": chat.username,
            "usernames": usernames_list,
            "description": getattr(chat, 'description', None),
            "dc_id": getattr(chat, 'dc_id', None),
            "dc_location": dc_location,
            "is_bot": False,
            "is_premium": False,
            "account_created": "Unknown",
            "account_age": "Unknown",
            "profile_photo_url": profile_photo_url,
            "api_owner": "@nkka404",
            "api_updates": "t.me/premium_channel_404",
            "links": {
                "join": join_link,
                "permanent": permanent_link
            }
        }
        return chat_data
    except (ChannelInvalid, PeerIdInvalid):
        return {"success": False, "error": "Chat not found or access denied"}
    except Exception as e:
        print(f"Error fetching chat info: {str(e)}")
        return {"success": False, "error": f"Failed to fetch chat information: {str(e)}"}

async def get_telegram_info(username_or_id):
    if not username_or_id:
        return {
            "success": False, 
            "error": "No username or ID provided", 
            "api_owner": "@nkka404", 
            "api_updates": "t.me/premium_channel_404"
        }
    
    cleaned_input = clean_username_or_id(username_or_id)
    if not cleaned_input:
        return {
            "success": False, 
            "error": "Invalid username or ID format", 
            "api_owner": "@nkka404", 
            "api_updates": "t.me/premium_channel_404"
        }
    
    print(f"Fetching info for: {username_or_id} (cleaned: {cleaned_input})")
    
    # First try as user
    user_info = await get_user_info(cleaned_input)
    if user_info["success"]:
        return user_info
    
    # Then try as chat
    chat_info = await get_chat_info(cleaned_input)
    if chat_info["success"]:
        return chat_info
    
    return {
        "success": False, 
        "error": "Entity not found in Telegram database", 
        "api_owner": "@nkka404", 
        "api_updates": "t.me/premium_channel_404"
    }

@app.get("/")
async def root():
    return {
        "message": "Telegram Info API by @nkka404",
        "status": "active",
        "endpoints": {
            "/api": "Get user/chat info",
            "/api/user/{username_or_id}": "Get specific user/chat info",
            "/health": "Check API health"
        },
        "version": "2.0.0",
        "owner": "@nkka404",
        "updates": "t.me/premium_channel_404",
        "supported_formats": [
            "https://t.me/username",
            "t.me/username",
            "@username", 
            "username",
            "https://t.me/joinchat/xxxx",
            "t.me/+invitecode",
            "User ID (123456789)",
            "Chat ID (-1001234567890)"
        ]
    }

@app.get("/api")
async def info_endpoint(username: str = "", size: int = 320):
    if not username:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "Missing 'username' parameter",
                "api_owner": "@nkka404",
                "api_updates": "t.me/premium_channel_404"
            }
        )
    
    try:
        result = await get_telegram_info(username)
        if result["success"] and "profile_photo_url" in result and result["profile_photo_url"]:
            result["profile_photo_url"] = get_profile_photo_url(
                result.get("username"), size
            ) if result.get("username") else None
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result)
            
    except Exception as e:
        print(f"Unexpected error fetching Telegram info for {username}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Internal server error: {str(e)}",
                "api_owner": "@nkka404",
                "api_updates": "t.me/premium_channel_404"
            }
        )

@app.get("/api/user/{username_or_id}")
async def user_endpoint(username_or_id: str, size: int = 320):
    return await info_endpoint(username_or_id, size)

@app.get("/health")
async def health_check():
    try:
        if await ensure_client():
            return {
                "status": "healthy",
                "client": "connected",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "unhealthy",
                "client": "disconnected",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }
