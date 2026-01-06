# api/index.py - Vercel Serverless Function
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pyrogram import Client
from pyrogram.enums import ChatType
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import os
import asyncio
import logging
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables for Vercel
API_ID = os.getenv("API_ID", "24785831").strip()
API_HASH = os.getenv("API_HASH", "81b87c7c85bf0c4ca15ca94dcea3fb95").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "8007668447:AAE9RK3SCTvYVAXB8ZTQFUClCoqCAbvF9jQ").strip()

## API_ID = os.getenv("API_ID")
## API_HASH = os.getenv("API_HASH")
## BOT_TOKEN = os.getenv("BOT_TOKEN")

# Validate environment variables
if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.error("Missing environment variables. Please set API_ID, API_HASH, and BOT_TOKEN in Vercel")
    raise RuntimeError("Missing required environment variables")

app = FastAPI(title="Telegram Info API", description="Get Telegram user/chat information", version="2.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global client instance
client = None

def get_dc_locations():
    """Get Telegram DC locations"""
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
    """Calculate account age from creation date"""
    today = datetime.now()
    delta = relativedelta(today, creation_date)
    years = delta.years
    months = delta.months
    days = delta.days
    return f"{years} years, {months} months, {days} days"

def estimate_account_creation_date(user_id):
    """Estimate account creation date based on user ID"""
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
    """Get profile photo URL"""
    if username:
        username = username.strip('@')
        return f"https://t.me/i/userpic/{size}/{username}.jpg"
    return None

def format_usernames_list(usernames):
    """Format usernames list"""
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
    """
    if not input_str:
        return None
    
    cleaned = input_str.strip()
    
    # Telegram URL patterns
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
    
    # Join chat links
    joinchat_pattern = r'https?://(?:www\.)?t\.me/joinchat/([a-zA-Z0-9_-]+)'
    match = re.search(joinchat_pattern, cleaned)
    if match:
        return match.group(1)
    
    # +joinchat links
    plus_joinchat_pattern = r'https?://(?:www\.)?t\.me/\+([a-zA-Z0-9_-]+)'
    match = re.search(plus_joinchat_pattern, cleaned)
    if match:
        return match.group(1)
    
    # @username format
    if cleaned.startswith('@'):
        return cleaned[1:]
    
    # Direct username or ID
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', cleaned)
    
    return cleaned if cleaned else None

async def get_client():
    """Get or create Pyrogram client (Vercel serverless compatible)"""
    global client
    
    if client is None:
        try:
            logger.info("Creating new Pyrogram client...")
            client = Client(
                name="telegram_info_bot",
                api_id=int(API_ID),
                api_hash=API_HASH,
                bot_token=BOT_TOKEN,
                in_memory=True
            )
            
            await client.start()
            me = await client.get_me()
            logger.info(f"Pyrogram client created. Bot: @{me.username}")
            
        except Exception as e:
            logger.error(f"Failed to create Pyrogram client: {str(e)}")
            client = None
            raise
    
    return client

async def get_user_info(username_or_id):
    """Get user information"""
    try:
        client = await get_client()
        DC_LOCATIONS = get_dc_locations()
        
        cleaned_input = clean_username_or_id(username_or_id)
        if not cleaned_input:
            return {"success": False, "error": "Invalid username or ID format"}
        
        logger.info(f"Looking up user: {cleaned_input}")
        
        # Try to get user
        try:
            if cleaned_input.isdigit():
                user_id = int(cleaned_input)
                user = await client.get_users(user_id)
            else:
                user = await client.get_users(cleaned_input)
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return {"success": False, "error": "User not found"}
        
        # Get bio if available
        try:
            full_user = await client.get_chat(user.id)
            bio = getattr(full_user, 'bio', None)
        except:
            bio = None
        
        # Prepare user data
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
        
    except Exception as e:
        logger.error(f"Error in get_user_info: {e}")
        return {"success": False, "error": "Failed to fetch user information"}

async def get_chat_info(username_or_id):
    """Get chat information"""
    try:
        client = await get_client()
        DC_LOCATIONS = get_dc_locations()
        
        cleaned_input = clean_username_or_id(username_or_id)
        if not cleaned_input:
            return {"success": False, "error": "Invalid username or ID format"}
        
        logger.info(f"Looking up chat: {cleaned_input}")
        
        # Try to get chat
        try:
            if cleaned_input.isdigit():
                chat_id = int(cleaned_input)
                chat = await client.get_chat(chat_id)
            else:
                chat = await client.get_chat(cleaned_input)
        except Exception as e:
            logger.error(f"Error getting chat: {e}")
            return {"success": False, "error": "Chat not found"}
        
        # Determine chat type
        chat_type_map = {
            ChatType.SUPERGROUP: "supergroup",
            ChatType.GROUP: "group", 
            ChatType.CHANNEL: "channel",
            ChatType.PRIVATE: "private"
        }
        chat_type = chat_type_map.get(chat.type, "unknown")
        
        dc_location = DC_LOCATIONS.get(getattr(chat, 'dc_id', None), "Unknown")
        profile_photo_url = get_profile_photo_url(chat.username) if chat.username else None
        usernames_list = format_usernames_list(getattr(chat, 'usernames', []))
        
        # Generate links
        if chat.username:
            join_link = f"https://t.me/{chat.username}"
            permanent_link = f"https://t.me/{chat.username}"
        elif chat.id < 0:
            chat_id_str = str(chat.id).replace('-100', '')
            join_link = f"https://t.me/c/{chat_id_str}/1"
            permanent_link = f"https://t.me/c/{chat_id_str}/1"
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
            "members_count": getattr(chat, 'members_count', None),
            "profile_photo_url": profile_photo_url,
            "api_owner": "@nkka404",
            "api_updates": "t.me/premium_channel_404",
            "links": {
                "join": join_link,
                "permanent": permanent_link
            }
        }
        return chat_data
        
    except Exception as e:
        logger.error(f"Error in get_chat_info: {e}")
        return {"success": False, "error": "Failed to fetch chat information"}

async def get_telegram_info(username_or_id):
    """Get information for user or chat"""
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
    
    logger.info(f"Fetching info for: {username_or_id}")
    
    # First try as user
    user_info = await get_user_info(cleaned_input)
    if user_info.get("success"):
        return user_info
    
    # Then try as chat
    chat_info = await get_chat_info(cleaned_input)
    if chat_info.get("success"):
        return chat_info
    
    return {
        "success": False, 
        "error": "Entity not found in Telegram database", 
        "api_owner": "@nkka404", 
        "api_updates": "t.me/premium_channel_404"
    }

# Vercel အတွက် handler function
async def handler(request):
    """Vercel serverless handler"""
    path = request.get('path', '/')
    method = request.get('method', 'GET')
    
    if path == '/api' or path.startswith('/api/'):
        # API endpoint
        username = request.get('query', {}).get('username', '')
        size = int(request.get('query', {}).get('size', 320))
        
        if not username:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    "success": False,
                    "error": "Missing 'username' parameter",
                    "api_owner": "@nkka404",
                    "api_updates": "t.me/premium_channel_404"
                })
            }
        
        try:
            result = await get_telegram_info(username)
            if result.get("success") and "profile_photo_url" in result and result["profile_photo_url"]:
                result["profile_photo_url"] = get_profile_photo_url(
                    result.get("username"), size
                ) if result.get("username") else None
            
            status_code = 200 if result.get("success") else 404
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    "success": False,
                    "error": f"Internal server error: {str(e)}",
                    "api_owner": "@nkka404",
                    "api_updates": "t.me/premium_channel_404"
                })
            }
    
    elif path == '/health':
        # Health check endpoint
        try:
            await get_client()
            status = "healthy"
        except:
            status = "unhealthy"
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                "status": status,
                "timestamp": datetime.now().isoformat()
            })
        }
    
    else:
        # Root endpoint
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                "message": "Telegram Info API by @nkka404",
                "status": "active",
                "version": "2.0.0",
                "owner": "@nkka404",
                "updates": "t.me/premium_channel_404",
                "endpoints": {
                    "/api?username=...": "Get user/chat info",
                    "/health": "Check API health"
                }
            })
        }

# FastAPI routes (compatibility)
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Telegram Info API by @nkka404",
        "status": "active",
        "version": "2.0.0",
        "owner": "@nkka404",
        "updates": "t.me/premium_channel_404",
        "endpoints": {
            "/api?username=...": "Get user/chat info",
            "/health": "Check API health"
        }
    }

@app.get("/api")
async def info_endpoint(username: str = "", size: int = 320):
    """Main API endpoint"""
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
        if result.get("success") and "profile_photo_url" in result and result["profile_photo_url"]:
            result["profile_photo_url"] = get_profile_photo_url(
                result.get("username"), size
            ) if result.get("username") else None
        
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=404, detail=result)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Internal server error: {str(e)}",
                "api_owner": "@nkka404",
                "api_updates": "t.me/premium_channel_404"
            }
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await get_client()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
