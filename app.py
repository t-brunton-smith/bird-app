import configparser
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlencode

import folium as folium
from folium.plugins import MarkerCluster
import requests
from flask import Flask, render_template, render_template_string, request, jsonify, redirect, make_response
import pandas as pd

app = Flask(__name__)

_obs_cache: dict = {}
_OBS_CACHE_TTL = 300  # seconds


def format_obs_date(obs_dt):
    if not obs_dt:
        return ''
    try:
        dt = datetime.strptime(obs_dt[:10], '%Y-%m-%d')
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except ValueError:
        return obs_dt

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


@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')


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
    dist = int(request.args.get('dist', 10))
    back = int(request.args.get('back', 7))

    raw_species = request.args.get('species_name') or ''
    species_names = [s.strip() for s in raw_species.split(',') if s.strip()]
    species_codes_list = [c for c in (species_name_to_code(n) for n in species_names) if c]
    species_name = raw_species or None
    species_code = species_codes_list[0] if len(species_codes_list) == 1 else None

    loc_id = request.args.get('loc_id') or None
    loc_name = request.args.get('loc_name') or None

    try:
        lat, lng = location_to_coordinates(location)
        return results_from_coordinates(lat, lng, notable=notable, species_code=species_code,
                                        dist=dist, back=back, location=location,
                                        species_name=species_name, loc_id=loc_id, loc_name=loc_name,
                                        species_codes_list=species_codes_list if len(species_codes_list) > 1 else None)
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


def _top_species_codes(index_obs, limit=50):
    """Return up to `limit` species codes from an index response, ordered most-recent first."""
    seen, ordered = set(), []
    for obs in sorted(index_obs, key=lambda o: o.get('obsDt', ''), reverse=True):
        code = obs.get('speciesCode')
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered[:limit]


def _fetch_all_obs_for_species(species_code, lat, lng, dist, back, headers, loc_id=None):
    """Fetch all recent checklist-level observations for one species. Returns [] on any error."""
    key = (species_code, loc_id, back) if loc_id else (species_code, round(lat, 4), round(lng, 4), dist, back)
    entry = _obs_cache.get(key)
    if entry and time.time() - entry[1] < _OBS_CACHE_TTL:
        return entry[0]
    try:
        if loc_id:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/{species_code}?back={back}&maxResults=10000'
        else:
            url = (f'https://api.ebird.org/v2/data/obs/geo/recent/{species_code}'
                   f'?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}')
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 429:
            time.sleep(1)
            resp = requests.get(url, headers=headers, timeout=10)
        result = resp.json()
        result = result if isinstance(result, list) else []
        _obs_cache[key] = (result, time.time())
        return result
    except Exception:
        return []


def results_from_coordinates(lat, lng, notable=False, species_code=None, dist=10, back=7,
                              location='', species_name=None, loc_id=None, loc_name=None,
                              species_codes_list=None):
    headers = {'X-eBirdApiToken': _EBIRD_TOKEN}

    if loc_id:
        if notable:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/notable?back={back}&maxResults=10000'
            all_obs = requests.get(url, headers=headers, timeout=10).json()
        elif species_codes_list:
            all_obs = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {
                    executor.submit(_fetch_all_obs_for_species, code, lat, lng, dist, back, headers, loc_id): code
                    for code in species_codes_list
                }
                for future in as_completed(futures):
                    all_obs.extend(future.result())
        elif species_code:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/{species_code}?back={back}&maxResults=10000'
            all_obs = requests.get(url, headers=headers, timeout=10).json()
        else:
            index_url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent?back={back}&maxResults=10000'
            index_obs = requests.get(index_url, headers=headers, timeout=10).json()
            species_codes = _top_species_codes(index_obs)
            if species_codes:
                all_obs = []
                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = {
                        executor.submit(_fetch_all_obs_for_species, code, lat, lng, dist, back, headers, loc_id): code
                        for code in species_codes
                    }
                    for future in as_completed(futures):
                        all_obs.extend(future.result())
            else:
                all_obs = index_obs
    elif species_codes_list:
        all_obs = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(_fetch_all_obs_for_species, code, lat, lng, dist, back, headers): code
                for code in species_codes_list
            }
            for future in as_completed(futures):
                all_obs.extend(future.result())
    elif species_code:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}"
        all_obs = requests.get(url, headers=headers, timeout=10).json()
    else:
        # Notable index identifies which species had notable sightings; regular index covers all.
        # Either way, Step 2 expands each species to all its checklists.
        if notable:
            index_url = (f'https://api.ebird.org/v2/data/obs/geo/recent/notable'
                         f'?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}')
        else:
            index_url = (f'https://api.ebird.org/v2/data/obs/geo/recent'
                         f'?lat={lat}&lng={lng}&dist={dist}&maxResults=10000&back={back}')
        index_obs = requests.get(index_url, headers=headers, timeout=10).json()
        species_codes = _top_species_codes(index_obs)
        if species_codes:
            all_obs = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {
                    executor.submit(_fetch_all_obs_for_species, code, lat, lng, dist, back, headers): code
                    for code in species_codes
                }
                for future in as_completed(futures):
                    all_obs.extend(future.result())
        else:
            all_obs = index_obs

    groups = {}
    order = []
    for obs in all_obs:
        name = obs.get('comName', '')
        if not name:
            continue
        raw_dt = obs.get('obsDt', '')
        record = {
            'date': format_obs_date(raw_dt),
            'raw_dt': raw_dt,
            'loc_name': obs.get('locName', ''),
            'sub_id': obs.get('subId', ''),
            'how_many': obs.get('howMany'),
        }
        if name not in groups:
            groups[name] = {'records': [], 'species_code': obs.get('speciesCode', '')}
            order.append(name)
        groups[name]['records'].append(record)

    species_data = []
    for name in order:
        records = sorted(groups[name]['records'], key=lambda r: r['raw_dt'], reverse=True)
        known = [r['how_many'] for r in records if r['how_many'] is not None]
        total = sum(known) if known else None
        species_data.append({
            'name': name,
            'species_code': groups[name]['species_code'],
            'total': total,
            'latest_dt': records[0]['raw_dt'] if records else '',
            'records': records,
        })

    species_data.sort(key=lambda s: (s['total'] is None, -(s['total'] or 0)))
    for i, s in enumerate(species_data):
        s['idx'] = i

    total_sightings = sum(len(s['records']) for s in species_data)

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
    search_url = '/?' + urlencode(params)

    return render_template('results.html',
                           species_data=species_data,
                           total_sightings=total_sightings,
                           location=location,
                           species_name=species_name, notable=notable,
                           dist=dist, back=back,
                           map_url=map_url, search_url=search_url,
                           loc_name=loc_name)


def create_map_with_pins(locations, center_location):
    map_obj = folium.Map(location=[center_location[0], center_location[1]], zoom_start=10, control_scale=True, tiles=None)

    satellite_url = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    satellite_attr = 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
    folium.TileLayer(tiles=satellite_url, attr=satellite_attr, name='Satellite', show=True).add_to(map_obj)
    folium.TileLayer('OpenStreetMap', name='Street Map', show=False).add_to(map_obj)
    folium.LayerControl(position='topright', collapsed=False).add_to(map_obj)

    folium.Marker(location=[center_location[0], center_location[1]],
                  icon=folium.Icon(icon='map-marker', color='red')).add_to(map_obj)

    cluster = MarkerCluster(name='Sightings').add_to(map_obj)
    for (lat, lng, comName, obsDt, howMany, subId) in locations:
        checklist = (f'<a href="https://ebird.org/checklist/{subId}" target="_blank" '
                     f'style="color:#c8881a;">View checklist ↗</a>') if subId else ''
        popup_html = (f'<div style="font-family:Arial,sans-serif;font-size:13px;min-width:160px;">'
                      f'<strong style="font-size:14px;display:block;margin-bottom:4px;">{comName}</strong>'
                      f'<span style="color:#666;">{obsDt}</span>'
                      f'{f"<br>Count: {howMany}" if howMany else ""}'
                      f'{"<br>" + checklist if checklist else ""}'
                      f'</div>')
        icon_html = (
            f'<div data-species="{comName}" style="line-height:0;">'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="26" viewBox="0 0 18 26">'
            f'<path d="M9 0C4.03 0 0 4.03 0 9c0 5.63 9 17 9 17S18 14.63 18 9c0-4.97-4.03-9-9-9z" fill="#c8881a"/>'
            f'<circle cx="9" cy="9" r="3.5" fill="white" opacity="0.9"/>'
            f'</svg></div>'
        )
        folium.Marker(location=[lat, lng],
                      icon=folium.DivIcon(html=icon_html, icon_size=(18, 26),
                                          icon_anchor=(9, 26), popup_anchor=(0, -26)),
                      popup=folium.Popup(popup_html, max_width=220)).add_to(cluster)

    return map_obj


@app.route('/map')
def map_endpoint():
    location = request.args.get('location')
    try:
        coords = location_to_coordinates(location)
        if not coords:
            return render_template('loc_not_found.html', location=location)
        lat, lng = coords
        center_coordinates = (lat, lng)
        dist = int(request.args.get('dist', 10))
        back = int(request.args.get('back', 7))

        notable = request.args.get('notable') == 'on'
        raw_species = request.args.get('species_name') or ''
        species_names_list = [s.strip() for s in raw_species.split(',') if s.strip()]
        species_codes_list = [c for c in (species_name_to_code(n) for n in species_names_list) if c]
        species_name = raw_species or None
        species_code = species_codes_list[0] if len(species_codes_list) == 1 else None
        loc_id = request.args.get('loc_id') or None
        loc_name = request.args.get('loc_name') or None

        sighting_coordinates = get_species_sightings_at_coordinates(
            center_coordinates, notable, species_code, dist, back, loc_id,
            species_codes_list=species_codes_list if len(species_codes_list) > 1 else None)

        if notable and species_name:
            map_title = f'Map of recent sightings of notable {species_name}s'
        elif notable:
            map_title = 'Map of recent sightings of notable species'
        elif species_name:
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
        search_url = '/?' + urlencode(params)

        totals = {}
        for s in sighting_coordinates:
            if s[4] is not None:
                totals[s[2]] = (totals.get(s[2]) or 0) + s[4]
            elif s[2] not in totals:
                totals[s[2]] = None
        species_summary = sorted(totals.items(), key=lambda x: (x[1] is None, -(x[1] or 0)))

        map_obj = create_map_with_pins(sighting_coordinates, center_coordinates)

        btn_style = ('display:inline-block; background:#c8881a; color:white; padding:7px 12px; '
                     'border-radius:6px; text-decoration:none; font-family:Arial,sans-serif; '
                     'font-size:13px; font-weight:bold; white-space:nowrap; flex-shrink:0;')
        nav_html = f'''
    <style>
        #map-header {{
            position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
            display: flex; align-items: center; gap: 8px; padding: 10px 14px;
            background: rgba(59,82,64,0.95); backdrop-filter: blur(3px);
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }}
        #map-header-title {{
            flex: 1; min-width: 0; text-align: center;
            color: rgba(255,255,255,0.9); font-family: Arial, sans-serif;
            font-size: 13px; font-weight: bold;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .leaflet-top {{ top: 52px !important; }}
        @media (max-width: 640px) {{
            #map-header {{ padding: 8px 10px; gap: 6px; }}
            #map-header a {{ padding: 5px 9px !important; font-size: 12px !important; }}
            #map-header-title {{ font-size: 11px; }}
            .leaflet-top {{ top: 46px !important; }}
            #map-summary {{ width: calc(100vw - 16px) !important; left: 8px !important;
                bottom: 40px !important; max-height: 200px !important; }}
        }}
    </style>
    <div id="map-header">
        <a href="{search_url}" style="{btn_style}">&#8592; Search</a>
        <span id="map-header-title">{map_title}</span>
        <a href="{list_url}" style="{btn_style}">List View</a>
    </div>'''
        map_obj.get_root().html.add_child(folium.Element(nav_html))

        map_var = map_obj.get_name()
        filter_js = (
            '<script>window.addEventListener("load",function(){'
            'var lmap=window["' + map_var + '"];'
            'if(!lmap)return;'
            'var active=null;'
            'window.filterSpecies=function(name){'
            'var rows=document.querySelectorAll("#map-summary [data-species]");'
            'var pins=document.querySelectorAll(".leaflet-marker-pane [data-species]");'
            'if(active===name){'
            'active=null;'
            'pins.forEach(function(el){var p=el.querySelector("path");if(p)p.setAttribute("fill","#c8881a");});'
            'rows.forEach(function(r){r.style.background="";r.style.fontWeight="";r.style.color="";});'
            '}else{'
            'active=name;'
            'pins.forEach(function(el){'
            'var p=el.querySelector("path");'
            'if(p)p.setAttribute("fill",el.dataset.species===name?"#c0522a":"#c8881a");'
            '});'
            'rows.forEach(function(r){'
            'var on=r.dataset.species===name;'
            'r.style.background=on?"rgba(200,136,26,0.15)":"";'
            'r.style.fontWeight=on?"bold":"";'
            'r.style.color=on?"#a86f10":"";'
            '});'
            'var b=[];'
            'lmap.eachLayer(function(l){'
            'if(!l._icon)return;'
            'var el=l._icon.querySelector("[data-species]");'
            'if(el&&el.dataset.species===name)b.push(l.getLatLng());'
            '});'
            'if(b.length)lmap.fitBounds(L.latLngBounds(b),{padding:[50,50],maxZoom:14});'
            '}'
            '};'
            '});'
            '</script>'
        )
        map_obj.get_root().html.add_child(folium.Element(filter_js))

        rows = ''.join(
            f'<div data-species="{name}" onclick="filterSpecies(this.dataset.species)"'
            f' style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:5px 4px;border-bottom:1px solid #eee;cursor:pointer;border-radius:4px;transition:background 0.12s;">'
            f'<span style="font-size:13px;font-family:Arial,sans-serif;">{name}</span>'
            f'<span style="background:#c8881a;color:white;border-radius:10px;padding:1px 8px;'
            f'font-size:12px;font-weight:bold;margin-left:8px;white-space:nowrap;">{"—" if count is None else count}</span>'
            f'</div>'
            for name, count in species_summary
        )
        summary_html = f'''
    <div id="map-summary" style="position:fixed; bottom:30px; left:16px; z-index:1000; background:white;
         border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.25); width:260px; max-height:280px;
         display:flex; flex-direction:column; overflow:hidden;">
        <div style="padding:8px 12px; background:#3b5240; color:white;
             font-family:Arial,sans-serif; font-size:13px; font-weight:bold; flex-shrink:0; line-height:1.5;">
            {len(species_summary)} species &mdash; {len(sighting_coordinates)} sightings
            <div style="font-size:10px;font-weight:normal;opacity:0.75;margin-top:1px;">Tap species to filter pins</div>
        </div>
        <div style="overflow-y:auto; padding:4px 12px;">{rows}</div>
    </div>'''
        map_obj.get_root().html.add_child(folium.Element(summary_html))

        return render_template_string(map_obj.get_root().render())
    except Exception:
        return render_template('loc_not_found.html', location=location)


def species_name_to_code(species_name):
    return _SPECIES_CODES.get(species_name.lower()) if species_name else None


def get_species_sightings_at_coordinates(coordinates, notable=False, species_code=None, dist=10, back=7, loc_id=None, species_codes_list=None):
    center_lat, center_lng = coordinates
    headers = {'X-eBirdApiToken': _EBIRD_TOKEN}

    if loc_id:
        if species_codes_list:
            all_obs = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {
                    executor.submit(_fetch_all_obs_for_species, code, center_lat, center_lng, dist, back, headers, loc_id): code
                    for code in species_codes_list
                }
                for future in as_completed(futures):
                    all_obs.extend(future.result())
        elif species_code:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/{species_code}?back={back}&maxResults=10000'
            all_obs = requests.get(url, headers=headers, timeout=10).json()
        elif notable:
            url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent/notable?back={back}&maxResults=10000'
            all_obs = requests.get(url, headers=headers, timeout=10).json()
        else:
            index_url = f'https://api.ebird.org/v2/data/obs/{loc_id}/recent?back={back}&maxResults=10000'
            index_obs = requests.get(index_url, headers=headers, timeout=10).json()
            species_codes = _top_species_codes(index_obs)
            if species_codes:
                all_obs = []
                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = {
                        executor.submit(_fetch_all_obs_for_species, code, center_lat, center_lng, dist, back, headers, loc_id): code
                        for code in species_codes
                    }
                    for future in as_completed(futures):
                        all_obs.extend(future.result())
            else:
                all_obs = index_obs
    elif species_codes_list:
        all_obs = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(_fetch_all_obs_for_species, code, center_lat, center_lng, dist, back, headers): code
                for code in species_codes_list
            }
            for future in as_completed(futures):
                all_obs.extend(future.result())
    elif species_code:
        url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=10000&back={back}"
        all_obs = requests.get(url, headers=headers, timeout=10).json()
    else:
        if notable:
            index_url = (f'https://api.ebird.org/v2/data/obs/geo/recent/notable'
                         f'?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=10000&back={back}')
        else:
            index_url = (f'https://api.ebird.org/v2/data/obs/geo/recent'
                         f'?lat={center_lat}&lng={center_lng}&dist={dist}&maxResults=10000&back={back}')
        index_obs = requests.get(index_url, headers=headers, timeout=10).json()
        species_codes = _top_species_codes(index_obs)
        if species_codes:
            all_obs = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {
                    executor.submit(_fetch_all_obs_for_species, code, center_lat, center_lng, dist, back, headers): code
                    for code in species_codes
                }
                for future in as_completed(futures):
                    all_obs.extend(future.result())
        else:
            all_obs = index_obs

    sighting_locations = []
    for this in all_obs:
        obs_lat = this.get('lat')
        obs_lng = this.get('lng')
        comName = this.get('comName')
        if obs_lat is None or obs_lng is None or not comName:
            continue
        sighting_locations.append((obs_lat, obs_lng, comName, format_obs_date(this.get('obsDt', '')), this.get('howMany'), this.get('subId', '')))

    return sighting_locations


if __name__ == '__main__':
    if os.path.exists('/app/ssl'):
        app.run(debug=True, host='0.0.0.0', ssl_context=('/app/ssl/cert2.pem', '/app/ssl/privkey2.pem'))
    else:
        app.run(debug=True, host='0.0.0.0')
