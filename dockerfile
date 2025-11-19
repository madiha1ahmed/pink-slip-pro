# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8000 available to the world outside the container
EXPOSE 8000

# Define environment variable
ENV FLASK_APP=app.py
ENV OPENAI_API_KEY=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


# Run the Flask app using gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
