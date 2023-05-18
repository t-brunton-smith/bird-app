import configparser
import os

import folium as folium
import requests
from flask import Flask, render_template, render_template_string, request, jsonify, redirect

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
    lat, lng = location_to_coordinates(location)
    return results_from_coordinates(lat, lng, notable=False)


@app.route('/notableresults')
def notableresults():
    # # Get the user's location from the form
    location = request.args.get('location')
    lat, lng = location_to_coordinates(location)
    return results_from_coordinates(lat, lng, notable=True)


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

    folium.Marker(location=[center_location[0], center_location[1]], icon=folium.Icon(icon='map-marker', color='red')).add_to(map_obj)
    for location in locations:
        folium.Marker(location=[location[0], location[1]], icon=folium.Icon(icon='map-marker')).add_to(map_obj)

    return map_obj

@app.route('/map')
def map_endpoint(qq):
    # Define your locations here
    locations = [(38.9359287, -74.9434519),
 (38.9319186, -74.9539848),
 (39.1049766, -74.8948436)]

    center_location=(39, -75)

    # Create the map using the provided function
    map_obj = create_map_with_pins(locations, center_location)

    # Save the map as HTML
    map_html = map_obj.get_root().render()

    # Render the map HTML template
    return render_template_string(map_html)



if __name__ == '__main__':
    # app.run(debug=True, host='0.0.0.0', ssl_context=('ssl/cert.pem', 'ssl/key.pem'))
    # print(os.listdir('/app/ssl'))
    # print(os.path.isfile('/app/ssl/privkey.pem'))
    if (os.path.exists('/app/ssl')):
        app.run(debug=True, host='0.0.0.0', ssl_context=('/app/ssl/cert.pem', '/app/ssl/privkey.pem'))
    else:
        app.run(debug=True, host='0.0.0.0')
