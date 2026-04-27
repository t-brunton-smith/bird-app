import configparser
import os
from urllib.parse import urlencode

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


@app.route('/api/hotspots')
def hotspots_endpoint():
    location = request.args.get('location')
    dist = int(request.args.get('dist', 25))
    coords = location_to_coordinates(location)
    if not coords:
        return jsonify([])
    lat, lng = coords
    url = f'https://api.ebird.org/v2/ref/hotspot/geo?lat={lat}&lng={lng}&dist={dist}&fmt=json'
    resp = requests.get(url, headers={'X-eBirdApiToken': _EBIRD_TOKEN}, timeout=10)
    hotspots = [
        {'locId': h['locId'], 'locName': h['locName'], 'numSpecies': h.get('numSpeciesAllTime', 0)}
        for h in resp.json()
    ]
    hotspots.sort(key=lambda x: x['numSpecies'], reverse=True)
    return jsonify(hotspots)


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

    loc_id = request.args.get('loc_id') or None
    loc_name = request.args.get('loc_name') or None

    try:
        lat, lng = location_to_coordinates(location)
        return results_from_coordinates(lat, lng, notable=notable, species_code=species_code,
                                        dist=dist, back=back, location=location,
                                        species_name=species_name, loc_id=loc_id, loc_name=loc_name)
    except Exception:
        return render_template('loc_not_found.html', location=location)


def location_to_coordinates(location):
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{location}.json?access_token={_MAPBOX_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        if len(data['features']) > 0:
            coordinates = data['features'][0]['center']
            return tuple(coordinates[::-1])
    return None


def coordinates_to_location(latitude, longitude):
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{longitude},{latitude}.json?access_token={_MAPBOX_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        if len(data['features']) > 0:
            return data['features'][0]['place_name']
    return None


def results_from_coordinates(lat, lng, notable=False, species_code=None, dist=25, back=14,
                              location='', species_name=None, loc_id=None, loc_name=None):
    if loc_id:
        if notable:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/notable?back={back}&maxResults=10000'
        elif species_code:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/{species_code}?back={back}&maxResults=10000'
        else:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent?back={back}&maxResults=10000'
    elif notable:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}'
    elif species_code:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}"
    else:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}'

    headers = {'X-eBirdApiToken': _EBIRD_TOKEN}
    response = requests.get(url, headers=headers, timeout=10)

    sightings = []
    for sighting in response.json():
        sightings.append((
            sighting['comName'],
            sighting['obsDt'],
            sighting['locName'],
            sighting.get('subId', ''),
            sighting.get('howMany') or 1,
        ))

    totals = {}
    for s in sightings:
        totals[s[0]] = totals.get(s[0], 0) + s[4]
    species_summary = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    params = {'location': location, 'dist': dist, 'back': back}
    if species_name:
        params['species_name'] = species_name
    if notable:
        params['notable'] = 'on'
    if loc_id:
        params['loc_id'] = loc_id
    if loc_name:
        params['loc_name'] = loc_name
    map_url = '/map?' + urlencode(params)

    return render_template('results.html', sightings=sightings, location=location,
                           species_name=species_name, notable=notable, dist=dist, back=back,
                           map_url=map_url, species_summary=species_summary, loc_name=loc_name)


def create_map_with_pins(locations, center_location, map_title):
    map_obj = folium.Map(location=[center_location[0], center_location[1]], zoom_start=10, control_scale=True)

    tile_url = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    attribution = 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'

    folium.TileLayer(tiles=tile_url, attr=attribution, API_key=_STADIA_TOKEN).add_to(map_obj)

    folium.Marker(location=[center_location[0], center_location[1]],
                  icon=folium.Icon(icon='map-marker', color='red')).add_to(map_obj)
    for this_location in locations:
        (lat, lng, comName, obsDt, howMany, subId) = this_location
        checklist = (f'<a href="https://ebird.org/checklist/{subId}" target="_blank" '
                     f'style="color:#007bff;">View checklist ↗</a>') if subId else ''
        popup_html = (f'<div style="font-family:Arial,sans-serif;font-size:13px;min-width:160px;">'
                      f'<strong style="font-size:14px;display:block;margin-bottom:4px;">{comName}</strong>'
                      f'<span style="color:#666;">{obsDt}</span>'
                      f'{f"<br>Count: {howMany}" if howMany else ""}'
                      f'{"<br>" + checklist if checklist else ""}'
                      f'</div>')
        folium.Marker(location=[lat, lng], icon=folium.Icon(icon='map-marker'),
                      popup=folium.Popup(popup_html, max_width=220)).add_to(map_obj)

    title_html = f'<h3 align="center" style="font-size:24px"><b>{map_title}</b></h3>'
    map_obj.get_root().html.add_child(folium.Element(title_html))
    return map_obj


@app.route('/map')
def map_endpoint():
    location = request.args.get('location')
    coords = location_to_coordinates(location)
    if not coords:
        return render_template('loc_not_found.html', location=location)
    lat, lng = coords
    center_coordinates = (lat, lng)
    dist = int(request.args.get('dist', 25))
    back = int(request.args.get('back', 14))

    notable = request.args.get('notable') == 'on'
    species_name = request.args.get('species_name') or None
    species_code = species_name_to_code(species_name) if species_name else None
    loc_id = request.args.get('loc_id') or None
    loc_name = request.args.get('loc_name') or None

    sighting_coordinates = get_species_sightings_at_coordinates(center_coordinates, notable, species_code, dist, back, loc_id)

    if notable and species_code:
        map_title = f'Map of recent sightings of notable {species_name}s'
    elif notable:
        map_title = 'Map of recent sightings of notable species'
    elif species_code:
        map_title = f'Map of recent sightings of {species_name}s'
    else:
        map_title = 'Map of recent sightings of all species'

    params = {'location': location, 'dist': dist, 'back': back}
    if species_name:
        params['species_name'] = species_name
    if notable:
        params['notable'] = 'on'
    if loc_id:
        params['loc_id'] = loc_id
    if loc_name:
        params['loc_name'] = loc_name
    list_url = '/results?' + urlencode(params)

    totals = {}
    for s in sighting_coordinates:
        totals[s[2]] = totals.get(s[2], 0) + (s[4] or 1)
    species_summary = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    map_obj = create_map_with_pins(sighting_coordinates, center_coordinates, map_title)

    btn_style = ('display:inline-block; background:#007bff; color:white; padding:7px 12px; '
                 'border-radius:6px; text-decoration:none; font-family:Arial,sans-serif; '
                 'font-size:13px; font-weight:bold;')
    buttons_html = f'''
    <style>
        @media (max-width:640px) {{
            #map-nav {{ top:8px !important; left:8px !important; gap:6px !important; }}
            #map-nav a {{ padding:6px 10px !important; font-size:12px !important; }}
            #map-summary {{ width:calc(100vw - 16px) !important; left:8px !important; bottom:40px !important; max-height:200px !important; }}
        }}
    </style>
    <div id="map-nav" style="position:fixed; top:16px; left:16px; z-index:1000; display:flex; gap:8px;">
        <a href="/" style="{btn_style}">&#8592; Search</a>
        <a href="{list_url}" style="{btn_style}">List View</a>
    </div>'''
    map_obj.get_root().html.add_child(folium.Element(buttons_html))

    rows = ''.join(
        f'<div style="display:flex; justify-content:space-between; align-items:center; '
        f'padding:4px 0; border-bottom:1px solid #eee;">'
        f'<span style="font-size:13px; font-family:Arial,sans-serif;">{name}</span>'
        f'<span style="background:#007bff; color:white; border-radius:10px; padding:1px 8px; '
        f'font-size:12px; font-weight:bold; margin-left:8px; white-space:nowrap;">{count}</span>'
        f'</div>'
        for name, count in species_summary
    )
    summary_html = f'''
    <div id="map-summary" style="position:fixed; bottom:30px; left:16px; z-index:1000; background:white;
         border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.25); width:260px; max-height:280px;
         display:flex; flex-direction:column; overflow:hidden;">
        <div style="padding:8px 12px; background:#3b5998; color:white;
             font-family:Arial,sans-serif; font-size:13px; font-weight:bold; flex-shrink:0;">
            {len(species_summary)} species &mdash; {len(sighting_coordinates)} sightings
        </div>
        <div style="overflow-y:auto; padding:4px 12px;">{rows}</div>
    </div>'''
    map_obj.get_root().html.add_child(folium.Element(summary_html))

    return render_template_string(map_obj.get_root().render())


def species_name_to_code(species_name):
    return _SPECIES_CODES.get(species_name.lower()) if species_name else None


def get_species_sightings_at_coordinates(coordinates, notable=False, species_code=None, dist=25, back=14, loc_id=None):
    center_lat, center_lng = coordinates
    headers = {'X-eBirdApiToken': _EBIRD_TOKEN}

    if loc_id:
        if species_code:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/{species_code}?back={back}&maxResults=10000'
        elif notable:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/notable?back={back}&maxResults=10000'
        else:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent?back={back}&maxResults=10000'
    elif species_code:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=10000&back={back}"
    elif notable:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=10000&back={back}'
    else:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=10000&back={back}"

    response = requests.get(url, headers=headers, timeout=10)

    sighting_locations = []
    for this in response.json():
        lat = this.get('lat')
        lng = this.get('lng')
        comName = this.get('comName')
        if not all((lat, lng, comName)):
            continue
        sighting_locations.append((lat, lng, comName, this.get('obsDt'), this.get('howMany'), this.get('subId', '')))

    return sighting_locations


if __name__ == '__main__':
    if os.path.exists('/app/ssl'):
        app.run(debug=True, host='0.0.0.0', ssl_context=('/app/ssl/cert2.pem', '/app/ssl/privkey2.pem'))
    else:
        app.run(debug=True, host='0.0.0.0')
