// Get the users location
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

// Toggle to get notable results
const form = document.querySelector('form');
const submitButton = document.querySelector('button[type="submit"]');

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  // const latitude = formData.get('latitude');
  // const longitude = formData.get('longitude');
  const location = formData.get('location');

  const isNotable = document.getElementById('notable').checked;

  let endpoint = '/results';
  if (isNotable) {
    endpoint = '/notableresults';
  }

  // window.location.href = `${endpoint}?latitude=${latitude}&longitude=${longitude}`;
  window.location.href = `${endpoint}?location=${location}`;
});
