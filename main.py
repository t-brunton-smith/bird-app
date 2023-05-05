from flask import Flask, request
from ebirdapi import EBirdAPI

app = Flask(__name__)
ebird = EBirdAPI()


@app.route("/")
def index():
    return "Welcome to the eBird sightings app!"


@app.route("/sightings", methods=["POST"])
def get_sightings():
    # Receive text message containing coordinates
    coordinates = request.values.get("Body")

    # Call the eBird API to get the most recent sightings for the specified coordinates
    sightings = ebird.get_recent_sightings(coordinates)

    # Generate a message with the 10 most recent sightings
    message = "The 10 most recent bird sightings for {} are:\n\n".format(coordinates)
    for i, sighting in enumerate(sightings[:10]):
        message += "{}. {} ({} {})\n".format(i + 1, sighting["comName"], sighting["lat"], sighting["lng"])

    # Send the message back to the user
    response = "<Response><Message>{}</Message></Response>".format(message)
    return response


if __name__ == "__main__":
    app.run(debug=True)