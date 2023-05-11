function getUserLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(fillLocationFields);
    } else {
        alert("Geolocation is not supported by this browser.");
    }
}

function fillLocationFields(position) {
    document.getElementById("latitude").value = position.coords.latitude;
    document.getElementById("longitude").value = position.coords.longitude;
}

document.getElementById("use-location-button").addEventListener("click", getUserLocation);
