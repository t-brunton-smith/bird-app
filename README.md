# Phlock — eBird Sightings App

A Flask web app for browsing recent bird sightings near any location, powered by the [eBird API](https://documenter.getpostman.com/view/664302/S1ENwy59). Search by location, filter by species or notable birds, and view results as a list or an interactive map.

## Features

- Search recent sightings by location (place name or address)
- Filter by species name with autocomplete (sourced from eBird taxonomy)
- Filter for notable/rare sightings only
- View results as a list or on an interactive map with pins
- HTTPS enforced in production; HTTP works on localhost

## Prerequisites

You need API keys for three services:

| Service | Purpose | Get a key |
|---------|---------|-----------|
| [eBird](https://ebird.org/api/keygen) | Bird sighting data | ebird.org/api/keygen |
| [Mapbox](https://account.mapbox.com/) | Location geocoding | account.mapbox.com |
| [Stadia Maps](https://stadiamaps.com/) | Map tile layer | stadiamaps.com |

## Configuration

Create `configs/keys.ini` with your API keys:

```ini
[ebird]
apitoken = YOUR_EBIRD_TOKEN

[mapbox]
apitoken = YOUR_MAPBOX_TOKEN

[stadia]
apitoken = YOUR_STADIA_TOKEN
```

## Running Locally

**Without Docker:**

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

**With Docker:**

```bash
docker build -t tbruntonsmith/bird-app-test .
docker run -p 80:5000 tbruntonsmith/bird-app-test
```

Open `http://localhost` in your browser.

## Deploying to Production

Build and push to Docker Hub:

```bash
docker build -t tbruntonsmith/bird-app .
docker push tbruntonsmith/bird-app
```

Run on the server with SSL certificates (e.g. from Let's Encrypt):

```bash
docker run --restart unless-stopped -p 443:5000 \
  -v /etc/letsencrypt/live/phlock.org/privkey.pem:/app/ssl/privkey2.pem \
  -v /etc/letsencrypt/live/phlock.org/cert.pem:/app/ssl/cert2.pem \
  -d tbruntonsmith/bird-app
```

The app detects SSL certificates at `/app/ssl` at startup and serves HTTPS automatically. HTTP requests are redirected to HTTPS (except on localhost).

## Project Structure

```
├── app.py               # Flask application
├── templates/
│   ├── index.html       # Main search form
│   ├── results.html     # Sightings list
│   └── loc_not_found.html
├── static/              # CSS, JS, fonts, icons
├── data/
│   └── ebird_taxonomy.csv  # Species list for autocomplete
├── configs/
│   └── keys.ini         # API keys (not committed)
└── Dockerfile
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main search page |
| `GET /results?location=&species_name=&notable=` | Sightings list |
| `GET /map?center_location=&species_name=&notable=` | Interactive map |
| `GET /api/species` | JSON list of all species names (for autocomplete) |
| `GET /location?lat=&long=` | Reverse geocode coordinates to a place name |
