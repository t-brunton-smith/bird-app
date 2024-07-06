# bird-app
An eBird app

# Run commands
To build the app:

docker build -t tbruntonsmith/bird-app .

# Push to registry
To push to dockerhub registry:

docker push tbruntonsmith/bird-app

# Run commands 
To run the docker container locally

docker run -p 5000:5000 ebird-app

To run the docker container on the server

docker run --restart unless-stopped -p 80:5000 -d tbruntonsmith/bird-app
docker run --restart unless-stopped -p 443:5000 -v /etc/letsencrypt/live/tbruntonsmith.com/privkey.pem:/app/ssl/privkey1.pem -v /etc/letsencrypt/live/tbruntonsmith.com/cert.pem:/app/ssl/cert1.pem -v /etc/letsencrypt/live/phlock.org/privkey.pem:/app/ssl/privkey2.pem -v /etc/letsencrypt/live/phlock.org/cert.pem:/app/ssl/cert2.pem -d tbruntonsmith/bird-app