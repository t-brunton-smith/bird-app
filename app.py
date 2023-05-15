import configparser
import os

import requests
from flask import Flask, render_template, request, jsonify, redirect

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


@app.route('/results')
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

@app.route('/notableresults')
def notableresults():
    # Get the user's location from the form
    lat = request.args.get('latitude')
    lng = request.args.get('longitude')

    # Read the API token from the configs/keys.ini file
    config = configparser.ConfigParser()
    config.read('configs/keys.ini')
    apitoken = config['ebird']['apitoken']

    # Make a request to the eBird API to get recent bird sightings in the user's location
    url = f'https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={lat}&lng={lng}&&maxResults=100&back=14'

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
    # app.run(debug=True, host='0.0.0.0', ssl_context=('ssl/cert.pem', 'ssl/key.pem'))
    # print(os.listdir('/app/ssl'))
    # print(os.path.isfile('/app/ssl/privkey.pem'))
    if (os.path.exists('/app/ssl')):
        app.run(debug=True, host='0.0.0.0', ssl_context=('/app/ssl/cert.pem', '/app/ssl/privkey.pem'))
    else:
        app.run(debug=True, host='0.0.0.0')
