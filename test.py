from collections import Counter

import requests


def get_recent_bird_sightings(api_key, location, lat, long, dist, max_days=14):
    """
    Retrieves the most recent bird sightings for a specified location using the eBird API.

    Parameters:
    - api_key: str - The eBird API key.
    - location: str - The eBird location identifier for the location of interest.
    - max_days: int - The maximum number of days for which to retrieve bird sightings (default is 14 days).

    Returns:
    - list of str - The species names for each bird sighting.
    """
    # Construct the URL for the eBird API request
    # url = f"https://api.ebird.org/v2/data/obs/{location}/recent?maxDays={max_days}&key={api_key}"
    url = f"https://api.ebird.org/v2/data/obs/geo/recent/notable?lat={lat}&lng={long}&back={max_days}&dist={dist}&key={api_key}"
    # Send the API request and get the response
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Extract the bird sightings from the response JSON
        sightings = response.json()
        # Extract the species names for each sighting
        species_names = [sighting["comName"] for sighting in sightings if sighting['obsValid']==True]
        valid_sightings = [sighting for sighting in sightings if sighting['obsValid']==True]
        return valid_sightings, species_names
    else:
        print("Error: Request failed with status code", response.status_code)
        return []

if __name__ == '__main__':
    sightings, species_names = get_recent_bird_sightings(api_key='95q5b5jutsd7', location=None, lat=40.08, long=-75.22, dist=10, max_days=3)
    unique_species = {}
    for sighting in sightings:
        species = sighting['comName']
        count_species = sighting['howMany']
        if species not in unique_species.keys():
            unique_species[species] = count_species
        else:
            unique_species[species] += count_species

    sorted_unique_species = dict(sorted(unique_species.items(), key=lambda x: -x[1]))
    for k,v in sorted_unique_species.items():
        print(k, v)

    pass