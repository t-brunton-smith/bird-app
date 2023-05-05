FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static/ static/
COPY templates/ templates/
COPY configs/ configs/

EXPOSE 5000

CMD ["python", "app.py"]





## Use a smaller base image
#FROM python:3.9-slim-buster AS build
#
## Set the working directory
#WORKDIR /app
#
## Copy the application files to the image
#COPY . .
#
## Install dependencies
#RUN pip install --no-cache-dir -r requirements.txt
#
## Use a smaller base image for the runtime
#FROM python:3.9-slim-buster
#
## Set the working directory
#WORKDIR /app
#
## Copy only the necessary artifacts from the build stage
#COPY --from=build /app .
#
#EXPOSE 5000
#
## Run the application
#CMD ["python", "app.py"]

## Use a smaller base image
#FROM python:3.9-slim-buster AS build
#
## Set the working directory
#WORKDIR /app
#
## Copy the application files to the image
#COPY . .
#
## Install dependencies
#RUN pip install --no-cache-dir -r requirements.txt
#
## Use a smaller base image for the runtime
#FROM python:3.9-slim-buster
#
## Set the working directory
#WORKDIR /app
#
## Copy only the necessary artifacts from the build stage
#COPY --from=build /app .
#
## Install packages
#RUN pip install --no-cache-dir -r requirements.txt
#
## Expose port 5000
#EXPOSE 5000
#
## Run the application
#CMD ["python", "app.py"]
