# CBU Smart Road Network - Setup & Quick Start Guide

## Quick Start (5 minutes)

### 1. Navigate to Project
```bash
cd /Users/lbs/Project-3011/backend
```

### 2. Activate Virtual Environment
```bash
source venv/bin/activate
```

### 3. Start Django Server
```bash
python manage.py runserver 0.0.0.0:8000
```

### 4. Access Application
- **Landing Page:** http://localhost:8000/
- **Dashboard:** http://localhost:8000/overview/
- **Admin Panel:** http://localhost:8000/admin/

---

## Project Structure

```
Project-3011/
├── backend/                          # Django project root
│   ├── manage.py                    # Django CLI (FIXED: uses backend.settings)
│   ├── db.sqlite3                   # Database
│   ├── backend/                     # Django configuration
│   │   ├── settings.py              # Project settings
│   │   ├── urls.py                  # Main URL routing
│   │   ├── asgi.py                  # WebSocket & ASGI config
│   │   └── wsgi.py                  # WSGI entry point
│   ├── api/                         # REST API
│   │   ├── models.py                # Data models
│   │   ├── views.py                 # API endpoints
│   │   ├── serializers.py           # DRF serializers
│   │   ├── services.py              # Business logic
│   │   ├── urls.py                  # API routes
│   │   └── migrations/              # Database migrations
│   └── dashboard/                   # Web dashboard
│       ├── views.py                 # Dashboard views
│       ├── urls.py                  # Dashboard routes
│       ├── templates/               # HTML templates (FIXED: added index.html)
│       └── static/                  # Static files (images, fonts)
├── API_REQUESTS_DEMO.txt            # API usage examples
└── PROJECT_COMPLETION_REPORT.md     # Detailed completion report
```

---

## Key Features

### ✅ Backend
- **20+ REST API Endpoints** - Full CRUD for roads, devices, hazards, telemetry
- **Real-time Violation Detection** - Automatic speeding detection with severity
- **WebSocket Support** - Live telemetry broadcasting
- **Map Versioning** - Version control for road data packages
- **Device Management** - Fleet tracking with last seen timestamps

### ✅ Frontend  
- **10 Dashboard Pages** - Landing, overview, roads, hazards, devices, violations, versions, analytics, map editor
- **Interactive Maps** - Leaflet.js integration for road visualization
- **Real-time Charts** - Chart.js for telemetry visualization
- **Responsive Design** - Mobile, tablet, and desktop support
- **Dark Theme** - Tailwind CSS with professional styling

---

## Database

### Models (7 total)
1. **Road** - Road segments with speed limits
2. **RoadNode** - Road path coordinates
3. **Hazard** - Road hazards (schools, curves, etc.)
4. **Device** - Fleet vehicles
5. **Telemetry** - Speed and location data
6. **Violation** - Speeding violations
7. **MapVersion** - Road data version control

### Initialize Database
```bash
python manage.py migrate
```

### Create Superuser (for admin panel)
```bash
python manage.py createsuperuser
```

---

## API Endpoints

### Devices
```bash
# Register device
POST /api/devices/register/
Body: {"device_id":"ESP32-001","device_name":"Test Device"}

# List devices
GET /api/devices/

# Get device details
GET /api/devices/ESP32-001/

# Get latest telemetry
GET /api/devices/ESP32-001/latest/

# Get telemetry history
GET /api/devices/ESP32-001/history/
```

### Roads
```bash
# List roads
GET /api/roads/

# Create road with nodes
POST /api/roads/
Body: {
  "name": "Main Street",
  "speed_limit": 50,
  "nodes": [
    {"latitude": -12.81, "longitude": 28.22},
    {"latitude": -12.82, "longitude": 28.23}
  ]
}

# Get road details
GET /api/roads/1/
```

### Telemetry & Violations
```bash
# Upload telemetry
POST /api/telemetry/upload/
Body: {
  "device_id": "ESP32-001",
  "road": 1,
  "speed": 75,
  "latitude": -12.81,
  "longitude": 28.22
}

# List violations
GET /api/violations/
```

### Map Versions
```bash
# List versions
GET /api/map-versions/

# Publish new version
POST /api/map-versions/publish/
Body: {"description": "Updated hazard data"}

# Check for updates
POST /api/maps/check-update/
Body: {"device_id": "ESP32-001", "current_version": "0.0.0"}

# Download map package
GET /api/maps/download/1.0.0.0.1/
```

---

## Common Commands

### Run Server
```bash
python manage.py runserver 0.0.0.0:8000
```

### Run Tests
```bash
python manage.py test
```

### Make Database Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Django Shell (for debugging)
```bash
python manage.py shell
```

### Collect Static Files (production)
```bash
python manage.py collectstatic --noinput
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'backend'"
**Fix:** Ensure you're in `/Users/lbs/Project-3011/backend` directory

### Issue: Database errors
**Fix:** Run `python manage.py migrate`

### Issue: Static files not loading
**Fix:** Ensure `DEBUG = True` in settings.py (development only)

### Issue: Port 8000 already in use
**Fix:** Use different port: `python manage.py runserver 0.0.0.0:8001`

---

## Files Modified/Created During Setup

✅ `/Users/lbs/Project-3011/manage.py` - Fixed DJANGO_SETTINGS_MODULE path  
✅ `/Users/lbs/Project-3011/backend/dashboard/templates/dashboard/index.html` - Created overview page  
✅ `/Users/lbs/Project-3011/backend/dashboard/templates/dashboard/device_detail.html` - Fixed template syntax  
✅ `/Users/lbs/Project-3011/backend/dashboard/templates/dashboard/index.html` - Fixed template syntax  

---

## Project Status

| Component | Status | Last Tested |
|-----------|--------|-------------|
| Backend API | ✅ Complete | 2026-09-01 |
| Frontend Dashboard | ✅ Complete | 2026-09-01 |
| Database | ✅ Complete | 2026-09-01 |
| WebSocket | ✅ Complete | 2026-09-01 |
| Migrations | ✅ Applied | 2026-09-01 |
| Static Files | ✅ Configured | 2026-09-01 |

---

## Technology Stack

- **Backend:** Django 6.1, Django REST Framework 3.18.0
- **Frontend:** HTML5, Tailwind CSS, JavaScript
- **Database:** SQLite3
- **Maps:** Leaflet.js 1.9.4
- **Charts:** Chart.js
- **WebSocket:** ASGIRef 3.12.1
- **Python:** 3.14

---

## For More Information

See `PROJECT_COMPLETION_REPORT.md` for detailed testing results and architecture documentation.

---

**Last Updated:** September 1, 2026  
**Status:** ✅ Production Ready
