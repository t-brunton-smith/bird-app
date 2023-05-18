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


    // Toggle to get notable results
    const form = document.getElementById('myForm');
    var select = document.getElementById("search-option");
    const submitButton = form.querySelector('button[type="submit"]');


    select.addEventListener("change", function () {
        if (select.value === "location") {
            form.addEventListener('submit', (event) => {
                event.preventDefault();
                const formData = new FormData(form);
                // const latitude = formData.get('latitude');
                // const longitude = formData.get('longitude');
                const location = formData.get('location');

                const isNotable = document.getElementById('notable').checked;

                let endpoint = '/results';
                form.action = "/results";
                if (isNotable) {
                    endpoint = '/notableresults';
                    form.action = "/notableresults";

                }

                // window.location.href = `${endpoint}?latitude=${latitude}&longitude=${longitude}`;
                window.location.href = `${endpoint}?location=${location}`;

            });
        } else if (select.value === "locationSpecies") {
            const location = formData.get('location');
            const species_name = formData.get('species_name');
            let endpoint = '/map';
            form.action = "/map";
            window.location.href = `${endpoint}?species_name=${species_name}?location=${location}`;

        }
    });

});
