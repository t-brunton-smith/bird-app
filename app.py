import configparser
import sys

import requests
from flask import Flask, render_template, request
from ast import literal_eval

app = Flask(__name__)

@ app.route('/')
def index():
    return render_template('index.html')

@ app.route('/results')
def results():
    # Get the user's location from the form
    lat = request.args.get('latitude')
    lng = request.args.get('longitude')

    # Read the API token from the configs/keys.ini file
    config = configparser.ConfigParser()
    config.read('configs/keys.ini')
    apitoken = config['ebird']['apitoken']

    # Make a request to the eBird API to get recent bird sightings in the user's location
    url = f'https://api.ebird.org/v2/data/obs/geo/recent?lat={lat}&lng={lng}&&maxResults=100&back=14'

    # url = f'https://api.ebird.org/v2/data/obs/geo/recent?latlng={location}&maxResults=10'
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')


