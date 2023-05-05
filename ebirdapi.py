import requests


class EBirdAPI:
    def __init__(self, api_key):
        """
        Initializes an instance of the EBirdAPI class with the specified eBird API key.

        Parameters:
        - api_key: str - The eBird API key.
        """
        self.api_key = api_key

    def get_recent_bird_sightings(self, location, max_days=14):
        """
        Retrieves the most recent bird sightings for a specified location using the eBird API.

        Parameters:
        - location: str - The eBird location identifier for the location of interest.
        - max_days: int - The maximum number of days for which to retrieve bird sightings (default is 14 days).

        Returns:
        - list of str - The species names for each bird sighting.
        """
        # Construct the URL for the eBird API request
        url = f"https://api.ebird.org/v2/data/obs/{location}/recent?maxDays={max_days}&key={self.api_key}"

        # Send the API request and get the response
        response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Extract the bird sightings from the response JSON
            sightings = response.json()
            # Extract the species names for each sighting
            species_names = [sighting["speciesName"] for sighting in sightings]
            return species_names
        else:
            print("Error: Request failed with status code", response.status_code)
            return []