document.addEventListener('DOMContentLoaded', function () {
    // User's current location
    function getUserLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(fillLocationFields);
        } else {
            alert("Geolocation is not supported by this browser.");
        }
    }

    function fillLocationFields(position) {
        const latitude = position.coords.latitude;
        const longitude = position.coords.longitude;

        const xhr = new XMLHttpRequest();
        xhr.open('GET', `/location?lat=${latitude}&long=${longitude}`);
        xhr.onload = function () {
            if (xhr.status === 200) {
                const location = xhr.responseText;
                document.getElementById("location").value = location;
            } else {
                alert('Unable to retrieve location');
            }
        };
        xhr.send();
    }

    document.getElementById("use-location-button").addEventListener("click", getUserLocation);

});
