import configparser
import os

import folium as folium
import requests
from flask import Flask, render_template, render_template_string, request, jsonify, redirect, make_response
import pandas as pd

app = Flask(__name__)

# Load taxonomy once at startup
_df_tax = pd.read_csv("data/ebird_taxonomy.csv")
_SPECIES_CODES = pd.Series(
    _df_tax.SPECIES_CODE.values,
    index=_df_tax.COMMON_NAME.str.lower()
).to_dict()
_SPECIES_NAMES = sorted(_df_tax['COMMON_NAME'].dropna().tolist())


def _load_api_key(env_var, ini_section):
    val = os.environ.get(env_var)
    if val:
        return val
    config = configparser.ConfigParser()
    config.read('configs/keys.ini')
    try:
        return config[ini_section]['apitoken']
    except KeyError:
        raise RuntimeError(f"Missing API key: set the {env_var} environment variable")


_EBIRD_TOKEN = _load_api_key('EBIRD_TOKEN', 'ebird')
_MAPBOX_TOKEN = _load_api_key('MAPBOX_TOKEN', 'mapbox')
_STADIA_TOKEN = _load_api_key('STADIA_TOKEN', 'stadia')


@app.before_request
def https_redirect():
    if request.host.split(':')[0] in ('localhost', '127.0.0.1'):
        return
    if not request.is_secure:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


@app.route('/')
def index():
    return render_template('index.html')


@app.route("/location")
def location():
    lat = request.args.get('lat')
    long = request.args.get('long')
    location_name = coordinates_to_location(lat, long)
    return location_name if location_name else "", 200


@app.route('/api/species')
def species_list():
    resp = make_response(jsonify(_SPECIES_NAMES))
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route('/results')
def results():
    location = request.args.get('location')
    notable = request.args.get('notable') == 'on'
    dist = int(request.args.get('dist', 25))
    back = int(request.args.get('back', 14))

    try:
        species_name = request.args.get('species_name') or None
        species_code = species_name_to_code(species_name) if species_name else None
    except Exception:
        species_name = None
        species_code = None

    try:
        lat, lng = location_to_coordinates(location)
        return results_from_coordinates(lat, lng, notable=notable, species_code=species_code,
                                        dist=dist, back=back, location=location,
                                        species_name=species_name)
    except Exception:
        return render_template('loc_not_found.html', location=location)


def location_to_coordinates(location):
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{location}.json?access_token={_MAPBOX_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if len(data['features']) > 0:
            coordinates = data['features'][0]['center']
            return tuple(coordinates[::-1])
    return None


def coordinates_to_location(latitude, longitude):
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{longitude},{latitude}.json?access_token={_MAPBOX_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if len(data['features']) > 0:
            return data['features'][0]['place_name']
    return None


def results_from_coordinates(lat, lng, notable=False, species_code=None, dist=25, back=14,
                              location='', species_name=None):
    if notable:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={lat}&lng={lng}&dist={dist}&maxResults=100&back={back}'
    elif species_code:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={lat}&lng={lng}&dist={dist}&maxResults=100&back={back}"
    else:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent?lat={lat}&lng={lng}&dist={dist}&maxResults=100&back={back}'

    headers = {'X-eBirdApiToken': _EBIRD_TOKEN}
    response = requests.get(url, headers=headers)

    sightings = []
    for sighting in response.json():
        sightings.append((
            sighting['comName'],
            sighting['obsDt'],
            sighting['locName'],
            sighting.get('subId', ''),
        ))

    return render_template('results.html', sightings=sightings, location=location,
                           species_name=species_name, notable=notable, dist=dist, back=back)


def create_map_with_pins(locations, center_location, map_title):
    map_obj = folium.Map(location=[center_location[0], center_location[1]], zoom_start=10, control_scale=True)

    tile_url = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    attribution = 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'

    folium.TileLayer(tiles=tile_url, attr=attribution, API_key=_STADIA_TOKEN).add_to(map_obj)

    folium.Marker(location=[center_location[0], center_location[1]],
                  icon=folium.Icon(icon='map-marker', color='red')).add_to(map_obj)
    for this_location in locations:
        (lat, lng, comName, obsDt, howMany) = this_location
        folium.Marker(location=[lat, lng], icon=folium.Icon(icon='map-marker'),
                      popup=f"{comName}\n{obsDt}\nNum: {howMany}").add_to(map_obj)

    title_html = f'<h3 align="center" style="font-size:24px"><b>{map_title}</b></h3>'
    map_obj.get_root().html.add_child(folium.Element(title_html))
    return map_obj


@app.route('/map')
def map_endpoint():
    location = request.args.get('location')
    lat, lng = location_to_coordinates(location)
    center_coordinates = (lat, lng)
    dist = int(request.args.get('dist', 25))
    back = int(request.args.get('back', 14))

    notable = request.args.get('notable') == 'on'
    species_name = request.args.get('species_name') or None
    species_code = species_name_to_code(species_name) if species_name else None

    sighting_coordinates = get_species_sightings_at_coordinates(center_coordinates, notable, species_code, dist, back)

    if notable and species_code:
        map_title = f'Map of recent sightings of notable {species_name}s'
    elif notable:
        map_title = 'Map of recent sightings of notable species'
    elif species_code:
        map_title = f'Map of recent sightings of {species_name}s'
    else:
        map_title = 'Map of recent sightings of all species'

    map_obj = create_map_with_pins(sighting_coordinates, center_coordinates, map_title)
    return render_template_string(map_obj.get_root().render())


def species_name_to_code(species_name):
    return _SPECIES_CODES.get(species_name.lower()) if species_name else None


def get_species_sightings_at_coordinates(coordinates, notable=False, species_code=None, dist=25, back=14):
    center_lat, center_lng = coordinates
    headers = {'X-eBirdApiToken': _EBIRD_TOKEN}

    if species_code:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=100&back={back}"
    elif notable:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=100&back={back}'
    else:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=100&back={back}"

    response = requests.get(url, headers=headers)

    sighting_locations = []
    for this in response.json():
        lat = this.get('lat')
        lng = this.get('lng')
        comName = this.get('comName')
        if not all((lat, lng, comName)):
            continue
        sighting_locations.append((lat, lng, comName, this.get('obsDt'), this.get('howMany')))

    return sighting_locations


if __name__ == '__main__':
    if os.path.exists('/app/ssl'):
        app.run(debug=True, host='0.0.0.0', ssl_context=('/app/ssl/cert2.pem', '/app/ssl/privkey2.pem'))
    else:
        app.run(debug=True, host='0.0.0.0')
