import configparser
import os

import folium as folium
import requests
from flask import Flask, render_template, render_template_string, request, jsonify, redirect
import pandas as pd

app = Flask(__name__)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


# Redirect all HTTP requests to HTTPS
@app.before_request
def https_redirect():
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


@app.route('/results')
def results():
    # # Get the user's location from the form
    location = request.args.get('location')

    try:
        notable = request.args.get('notable')
        if notable == 'on':
            notable = True
        else:
            notable = False
    except:
        notable = False

    lat, lng = location_to_coordinates(location)
    return results_from_coordinates(lat, lng, notable=notable)


def location_to_coordinates(location):
    # Get the users location
    location = request.args.get('location')

    config = configparser.ConfigParser()
    config.read('configs/keys.ini')
    apitoken = config['mapbox']['apitoken']

    """Convert a location string to latitude and longitude coordinates using Mapbox Geocoding API"""
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{location}.json?access_token={apitoken}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if len(data['features']) > 0:
            coordinates = data['features'][0]['center']
            return tuple(coordinates[::-1])  # return coordinates as (latitude, longitude)
    return None


def coordinates_to_location(latitude, longitude):
    config = configparser.ConfigParser()
    config.read('configs/keys.ini')
    apitoken = config['mapbox']['apitoken']

    """Reverse geocode a set of latitude and longitude coordinates into a location name using Mapbox Geocoding API"""
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{longitude},{latitude}.json?access_token={apitoken}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if len(data['features']) > 0:
            location = data['features'][0]['place_name']
            return location
    return None


def results_from_coordinates(lat, lng, notable=False):
    # Read the API token from the configs/keys.ini file
    config = configparser.ConfigParser()
    config.read('configs/keys.ini')
    apitoken = config['ebird']['apitoken']

    # Make a request to the eBird API to get recent bird sightings in the user's location
    if notable:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={lat}&lng={lng}&&maxResults=100&back=14'
    else:
        url = f'https://api.ebird.org/v2/data/obs/geo/recent?lat={lat}&lng={lng}&&maxResults=100&back=14'

    headers = {'X-eBirdApiToken': apitoken}
    response = requests.get(url, headers=headers)

    # Parse the JSON response and extract the relevant information
    sightings = []
    for sighting in response.json():
        species_name = sighting['comName']
        date = sighting['obsDt']
        location_name = sighting['locName']
        sightings.append((species_name, date, location_name))

    # Render the results template with the sightings
    return render_template('results.html', sightings=sightings)


def create_map_with_pins(locations, center_location):
    """
    Create a map with pins at specified latitude and longitude locations using Folium.
    locations: list of tuples representing latitude and longitude coordinates
    center_location: tuple representing the latitude and longitude of the center location
    """
    map_obj = folium.Map(location=[center_location[0], center_location[1]], zoom_start=10, control_scale=True)

    folium.Marker(location=[center_location[0], center_location[1]],
                  icon=folium.Icon(icon='map-marker', color='red')).add_to(map_obj)
    for location in locations:
        folium.Marker(location=[location[0], location[1]], icon=folium.Icon(icon='map-marker')).add_to(map_obj)

    return map_obj


@app.route('/map')
def map_endpoint():
    center_location = request.args.get('center_location')
    lat, lng = location_to_coordinates(center_location)
    center_coordinates = (lat, lng)

    # Get the name
    species_name = request.args.get('species_name')

    # Convert name to species code
    species_code = species_name_to_code(species_name)

    # Get the coordinates for sightings of this species code
    sighting_coordinates = get_species_sightings_at_coordinates(center_coordinates, species_code)

    # Create the map using the provided function
    map_obj = create_map_with_pins(sighting_coordinates, center_coordinates)

    # Save the map as HTML
    map_html = map_obj.get_root().render()

    # Render the map HTML template
    return render_template_string(map_html)


def species_name_to_code(species_name):
    df_tax = pd.read_csv("data/ebird_taxonomy.csv")

    # Lower case the species names
    df_tax['COMMON_NAME'] = df_tax['COMMON_NAME'].apply(str.lower)
    species_name = species_name.lower()
    dict_tax = pd.Series(df_tax.SPECIES_CODE.values, index=df_tax.COMMON_NAME).to_dict()

    print(dict_tax)
    if species_name in dict_tax.keys():
        return dict_tax[species_name]
    else:
        return None


def get_species_sightings_at_coordinates(coordinates, species_code):
    center_lat, center_lng = coordinates

    config = configparser.ConfigParser()
    config.read('configs/keys.ini')

    apitoken = config['ebird']['apitoken']
    headers = {'X-eBirdApiToken': apitoken}

    url = f"https://api.ebird.org/v2/data/obs/geo/recent/{species_code}?lat={center_lat}&lng={center_lng}"

    response = requests.get(url, headers=headers)
    results = response.json()

    sighting_locations = []
    for this in results:
        sighting_locations.append((this['lat'], this['lng']))

    return sighting_locations


if __name__ == '__main__':
    # app.run(debug=True, host='0.0.0.0', ssl_context=('ssl/cert.pem', 'ssl/key.pem'))
    # print(os.listdir('/app/ssl'))
    # print(os.path.isfile('/app/ssl/privkey.pem'))
    if (os.path.exists('/app/ssl')):
        app.run(debug=True, host='0.0.0.0', ssl_context=('/app/ssl/cert.pem', '/app/ssl/privkey.pem'))
    else:
        app.run(debug=True, host='0.0.0.0')
