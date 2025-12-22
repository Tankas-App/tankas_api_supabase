# 🌍 Tankas App - Environmental Cleanup Coordination Platform

> Making environmental cleanup organized, rewarding, and fun through community-driven action and gamification.

**Status:** Active Development 🚀  
**Version:** 0.2.0 (Leaderboard System Added)  
**Last Updated:** December 2024

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Database Schema](#database-schema)
- [API Endpoints](#api-endpoints)
- [System Architecture](#system-architecture)
- [Development Guide](#development-guide)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Project Overview

**Tankas** solves a critical problem in Ghana and across Africa: environmental pollution lacks organization, incentives, and recognition.

### The Problem
- Environmental issues pile up with no coordination system
- Volunteers have no incentive or recognition for cleanup work
- Communities can't measure environmental progress
- No way to connect collectors with garbage disposal destinations

### Our Solution
A mobile-first platform that:
1. **Reports** environmental issues with AI verification
2. **Organizes** cleanup teams with group leadership
3. **Gamifies** participation with points, badges, and leaderboards
4. **Connects** collectors to verified disposal destinations
5. **Rewards** users with cash, vouchers, and community recognition

### Impact
- ✅ Organized cleanup efforts across communities
- ✅ Incentivized environmental action
- ✅ Measurable community impact
- ✅ Economic opportunity for garbage collectors
- ✅ Sustainable behavioral change

---

## 🛠️ Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.9+)
- **Database:** PostgreSQL via Supabase
- **Authentication:** JWT (Python-jose)
- **Image Processing:** Google Vision API + Cloudinary
- **Hashing:** bcrypt
- **Geocoding:** Haversine formula for distance calculations

### Infrastructure
- **Hosting:** Supabase (Database + Storage)
- **Image CDN:** Cloudinary
- **Deployment:** FastAPI with Uvicorn

### Key Dependencies
```
fastapi==0.104.1
uvicorn==0.24.0
supabase==2.0.3
pydantic==2.5.0
bcrypt==4.1.1
python-jose==3.3.0
google-cloud-vision==3.4.4
cloudinary==1.36.0
pillow==10.1.0
piexif==1.1.3
```

---

## ✨ Features

### Core Features (Phase 1) ✅

#### 1. User Authentication
- User signup with email validation
- Secure login with JWT tokens
- Password hashing with bcrypt
- User profiles with avatar support

#### 2. Issue Reporting
- Users report environmental issues with photos
- AI-powered image analysis (Google Vision)
- Automatic difficulty classification (easy/medium/hard)
- Points assigned based on difficulty and priority
- GPS location capture (EXIF + manual)
- Immediate 15-point reward for reporting

#### 3. Volunteer Coordination
- Users can join issues to form cleanup groups
- Automatic leader assignment (first joiner)
- Leadership transfer capability
- Group member management
- Solo work option for individuals

#### 4. Work Verification
- Group leaders mark issues as complete with before/after photos
- AI verification comparing original and cleanup photos
- Manual verification by administrators
- Points distribution among verified volunteers
- Leader bonus for group management

#### 5. Garbage Collection & Payments
- Collectors gather garbage from resolved issues
- Submit collection with photos and estimated weight
- Destinations verify deliveries with proof photos
- Automatic payment calculation (GHS per kg)
- Points awarded for verified collections
- Real-time payment tracking

#### 6. Gamification System ✨ NEW
- **Points System:**
  - Issue reporting: 15 points
  - Cleanup completion: 20-60 points (based on difficulty)
  - Collection verification: 5 points per kg

- **Badge System:**
  - Tier badges: Bronze (100 pts), Silver (500 pts), Gold (2000 pts)
  - Achievement badges: Champion, Cleanup Hero, Team Player, etc.
  - Weekly rotating badges: Rising Star, Momentum, On Fire

- **Leaderboards:** ✨ NEW
  - 5 different ranking types (points, issues, collections, kg, hours)
  - 3 location filters (global, region, community)
  - Real-time GPS integration
  - Smart caching (5-min TTL)
  - Weekly badge resets

---

## 📁 Project Structure

```
tankas_api_supabase/
├── app/
│   ├── __init__.py
│   ├── config.py                 # Environment variables & config
│   ├── database.py               # Supabase client initialization
│   │
│   ├── models/                   # Data models (placeholder)
│   │   └── __init__.py
│   │
│   ├── schemas/                  # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── user_schema.py        # Auth schemas
│   │   ├── completion_schema.py  # Issue completion schemas
│   │   ├── collection_schema.py  # Collection schemas
│   │   └── volunteer_schema.py   # Volunteer schemas
│   │
│   ├── services/                 # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py       # User authentication
│   │   ├── issue_service.py      # Issue management + AI verification
│   │   ├── volunteer_service.py  # Volunteer groups
│   │   ├── completion_service.py # Issue completion & verification
│   │   ├── collection_service.py # Garbage collection & payments
│   │   ├── points_service.py     # Points, activities, badges ✨ NEW
│   │   └── leaderboard_service.py # Rankings & leaderboards ✨ NEW
│   │
│   ├── routes/                   # API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py               # /api/auth/*
│   │   ├── issues.py             # /api/issues/*
│   │   ├── volunteers.py         # /api/volunteers/*
│   │   ├── completion.py         # /api/completion/*
│   │   ├── collection.py         # /api/collections/*
│   │   ├── leaderboards.py       # /api/leaderboards/* ✨ NEW
│   │   └── test.py               # Test endpoints
│   │
│   └── utils/                    # Utility functions
│       ├── __init__.py
│       ├── ai_service.py         # Google Vision integration
│       ├── cloudinary_helper.py  # Image uploads
│       ├── distance_calculator.py # Haversine formula
│       ├── exif_helper.py        # GPS extraction
│       ├── hashing.py            # Password hashing
│       ├── jwt_handler.py        # JWT token management
│       ├── points_calculator.py  # Points calculation logic
│       └── validators.py         # Input validation
│
├── main.py                       # FastAPI app initialization
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
├── .gitignore                    # Git ignore rules
└── README.md                     # This file
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- PostgreSQL database (via Supabase)
- Google Cloud Vision API credentials
- Cloudinary account for image storage

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/Tankas-App/tankas_api_supabase.git
cd tankas_api_supabase
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Setup environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials:
# - SUPABASE_URL
# - SUPABASE_KEY
# - JWT_SECRET
# - GOOGLE_VISION_CREDENTIALS_PATH
# - CLOUDINARY credentials
```

5. **Run database migrations**
```bash
# Run the migration SQL in Supabase console
# See database/migrations/ directory
```

6. **Start the server**
```bash
python main.py
# Server runs on http://localhost:8000
```

7. **Access API documentation**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🗄️ Database Schema

### Core Tables

#### `users`
Stores user accounts and statistics
- `id` (UUID) - Primary key
- `email` (VARCHAR) - User email
- `username` (VARCHAR) - Unique username
- `password_hash` (VARCHAR) - Hashed password
- `display_name` (VARCHAR) - Display name
- `avatar_url` (TEXT) - Profile picture
- `total_points` (INT) - Accumulated points
- `badge_tier` (VARCHAR) - bronze/silver/gold
- `issues_reported` (INT) - Count of issues
- `tasks_completed` (INT) - Count of tasks
- `admin_region` (VARCHAR) - User's region ✨
- `total_kg_collected` (DECIMAL) - Total garbage ✨
- `volunteer_streak` (INT) - Consecutive days ✨

#### `issues`
Environmental issues reported by users
- `id` (UUID) - Primary key
- `user_id` (UUID) - Reporter
- `title` (VARCHAR) - Issue title
- `picture_url` (TEXT) - Photo of issue
- `latitude` (FLOAT) - GPS latitude
- `longitude` (FLOAT) - GPS longitude
- `difficulty` (VARCHAR) - easy/medium/hard
- `priority` (VARCHAR) - low/medium/high
- `points_assigned` (INT) - Points for cleanup
- `status` (VARCHAR) - open/resolved
- `ai_labels` (TEXT[]) - AI-detected labels
- `ai_confidence_score` (FLOAT) - AI confidence

#### `volunteers`
Users volunteering for cleanup
- `id` (UUID) - Primary key
- `user_id` (UUID) - Volunteer
- `issue_id` (UUID) - Issue they're working on
- `group_id` (UUID) - Group they joined
- `is_leader` (BOOLEAN) - Group leader?
- `verified` (BOOLEAN) - Verified by leader?
- `points_earned` (INT) - Points awarded
- `verified_at` (TIMESTAMP) - When verified

#### `groups`
Cleanup team organizing
- `id` (UUID) - Primary key
- `issue_id` (UUID) - Issue being cleaned
- `leader_id` (UUID) - Group leader
- `name` (VARCHAR) - Group name
- `status` (VARCHAR) - active/completed

#### `collections`
Garbage collection tracking
- `id` (UUID) - Primary key
- `issue_id` (UUID) - Issue source
- `collected_by_user_id` (UUID) - Collector
- `quantity` (FLOAT) - Weight in kg
- `photo_url` (TEXT) - Photo of garbage
- `verified` (BOOLEAN) - Verified at destination?
- `verified_at` (TIMESTAMP) - When verified

### Gamification Tables ✨

#### `badge_definitions`
Master list of all possible badges
- `id` (UUID) - Primary key
- `badge_type` (VARCHAR) - Unique badge ID
- `display_name` (VARCHAR) - Display name
- `emoji` (VARCHAR) - Badge emoji
- `category` (VARCHAR) - tier/achievement/weekly
- `is_permanent` (BOOLEAN) - Earned once or weekly?
- `unlock_condition` (JSONB) - Condition to earn

#### `user_badges`
Tracks badges earned by users
- `id` (UUID) - Primary key
- `user_id` (UUID) - User who earned it
- `badge_type` (VARCHAR) - Badge type
- `earned_at` (TIMESTAMP) - When earned
- `current_week_earned` (BOOLEAN) - Current week?
- `metadata` (JSONB) - Extra info

#### `user_activity_log`
Logs every action for analytics
- `id` (UUID) - Primary key
- `user_id` (UUID) - User performing action
- `activity_type` (VARCHAR) - issue_reported/cleanup_verified/etc
- `activity_date` (DATE) - Date of action
- `points_earned` (INT) - Points from this action
- `reference_id` (UUID) - Related record

#### `leaderboard_cache`
Caches rankings for performance
- `id` (VARCHAR) - Cache key
- `leaderboard_type` (VARCHAR) - points/issues/etc
- `location_type` (VARCHAR) - global/region/community
- `location_value` (VARCHAR) - Region or coordinates
- `rankings` (JSONB) - Cached ranking data
- `cached_at` (TIMESTAMP) - When cached
- `expires_at` (TIMESTAMP) - When expires

---

## 📡 API Endpoints

### Authentication
```
POST   /api/auth/signup          Create new user account
POST   /api/auth/login           Login user
```

### Issues
```
POST   /api/issues               Report new environmental issue
GET    /api/issues/{id}          Get issue details
GET    /api/issues/nearby        Get nearby issues
POST   /api/issues/{id}/resolve  Mark issue as resolved
```

### Volunteers
```
POST   /api/volunteers           Join an issue as volunteer
GET    /api/volunteers/groups/{id}        Get group members
GET    /api/volunteers/profile/{id}       Get volunteer profile
POST   /api/volunteers/my-profile         Get my profile
POST   /api/volunteers/{id}/transfer-leadership  Transfer leadership
```

### Completion
```
POST   /api/completion/confirm-participation    Confirm you participated
POST   /api/completion/complete-issue           Mark issue complete (leader only)
POST   /api/completion/verify-volunteers        Verify volunteers & distribute points (leader only)
```

### Collections
```
POST   /api/destinations                        Create collection destination (admin)
GET    /api/destinations/nearby                Get nearby destinations
POST   /api/issues/{id}/assign-destination     Assign destination to issue
POST   /api/start/{id}                         Start collection
POST   /api/submit/{id}                        Submit collected garbage
POST   /api/verify/{id}                        Verify delivery & award payment
GET    /api/collectors/{id}/statistics         Get collector stats
```

### Leaderboards ✨ NEW
```
GET    /api/leaderboards                       List all leaderboard types
GET    /api/leaderboards/{type}                Get leaderboard rankings
GET    /api/leaderboards/{type}/context        Get ranking context for user
GET    /api/users/{id}/rank                    Get user's rank
POST   /api/admin/weekly-badges-reset          Manually reset weekly badges
POST   /api/admin/schedule-weekly-badges       Setup automatic reset
```

---

## 🏗️ System Architecture

### Points Flow
```
User Action (report issue / cleanup / collect)
    ↓
Points Awarded via PointsService
    ↓
Activity Logged for Analytics
    ↓
Badge Conditions Checked
    ↓
Badges Auto-Awarded if Unlocked
    ↓
Leaderboard Cache Invalidated
    ↓
Fresh Rankings on Next Leaderboard Request
```

### Location Filtering
```
Leaderboard Request with GPS Location
    ↓
Determine Location Type (global/region/community)
    ↓
Filter Users by Location
    ↓
Rank by Selected Metric
    ↓
Cache Results (5 min TTL)
    ↓
Return Rankings + User's Context
```

### Badge System
```
Permanent Badges (Earned once)
├── Tier Badges (Bronze/Silver/Gold based on points)
└── Achievement Badges (Cleanup Hero, Team Player, etc)

Weekly Rotating Badges (Reset every Monday)
├── Rising Star (Top 10 by points + activities)
├── Momentum (100+ points this week)
└── On Fire (3+ cleanups this week)

Auto-Check Happens When:
- Points awarded
- Activities logged
- Weekly reset triggered
```

---

## 👨‍💻 Development Guide

### Adding a New Leaderboard Type

1. **Add to `LeaderboardService.get_available_leaderboards()`:**
```python
"my_metric": {
    "name": "My Metric Leaderboard",
    "description": "Ranked by my_metric",
    "metric": "my_metric",
    "order": "DESC"
}
```

2. **Add metric calculation in `_get_metric_value()`:**
```python
elif metric == "my_metric":
    response = self.supabase.table("users").select("my_metric").eq("id", user_id).execute()
    return response.data[0].get("my_metric", 0) or 0
```

3. **Add API endpoint (optional custom logic)**

### Adding a New Badge Type

1. **Insert into `badge_definitions` table:**
```sql
INSERT INTO badge_definitions (badge_type, display_name, emoji, category, is_permanent, unlock_condition)
VALUES ('my_badge', 'My Badge', '🎯', 'achievement', true, '{"type": "custom", "value": 100}');
```

2. **Add condition check in `_check_badge_condition()`:**
```python
elif condition_type == "custom":
    # Your custom logic here
    return some_condition_met
```

### Extending the Points System

To award points for a new action:
```python
from app.services.points_service import PointsService

points_service = PointsService()

await points_service.award_points(
    user_id=user_id,
    points=25,
    activity_type="my_new_action",
    reference_id=related_id,
    reference_type="my_table",
    metadata={"key": "value"}
)
```

---

## 🌐 Deployment

### Environment Variables Required
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
JWT_SECRET=your_jwt_secret_key
GOOGLE_VISION_CREDENTIALS_PATH=/path/to/credentials.json
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

### Deployment Options

#### Option 1: Railway (Recommended)
```bash
railway init
railway up
```

#### Option 2: Docker
```bash
docker build -t tankas-api .
docker run -p 8000:8000 --env-file .env tankas-api
```

#### Option 3: Heroku
```bash
heroku create tankas-api
git push heroku main
```

### Weekly Badge Automation

**Option A: External Cron (Simplest)**
```bash
# In your server's crontab
0 0 * * 1 curl -X POST https://your-api.com/api/admin/weekly-badges-reset \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Option B: APScheduler**
```python
from apscheduler.schedulers.background import BackgroundScheduler
from app.services.leaderboard_service import LeaderboardService

scheduler = BackgroundScheduler()
scheduler.add_job(
    LeaderboardService().reset_weekly_badges,
    'cron',
    day_of_week='mon',
    hour=0,
    minute=0
)
scheduler.start()
```

**Option C: Celery + Redis**
For large-scale deployments

---

## 🤝 Contributing

We welcome contributions! Here's how:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Write tests if applicable
5. Commit (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Style
- Follow PEP 8
- Use type hints
- Document complex functions
- Write docstrings

---

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

---

## 🙋 Support & Community

- **Issues:** GitHub Issues for bug reports
- **Discussions:** GitHub Discussions for questions
- **Email:** support@tankas.app
- **Twitter:** @TankasApp

---

## 🎉 Acknowledgments

Special thanks to:
- Anthropic Claude for development assistance
- Google Cloud Vision for AI capabilities
- Supabase for database infrastructure
- Cloudinary for image hosting
- The Ghana environmental community for inspiration

---

**Made with ❤️ in Accra, Ghana**

For updates and news: [tankas.app](https://tankas.app)